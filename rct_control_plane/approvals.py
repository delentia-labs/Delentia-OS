"""
Signed human approval for paused agent actions (Round 48 R1.4 + audit tier A1/A2).

Before this module, `pending_approval` simply ended an episode: nothing
recorded WHAT was waiting, and there was no way to continue after a human
said yes. The older approval_queue.py is in-memory (lost on restart) and
stores an approver "signature" without ever verifying it.

Here:
  - every paused action is persisted (SQLite, the loop's own persistence DB)
    with a SHA-256 digest of exactly what would run: namespace, goal, tool
    and arguments;
  - a decision is only accepted with an Ed25519 signature over
    "delentia-approval:v1:<approval_id>:<action_sha256>:<DECISION>", made
    with a key whose public half is on the trusted-approver list;
  - the trusted list is configured OUTSIDE the agent's reach
    (DELENTIA_APPROVER_PUBKEYS env var, or ~/.delentia/approvers.json) and is
    fail-closed: with no trusted approver configured, nothing can be approved;
  - the approver's private key is generated to a path outside the repository
    (generate_approver_key refuses paths inside it), out of reach of the
    agent's repo-confined file tools. The local shell sandbox is NOT a jail,
    though: it runs as the same OS user and could read a key on the same
    machine (sandbox.py denies commands naming key material, but that is a
    speed bump). The real protection is keeping the approver key on another
    device - `delentia approvals sign` works offline and only the signature
    is sent to the agent host - or under a different OS user;
  - approval is bound to one exact action: changing any argument changes the
    digest and invalidates the signature, and an action executes at most once.

The signature is verified again at execution time, so editing the database
row (e.g. flipping status to APPROVED) is not enough to get an action run.

Round 65: an approval is also bounded in TIME. A request nobody decided within
DELENTIA_APPROVAL_DECISION_TTL_SECONDS (default 7 days) can no longer be approved,
and an approved action not resumed within DELENTIA_APPROVAL_EXECUTION_TTL_SECONDS
(default 24 h) is marked EXPIRED and never runs: the situation a person looked at
is not the situation a week later. Expired rows stay on disk (Zero-Delete). A value
of 0 switches that window off. Removing an approver's key from the trusted list
revokes every approval it signed that has not yet run (the signature is re-checked
against the list at execution).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Any, Dict, List, Optional

from rct_control_plane.persistence import ControlPlanePersistence

APPROVAL_MESSAGE_VERSION = "delentia-approval:v1"
DECISIONS = ("APPROVED", "REJECTED")
APPROVERS_ENV = "DELENTIA_APPROVER_PUBKEYS"
DECISION_TTL_ENV = "DELENTIA_APPROVAL_DECISION_TTL_SECONDS"
EXECUTION_TTL_ENV = "DELENTIA_APPROVAL_EXECUTION_TTL_SECONDS"
DEFAULT_DECISION_TTL_SECONDS = 7 * 24 * 3600
DEFAULT_EXECUTION_TTL_SECONDS = 24 * 3600
OUTCOME_UNKNOWN_AFTER_SECONDS = 900          # Round 82 (T06): an action claimed this long ago with no receipt is OUTCOME_UNKNOWN

_REPO_ROOT = Path(__file__).resolve().parent.parent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_actions (
    approval_id          TEXT PRIMARY KEY,
    namespace            TEXT NOT NULL,
    goal                 TEXT NOT NULL,
    tool_name            TEXT NOT NULL,
    tool_args_json       TEXT NOT NULL,
    action_sha256        TEXT NOT NULL,
    reason               TEXT,
    status               TEXT NOT NULL,
    created_at           REAL NOT NULL,
    decided_at           REAL,
    approver_public_key  TEXT,
    signature_hex        TEXT,
    executed_at          REAL,
    result_json          TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status, created_at);
CREATE TABLE IF NOT EXISTS pending_action_signatures (
    approval_id          TEXT NOT NULL,
    public_key           TEXT NOT NULL,
    signature_hex        TEXT NOT NULL,
    decided_at           REAL NOT NULL,
    PRIMARY KEY (approval_id, public_key)
);
"""
# Round 54: columns added to pending_actions after the first release (owner policy: how many signatures, from which roles).
_EXTRA_COLUMNS = (
    ("required_signatures", "INTEGER NOT NULL DEFAULT 1"),
    ("approver_roles_json", "TEXT"),
    ("policy_rule", "TEXT"),
    ("policy_digest", "TEXT"),
    ("workspace", "TEXT"),            # Round 82 (N2): the folder the action was asked for; part of what the approver signs
    ("claimed_at", "REAL"),           # Round 82 (T06): when the action was claimed for execution, so a claim that never got a receipt can be found
)


