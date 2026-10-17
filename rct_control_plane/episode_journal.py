"""
Round 84: a durable journal of every governed episode, so an episode that is cut off (the process killed, the machine restarted) can be continued instead of started again.

Before this, only ONE thing survived a crash: the approval of a single action (`approvals.py`). The steps an episode had already taken lived in memory; a restart began the goal from nothing and, worse,
could run a side effect a second time (DAAES TC-010 beyond the approval). The journal is the missing half:

  begin   the goal, who asked, the process that is running it (pid and its start time)
  intent  WRITTEN BEFORE a tool is dispatched (after the gate allowed it): tool and arguments
  result  written after: a digest of what came back and a short preview
  end     how the episode stopped

Reading it after a crash tells exactly where it stopped. A tool with an `intent` and no `result` is one whose effect is UNKNOWN: if it can only read, running it again is safe; if it can change
something (the same side-effect classes the gate uses), nothing is run again on its own, a person decides. Resuming does not replay results into a model's history: it starts a NEW governed episode (the
gate, the policy, the budget and the audit all apply as usual) that is told, in a note, which steps already ran and with what outcome, and an episode that had read outside text starts tainted.

What is stored is personal (goals, arguments, results), so the payload is sealed under the person's key like the audit chain's text (`audit_text`), and `erase_person` scrubs the table. Each row's hash covers the
row before it in its episode, so a journal that was edited is refused. A journal is working state, not evidence: it does not replace the audit chain.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rct_control_plane import audit_text

ENV = "DELENTIA_EPISODE_JOURNAL"
PREVIEW_CHARS = 400
SEALED_FIELDS = ("goal", "args", "preview", "final_answer")
STALE_AFTER_SECONDS = 900.0


def enabled() -> bool:
    return (os.environ.get(ENV) or "on").strip().lower() not in ("off", "0", "false", "no")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _proc_start(pid: int) -> Optional[float]:
    try:
        import psutil
        return float(psutil.Process(pid).create_time())
    except Exception:                                                  # noqa: BLE001
        return None


def _alive(pid: Optional[int], started: Optional[float]) -> bool:
    if not pid:
        return False
    now = _proc_start(int(pid))
    if now is None:
        return False
    return started is None or abs(now - float(started)) < 2.0


@dataclass
class JournalStep:
    n: int
    tool: str
    args: Any
    state: str                      # done | dangling
    preview: str = ""
    result_sha256: str = ""
    taint: Optional[str] = None


@dataclass
class JournalEpisode:
    episode_id: str
    namespace: str
    goal: str
    steps: List[JournalStep] = field(default_factory=list)
    ended: bool = False
    stopped_reason: Optional[str] = None
    resumed_by: Optional[str] = None
    chain_ok: bool = True
    taint: Optional[str] = None
    pid: Optional[int] = None
    proc_started: Optional[float] = None
    started_at: float = 0.0
    last_at: float = 0.0
    resumed_from: Optional[str] = None


class EpisodeJournal:
    def __init__(self, persistence: Any) -> None:
        self._p = persistence
        self._ensure()

    def _ensure(self) -> None:
        with self._p._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episode_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, episode_id TEXT NOT NULL, namespace TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL, pid INTEGER, proc_started REAL, created_at REAL NOT NULL,
                    UNIQUE (episode_id, seq));
                CREATE INDEX IF NOT EXISTS idx_episode_journal_ns ON episode_journal (namespace, kind);
                """)

    # ------------------------------------------------------------------------------------------------------------------ writing
    def _append(self, episode_id: str, namespace: str, kind: str, payload: Dict[str, Any]) -> int:
        sealed = audit_text.protect(namespace, payload, SEALED_FIELDS)
        body = json.dumps(sealed, sort_keys=True, ensure_ascii=False, default=str)
        pid = os.getpid()
        with self._p._connect() as conn:
            row = conn.execute("SELECT seq, row_hash FROM episode_journal WHERE episode_id = ? ORDER BY seq DESC LIMIT 1", (episode_id,)).fetchone()
            seq, prev = (int(row[0]) + 1, str(row[1])) if row else (1, "genesis")
            h = hashlib.sha256(f"{prev}|{seq}|{kind}|{body}".encode("utf-8")).hexdigest()
            conn.execute("INSERT INTO episode_journal (episode_id, namespace, seq, kind, payload, prev_hash, row_hash, pid, proc_started, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (episode_id, namespace, seq, kind, body, prev, h, pid, _proc_start(pid), time.time()))
        return seq

    def begin(self, episode_id: str, namespace: str, goal: str, resumed_from: Optional[str] = None) -> None:
        self._append(episode_id, namespace, "begin", {"goal": goal, "resumed_from": resumed_from})

    def intent(self, episode_id: str, namespace: str, step: int, tool: str, args: Any, taint: Optional[str] = None) -> None:
        self._append(episode_id, namespace, "intent", {"step": step, "tool": tool, "args": args, "taint": taint})

    def result(self, episode_id: str, namespace: str, step: int, tool: str, result: Any, taint: Optional[str] = None) -> None:
        text = json.dumps(result, ensure_ascii=False, default=str)
        self._append(episode_id, namespace, "result", {"step": step, "tool": tool, "result_sha256": _digest(result), "preview": text[:PREVIEW_CHARS], "taint": taint})

    def end(self, episode_id: str, namespace: str, stopped_reason: str, final_answer: Optional[str]) -> None:
        self._append(episode_id, namespace, "end", {"stopped_reason": stopped_reason, "final_answer": (final_answer or "")[:600]})

    def claim_resume(self, episode_id: str, namespace: str, by: str) -> bool:
        """Exactly one resume per interrupted episode: the row is written under the UNIQUE (episode_id, seq) key, so two claimers cannot both succeed."""
        ep = self.load(episode_id)
        if ep is None or ep.resumed_by or ep.ended:
            return False
        try:
            self._append(episode_id, namespace, "resumed", {"by": by})
        except Exception:                                              # noqa: BLE001 - a second claimer hits the UNIQUE key
            return False
        return self.load(episode_id).resumed_by == by                  # type: ignore[union-attr]

    # ------------------------------------------------------------------------------------------------------------------ reading
    def load(self, episode_id: str) -> Optional[JournalEpisode]:
        with self._p._connect() as conn:
            rows = conn.execute("SELECT seq, kind, payload, prev_hash, row_hash, pid, proc_started, created_at, namespace FROM episode_journal WHERE episode_id = ? ORDER BY seq", (episode_id,)).fetchall()
        if not rows:
            return None
        ep = JournalEpisode(episode_id=episode_id, namespace=str(rows[0][8]), goal="")
        prev = "genesis"
        steps: Dict[int, JournalStep] = {}
        for seq, kind, payload, prev_hash, row_hash, pid, started, created, namespace in rows:
            expect = hashlib.sha256(f"{prev}|{seq}|{kind}|{payload}".encode("utf-8")).hexdigest()
            if prev_hash != prev or row_hash != expect or namespace != ep.namespace:
                ep.chain_ok = False
            prev = row_hash
            try:
                data = json.loads(payload)
            except ValueError:
                ep.chain_ok = False
                continue
            ep.last_at = float(created)
            if kind == "begin":
                ep.goal = str(audit_text.reveal(ep.namespace, data.get("goal")) or "")
                ep.pid, ep.proc_started, ep.started_at = pid, started, float(created)
                ep.resumed_from = data.get("resumed_from")
            elif kind == "intent":
                n = int(data.get("step", len(steps) + 1))
                steps[n] = JournalStep(n=n, tool=str(data.get("tool")), args=audit_text.reveal(ep.namespace, data.get("args")), state="dangling", taint=data.get("taint"))
                ep.taint = data.get("taint") or ep.taint
            elif kind == "result":
                n = int(data.get("step", len(steps)))
                step = steps.get(n) or JournalStep(n=n, tool=str(data.get("tool")), args=None, state="done")
                step.state, step.result_sha256, step.preview, step.taint = "done", str(data.get("result_sha256") or ""), str(audit_text.reveal(ep.namespace, data.get("preview")) or ""), data.get("taint")
                steps[n] = step
                ep.taint = data.get("taint") or ep.taint
            elif kind == "end":
                ep.ended, ep.stopped_reason = True, str(data.get("stopped_reason"))
            elif kind == "resumed":
                ep.resumed_by = str(data.get("by"))
        ep.steps = [steps[k] for k in sorted(steps)]
        return ep

    def interrupted(self, namespace: Optional[str] = None, stale_after: float = STALE_AFTER_SECONDS) -> List[JournalEpisode]:
        """Episodes that began, never ended, and whose process is gone (or that have been silent longer than `stale_after`). Newest first."""
        with self._p._connect() as conn:
            q = ("SELECT DISTINCT episode_id FROM episode_journal WHERE kind = 'begin'" + (" AND namespace = ?" if namespace else "")
                 + " AND episode_id NOT IN (SELECT episode_id FROM episode_journal WHERE kind IN ('end', 'resumed')) ORDER BY id DESC LIMIT 200")
            ids = [r[0] for r in conn.execute(q, (namespace,) if namespace else ())]
        out = []
        now = time.time()
        for eid in ids:
            ep = self.load(eid)
            if ep is None or ep.ended or ep.resumed_by:
                continue
            if _alive(ep.pid, ep.proc_started) and now - ep.last_at < stale_after:
                continue                                                # still running, not interrupted
            out.append(ep)
        return out


def note_for(ep: JournalEpisode, side_effect_tools: frozenset, unknown_ok: bool) -> str:
    """The text a resumed episode is told: what already ran, in order, and what is uncertain. Facts only; it grants no permission."""
    lines = ["This request continues an episode that was interrupted (the process stopped before it finished). Facts from its journal, in order:"]
    for s in ep.steps:
        if s.state == "done":
            lines.append(f"  step {s.n}: {s.tool} {json.dumps(s.args, ensure_ascii=False, default=str)[:200]} -> done; result began: {s.preview[:200]}")
        else:
            kind = "can change something" if s.tool in side_effect_tools else "only reads"
            lines.append(f"  step {s.n}: {s.tool} {json.dumps(s.args, ensure_ascii=False, default=str)[:200]} -> OUTCOME UNKNOWN (it was about to run or was running when the process stopped; this tool {kind})")
    if any(s.state == "dangling" and s.tool in side_effect_tools for s in ep.steps):
        lines.append("A step whose outcome is unknown may or may not have taken effect. Check with a read-only tool first. Do not repeat it blindly." + (" A person has said to go on." if unknown_ok else ""))
    lines.append("Do not repeat the steps that are done. Continue toward the goal from here.")
    return "\n".join(lines)
