"""
Round 61: the memory nudge - "you told me something about yourself; should I keep it?" - without a model and without a back door.

A weak model forgets to call `delentia_remember`, so what a person said about themselves ("my favourite colour is green", "I live in Chiang Mai", "ฉันชอบกาแฟ") is lost between conversations. Hermes
nudges the agent to save. Here the RUNTIME notices, deterministically, and ASKS THE PERSON:

  * a candidate comes from the PERSON'S OWN message only - never from a tool result, a page, a file or a webhook payload (an episode that read outside text, or that started from an outside
    payload, proposes nothing: a memory is an instruction that survives restarts, which is exactly what an injection wants to plant);
  * nothing is stored until the person says yes (`/remember <id>`, `delentia memory accept <id>`, the Desk); `/skip <id>` or `delentia memory dismiss <id>` throws it away; unanswered
    candidates expire after 14 days;
  * text that looks like a secret (a password, a key, a token, a card or ID number) is never even proposed;
  * accepted memories carry provenance {"tainted": false, "via": "memory_nudge"}, the same record every other memory has, and the acceptance is in the audit trail;
  * a candidate belongs to one namespace and only that namespace can accept or dismiss it.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

ENV = "DELENTIA_MEMORY_NUDGE"
EXPIRES_AFTER_S = 14 * 24 * 3600
MAX_PER_EPISODE = 2
MAX_PENDING_PER_USER = 20
MAX_CHARS = 220

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_candidates (
    id          TEXT PRIMARY KEY,
    namespace   TEXT NOT NULL,
    text        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    goal_sha256 TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    decided_at  REAL,
    memory_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_candidates_ns ON memory_candidates(namespace, status);
"""

_PATTERNS = [
    ("fact", re.compile(r"\bmy\s+(?:name|nickname|birthday|email|timezone|time zone|job|role|company|team|manager|boss|dog|cat|wife|husband|partner|son|daughter|kids?|city|country|language)\s+(?:is|are|was)\s+[^.!?\n]{2,}", re.I)),
    ("preference", re.compile(r"\bmy\s+favou?rite\s+[a-z ]{2,20}\s+(?:is|are)\s+[^.!?\n]{2,}", re.I)),
    ("fact", re.compile(r"\bcall me\s+[^.!?\n]{2,}", re.I)),
    ("fact", re.compile(r"\bi\s+(?:live|work|study|was born|grew up)\s+(?:in|at|for|as|on)\s+[^.!?\n]{2,}", re.I)),
    ("fact", re.compile(r"\bi(?:\s+am|'m)\s+(?:a|an|the)\s+[^.!?\n]{3,}", re.I)),
    ("preference", re.compile(r"\bi\s+(?:prefer|like|love|enjoy|hate|dislike|always|never|usually)\s+[^.!?\n]{2,}", re.I)),
    ("fact", re.compile(r"\bremember(?:\s+that)?\s+[^.!?\n]{3,}", re.I)),
    ("fact", re.compile(r"(?:ฉัน|ผม|หนู|เรา)ชื่อ\s*\S+")),
    ("fact", re.compile(r"ชื่อ(?:ของ)?(?:ฉัน|ผม|หนู)\s*(?:คือ)?\s*\S+")),
    ("preference", re.compile(r"(?:ฉัน|ผม|หนู)(?:ชอบ|ไม่ชอบ|รัก|เกลียด|นิยม)\s*[^\n.!?]{2,}")),
    ("fact", re.compile(r"(?:ฉัน|ผม|หนู)(?:อาศัยอยู่|อยู่ที่|ทำงานที่|ทำงานเป็น|เรียนที่)\s*[^\n.!?]{2,}")),
    ("fact", re.compile(r"จำไว้ว่า\s*[^\n]{3,}")),
]
_SECRET = re.compile(r"\b(?:pass(?:word|code)?|pwd|api[ _-]?key|secret|token|private key|ssn|credit card|card number|cvv|pin)\b|\d{9,}|sk-[A-Za-z0-9]{10,}|-----BEGIN|พาสเวิร์ด|รหัสผ่าน|รหัสบัตร", re.I)
_QUESTION_END = re.compile(r"[?？]\s*$")


def enabled() -> bool:
    return (os.environ.get(ENV) or "").strip().lower() in ("1", "on", "true", "yes")


def extract(goal: str) -> List[Dict[str, str]]:
    """Statements in the person's own message that look like something worth keeping. Deterministic; at most MAX_PER_EPISODE."""
    out: List[Dict[str, str]] = []
    seen: set = set()
    for sentence in re.split(r"(?<=[.!?。])\s+|\n+", str(goal or "")):
        sentence = " ".join(sentence.split())
        if not sentence or len(sentence) > 400 or _QUESTION_END.search(sentence) or _SECRET.search(sentence):
            continue
        for kind, pattern in _PATTERNS:
            if pattern.search(sentence):
                text = sentence[:MAX_CHARS]
                key = text.lower()
                if key not in seen:
                    seen.add(key)
                    out.append({"text": text, "kind": kind})
                break
        if len(out) >= MAX_PER_EPISODE:
            break
    return out


