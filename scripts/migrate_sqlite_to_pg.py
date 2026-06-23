#!/usr/bin/env python3
"""
scripts/migrate_sqlite_to_pg.py
================================
Migrate RCT Control Plane data from SQLite to PostgreSQL.

Reads all rows from the local SQLite DB and upserts them into the
target PostgreSQL database.  Safe to re-run (uses ON CONFLICT upsert).

Usage::

    python scripts/migrate_sqlite_to_pg.py \\
        --sqlite rct_control_plane.db \\
        --dsn postgresql://rct:secret@localhost/rctdb

    # or via env vars:
    RCT_PG_DSN=postgresql://... python scripts/migrate_sqlite_to_pg.py

Options:
    --sqlite   Path to the source SQLite file  [default: rct_control_plane.db]
    --dsn      PostgreSQL DSN                   [default: RCT_PG_DSN env var]
    --dry-run  Print row counts only; do not write to PostgreSQL
    --verbose  Print each migrated row id
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MIGRATE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sqlite_rows(db_path: str, table: str) -> List[Dict[str, Any]]:
    """Return all rows from *table* in the SQLite DB as plain dicts."""
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 — trusted internal path
    return [dict(r) for r in rows]


def _decode_json_col(value: Any) -> Any:
    """Decode a JSON string column to Python object (idempotent)."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _sqlite_ts_to_pg(ts: Any) -> datetime:
    """Convert SQLite ISO timestamp string to tz-aware datetime."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Migration tables
# ---------------------------------------------------------------------------

def migrate_intents(cur: Any, rows: List[Dict[str, Any]], verbose: bool) -> int:
    count = 0
    for r in rows:
        cur.execute(
            """INSERT INTO intents
               (id, user_id, user_tier, intent_type, goal, metadata,
                created_at, is_valid, errors)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 user_tier   = EXCLUDED.user_tier,
                 intent_type = EXCLUDED.intent_type,
                 goal        = EXCLUDED.goal,
                 metadata    = EXCLUDED.metadata,
                 is_valid    = EXCLUDED.is_valid,
                 errors      = EXCLUDED.errors""",
            (
                r["id"], r["user_id"],
                r.get("user_tier", "FREE"),
                r["intent_type"], r["goal"],
                json.dumps(_decode_json_col(r.get("metadata", {}))),
                _sqlite_ts_to_pg(r["created_at"]),
                bool(r.get("is_valid", 1)),
                json.dumps(_decode_json_col(r.get("errors", []))),
            ),
        )
        count += 1
        if verbose:
            print(f"  intent  {r['id']}")
    return count


def migrate_states(cur: Any, rows: List[Dict[str, Any]], verbose: bool) -> int:
    count = 0
    for r in rows:
        cur.execute(
            """INSERT INTO states (id, namespace, key, value, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (namespace, key) DO UPDATE SET
                 value      = EXCLUDED.value,
                 updated_at = EXCLUDED.updated_at""",
            (
                r["id"], r["namespace"], r["key"],
                json.dumps(_decode_json_col(r.get("value", {}))),
                _sqlite_ts_to_pg(r["created_at"]),
                _sqlite_ts_to_pg(r.get("updated_at", r["created_at"])),
            ),
        )
        count += 1
        if verbose:
            print(f"  state   {r['namespace']}:{r['key']}")
    return count


def migrate_policy_decisions(cur: Any, rows: List[Dict[str, Any]], verbose: bool) -> int:
    count = 0
    for r in rows:
        cur.execute(
            """INSERT INTO policy_decisions
               (id, intent_id, user_id, decision, policy_name, reason, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 decision    = EXCLUDED.decision,
                 policy_name = EXCLUDED.policy_name,
                 reason      = EXCLUDED.reason""",
            (
                r["id"], r.get("intent_id"), r["user_id"],
                r["decision"], r["policy_name"],
                r.get("reason"),
                _sqlite_ts_to_pg(r["created_at"]),
            ),
        )
        count += 1
        if verbose:
            print(f"  policy  {r['id']}")
    return count


def migrate_audit_trail(cur: Any, rows: List[Dict[str, Any]], verbose: bool) -> int:
    count = 0
    for r in rows:
        cur.execute(
            """INSERT INTO audit_trail
               (entity_type, entity_id, action, actor, changes, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                r["entity_type"], r.get("entity_id"),
                r["action"], r.get("actor"),
                json.dumps(_decode_json_col(r.get("changes", {}))),
                _sqlite_ts_to_pg(r["created_at"]),
            ),
        )
        count += 1
        if verbose:
            print(f"  audit   id={r['id']}")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate RCT Control Plane SQLite → PostgreSQL"
    )
    parser.add_argument(
        "--sqlite",
        default=str(Path(__file__).parent.parent / "rct_control_plane.db"),
        help="Source SQLite file path",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN (falls back to RCT_PG_DSN / RCT_PG_* env vars)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    sqlite_path = args.sqlite
    dsn = args.dsn or os.environ.get("RCT_PG_DSN")
    if not dsn:
        host = os.environ.get("RCT_PG_HOST", "localhost")
        port = os.environ.get("RCT_PG_PORT", "5432")
        db   = os.environ.get("RCT_PG_DB",   "rctdb")
        user = os.environ.get("RCT_PG_USER", "rct")
        pw   = os.environ.get("RCT_PG_PASS", "")
        dsn  = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    print(f"migrate_sqlite_to_pg v{MIGRATE_VERSION}")
    print(f"  source : {sqlite_path}")
    print(f"  target : {dsn}")
    if args.dry_run:
        print("  mode   : DRY RUN (no writes)")

    # Read all tables
    tables = {
        "intents":          _sqlite_rows(sqlite_path, "intents"),
        "states":           _sqlite_rows(sqlite_path, "states"),
        "policy_decisions": _sqlite_rows(sqlite_path, "policy_decisions"),
        "audit_trail":      _sqlite_rows(sqlite_path, "audit_trail"),
    }
    for name, rows in tables.items():
        print(f"  {name:<20} {len(rows):>6} rows")

    if args.dry_run:
        print("Dry run complete — no data written.")
        return 0

    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        return 1

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            n_i = migrate_intents(cur, tables["intents"], args.verbose)
            n_s = migrate_states(cur, tables["states"], args.verbose)
            n_p = migrate_policy_decisions(cur, tables["policy_decisions"], args.verbose)
            n_a = migrate_audit_trail(cur, tables["audit_trail"], args.verbose)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: migration failed — {exc}", file=sys.stderr)
        conn.close()
        return 2
    conn.close()

    print(
        f"Migration complete: "
        f"{n_i} intents, {n_s} states, {n_p} policy_decisions, {n_a} audit rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