class ApprovalError(ValueError):
    pass


def _now() -> float:
    return time.time()


def _ttl(env: str, default: int) -> float:
    """Seconds, or 0 for "no limit". An unreadable value falls back to the default (never to "no limit")."""
    raw = (os.getenv(env) or "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(default)


def decision_ttl_seconds() -> float:
    return _ttl(DECISION_TTL_ENV, DEFAULT_DECISION_TTL_SECONDS)


def execution_ttl_seconds() -> float:
    return _ttl(EXECUTION_TTL_ENV, DEFAULT_EXECUTION_TTL_SECONDS)


@dataclass
class PendingAction:
    approval_id: str
    namespace: str
    goal: str
    tool_name: str
    tool_args: Dict[str, Any]
    action_sha256: str
    reason: Optional[str]
    status: str
    created_at: float
    decided_at: Optional[float] = None
    approver_public_key: Optional[str] = None
    signature_hex: Optional[str] = None
    executed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    required_signatures: int = 1
    approver_roles: Optional[List[str]] = None
    policy_rule: Optional[str] = None
    policy_digest: Optional[str] = None
    workspace: Optional[str] = None
    claimed_at: Optional[float] = None
    signatures_collected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def action_digest(approval_id: str, namespace: str, goal: str, tool_name: str, tool_args: Dict[str, Any],
                  policy_digest: Optional[str] = None, workspace: Optional[str] = None) -> str:
    """What an approver signs. Round 82 (N2): the owner policy that judged the request and the workspace it was asked in are part of it when they are known, so a signature cannot be
    carried over to a changed policy or another folder. When neither is given the digest is exactly the one older approvals were signed with."""
    body: Dict[str, Any] = {"approval_id": approval_id, "namespace": namespace, "goal": goal, "tool_name": tool_name, "tool_args": tool_args}
    if policy_digest:
        body["policy_digest"] = policy_digest
    if workspace:
        body["workspace"] = workspace
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_passkey(key: str) -> bool:
    return isinstance(key, str) and key.startswith("passkey:")


def _fingerprint(key: str) -> str:
    """A short, stable name for a signer's key: the first 16 hex of the SHA-256 of an Ed25519 public key, or of the passkey's identifier."""
    return hashlib.sha256(key.encode("utf-8") if _is_passkey(key) else bytes.fromhex(key)).hexdigest()[:16]


def approval_message(approval_id: str, action_sha256: str, decision: str) -> bytes:
    decision = decision.strip().upper()
    if decision not in DECISIONS:
        raise ApprovalError(f"decision must be one of {DECISIONS}")
    return f"{APPROVAL_MESSAGE_VERSION}:{approval_id}:{action_sha256}:{decision}".encode("utf-8")


# ----------------------------------------------------------- trusted approvers

def _approvers_file() -> Path:
    return Path(os.getenv("DELENTIA_APPROVERS_FILE") or (Path.home() / ".delentia" / "approvers.json"))


def trusted_approver_keys() -> Dict[str, str]:
    """public_key_hex -> approver name. Env var first, then the approvers
    file. Empty dict = nobody can approve (fail-closed)."""
    keys: Dict[str, str] = {}
    for i, part in enumerate((os.getenv(APPROVERS_ENV) or "").split(",")):
        part = part.strip().lower()
        if part:
            keys[part] = f"env-approver-{i + 1}"
    path = _approvers_file()
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApprovalError(f"cannot read approvers file {path}: {exc}") from exc
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("public_key_hex"):
                keys[str(entry["public_key_hex"]).strip().lower()] = str(entry.get("name") or "approver")
    return keys


def trusted_approver_roles() -> Dict[str, str]:
    """public_key_hex -> role, from the approvers file (`{"name", "public_key_hex", "role"}`). Keys given through the
    environment variable carry no role: they can sign anything that does not ask for a role."""
    roles: Dict[str, str] = {}
    path = _approvers_file()
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return roles
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("public_key_hex") and entry.get("role"):
                roles[str(entry["public_key_hex"]).strip().lower()] = str(entry["role"]).strip()
    return roles


def verify_signature(public_key_hex: str, message: bytes, signature_hex: str) -> bool:
    """Public form of the check used everywhere a signature is accepted (and by the Desk's signature ledger)."""
    return _verify(public_key_hex, message, signature_hex)


def _verify(public_key_hex: str, message: bytes, signature_hex: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(bytes.fromhex(signature_hex), message)
        return True
    except (InvalidSignature, ValueError):
        return False


# ------------------------------------------------------------ approver keys

def _is_inside_repo(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(_REPO_ROOT)
    except (OSError, ValueError):
        return False


def generate_approver_key(private_key_path: str) -> str:
    """Writes a new Ed25519 private key (PEM, unencrypted, owner-only where
    the OS supports it) and returns the public key hex to put on the
    trusted-approver list. Refuses any path inside the repository, where the
    agent's own file tools could read it."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )
    path = Path(private_key_path).expanduser()
    if _is_inside_repo(path):
        raise ApprovalError(
            f"refusing to store an approver key inside the repository ({_REPO_ROOT}): "
            "the agent's file tools can read the repo, so it could sign its own approvals"
        )
    if path.exists():
        raise ApprovalError(f"{path} already exists; refusing to overwrite a key")
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def sign_decision(private_key_path: str, approval_id: str, action_sha256: str, decision: str) -> Dict[str, str]:
    """Signs a decision with an approver key file. Runs wherever the key is
    (e.g. the approver's laptop) - it needs no database access."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
    key = load_pem_private_key(Path(private_key_path).expanduser().read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ApprovalError("approver key must be an Ed25519 private key")
    message = approval_message(approval_id, action_sha256, decision)
    return {
        "public_key_hex": key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        "signature_hex": key.sign(message).hex(),
        "decision": decision.strip().upper(),
    }


# ------------------------------------------------------------------- store

_SELECT = ("SELECT approval_id, namespace, goal, tool_name, tool_args_json, action_sha256, reason, status, "
           "created_at, decided_at, approver_public_key, signature_hex, executed_at, result_json, "
           "required_signatures, approver_roles_json, policy_rule, policy_digest, workspace, claimed_at FROM pending_actions")


class PendingActionStore:
    def __init__(self, persistence: ControlPlanePersistence):
        self._persistence = persistence
        with self._persistence._connect() as conn:
            conn.executescript(_SCHEMA)
            have = {row[1] for row in conn.execute("PRAGMA table_info(pending_actions)").fetchall()}
            for column, ddl in _EXTRA_COLUMNS:
                if column not in have:
                    conn.execute(f"ALTER TABLE pending_actions ADD COLUMN {column} {ddl}")

    def create(self, namespace: str, goal: str, tool_name: str, tool_args: Dict[str, Any],
               reason: Optional[str] = None, *, required_signatures: int = 1,
               approver_roles: Optional[List[str]] = None, policy_rule: Optional[str] = None,
               policy_digest: Optional[str] = None, workspace: Optional[str] = None) -> PendingAction:
        approval_id = uuid.uuid4().hex[:12]
        digest = action_digest(approval_id, namespace, goal, tool_name, tool_args, policy_digest, workspace)
        required_signatures = max(1, min(3, int(required_signatures)))
        action = PendingAction(approval_id, namespace, goal, tool_name, dict(tool_args), digest,
                               reason, "PENDING", _now(), required_signatures=required_signatures,
                               approver_roles=list(approver_roles) if approver_roles else None,
                               policy_rule=policy_rule, policy_digest=policy_digest, workspace=workspace)
        with self._persistence._connect() as conn:
            conn.execute(
                "INSERT INTO pending_actions (approval_id, namespace, goal, tool_name, tool_args_json, "
                "action_sha256, reason, status, created_at, required_signatures, approver_roles_json, "
                "policy_rule, policy_digest, workspace) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (approval_id, namespace, goal, tool_name, json.dumps(tool_args, sort_keys=True),
                 digest, reason, "PENDING", action.created_at, required_signatures,
                 json.dumps(action.approver_roles) if action.approver_roles else None, policy_rule, policy_digest, workspace),
            )
        try:
            self._persistence.append_audit(
                entity_type="pending_action_created", entity_id=approval_id, action="waiting", actor=namespace,
                changes={"tool_name": tool_name, "action_sha256": digest, "required_signatures": required_signatures,
                         "approver_roles": action.approver_roles, "policy_rule": policy_rule, "reason": reason})
        except Exception:           # an audit problem must not decide whether the action can be asked for
            pass
        try:                        # Round 60: tell the owner (owner_notify.py): tool name, asker and code only; never fatal
            from rct_control_plane import owner_notify
            owner_notify.on_pending_action(action, self._persistence)
        except Exception:
            pass
        return action

    def _expire_stale(self) -> None:
        """Marks overdue rows EXPIRED (kept on disk). Pending past the decision window; approved past the execution window."""
        now = _now()
        decision_ttl, execution_ttl = decision_ttl_seconds(), execution_ttl_seconds()
        with self._persistence._connect() as conn:
            if decision_ttl > 0:
                conn.execute("UPDATE pending_actions SET status = 'EXPIRED' WHERE status = 'PENDING' AND created_at < ?",
                             (now - decision_ttl,))
            if execution_ttl > 0:
                conn.execute("UPDATE pending_actions SET status = 'EXPIRED' WHERE status = 'APPROVED' AND decided_at IS NOT NULL "
                             "AND decided_at < ?", (now - execution_ttl,))

    def get(self, approval_id: str) -> Optional[PendingAction]:
        self._expire_stale()
        with self._persistence._connect() as conn:
            row = conn.execute(
                _SELECT + " WHERE approval_id = ?", (approval_id,),
            ).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM pending_action_signatures WHERE approval_id = ?",
                                 (approval_id,)).fetchone()[0] if row else 0
        if not row:
            return None
        found = self._from_row(row)
        found.signatures_collected = int(count)
        return found

    def list(self, status: Optional[str] = "PENDING", limit: int = 50) -> List[PendingAction]:
        self._expire_stale()
        self.reconcile()                      # Round 82 (T06): a claim that never got a receipt is shown as OUTCOME_UNKNOWN, not as EXECUTING forever
        query = _SELECT
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status.upper(),)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._persistence._connect() as conn:
            rows = conn.execute(query, params + (limit,)).fetchall()
            counts = dict(conn.execute("SELECT approval_id, COUNT(*) FROM pending_action_signatures GROUP BY approval_id").fetchall())
        listed = [self._from_row(r) for r in rows]
        for found in listed:                  # list() used to leave this at 0, so the Approvals page showed no progress on a 2-of-3 action
            found.signatures_collected = int(counts.get(found.approval_id, 0))
        return listed

    @staticmethod
    def _from_row(row: tuple) -> PendingAction:
        return PendingAction(
            approval_id=row[0], namespace=row[1], goal=row[2], tool_name=row[3],
            tool_args=json.loads(row[4]), action_sha256=row[5], reason=row[6], status=row[7],
            created_at=row[8], decided_at=row[9], approver_public_key=row[10], signature_hex=row[11],
            executed_at=row[12], result=json.loads(row[13]) if row[13] else None,
            required_signatures=int(row[14] or 1), approver_roles=json.loads(row[15]) if row[15] else None,
            policy_rule=row[16], policy_digest=row[17], workspace=row[18], claimed_at=row[19],
        )

    def decide(self, approval_id: str, decision: str, public_key_hex: str, signature_hex: str) -> PendingAction:
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status == "EXPIRED":
            raise ApprovalError(f"action {approval_id} expired before it was decided; ask for it again")
        if action.status != "PENDING":
            raise ApprovalError(f"action {approval_id} is already {action.status}")
        decision = decision.strip().upper()
        public_key_hex = public_key_hex.strip().lower()
        self._check_signature(action, decision, public_key_hex, signature_hex)
        if decision == "APPROVED":
            self._check_role(action, public_key_hex)
            self._check_scope(action, public_key_hex)
        now = _now()
        with self._persistence._connect() as conn:
            if decision == "REJECTED":
                # Any trusted approver can stop an action; a refusal needs no role and no second signature.
                conn.execute(
                    "UPDATE pending_actions SET status = ?, decided_at = ?, approver_public_key = ?, signature_hex = ? "
                    "WHERE approval_id = ? AND status = 'PENDING'",
                    (decision, now, public_key_hex, signature_hex, approval_id),
                )
            else:
                taken = conn.execute("SELECT 1 FROM pending_action_signatures WHERE approval_id = ? AND public_key = ?",
                                     (approval_id, public_key_hex)).fetchone()
                if taken:
                    raise ApprovalError("this approver key has already signed this action; "
                                        f"{action.required_signatures} distinct keys are required")
                conn.execute("INSERT INTO pending_action_signatures (approval_id, public_key, signature_hex, decided_at) "
                             "VALUES (?, ?, ?, ?)", (approval_id, public_key_hex, signature_hex, now))
                collected = conn.execute("SELECT COUNT(*) FROM pending_action_signatures WHERE approval_id = ?",
                                         (approval_id,)).fetchone()[0]
                if collected >= action.required_signatures:
                    first = conn.execute("SELECT public_key, signature_hex FROM pending_action_signatures "
                                         "WHERE approval_id = ? ORDER BY decided_at, public_key LIMIT 1", (approval_id,)).fetchone()
                    conn.execute(
                        "UPDATE pending_actions SET status = 'APPROVED', decided_at = ?, approver_public_key = ?, signature_hex = ? "
                        "WHERE approval_id = ? AND status = 'PENDING'", (now, first[0], first[1], approval_id))
        self._persistence.append_audit(
            entity_type="pending_action_decided", entity_id=approval_id, action=decision.lower(),
            actor=f"approver:{self._signer_info(public_key_hex)[0] or '?'}:{public_key_hex[:24]}",
            changes={"action_sha256": action.action_sha256, "tool_name": action.tool_name,
                     "signature_hex": signature_hex, "approver_public_key": public_key_hex, "scheme": "passkey" if _is_passkey(public_key_hex) else "ed25519",
                     "approver_role": self._signer_info(public_key_hex)[1],
                     "required_signatures": action.required_signatures, "policy_rule": action.policy_rule},
        )
        decided = self.get(approval_id)
        assert decided is not None
        if decided.status in ("APPROVED", "REJECTED"):
            self._record_architect_decision(decided, public_key_hex)
        return decided

    def decide_with_passkey(self, approval_id: str, decision: str, assertion: Dict[str, Any]) -> PendingAction:
        """Round 101: a decision confirmed on a device (Windows Hello, a security key, a phone). The assertion is checked against THIS action and THIS decision (passkeys.py), then the decision is recorded
        by the same code path as an Ed25519 signature: roles, distinct signers, scope, expiry, at-most-once, audit and the RCTDB copy all apply unchanged."""
        from rct_control_plane import passkeys
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status != "PENDING":
            raise ApprovalError(f"action {approval_id} is already {action.status}" if action.status != "EXPIRED" else f"action {approval_id} expired before it was decided; ask for it again")
        decision = decision.strip().upper()
        if decision not in DECISIONS:
            raise ApprovalError(f"decision must be one of {DECISIONS}")
        if action.tool_name == passkeys.ENROLL_TOOL and decision == "APPROVED":
            raise ApprovalError("a device can not approve the enrolment of a device: it needs the signature of an approver key (SIGN_PENDING.bat, or `delentia approvals approve`)")
        try:
            cred, stored = passkeys.PasskeyStore(self._persistence).verify_new(approval_id, action.action_sha256, decision, assertion)
        except passkeys.PasskeyError as exc:
            raise ApprovalError(str(exc)) from exc
        return self.decide(approval_id, decision, cred.signer_key, stored)

    def _record_architect_decision(self, action: PendingAction, last_key: str) -> None:
        """RCTDB's architect_decisions collection is where the human's sign-offs belong (the A in F = D^I x A). Until Round 56
        nothing wrote a signed approval there. Each row keeps the action's digest, who signed (name, role, key fingerprint) and
        the outcome; never the signature secret, and the arguments only as a hash."""
        try:
            with self._persistence._connect() as conn:
                rows = conn.execute("SELECT public_key, decided_at FROM pending_action_signatures WHERE approval_id = ? ORDER BY decided_at",
                                    (action.approval_id,)).fetchall()
            signers = [{"name": self._signer_info(pk)[0], "role": self._signer_info(pk)[1], "key_fingerprint": _fingerprint(pk), "scheme": "passkey" if _is_passkey(pk) else "ed25519", "at": at}
                       for pk, at in rows] or [{"name": self._signer_info(last_key)[0], "role": self._signer_info(last_key)[1],
                                                "key_fingerprint": _fingerprint(last_key), "scheme": "passkey" if _is_passkey(last_key) else "ed25519", "at": action.decided_at}]
            self._persistence.save_architect_decision(
                f"approval-{action.approval_id}", "signed_approval" if action.status == "APPROVED" else "signed_rejection",
                f"{action.tool_name}: {action.status.lower()} by {len(signers)} signature(s)",
                {"tool_name": action.tool_name, "action_sha256": action.action_sha256, "policy_rule": action.policy_rule,
                 "required_signatures": action.required_signatures, "roles_required": action.approver_roles,
                 "args_sha256": hashlib.sha256(json.dumps(action.tool_args, sort_keys=True).encode("utf-8")).hexdigest()},
                {"status": action.status, "signers": signers}, linked_intent_id=None)
        except Exception:           # the signed decision itself is already stored and audited; this is its RCTDB copy
            pass

    def _signer_info(self, key: str) -> Any:
        """(name, role) of a signer: an Ed25519 key from the approvers file/environment, or a passkey registered in the database."""
        if _is_passkey(key):
            try:
                from rct_control_plane import passkeys
                cred = passkeys.PasskeyStore(self._persistence).get_by_signer(key)
                return (cred.name, cred.role) if cred else (None, None)
            except Exception:                                   # noqa: BLE001 - naming a signer must never break a decision
                return (None, None)
        return trusted_approver_keys().get(key), trusted_approver_roles().get(key)

    def _check_scope(self, action: PendingAction, key: str) -> None:
        """A passkey may be limited to some kinds of action, people and workspaces (passkeys.check_scope). An Ed25519 key has no scope field yet."""
        if not _is_passkey(key):
            return
        from rct_control_plane import passkeys
        cred = passkeys.PasskeyStore(self._persistence).get_by_signer(key)
        if cred is None:
            raise ApprovalError("signing device is not a trusted approver")
        try:
            passkeys.check_scope(cred, action)
        except passkeys.PasskeyError as exc:
            raise ApprovalError(str(exc)) from exc

    def _check_role(self, action: PendingAction, public_key_hex: str) -> None:
        if not action.approver_roles:
            return
        role = self._signer_info(public_key_hex)[1]
        if role not in action.approver_roles:
            held = f"role {role!r}" if role else "no role"
            raise ApprovalError(f"this action needs an approver with the role {' or '.join(action.approver_roles)}; "
                                f"the signing key has {held}")

    def _check_signature(self, action: PendingAction, decision: str, public_key_hex: str, signature_hex: str) -> None:
        if _is_passkey(public_key_hex):
            recomputed = action_digest(action.approval_id, action.namespace, action.goal, action.tool_name, action.tool_args, action.policy_digest, action.workspace)
            if recomputed != action.action_sha256:
                raise ApprovalError("stored action does not match its digest (the record was altered)")
            from rct_control_plane import passkeys
            try:
                passkeys.PasskeyStore(self._persistence).verify_stored(public_key_hex, action.approval_id, action.action_sha256, decision.strip().upper(), signature_hex)
            except passkeys.PasskeyError as exc:
                raise ApprovalError(str(exc)) from exc
            return
        trusted = trusted_approver_keys()
        if not trusted:
            raise ApprovalError(
                f"no trusted approvers configured ({APPROVERS_ENV} or {_approvers_file()}); "
                "nothing can be approved (fail-closed)"
            )
        if public_key_hex not in trusted:
            raise ApprovalError("signing key is not on the trusted-approver list")
        recomputed = action_digest(action.approval_id, action.namespace, action.goal,
                                   action.tool_name, action.tool_args, action.policy_digest, action.workspace)
        if recomputed != action.action_sha256:
            raise ApprovalError("stored action does not match its digest (the record was altered)")
        if not _verify(public_key_hex, approval_message(action.approval_id, action.action_sha256, decision),
                       signature_hex):
            raise ApprovalError("signature does not verify for this exact action and decision")

    def check_context(self, action: PendingAction, workspace: Optional[str], policy_digest: Optional[str]) -> None:
        """Round 82 (N2): refuse to run an approval in a different workspace, or under a different owner policy, than the one the approver signed for. Called BEFORE
        claim_for_execution, so a refusal does not use the approval up. Approvals that recorded neither (made before this change) are not constrained."""
        if action.workspace and workspace != action.workspace:
            raise ApprovalError(f"action {action.approval_id} was approved for the workspace {action.workspace!r}, not {workspace!r}; it was not run")
        if action.policy_digest and policy_digest != action.policy_digest:
            raise ApprovalError(f"action {action.approval_id} was approved under an owner policy that has since changed; it was not run, ask for it again")

    def claim_for_execution(self, approval_id: str) -> PendingAction:
        """Re-verifies everything at execution time (status alone is not
        trusted, because a database row can be edited), then atomically
        moves APPROVED -> EXECUTING so two concurrent resumes can never
        both run the action. Round 54: with an owner policy every required
        signature is re-verified, from distinct trusted keys that hold the
        required role."""
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status == "EXPIRED":
            raise ApprovalError(f"action {approval_id} expired before it ran; ask for it again")
        if action.status == "OUTCOME_UNKNOWN":
            raise ApprovalError(f"action {approval_id} was claimed and the process stopped before it recorded a result: its outcome is unknown, so it will not be run again; "
                                "a person checks and records what happened (delentia approvals resolve)")
        if action.status in ("EXECUTING", "EXECUTED"):
            raise ApprovalError(f"action {approval_id} was already {action.status.lower()}")
        if action.status != "APPROVED":
            raise ApprovalError(f"action {approval_id} is {action.status}, not APPROVED")
        if not action.approver_public_key or not action.signature_hex:
            raise ApprovalError(f"action {approval_id} has no approver signature")
        with self._persistence._connect() as conn:
            stored = conn.execute("SELECT public_key, signature_hex FROM pending_action_signatures WHERE approval_id = ?",
                                  (approval_id,)).fetchall()
        signers = {key: sig for key, sig in stored}
        if not signers:                                          # approved before multi-signature existed
            signers = {action.approver_public_key: action.signature_hex}
        if len(signers) < action.required_signatures:
            raise ApprovalError(f"action {approval_id} needs {action.required_signatures} signatures, "
                                f"{len(signers)} are on record")
        for key, signature in signers.items():
            self._check_signature(action, "APPROVED", key, signature)
            self._check_role(action, key)
            self._check_scope(action, key)
        with self._persistence._connect() as conn:
            claimed = conn.execute(
                "UPDATE pending_actions SET status = 'EXECUTING', claimed_at = ? WHERE approval_id = ? AND status = 'APPROVED'",
                (_now(), approval_id),
            ).rowcount
        if claimed != 1:
            raise ApprovalError(f"action {approval_id} was claimed by another resume")
        action.status = "EXECUTING"
        return action

    def reconcile(self, older_than: float = OUTCOME_UNKNOWN_AFTER_SECONDS, now: Optional[float] = None) -> List[PendingAction]:
        """Round 82 (T06). An action is claimed (APPROVED -> EXECUTING) BEFORE its effect so it can never run twice; if the process dies after the claim, nobody knows whether the effect
        happened. An EXECUTING row silent for longer than `older_than` seconds becomes OUTCOME_UNKNOWN: audited, the owner is told, and it is never run again by the system. A person
        looks at the world and records the truth with `resolve_unknown`. The promise is at-most-once, not exactly-once."""
        when = _now() if now is None else now
        flagged: List[str] = []
        with self._persistence._connect() as conn:
            rows = conn.execute("SELECT approval_id FROM pending_actions WHERE status = 'EXECUTING' AND COALESCE(claimed_at, decided_at, created_at) <= ?",
                                (when - float(older_than),)).fetchall()
            for (approval_id,) in rows:
                done = conn.execute("UPDATE pending_actions SET status = 'OUTCOME_UNKNOWN' WHERE approval_id = ? AND status = 'EXECUTING'", (approval_id,)).rowcount
                if done == 1:
                    flagged.append(approval_id)
        result: List[PendingAction] = []
        for approval_id in flagged:
            action = self.get(approval_id)
            if action is None:
                continue
            try:
                self._persistence.append_audit(
                    entity_type="pending_action_outcome_unknown", entity_id=approval_id, action="needs_a_person", actor="reconcile",
                    changes={"tool_name": action.tool_name, "action_sha256": action.action_sha256, "claimed_at": action.claimed_at, "namespace": action.namespace})
            except Exception:
                pass
            try:
                from rct_control_plane import owner_notify
                owner_notify.on_outcome_unknown(action, self._persistence)
            except Exception:
                pass
            result.append(action)
        return result

    def resolve_unknown(self, approval_id: str, outcome: str, note: str, actor: str = "owner") -> PendingAction:
        """A person records what really happened to an OUTCOME_UNKNOWN action: `done` (it took effect) or `not_done`. This only writes the record; it runs nothing. Asking for the action
        again is a new request with a new signature."""
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status != "OUTCOME_UNKNOWN":
            raise ApprovalError(f"action {approval_id} is {action.status}; only an OUTCOME_UNKNOWN action is resolved this way")
        if outcome not in ("done", "not_done"):
            raise ApprovalError("the outcome is 'done' or 'not_done'")
        if not str(note or "").strip():
            raise ApprovalError("a note is required: what did you check?")
        status = "EXECUTED" if outcome == "done" else "NOT_EXECUTED"
        record = {"reconciled_by_person": outcome, "note": str(note).strip()[:500], "actor": actor, "at": _now()}
        with self._persistence._connect() as conn:
            conn.execute("UPDATE pending_actions SET status = ?, executed_at = ?, result_json = ? WHERE approval_id = ? AND status = 'OUTCOME_UNKNOWN'",
                         (status, _now(), json.dumps(record), approval_id))
        try:
            self._persistence.append_audit(entity_type="pending_action_outcome_resolved", entity_id=approval_id, action=outcome, actor=actor,
                                           changes={"note": record["note"], "tool_name": action.tool_name, "action_sha256": action.action_sha256})
        except Exception:
            pass
        resolved = self.get(approval_id)
        assert resolved is not None
        return resolved

    def reconcile_by_receipt(self, approval_id: str, lookup: Callable[[PendingAction], Dict[str, Any]], actor: str = "reconciler") -> Dict[str, Any]:
        """Round 83 (DAAES TC-010): settle an OUTCOME_UNKNOWN action by asking the PROVIDER, not a person. `lookup(action)` queries the provider by the operation id the call carried and returns
        {"committed": True | False | None, "receipt": ...}: True records the action as done (with the receipt's hash as the note), False as not done, None (the provider cannot say, or the lookup failed)
        leaves it unknown. It records the truth and runs nothing; whether a not-done action is asked for again is a new request with its own signature."""
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status != "OUTCOME_UNKNOWN":
            raise ApprovalError(f"action {approval_id} is {action.status}; only an OUTCOME_UNKNOWN action is reconciled")
        try:
            found = lookup(action)
        except Exception as exc:                                    # noqa: BLE001 - a provider that cannot be asked leaves the question open
            return {"status": "OUTCOME_UNKNOWN", "reason": f"the provider could not be asked ({type(exc).__name__})"}
        committed = found.get("committed")
        if committed is None:
            return {"status": "OUTCOME_UNKNOWN", "reason": "the provider could not say"}
        receipt = hashlib.sha256(json.dumps(found.get("receipt"), sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        note = (f"provider receipt confirmed the effect (receipt sha256 {receipt})" if committed else "the provider holds no receipt for this operation: it did not happen")
        resolved = self.resolve_unknown(approval_id, "done" if committed else "not_done", note, actor=actor)
        return {"status": resolved.status, "committed": bool(committed), "receipt_sha256": receipt}

    def mark_executed(self, approval_id: str, result: Dict[str, Any]) -> None:
        with self._persistence._connect() as conn:
            conn.execute(
                "UPDATE pending_actions SET status = 'EXECUTED', executed_at = ?, result_json = ? "
                "WHERE approval_id = ? AND status = 'EXECUTING'",
                (_now(), json.dumps(result, default=str), approval_id),
            )


# --------------------------------------------------------- Architect tokens
# Round 48: the same Ed25519 approver key also signs delentia-mcp-ecosystem
# Architect tokens (the A in FDIA for evaluate_fdia's REQUIRE_HUMAN_SIGNATURE
# rules). Format and message must stay byte-identical to
# packages/shared/src/architect-token.ts; test_architect_token_real.py pins a
# deterministic cross-language vector.

ARCHITECT_TOKEN_VERSION = "dat1"
ARCHITECT_TOKEN_MAX_TTL_SECONDS = 24 * 60 * 60


def _b64url(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def architect_token_message(key_id: str, action_name: str, target_payload: str, expires: int) -> str:
    payload_hash = hashlib.sha256(target_payload.encode("utf-8")).hexdigest()
    return f"delentia-architect-token:v1|{key_id}|{action_name}|{payload_hash}|{expires}"


def sign_architect_token(private_key_path: str, key_id: str, action_name: str, target_payload: str = "",
                         ttl_seconds: int = 900, now_seconds: Optional[int] = None) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    if "." in key_id:
        raise ApprovalError("key_id must not contain '.'")
    key = load_pem_private_key(Path(private_key_path).expanduser().read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ApprovalError("Architect key must be an Ed25519 private key")
    now = int(time.time()) if now_seconds is None else now_seconds
    expires = now + min(max(1, int(ttl_seconds)), ARCHITECT_TOKEN_MAX_TTL_SECONDS)
    signature = key.sign(architect_token_message(key_id, action_name, target_payload, expires).encode("utf-8"))
    return f"{ARCHITECT_TOKEN_VERSION}.{key_id}.{expires}.{_b64url(signature)}"


def architect_key_entry(private_key_path: str, key_id: str, role: str) -> Dict[str, str]:
    """The FDIA_ARCHITECT_KEYS_JSON entry (public key only) for a private key file."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
    key = load_pem_private_key(Path(private_key_path).expanduser().read_bytes(), password=None)
    public_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()  # type: ignore[union-attr]
    return {"key_id": key_id, "role": role, "public_key_hex": public_hex}
