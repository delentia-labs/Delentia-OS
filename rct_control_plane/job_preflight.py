"""Read-only, aggregate-only job upgrade inspection; not a readiness certificate.

python -m rct_control_plane.job_preflight --database /path/agentic.db --require-drained
Stop the old service before running the final check. This takes no admission
lock and cannot prevent an old process from starting work after inspection.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote


def inspect_database(database: Path) -> dict:
    path = database.resolve(strict=True)
    if not path.is_file():
        raise ValueError('database must be an existing regular file')
    with sqlite3.connect('file:' + quote(str(path), safe='/') + '?mode=ro', uri=True, timeout=5) as conn:
        conn.execute('PRAGMA query_only=ON')
        integrity = conn.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        statuses = dict(conn.execute('SELECT status,COUNT(*) FROM agent_jobs GROUP BY status')) if 'agent_jobs' in tables else {}
        live = sum(statuses.get(s, 0) for s in ('queued', 'running'))
        unknown = sorted(set(statuses) - {'queued', 'running', 'done', 'failed', 'cancelled', 'interrupted'})
        owner_columns = {r[1] for r in conn.execute('PRAGMA table_info(agent_job_owners)')}
        clock_schema = 'heartbeat_wall' in owner_columns
        legacy = conn.execute("SELECT COUNT(*) FROM agent_jobs j LEFT JOIN agent_job_owners o ON o.job_id=j.id "
            "WHERE j.status IN ('queued','running') AND o.heartbeat_wall IS NULL").fetchone()[0] if clock_schema else live
        metadata = {}
        for table in ('intent_request_keys', 'readonly_budget_jobs', 'agent_job_owners'):
            if table in tables:
                metadata[table] = conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]  # nosec B608 - fixed table names
    return {'schema_version': '1', 'inspection': 'read_only_aggregate_snapshot',
            'database_integrity_ok': integrity, 'job_status_counts': statuses,
            'unknown_statuses': unknown, 'live_jobs': live, 'legacy_live_jobs': legacy,
            'clock_fencing_schema_present': clock_schema,
            'drained_upgrade_snapshot_ok': integrity and not unknown and live == 0,
            'metadata_row_counts': metadata, 'retention_policy_verified': False,
            'limitations': ['stop old workers before final check; this snapshot does not fence admission',
                            'clock stability, host readiness and backup restore are not measured',
                            'metadata counts do not prove personal-data erasure']}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--require-drained', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = inspect_database(args.database)
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({'schema_version': '1', 'error': 'database inspection unavailable'}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 1 if args.require_drained and not report['drained_upgrade_snapshot_ok'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
