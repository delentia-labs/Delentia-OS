"""
GroundTruthStore — Round 26 Phase 18 Task 39.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-33
FGHF) specifies checking answers "against Ground Truth ในฐานข้อมูล" (in a
database). The real `HallucinationDetector` (algo_33_fghf.py) only carries a
small, non-persisted, non-queryable Python dict of known temporal facts
(`_check_temporal_consistency`'s `known_errors`) — real, but not a database.

This module closes that specific gap: a real, persisted, queryable sqlite
table of (subject, predicate, value) facts, following the exact same
connect/execute/commit pattern `persistence.py`'s `ControlPlanePersistence`
already uses. Seeded with the SAME facts `HallucinationDetector` already
encodes in-code, plus a couple more real, easily-verifiable facts — a small,
honestly-scoped store, not a claim of comprehensive ground-truth coverage.

Deliberately its own file/table rather than a new method bolted onto
`ControlPlanePersistence` — this is a distinct concern (verifiable public
facts) from that class's intent/state/audit/memory bookkeeping, and keeping
it separate avoids growing that already-large class further.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Dict, Optional

from rct_control_plane.persistence import _ReusableConnectionContext

def _default_db_path() -> str:
    """GROUND_TRUTH_DB_PATH, else under DELENTIA_HOME, else beside the repository (a source checkout) or under ~/.delentia (an installed package: site-packages may be read-only)."""
    explicit = os.environ.get("GROUND_TRUTH_DB_PATH")
    if explicit:
        return explicit
    from rct_control_plane import data_home
    home = data_home.data_home()
    if home is not None:
        home.mkdir(parents=True, exist_ok=True)
        return str(home / "ground_truth_store.db")
    return data_home.legacy_default("ground_truth_store.db")


_DEFAULT_DB_PATH = _default_db_path()

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ground_truth_facts (
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (subject, predicate)
);
"""

# Same real facts HallucinationDetector's own known_errors dict already
# encodes (algo_33_fghf.py:257-260), plus 2 more real, easily-verifiable
# facts — small and honestly scoped.
_SEED_FACTS = [
    ("eiffel tower", "construction_completed_year", "1889"),
    ("french revolution", "start_year", "1789"),
    ("einstein", "birth_year", "1879"),
    ("moon landing", "year", "1969"),
    ("world war ii", "end_year", "1945"),
]


class GroundTruthStore:
    """Real, persisted, queryable ground-truth fact table."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH, seed: bool = True, reuse_connection: bool = False) -> None:
        self.db_path = db_path
        self.reuse_connection = reuse_connection
        self._cached_conn: Optional[sqlite3.Connection] = None
        self._conn_lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
        if seed:
            for subject, predicate, value in _SEED_FACTS:
                self.add_fact(subject, predicate, value)

    def _connect(self):
        """Round 28 Phase 27 Task 54: same additive, OFF-by-default reuse
        pattern as persistence.py's ControlPlanePersistence._connect() -
        see that method's docstring for the full rationale."""
        if not self.reuse_connection:
            return sqlite3.connect(self.db_path)
        if self._cached_conn is None:
            self._cached_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return _ReusableConnectionContext(self._cached_conn, self._conn_lock)

    def add_fact(self, subject: str, predicate: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ground_truth_facts (subject, predicate, value) VALUES (?, ?, ?)",
                (subject.lower(), predicate.lower(), value),
            )

    def check_claim(self, subject: str, predicate: str, claimed_value: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM ground_truth_facts WHERE subject = ? AND predicate = ?",
                (subject.lower(), predicate.lower()),
            ).fetchone()

        if row is None:
            return {
                "subject": subject, "predicate": predicate, "claimed_value": claimed_value,
                "known_value": None, "matches": None,
                "reason": "no ground truth on file for this subject/predicate",
            }

        known_value = row[0]
        return {
            "subject": subject, "predicate": predicate, "claimed_value": claimed_value,
            "known_value": known_value, "matches": (str(claimed_value) == str(known_value)),
        }
