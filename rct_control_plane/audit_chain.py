"""
Tamper-evident audit trail (Round 48, audit tier A1).

Before this module, `audit_trail` was a plain SQLite table: any row could be
edited or deleted without a trace, and the "signatures" recorded around it
(GovernedAutonomousLoop's per-instance JITNA key) could not be re-checked
after the process exited.

Every row written through ControlPlanePersistence._append_audit now also
gets a row in `audit_chain`:

    row_hash = SHA-256(canonical JSON of
                       [prev_hash, audit_id, entity_type, entity_id,
                        action, actor, changes, created_at])

linked to the previous row's hash, and - when DELENTIA_AUDIT_SIGNING_KEY
points at an Ed25519 key file - signed. verify_audit_chain() recomputes the
whole chain and reports the first break: an edited row, a deleted row, a
row inserted without going through the chain, or a bad signature.

What this does NOT defend against (see CLAUDE.md "Audit trail and key
custody"): someone who can write the database AND recompute hashes can
rewrite history from any point to the end; truncating the newest rows is
invisible. That needs the chain head published outside the host (tier A3:
sign_anchor() / check_anchors() below, sent to the fdia Worker's
/v1/audit/anchor witness by `delentia audit-chain anchor`) and a signer the agent cannot reach
(tier A2). A signing key on the agent's own host is readable by the
agent's shell tool, which is not a jail - so it proves "written by this
host", not "not written by the agent".
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SIGNING_KEY_ENV = "DELENTIA_AUDIT_SIGNING_KEY"
PUBKEY_ENV = "DELENTIA_AUDIT_PUBKEY"
GENESIS_HASH = "0" * 64

_REPO_ROOT = Path(__file__).resolve().parent.parent

CHAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_chain (
    seq                 INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id            INTEGER NOT NULL UNIQUE,
    prev_hash           TEXT NOT NULL,
    row_hash            TEXT NOT NULL,
    signature_hex       TEXT,
    signer_fingerprint  TEXT
);
"""

_signer_cache: Dict[Tuple[str, float], Any] = {}


