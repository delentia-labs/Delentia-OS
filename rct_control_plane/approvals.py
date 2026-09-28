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
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane.persistence import ControlPlanePersistence

APPROVAL_MESSAGE_VERSION = "delentia-approval:v1"
DECISIONS = ("APPROVED", "REJECTED")
APPROVERS_ENV = "DELENTIA_APPROVER_PUBKEYS"

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
"""


class ApprovalError(ValueError):
    pass


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def action_digest(approval_id: str, namespace: str, goal: str, tool_name: str, tool_args: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {"approval_id": approval_id, "namespace": namespace, "goal": goal,
         "tool_name": tool_name, "tool_args": tool_args},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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

class PendingActionStore:
    def __init__(self, persistence: ControlPlanePersistence):
        self._persistence = persistence
        with self._persistence._connect() as conn:
            conn.executescript(_SCHEMA)

    def create(self, namespace: str, goal: str, tool_name: str, tool_args: Dict[str, Any],
               reason: Optional[str] = None) -> PendingAction:
        approval_id = uuid.uuid4().hex[:12]
        digest = action_digest(approval_id, namespace, goal, tool_name, tool_args)
        action = PendingAction(approval_id, namespace, goal, tool_name, dict(tool_args), digest,
                               reason, "PENDING", time.time())
        with self._persistence._connect() as conn:
            conn.execute(
                "INSERT INTO pending_actions (approval_id, namespace, goal, tool_name, tool_args_json, "
                "action_sha256, reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (approval_id, namespace, goal, tool_name, json.dumps(tool_args, sort_keys=True),
                 digest, reason, "PENDING", action.created_at),
            )
        return action

    def get(self, approval_id: str) -> Optional[PendingAction]:
        with self._persistence._connect() as conn:
            row = conn.execute(
                "SELECT approval_id, namespace, goal, tool_name, tool_args_json, action_sha256, reason, status, "
                "created_at, decided_at, approver_public_key, signature_hex, executed_at, result_json "
                "FROM pending_actions WHERE approval_id = ?", (approval_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, status: Optional[str] = "PENDING", limit: int = 50) -> List[PendingAction]:
        query = ("SELECT approval_id, namespace, goal, tool_name, tool_args_json, action_sha256, reason, status, "
                 "created_at, decided_at, approver_public_key, signature_hex, executed_at, result_json "
                 "FROM pending_actions")
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status.upper(),)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._persistence._connect() as conn:
            rows = conn.execute(query, params + (limit,)).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: tuple) -> PendingAction:
        return PendingAction(
            approval_id=row[0], namespace=row[1], goal=row[2], tool_name=row[3],
            tool_args=json.loads(row[4]), action_sha256=row[5], reason=row[6], status=row[7],
            created_at=row[8], decided_at=row[9], approver_public_key=row[10], signature_hex=row[11],
            executed_at=row[12], result=json.loads(row[13]) if row[13] else None,
        )

    def decide(self, approval_id: str, decision: str, public_key_hex: str, signature_hex: str) -> PendingAction:
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status != "PENDING":
            raise ApprovalError(f"action {approval_id} is already {action.status}")
        decision = decision.strip().upper()
        public_key_hex = public_key_hex.strip().lower()
        self._check_signature(action, decision, public_key_hex, signature_hex)
        now = time.time()
        with self._persistence._connect() as conn:
            conn.execute(
                "UPDATE pending_actions SET status = ?, decided_at = ?, approver_public_key = ?, signature_hex = ? "
                "WHERE approval_id = ? AND status = 'PENDING'",
                (decision, now, public_key_hex, signature_hex, approval_id),
            )
        self._persistence.append_audit(
            entity_type="pending_action_decided", entity_id=approval_id, action=decision.lower(),
            actor=f"approver:{trusted_approver_keys().get(public_key_hex, '?')}:{public_key_hex[:16]}",
            changes={"action_sha256": action.action_sha256, "tool_name": action.tool_name,
                     "signature_hex": signature_hex, "approver_public_key": public_key_hex},
        )
        decided = self.get(approval_id)
        assert decided is not None
        return decided

    def _check_signature(self, action: PendingAction, decision: str, public_key_hex: str, signature_hex: str) -> None:
        trusted = trusted_approver_keys()
        if not trusted:
            raise ApprovalError(
                f"no trusted approvers configured ({APPROVERS_ENV} or {_approvers_file()}); "
                "nothing can be approved (fail-closed)"
            )
        if public_key_hex not in trusted:
            raise ApprovalError("signing key is not on the trusted-approver list")
        recomputed = action_digest(action.approval_id, action.namespace, action.goal,
                                   action.tool_name, action.tool_args)
        if recomputed != action.action_sha256:
            raise ApprovalError("stored action does not match its digest (the record was altered)")
        if not _verify(public_key_hex, approval_message(action.approval_id, action.action_sha256, decision),
                       signature_hex):
            raise ApprovalError("signature does not verify for this exact action and decision")

    def claim_for_execution(self, approval_id: str) -> PendingAction:
        """Re-verifies everything at execution time (status alone is not
        trusted, because a database row can be edited), then atomically
        moves APPROVED -> EXECUTING so two concurrent resumes can never
        both run the action."""
        action = self.get(approval_id)
        if action is None:
            raise ApprovalError(f"no pending action {approval_id!r}")
        if action.status in ("EXECUTING", "EXECUTED"):
            raise ApprovalError(f"action {approval_id} was already {action.status.lower()}")
        if action.status != "APPROVED":
            raise ApprovalError(f"action {approval_id} is {action.status}, not APPROVED")
        if not action.approver_public_key or not action.signature_hex:
            raise ApprovalError(f"action {approval_id} has no approver signature")
        self._check_signature(action, "APPROVED", action.approver_public_key, action.signature_hex)
        with self._persistence._connect() as conn:
            claimed = conn.execute(
                "UPDATE pending_actions SET status = 'EXECUTING' WHERE approval_id = ? AND status = 'APPROVED'",
                (approval_id,),
            ).rowcount
        if claimed != 1:
            raise ApprovalError(f"action {approval_id} was claimed by another resume")
        action.status = "EXECUTING"
        return action

    def mark_executed(self, approval_id: str, result: Dict[str, Any]) -> None:
        with self._persistence._connect() as conn:
            conn.execute(
                "UPDATE pending_actions SET status = 'EXECUTED', executed_at = ?, result_json = ? "
                "WHERE approval_id = ? AND status = 'EXECUTING'",
                (time.time(), json.dumps(result, default=str), approval_id),
            )