class MemoryCandidates:
    def __init__(self, persistence: Any):
        self._p = persistence
        with self._p._connect() as conn:
            conn.executescript(_SCHEMA)

    def _audit(self, action: str, candidate_id: str, namespace: str, extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._p.append_audit(entity_type="memory_candidate", entity_id=candidate_id, action=action, actor=namespace, changes=extra or {})
        except Exception:                                              # noqa: BLE001
            pass

    def _expire(self) -> None:
        with self._p._connect() as conn:
            conn.execute("UPDATE memory_candidates SET status = 'expired', decided_at = ? WHERE status = 'pending' AND created_at < ?", (time.time(), time.time() - EXPIRES_AFTER_S))

    def propose_from_goal(self, namespace: str, goal: str, *, tainted: bool = False, from_outside: bool = False) -> List[Dict[str, Any]]:
        """Candidates for what the person wrote. Nothing when the episode read outside text or started from an outside payload."""
        if tainted or from_outside or not enabled():
            return []
        self._expire()
        made: List[Dict[str, Any]] = []
        with self._p._connect() as conn:
            pending = conn.execute("SELECT COUNT(*) FROM memory_candidates WHERE namespace = ? AND status = 'pending'", (namespace,)).fetchone()[0]
            known = {r[0].lower() for r in conn.execute("SELECT text FROM memory_candidates WHERE namespace = ? AND status IN ('pending', 'accepted')", (namespace,)).fetchall()}
            known |= {r[0].lower() for r in conn.execute("SELECT content FROM memories WHERE namespace = ?", (namespace,)).fetchall()}
            for item in extract(goal):
                if pending + len(made) >= MAX_PENDING_PER_USER or item["text"].lower() in known:
                    continue
                cid = "mc-" + uuid.uuid4().hex[:8]
                conn.execute("INSERT INTO memory_candidates (id, namespace, text, kind, goal_sha256, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                             (cid, namespace, item["text"], item["kind"], hashlib.sha256(goal.encode("utf-8")).hexdigest(), time.time()))
                made.append({"id": cid, "text": item["text"], "kind": item["kind"]})
        for item in made:
            self._audit("proposed", item["id"], namespace, {"kind": item["kind"], "chars": len(item["text"])})
        return made

    def list(self, namespace: Optional[str] = None, status: str = "pending", limit: int = 50) -> List[Dict[str, Any]]:
        self._expire()
        sql, args = "SELECT * FROM memory_candidates WHERE status = ?", [status]
        if namespace is not None:
            sql += " AND namespace = ?"
            args.append(namespace)
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC LIMIT ?", (*args, max(1, min(limit, 200)))).fetchall()]

    def _get(self, candidate_id: str, namespace: Optional[str]) -> Optional[Dict[str, Any]]:
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM memory_candidates WHERE id = ?", (candidate_id,)).fetchone()
        if row is None or (namespace is not None and row["namespace"] != namespace):
            return None
        return dict(row)

    def accept(self, candidate_id: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """The person said yes: store it as a memory of their own (provenance: not tainted, via the nudge) and mark the candidate accepted."""
        self._expire()
        row = self._get(candidate_id, namespace)
        if row is None:
            raise ValueError("no such suggestion")
        if row["status"] != "pending":
            raise ValueError(f"that suggestion is already {row['status']}")
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        self._p.save_memory(memory_id=memory_id, namespace=row["namespace"], memory_type=row["kind"], content=row["text"],
                            context={"provenance": {"tainted": False, "source_tool": "", "via": "memory_nudge"}}, importance=0.7)
        with self._p._connect() as conn:
            conn.execute("UPDATE memory_candidates SET status = 'accepted', decided_at = ?, memory_id = ? WHERE id = ?", (time.time(), memory_id, candidate_id))
        self._audit("accepted", candidate_id, row["namespace"], {"memory_id": memory_id})
        return {"id": candidate_id, "memory_id": memory_id, "text": row["text"]}

    def dismiss(self, candidate_id: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        row = self._get(candidate_id, namespace)
        if row is None:
            raise ValueError("no such suggestion")
        if row["status"] != "pending":
            raise ValueError(f"that suggestion is already {row['status']}")
        with self._p._connect() as conn:
            conn.execute("UPDATE memory_candidates SET status = 'dismissed', decided_at = ? WHERE id = ?", (time.time(), candidate_id))
        self._audit("dismissed", candidate_id, row["namespace"])
        return {"id": candidate_id, "dismissed": True}


def nudge_text(candidates: List[Dict[str, Any]]) -> str:
    """The line a chat gateway adds under the answer."""
    if not candidates:
        return ""
    lines = ["", "I can remember this for you:"]
    for c in candidates:
        lines.append(f"  “{c['text']}”  →  /remember {c['id']}   (or /skip {c['id']})")
    return "\n".join(lines)
