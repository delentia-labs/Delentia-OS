"""
Originals of compressed tool output (Round 48, COMPRESS step).

When GovernedAutonomousLoop compresses a large tool result with Delta v2, the
full text is kept here so the agent can read any part of it again through
the `delentia_expand_tool_output` MCP tool ("compress, but recoverable" -
Round 46 measured that expanding on a miss recovers answers compression
alone loses). Ids are random 16-hex strings; originals live in the same
persistence DB as the audit trail, which already records every tool result.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_output_originals (
    id          TEXT PRIMARY KEY,
    namespace   TEXT NOT NULL,
    tool_name   TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

MAX_EXPAND_CHARS = 8000


class ToolOutputStore:
    def __init__(self, persistence: Any):
        self._persistence = persistence
        with self._persistence._connect() as conn:
            conn.executescript(_SCHEMA)

    def save(self, namespace: str, tool_name: str, content: str) -> str:
        original_id = uuid.uuid4().hex[:16]
        with self._persistence._connect() as conn:
            conn.execute(
                "INSERT INTO tool_output_originals (id, namespace, tool_name, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (original_id, namespace, tool_name, content, datetime.now(timezone.utc).isoformat()),
            )
        return original_id

    def get(self, original_id: str) -> Optional[str]:
        with self._persistence._connect() as conn:
            row = conn.execute("SELECT content FROM tool_output_originals WHERE id = ?", (original_id,)).fetchone()
        return row[0] if row else None

    def expand(self, original_id: str, start_line: Optional[int] = None, end_line: Optional[int] = None,
               query: Optional[str] = None, max_chars: int = MAX_EXPAND_CHARS) -> Dict[str, Any]:
        """A 1-based line range, or the lines matching `query` (case-insensitive,
        every word must appear) with one line of context, capped at max_chars."""
        content = self.get(original_id)
        if content is None:
            return {"error": f"no stored tool output {original_id!r}"}
        lines = content.split("\n")
        total = len(lines)
        picked: List[str] = []
        if query:
            words = [w for w in re.split(r"\s+", query.lower()) if w]
            keep = [False] * total
            for i, line in enumerate(lines):
                lower = line.lower()
                if words and all(w in lower for w in words):
                    for j in range(max(0, i - 1), min(total - 1, i + 1) + 1):
                        keep[j] = True
            last = -2
            for i, line in enumerate(lines):
                if keep[i]:
                    if i != last + 1 and picked:
                        picked.append("…")
                    picked.append(f"L{i + 1}: {line}")
                    last = i
            mode = "query"
        else:
            start = max(1, start_line or 1)
            end = min(total, end_line or total)
            picked = [f"L{i}: {lines[i - 1]}" for i in range(start, end + 1)]
            mode = "range"
        text = "\n".join(picked)
        truncated = len(text) > max_chars
        return {"original_id": original_id, "mode": mode, "total_lines": total,
                "content": text[:max_chars], "truncated": truncated,
                "matched": bool(picked)}
