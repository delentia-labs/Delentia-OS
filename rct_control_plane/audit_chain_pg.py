"""
Tamper-evident audit trail on PostgreSQL (Round 50, parity with audit_chain.py).

`audit_chain.py` chains every SQLite `audit_trail` row. `PostgresPersistence`
(persistence_pg.py, `RCT_DB_BACKEND=postgres`) wrote plain rows with no chain,
so choosing Postgres (the backend a multi-host deployment would use) silently
dropped audit tier A1. This module is the same chain for Postgres.

Two Postgres-specific points:

- Ordering. SQLite serialises writers with its database lock. Postgres runs
  writers concurrently, so two appends could read the same previous hash and
  fork the chain. Every append takes a transaction-scoped advisory lock
  (`pg_advisory_xact_lock`) before reading the head, so links are strictly
  sequential and the lock is released on commit or rollback.
- Canonical form. `changes` is JSONB (Postgres normalises key order and
  whitespace) and `created_at` is TIMESTAMPTZ. The hash covers the values as
  stored and read back (canonical JSON with sorted keys, UTC ISO timestamp
  with microseconds), so verification recomputes exactly what was hashed.

Signing uses the same key as the SQLite chain (DELENTIA_AUDIT_SIGNING_KEY) and
`audit_chain.row_hash`, so one verifier understands both backends. The same
limits apply (see audit_chain.py): whoever can write the database and
recompute hashes can rewrite history from a point onwards; anchoring the head
outside the host (tier A3) is what exposes that.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from rct_control_plane.audit_chain import (
    GENESIS_HASH,
    ChainReport,
    PUBKEY_ENV,
    _public_hex,
    fingerprint,
    load_signing_key,
    row_hash,
)

# Arbitrary constant naming "the audit chain" for pg_advisory_xact_lock.
AUDIT_CHAIN_LOCK_KEY = 0x44454C454E544941  # "DELENTIA"

PG_CHAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_chain (
    seq                 BIGSERIAL PRIMARY KEY,
    audit_id            BIGINT NOT NULL UNIQUE REFERENCES audit_trail(id),
    prev_hash           TEXT NOT NULL,
    row_hash            TEXT NOT NULL,
    signature_hex       TEXT,
    signer_fingerprint  TEXT
)
"""


def canonical_changes(changes: Any) -> str:
    return json.dumps(changes, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_created_at(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc).isoformat(timespec="microseconds")


def append_pg(cur: Any, entity_type: str, entity_id: Optional[str], action: str, actor: Optional[str],
              changes: Dict[str, Any], json_adapter: Any) -> str:
    """Inserts one audit_trail row and links it into the chain, in the caller's
    transaction. Takes the chain lock first, so concurrent writers queue."""
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (AUDIT_CHAIN_LOCK_KEY,))
    now = datetime.now(timezone.utc)
    cur.execute(
        """INSERT INTO audit_trail (entity_type, entity_id, action, actor, changes, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id, changes, created_at""",
        (entity_type, entity_id, action, actor, json_adapter(changes), now),
    )
    audit_id, stored_changes, stored_at = cur.fetchone()
    cur.execute("SELECT row_hash FROM audit_chain ORDER BY seq DESC LIMIT 1")
    prev = cur.fetchone()
    prev_hash = prev[0] if prev else GENESIS_HASH
    h = row_hash(prev_hash, int(audit_id), entity_type, entity_id, action, actor,
                 canonical_changes(stored_changes), canonical_created_at(stored_at))
    signature_hex = signer_fp = None
    signer = load_signing_key()
    if signer is not None:
        signature_hex = signer.sign(bytes.fromhex(h)).hex()
        signer_fp = fingerprint(_public_hex(signer))
    cur.execute(
        "INSERT INTO audit_chain (audit_id, prev_hash, row_hash, signature_hex, signer_fingerprint) "
        "VALUES (%s, %s, %s, %s, %s)",
        (audit_id, prev_hash, h, signature_hex, signer_fp),
    )
    return h


def verify_pg(conn: Any, public_key_hex: Optional[str] = None) -> ChainReport:
    """Recomputes every link (same checks and messages as audit_chain.verify_audit_chain)."""
    import os
    public_key_hex = (public_key_hex or os.getenv(PUBKEY_ENV) or "").strip().lower() or None
    verifier = None
    expected_fp = None
    if public_key_hex:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        expected_fp = fingerprint(public_key_hex)

    with conn.cursor() as cur:
        cur.execute("SELECT seq, audit_id, prev_hash, row_hash, signature_hex, signer_fingerprint "
                    "FROM audit_chain ORDER BY seq")
        chain = cur.fetchall()
        first_chained = chain[0][1] if chain else None
        if first_chained is None:
            cur.execute("SELECT COUNT(*) FROM audit_trail")
        else:
            cur.execute("SELECT COUNT(*) FROM audit_trail WHERE id < %s", (first_chained,))
        legacy = cur.fetchone()[0]

        signed = 0

        def fail(seq: Optional[int], reason: str) -> ChainReport:
            head = chain[-1] if chain else None
            return ChainReport(False, len(chain), signed, legacy, head[0] if head else None,
                               head[3] if head else None, seq, reason)

        prev_hash = GENESIS_HASH
        for seq, audit_id, stored_prev, stored_hash, sig, signer_fp in chain:
            if stored_prev != prev_hash:
                return fail(seq, "broken link: prev_hash does not match the previous row (a row was removed or reordered)")
            cur.execute("SELECT entity_type, entity_id, action, actor, changes, created_at FROM audit_trail WHERE id = %s",
                        (audit_id,))
            row = cur.fetchone()
            if row is None:
                return fail(seq, f"audit_trail row {audit_id} is missing (deleted)")
            et, eid, act, actor, changes, created_at = row
            if row_hash(stored_prev, int(audit_id), et, eid, act, actor,
                        canonical_changes(changes), canonical_created_at(created_at)) != stored_hash:
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

        if first_chained is not None:
            cur.execute("SELECT MIN(t.id) FROM audit_trail t LEFT JOIN audit_chain c ON c.audit_id = t.id "
                        "WHERE t.id >= %s AND c.audit_id IS NULL", (first_chained,))
            unchained = cur.fetchone()[0]
            if unchained is not None:
                return fail(None, f"audit_trail row {unchained} was inserted without going through the chain")

    head = chain[-1] if chain else None
    return ChainReport(True, len(chain), signed, legacy, head[0] if head else None, head[3] if head else None)


def head_pg(conn: Any) -> Optional[Dict[str, Any]]:
    """The value to anchor outside the host (tier A3), same shape as audit_chain.chain_head."""
    with conn.cursor() as cur:
        cur.execute("SELECT seq, row_hash FROM audit_chain ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
    return {"seq": row[0], "row_hash": row[1]} if row else None
