"""
Round 67: erasing one person's memory by destroying their key (crypto-shredding), a prototype.

The problem (CLAUDE.md, "PDPA vs append-only"): the memory event log is hash-chained, so an event cannot be edited or removed without breaking the chain, but a person has the right to
have their data erased. And the Zero-Delete policy forbids deleting rows. The way out the Architect wrote down: keep personal data off the chain - the chain holds only what cannot
identify anyone - and make the readable copy depend on a key that can be destroyed.

What this module does
  * Every event payload of the memory log (add / edit / revoke) and every checkpoint is SEALED with AES-256-GCM under a key that belongs to ONE person (namespace). The event hash covers
    the ciphertext, so the chain keeps verifying after the key is gone.
  * The key lives in a file outside the database (`$DELENTIA_MEMORY_KEYS_DIR`, default `<data home>/memory_keys/`, mode 0600). Whoever can read the database but not that directory
    cannot read the log's text.
  * `erase_person` destroys that key (overwritten, then removed), scrubs the readable copy in the `memories` table, writes an `erase` event and an audit row, and forces an anchor in the
    audit chain. Afterwards the log still verifies, the person's events are still counted, and their text is unrecoverable from the log.
  * Erasure is irreversible, so it needs the signature of a trusted approver key over the exact request (namespace and the log head at that moment). No approver key configured = it
    cannot be done, the same rule as every other irreversible action here.

Round 68 - the other tables. `erase_person(..., scrub_tables=True)` (the default) also overwrites the text columns of every table that carries the person's namespace (past requests and answers and
their full-text index, the key-value states such as the warm-recall cache, the approvals' goals and arguments), expires their waiting approvals, rebuilds the full-text index and VACUUMs. The audit
rows that held their words (`goal`, the model's reasoning, tool arguments) are sealed under the same key (audit_text.py), so destroying it erases those too. Rows are overwritten, never deleted.

What it does NOT do, and says so in its report
  * Events written BEFORE sealing was on are plaintext in the chain and cannot be sealed afterwards (changing them would break their hashes). The report counts them.
  * The `memories` table keeps a readable copy for recall; erasure scrubs it (the one overwrite this policy allows, because it is the purpose of erasure). Other tables that carry the
    person's text under their namespace (past requests and answers, learned skills, experiment rows ...) are listed in the report and left alone: erasing those is a separate decision.
  * Backups made before the erasure still hold the readable table copy and, if the key file was backed up, the key. `delentia backup` leaves memory keys out unless asked.
  * Key custody is the weak point: a key file on the same disk and the same OS user as the agent protects against reading the database, not against the host itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG = logging.getLogger(__name__)
SEAL_ENV = "DELENTIA_MEMORY_SEAL"
KEYS_ENV = "DELENTIA_MEMORY_KEYS_DIR"
MAGIC = b"DLSEAL1"
ERASED_TEXT = "[erased]"
ERASE_MESSAGE_PREFIX = "delentia-memory-erase|"


def sealing_enabled() -> bool:
    return (os.environ.get(SEAL_ENV) or "").strip().lower() not in ("0", "off", "false", "no")


def keys_dir() -> Path:
    override = os.environ.get(KEYS_ENV)
    if override:
        return Path(override)
    from rct_control_plane.data_home import data_home
    return (data_home() or (Path.home() / ".delentia")) / "memory_keys"


def _key_path(namespace: str) -> Path:
    return keys_dir() / (hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:40] + ".key")


def get_key(namespace: str, create: bool = False) -> Optional[bytes]:
    path = _key_path(namespace)
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pass
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:                                              # another writer created it between our read and now
        return get_key(namespace, create=False)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(key.hex() + "\n")
    return key


def fingerprint(key: bytes) -> str:
    return hashlib.sha256(b"delentia-memory-key|" + key).hexdigest()[:16]


def _aead(key: bytes) -> Any:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)


# ------------------------------------------------------------------------------- event payloads (text)

def seal(namespace: str, plain_json: str) -> str:
    """The stored form of an event payload. Falls back to the plain text (and says so in the log) if the key cannot be created: a memory write must never fail because of this."""
    if not sealing_enabled():
        return plain_json
    try:
        key = get_key(namespace, create=True)
        if key is None:
            return plain_json
        nonce = secrets.token_bytes(12)
        blob = nonce + _aead(key).encrypt(nonce, plain_json.encode("utf-8"), namespace.encode("utf-8"))
        return json.dumps({"enc": base64.b64encode(blob).decode("ascii"), "kid": fingerprint(key), "v": 1}, sort_keys=True, separators=(",", ":"))
    except Exception as exc:                                             # noqa: BLE001
        LOG.warning("memory payload not sealed (%s): %s", type(exc).__name__, exc)
        return plain_json


def open_payload(namespace: str, stored: str) -> Dict[str, Any]:
    """The payload as a dict. A sealed payload whose key is gone (erased) or does not match comes back as {"_erased": True}."""
    data = json.loads(stored)
    if not isinstance(data, dict) or "enc" not in data:
        return data
    key = get_key(namespace, create=False)
    if key is None or fingerprint(key) != data.get("kid"):
        return {"_erased": True}
    try:
        blob = base64.b64decode(data["enc"])
        return json.loads(_aead(key).decrypt(blob[:12], blob[12:], namespace.encode("utf-8")).decode("utf-8"))
    except Exception:                                                    # noqa: BLE001 - a wrong tag is the same as an absent key
        return {"_erased": True}


def is_sealed(stored: str) -> bool:
    try:
        data = json.loads(stored)
    except ValueError:
        return False
    return isinstance(data, dict) and "enc" in data


# ------------------------------------------------------------------------------- checkpoints (bytes)

def seal_bytes(namespace: str, data: bytes) -> bytes:
    if not sealing_enabled():
        return data
    try:
        key = get_key(namespace, create=True)
        if key is None:
            return data
        nonce = secrets.token_bytes(12)
        return MAGIC + bytes.fromhex(fingerprint(key)) + nonce + _aead(key).encrypt(nonce, data, namespace.encode("utf-8"))
    except Exception as exc:                                             # noqa: BLE001
        LOG.warning("checkpoint not sealed (%s): %s", type(exc).__name__, exc)
        return data


def is_sealed_bytes(blob: bytes) -> bool:
    return blob[:len(MAGIC)] == MAGIC


def open_bytes(namespace: str, blob: bytes) -> Optional[bytes]:
    """The plain bytes, or None when the key is gone or does not match."""
    if not is_sealed_bytes(blob):
        return blob
    key = get_key(namespace, create=False)
    body = blob[len(MAGIC):]
    if key is None or bytes.fromhex(fingerprint(key)) != body[:8]:
        return None
    try:
        return _aead(key).decrypt(body[8:20], body[20:], namespace.encode("utf-8"))
    except Exception:                                                    # noqa: BLE001
        return None


# ------------------------------------------------------------------------------- erasure

def erase_message(namespace: str, head_hash: str) -> bytes:
    """What an approver signs: this person, at exactly this state of the log. A signature for another head (more has been written since) does not verify."""
    return (ERASE_MESSAGE_PREFIX + namespace + "|" + head_hash).encode("utf-8")


def sign_erase(private_key_path: str, namespace: str, head_hash: str) -> Dict[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ErasureError("the approver key must be an Ed25519 key (as made by `delentia approvals keygen`)")
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return {"public_key": public, "signature": key.sign(erase_message(namespace, head_hash)).hex()}


class ErasureError(ValueError):
    pass


def inventory(persistence: Any, namespace: str) -> Dict[str, Any]:
    """What still holds this person's text, found by looking, not by a list we wrote."""
    with persistence._connect() as conn:
        events = conn.execute("SELECT payload FROM memory_events WHERE namespace = ? AND kind != 'erase'", (namespace,)).fetchall()
        sealed = sum(1 for (p,) in events if is_sealed(p))
        other: List[Dict[str, Any]] = []
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            if table in ("memory_events", "memory_checkpoints", "memories", "audit_trail", "audit_chain") or table in NO_PERSONAL_TEXT or "_fts" in table:
                continue
            try:
                cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
                if "namespace" in cols:
                    carrying = [c for c in cols if c in TEXT_COLUMNS]
                    n = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE namespace = ?', (namespace,)).fetchone()[0]
                    erased = 0
                    if carrying:
                        probe = " AND ".join(f'(COALESCE("{c}", \'\') IN (\'\', ?))' for c in carrying)
                        erased = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE namespace = ? AND {probe}', [namespace] + [TEXT_COLUMNS[c] for c in carrying]).fetchone()[0]
                    if n - erased > 0:
                        other.append({"table": table, "rows": int(n - erased)})
            except sqlite3.Error:
                continue
        plain_audit = _plain_audit_rows(conn, namespace)
        plain_experiments = conn.execute("SELECT COUNT(*) FROM experiments WHERE name NOT LIKE 'goal sha256:%' AND name NOT LIKE 'governed-loop:%'").fetchone()[0] if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'experiments'").fetchone() else 0
        table_rows = conn.execute("SELECT COUNT(*) FROM memories WHERE namespace = ?", (namespace,)).fetchone()[0]
    return {"events": len(events), "sealed_events": sealed, "plaintext_events": len(events) - sealed, "memory_rows": int(table_rows), "other_tables_with_this_person": other,
            "plain_audit_rows": plain_audit, "experiments_named_by_goal": int(plain_experiments), "has_key": get_key(namespace) is not None}


