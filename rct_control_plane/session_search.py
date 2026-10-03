"""
Round 57: "what did we decide about the backup job last week?" - search over the agent's own past episodes (Hermes: FTS5 session search).

Until now a finished episode left a row of numbers in the audit trail and nothing that could be searched: the goal was in a hash-chained row for episode
START, the answer was shown to the person and then gone. This keeps, per person, the goal and the final answer of every episode (never tool results, which can
carry third-party text and large data) in an SQLite FTS5 index and answers keyword queries over it:

  * the trigram tokenizer, so Thai (which has no spaces between words) and mixed Thai/English text are searchable by any fragment of three or more characters;
    a shorter query falls back to a plain substring match; a machine whose SQLite has no FTS5 falls back to substring matching for everything;
  * strictly per person: a search only ever sees the caller's own namespace (the loop pins it for the agent's tool, so a gateway sender cannot read the
    owner's history and the owner's history does not leak into a stranger's answers);
  * what comes back to the model is treated like any other stored text: the tool is on the list of tools whose results are screened for injected instructions;
  * text is stored as written (the same data the memory store already keeps), capped at 4,000 characters per answer; nothing is ever deleted by the runtime.
"""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

MAX_ANSWER_CHARS = 4_000
MAX_GOAL_CHARS = 2_000
MAX_RESULTS = 25

SCHEMA = """
CREATE TABLE IF NOT EXISTS episode_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace      TEXT NOT NULL,
    episode_id     TEXT,
    goal           TEXT NOT NULL,
    answer         TEXT,
    stopped_reason TEXT,
    tools          TEXT,
    created_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episode_log_ns ON episode_log(namespace, id);
"""
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS episode_log_fts USING fts5(goal, answer, content='episode_log', content_rowid='id', tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS episode_log_ai AFTER INSERT ON episode_log BEGIN
    INSERT INTO episode_log_fts(rowid, goal, answer) VALUES (new.id, new.goal, COALESCE(new.answer, ''));
END;
"""


class SessionLog:
    def __init__(self, persistence: Any):
        self._p = persistence
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)
            try:
                conn.executescript(FTS)
                self.fts = True
            except sqlite3.OperationalError:               # this SQLite was built without FTS5 or the trigram tokenizer
                self.fts = False

    def record(self, namespace: str, goal: str, answer: Optional[str], stopped_reason: str = "", episode_id: str = "", tools: Optional[List[str]] = None,
               now: Optional[float] = None) -> int:
        with self._p._connect() as conn:
            cur = conn.execute("INSERT INTO episode_log (namespace, episode_id, goal, answer, stopped_reason, tools, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (namespace, episode_id, (goal or "")[:MAX_GOAL_CHARS], (answer or "")[:MAX_ANSWER_CHARS] or None, stopped_reason,
                                ",".join(dict.fromkeys(tools or []))[:500], time.time() if now is None else now))
            return int(cur.lastrowid or 0)

    def search(self, namespace: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Newest-relevant first, only this person's episodes. An empty query lists the most recent ones."""
        limit = max(1, min(int(limit), MAX_RESULTS))
        query = " ".join(str(query or "").split())[:200]
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            if not query:
                rows = conn.execute("SELECT *, NULL AS snippet FROM episode_log WHERE namespace = ? ORDER BY id DESC LIMIT ?", (namespace, limit)).fetchall()
            elif self.fts and len(query) >= 3:
                phrase = '"' + query.replace('"', '""') + '"'
                try:
                    rows = conn.execute(
                        "SELECT e.*, snippet(episode_log_fts, -1, '[', ']', '…', 12) AS snippet FROM episode_log_fts JOIN episode_log e ON e.id = episode_log_fts.rowid "
                        "WHERE episode_log_fts MATCH ? AND e.namespace = ? ORDER BY e.id DESC LIMIT ?", (phrase, namespace, limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                like = "%" + re.sub(r"([%_\\])", r"\\\1", query) + "%"
                rows = conn.execute("SELECT *, NULL AS snippet FROM episode_log WHERE namespace = ? AND (goal LIKE ? ESCAPE '\\' OR COALESCE(answer, '') LIKE ? ESCAPE '\\') "
                                    "ORDER BY id DESC LIMIT ?", (namespace, like, like, limit)).fetchall()
        return [{"id": r["id"], "at": r["created_at"], "goal": r["goal"], "answer": (r["answer"] or "")[:600], "stopped_reason": r["stopped_reason"],
                 "tools": [t for t in (r["tools"] or "").split(",") if t], "match": r["snippet"]} for r in rows]

    def count(self, namespace: Optional[str] = None) -> int:
        with self._p._connect() as conn:
            if namespace is None:
                return int(conn.execute("SELECT COUNT(*) FROM episode_log").fetchone()[0])
            return int(conn.execute("SELECT COUNT(*) FROM episode_log WHERE namespace = ?", (namespace,)).fetchone()[0])