def row_hash(prev_hash: str, audit_id: int, entity_type: str, entity_id: Optional[str], action: str,
             actor: Optional[str], changes_json: str, created_at: str) -> str:
    canonical = json.dumps(
        [prev_hash, audit_id, entity_type, entity_id, action, actor, changes_json, created_at],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_signing_key() -> Optional[Any]:
    path = os.getenv(SIGNING_KEY_ENV)
    if not path:
        return None
    p = Path(path).expanduser()
    key = (str(p), p.stat().st_mtime)
    if key not in _signer_cache:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        loaded = load_pem_private_key(p.read_bytes(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError(f"{SIGNING_KEY_ENV} must point at an Ed25519 private key")
        _signer_cache.clear()
        _signer_cache[key] = loaded
    return _signer_cache[key]


def _public_hex(private_key: Any) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def fingerprint(public_key_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]


def generate_signing_key(private_key_path: str) -> str:
    """Creates the audit signing key outside the repository and returns its
    public key hex (publish it; verifiers need it)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    path = Path(private_key_path).expanduser()
    try:
        inside = path.resolve().is_relative_to(_REPO_ROOT)
    except (OSError, ValueError):
        inside = False
    if inside:
        raise ValueError(f"refusing to store the audit signing key inside the repository ({_REPO_ROOT})")
    if path.exists():
        raise ValueError(f"{path} already exists; refusing to overwrite a key")
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return _public_hex(key)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CHAIN_SCHEMA)


def append(conn: sqlite3.Connection, audit_id: int, entity_type: str, entity_id: Optional[str], action: str,
           actor: Optional[str], changes_json: str, created_at: str) -> str:
    """Links one freshly inserted audit_trail row into the chain. Must run in
    the same transaction, after that INSERT: the connection then already
    holds SQLite's write lock, so no other writer can take the same
    prev_hash and fork the chain."""
    prev = conn.execute("SELECT row_hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = prev[0] if prev else GENESIS_HASH
    h = row_hash(prev_hash, audit_id, entity_type, entity_id, action, actor, changes_json, created_at)
    signature_hex = signer_fp = None
    signer = load_signing_key()
    if signer is not None:
        signature_hex = signer.sign(bytes.fromhex(h)).hex()
        signer_fp = fingerprint(_public_hex(signer))
    conn.execute(
        "INSERT INTO audit_chain (audit_id, prev_hash, row_hash, signature_hex, signer_fingerprint) "
        "VALUES (?, ?, ?, ?, ?)",
        (audit_id, prev_hash, h, signature_hex, signer_fp),
    )
    return h


@dataclass
class ChainReport:
    ok: bool
    chained_rows: int
    signed_rows: int
    legacy_unchained_rows: int
    head_seq: Optional[int]
    head_hash: Optional[str]
    first_bad_seq: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def verify_audit_chain(conn: sqlite3.Connection, public_key_hex: Optional[str] = None) -> ChainReport:
    """Recomputes every link. Rows written before the chain existed are
    counted as legacy (unverifiable), not as failures."""
    ensure_schema(conn)
    public_key_hex = (public_key_hex or os.getenv(PUBKEY_ENV) or "").strip().lower() or None
    verifier = None
    expected_fp = None
    if public_key_hex:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        expected_fp = fingerprint(public_key_hex)

    chain = conn.execute(
        "SELECT seq, audit_id, prev_hash, row_hash, signature_hex, signer_fingerprint FROM audit_chain ORDER BY seq"
    ).fetchall()
    first_chained_audit_id = chain[0][1] if chain else None
    legacy = conn.execute(
        "SELECT COUNT(*) FROM audit_trail WHERE ? IS NULL OR id < ?",
        (first_chained_audit_id, first_chained_audit_id),
    ).fetchone()[0]

    def fail(seq: Optional[int], reason: str) -> ChainReport:
        head = chain[-1] if chain else None
        return ChainReport(False, len(chain), signed, legacy, head[0] if head else None,
                           head[3] if head else None, seq, reason)

    signed = 0
    prev_hash = GENESIS_HASH
    for seq, audit_id, stored_prev, stored_hash, sig, signer_fp in chain:
        if stored_prev != prev_hash:
            return fail(seq, "broken link: prev_hash does not match the previous row (a row was removed or reordered)")
        row = conn.execute(
            "SELECT entity_type, entity_id, action, actor, changes, created_at FROM audit_trail WHERE id = ?",
            (audit_id,),
        ).fetchone()
        if row is None:
            return fail(seq, f"audit_trail row {audit_id} is missing (deleted)")
        if row_hash(stored_prev, audit_id, *row) != stored_hash:
            return fail(seq, f"audit_trail row {audit_id} was modified after it was written")
        if sig:
            signed += 1
            if verifier is not None:
                if signer_fp != expected_fp:
                    return fail(seq, f"row signed by an unexpected key ({signer_fp})")
                try:
                    verifier.verify(bytes.fromhex(sig), bytes.fromhex(stored_hash))
                except Exception:
                    return fail(seq, "signature does not verify")
        elif verifier is not None:
            return fail(seq, "row is unsigned but a signing public key was given")
        prev_hash = stored_hash

    if first_chained_audit_id is not None:
        unchained = conn.execute(
            "SELECT MIN(t.id) FROM audit_trail t LEFT JOIN audit_chain c ON c.audit_id = t.id "
            "WHERE t.id >= ? AND c.audit_id IS NULL", (first_chained_audit_id,),
        ).fetchone()[0]
        if unchained is not None:
            return fail(None, f"audit_trail row {unchained} was inserted without going through the chain")

    head = chain[-1] if chain else None
    return ChainReport(True, len(chain), signed, legacy, head[0] if head else None, head[3] if head else None)


def chain_head(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """The value to publish outside the host (tier A3 anchoring)."""
    ensure_schema(conn)
    row = conn.execute("SELECT seq, row_hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
    return {"seq": row[0], "row_hash": row[1]} if row else None


# ---------------------------------------------------------------------------
# Round 50, tier A3: anchor the chain head at an outside witness.
# Same protocol as delentia-guard (packages/shared/src/audit-anchor.ts):
#   message = "delentia-audit-anchor:v1|<key_id>|<entries>|<head>|<signed_at>"
# where entries = audit_chain.seq of the head row (seq starts at 1).
# ---------------------------------------------------------------------------
ANCHOR_MESSAGE_PREFIX = "delentia-audit-anchor:v1"


def anchor_message(key_id: str, entries: int, head: str, signed_at: str) -> str:
    return f"{ANCHOR_MESSAGE_PREFIX}|{key_id}|{entries}|{head}|{signed_at}"


def sign_anchor(conn: sqlite3.Connection, key_id: str, private_key: Optional[Any] = None,
                signed_at: Optional[str] = None) -> Dict[str, Any]:
    """The current chain head, signed for POST <witness>/v1/audit/anchor.
    Uses DELENTIA_AUDIT_SIGNING_KEY unless a key is passed."""
    from datetime import datetime, timezone
    signer = private_key if private_key is not None else load_signing_key()
    if signer is None:
        raise ValueError(f"no signing key: set {SIGNING_KEY_ENV} (see `delentia audit-chain keygen`)")
    head = chain_head(conn)
    if head is None:
        raise ValueError("the audit chain is empty; nothing to anchor")
    when = signed_at or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    message = anchor_message(key_id, int(head["seq"]), head["row_hash"], when)
    return {"key_id": key_id, "entries": int(head["seq"]), "head": head["row_hash"], "signed_at": when,
            "signature": signer.sign(message.encode("utf-8")).hex()}


def check_anchors(conn: sqlite3.Connection, witness: Dict[str, Any]) -> Dict[str, Any]:
    """Every anchored (entries, head) from GET <witness>/v1/audit/anchor/<key_id>
    must match this database's chain; conflicts the witness recorded
    (rollback/fork) are reported too."""
    ensure_schema(conn)
    problems = []
    anchors = witness.get("anchors") or []
    for a in anchors:
        row = conn.execute("SELECT row_hash FROM audit_chain WHERE seq = ?", (int(a["entries"]),)).fetchone()
        if row is None:
            problems.append(f"chain has no row {a['entries']}, but it was anchored at {a.get('received_at')} (truncated)")
        elif row[0] != a["head"]:
            problems.append(f"row {a['entries']} hashes to {row[0][:12]}..., anchored {a['head'][:12]}... "
                            f"at {a.get('received_at')} (rewritten)")
    conflicts = witness.get("conflicts") or []
    if conflicts:
        problems.append(f"the witness recorded {len(conflicts)} conflicting anchor(s) (rollback/fork) for this key")
    return {"ok": not problems, "checked": len(anchors), "problems": problems}