# columns that hold a person's words, and what an erased value looks like (so a reader that parses JSON still parses it)
TEXT_COLUMNS = {"goal": ERASED_TEXT, "answer": ERASED_TEXT, "content": ERASED_TEXT, "message": ERASED_TEXT, "text": ERASED_TEXT, "reason": ERASED_TEXT, "note": ERASED_TEXT, "title": ERASED_TEXT,
                "context": "{}", "value": "{}", "tool_args_json": "{}", "result_json": "{}", "tools": "[]"}
NEVER_SCRUB = {"audit_trail", "audit_chain", "memory_events", "memory_checkpoints", "memories", "pending_action_signatures"}
NO_PERSONAL_TEXT = {"spend_ledger"}                    # numbers per person per day: counted, not listed as holding words


def _namespaced_tables(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    found = []
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        if table in NEVER_SCRUB or "_fts" in table:
            continue
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        if "namespace" in cols:
            found.append({"table": table, "columns": [c for c in cols if c in TEXT_COLUMNS]})
    return found


def _plain_audit_rows(conn: sqlite3.Connection, namespace: str) -> int:
    """Audit rows of this person that still hold their words in the clear (written before audit_text sealing was on). They are chained, so they cannot be edited."""
    n = 0
    for entity_type, text in conn.execute("SELECT entity_type, changes FROM audit_trail WHERE actor = ? AND entity_type IN ('governed_loop_episode_start', 'autonomous_loop_step')", (namespace,)):
        try:
            changes = json.loads(text)
        except ValueError:
            continue
        fields = ("goal", "rct7_steps") if entity_type == "governed_loop_episode_start" else ("tool_args", "reasoning")
        if any(changes.get(f) not in (None, "", [], {}) and not (isinstance(changes.get(f), dict) and "sealed" in changes[f]) for f in fields):
            n += 1
    return n


def scrub_tables(conn: sqlite3.Connection, namespace: str) -> Dict[str, Any]:
    """Overwrite the person's text in every namespaced table. Waiting approvals are expired first (their digest covers the text they are about to lose)."""
    done: List[Dict[str, Any]] = []
    for entry in _namespaced_tables(conn):
        table, cols = entry["table"], entry["columns"]
        if table == "pending_actions":
            conn.execute("UPDATE pending_actions SET status = 'EXPIRED' WHERE namespace = ? AND status = 'PENDING'", (namespace,))
        if not cols:
            continue
        sets = ", ".join(f'"{c}" = ?' for c in cols)
        count = conn.execute(f'UPDATE "{table}" SET {sets} WHERE namespace = ?', [TEXT_COLUMNS[c] for c in cols] + [namespace]).rowcount
        if count:
            done.append({"table": table, "rows": int(count), "columns": cols})
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'episode_log_fts'").fetchone():
        conn.execute("INSERT INTO episode_log_fts(episode_log_fts) VALUES ('rebuild')")           # the index kept the old words; it reads the (now scrubbed) content table again
    return {"tables": done}


def _destroy_key(namespace: str) -> bool:
    path = _key_path(namespace)
    if not path.exists():
        return False
    try:
        size = path.stat().st_size
        with open(path, "r+b") as handle:                                # overwrite before unlinking; on a journalling or SSD volume this is best effort, not a guarantee
            handle.write(b"\0" * max(size, 64))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        pass
    path.unlink()
    return True


def _vacuum(persistence: Any) -> bool:
    """Rewrite the database file so the old bytes of the scrubbed rows are gone from free pages and the write-ahead log. Needs a file database and no open transaction."""
    path = getattr(persistence, "db_path", None)
    if not path or str(path) == ":memory:":
        return False
    try:
        raw = sqlite3.connect(str(path), isolation_level=None)
        try:
            raw.execute("PRAGMA secure_delete = ON")
            raw.execute("VACUUM")
            raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            raw.close()
        return True
    except sqlite3.Error as exc:
        LOG.warning("vacuum after erasure failed: %s", exc)
        return False


def erase_person(persistence: Any, namespace: str, reason: str, public_key_hex: str, signature_hex: str, scrub_other_tables: bool = True) -> Dict[str, Any]:
    from rct_control_plane import approvals, memory_eventlog
    if not namespace or not reason.strip():
        raise ErasureError("a namespace and a reason are required")
    trusted = approvals.trusted_approver_keys()
    if not trusted:
        raise ErasureError("no approver key is configured, so nothing irreversible can be authorised (see `delentia approvals keygen`)")
    log = memory_eventlog.MemoryEventLog(persistence)
    head = log.head()
    if public_key_hex.lower() not in trusted:
        raise ErasureError("the signing key is not a trusted approver key")
    if not approvals.verify_signature(public_key_hex, erase_message(namespace, head["hash"]), signature_hex):
        raise ErasureError("the signature does not match this request and the current head of the log (sign again with `delentia memory erase-request`)")
    before = inventory(persistence, namespace)
    destroyed = _destroy_key(namespace)
    from rct_control_plane.persistence import ControlPlanePersistence
    with persistence._connect() as conn:
        conn.execute("PRAGMA secure_delete = ON")                        # overwritten pages are zeroed, not just unlinked (found by looking at the raw file after an erase)
        scrubbed = conn.execute("UPDATE memories SET content = ?, context = '{}', revoked_reason = CASE WHEN revoked_reason IS NULL THEN NULL ELSE ? END WHERE namespace = ?", (ERASED_TEXT, ERASED_TEXT, namespace)).rowcount
        scrubbed_tables = scrub_tables(conn, namespace) if scrub_other_tables else {"tables": []}
        seq = memory_eventlog.append(conn, namespace, "erase", "-", {"reason": reason.strip()[:300], "key_destroyed": destroyed})
        ControlPlanePersistence._append_audit(conn, memory_eventlog.ANCHOR_ENTITY, namespace, "memory_erased", "memory_erasure",
                                              {"namespace": namespace, "reason": reason.strip()[:300], "key_destroyed": destroyed, "events": before["events"],
                                               "sealed_events": before["sealed_events"], "plaintext_events": before["plaintext_events"], "approver_key": public_key_hex[:16], "event_seq": seq})
        memory_eventlog._maybe_anchor(conn, seq, conn.execute("SELECT event_hash FROM memory_events WHERE seq = ?", (seq,)).fetchone()[0], force=True)
    vacuumed = _vacuum(persistence)
    after = inventory(persistence, namespace)
    return {"erased": True, "vacuumed": vacuumed, "namespace": namespace, "key_destroyed": destroyed, "table_rows_scrubbed": int(scrubbed), "other_tables_scrubbed": scrubbed_tables["tables"],
            "before": before, "after": after,
            "not_erased": {"plaintext_events_in_the_chain": after["plaintext_events"], "other_tables": after["other_tables_with_this_person"],
                           "plain_audit_rows": after["plain_audit_rows"], "experiments_named_by_goal": after["experiments_named_by_goal"],
                           "skills_database": "learned skills live in a separate file and are shared knowledge; not scrubbed",
                           "note": "backups made earlier, any copy of the key file, and remnants outside the database file (filesystem journal, swap, snapshots) still hold the readable data"}}
