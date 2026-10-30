"""
Round 106: the Delta Engine's durable log joins the main path. Criteria written first: research/DELTA_STATE_LOG_CRITERIA_R106.md.

What was wrong. The governed loop's RECORD step has always built a `DeltaBlock` for every episode and handed it to `self._delta_engine.store_delta(...)`; that engine is a fresh in-memory
`DeltaEngine()` made with the loop, so the record was gone when the process ended, while the durable, verified log of Round 83-84 (`delta_log.VersionedDeltaLog`) was called by nothing.

What this does. One `VersionedDeltaLog` per person (file named by a hash of the namespace), one version per governed episode. The state is the person's agent state as NUMBERS AND HASHES: how
many episodes, how many verified, why they stopped (counts), tool calls, spend, the growth score, the memory log's head, the number of learned skills, and the audit row of the episode. No goal,
no answer, no tool argument and no memory text is ever put in it, so there is nothing personal here to erase (a test scans the raw bytes for the words of the episodes it recorded).

Every `DELENTIA_STATE_LOG_ANCHOR_EVERY` versions (25) the head is written into the audit chain, so cutting off the newest versions or rewriting the history is detected even by someone who can
recompute this file's own hashes. A failure here never changes an episode's outcome: it is reported as `result["state_log"] = {"error": ...}`.

It is not a claim that memory is smaller or recall better (the memory event log carries the memory text, sealed per person; Round 65 measured snapshot + zstd as small as deltas). It makes
the person's agent history exact to rebuild at any episode and its damage or truncation detectable, which a counter in a table does not.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane.algo_25_delta_block import DeltaConflictError
from rct_control_plane.delta_log import VersionedDeltaLog

ENV = "DELENTIA_STATE_LOG"
ANCHOR_ENV = "DELENTIA_STATE_LOG_ANCHOR_EVERY"
DEFAULT_ANCHOR_EVERY = 25
SNAPSHOT_EVERY = 50

_LOGS: Dict[str, "AgentStateLog"] = {}
_REGISTRY_LOCK = threading.Lock()


def enabled() -> bool:
    return (os.environ.get(ENV) or "on").strip().lower() not in ("off", "0", "false", "no")


def anchor_every() -> int:
    try:
        return max(0, int(os.environ.get(ANCHOR_ENV, DEFAULT_ANCHOR_EVERY)))
    except ValueError:
        return DEFAULT_ANCHOR_EVERY


def name_for(namespace: str) -> str:
    """A name that identifies the person's log without saying who the person is."""
    return hashlib.sha256(("delentia-state-log:" + namespace).encode("utf-8")).hexdigest()[:24]


def base_dir_for(persistence: Any) -> Optional[Path]:
    db = str(getattr(persistence, "db_path", "") or "")
    if not db or db == ":memory:" or db.startswith("file::memory"):
        return None
    return Path(db).resolve().parent / "state_logs"


def initial_state() -> Dict[str, Any]:
    return {"episodes": 0, "verified_episodes": 0, "stopped": {}, "tool_calls": 0, "cost_usd": 0.0, "growth_G": None,
            "memory": {"events": 0, "head_hash": ""}, "skills": 0, "audit": {"seq": 0, "row_hash": ""}, "last": {}}


def next_state(current: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    """The state after one more episode. `summary` holds numbers and hashes only (see summarise())."""
    state = deepcopy(current)
    state["episodes"] = int(state.get("episodes", 0)) + 1
    if summary.get("verified"):
        state["verified_episodes"] = int(state.get("verified_episodes", 0)) + 1
    reason = str(summary.get("stopped_reason") or "unknown")
    stopped = dict(state.get("stopped") or {})
    stopped[reason] = int(stopped.get(reason, 0)) + 1
    state["stopped"] = stopped
    state["tool_calls"] = int(state.get("tool_calls", 0)) + int(summary.get("tool_calls") or 0)
    state["cost_usd"] = round(float(state.get("cost_usd") or 0.0) + float(summary.get("cost_usd") or 0.0), 6)
    if summary.get("growth_G") is not None:
        state["growth_G"] = round(float(summary["growth_G"]), 4)
    for key in ("memory", "audit"):
        if summary.get(key):
            state[key] = dict(summary[key])
    if summary.get("skills") is not None:
        state["skills"] = int(summary["skills"])
    state["last"] = {"episode_id": str(summary.get("episode_id") or ""), "stopped_reason": reason, "iterations": int(summary.get("iterations") or 0),
                     "verified": bool(summary.get("verified")), "at": round(float(summary.get("at") or time.time()), 3)}
    return state


class AgentStateLog:
    def __init__(self, path: Path, name: str) -> None:
        self.path, self.name = Path(path), name
        self.log = VersionedDeltaLog(str(path), initial_state=initial_state(), snapshot_every=SNAPSHOT_EVERY)
        self._lock = threading.RLock()

    @classmethod
    def for_namespace(cls, namespace: str, persistence: Any) -> Optional["AgentStateLog"]:
        base = base_dir_for(persistence)
        if base is None:
            return None
        name = name_for(namespace)
        path = base / f"{name}.db"
        key = str(path)
        with _REGISTRY_LOCK:
            found = _LOGS.get(key)
            if found is None:
                found = _LOGS[key] = cls(path, name)
            return found

    def record_episode(self, summary: Dict[str, Any], persistence: Any = None) -> int:
        """Append one version. Two episodes of the same person finishing together are serialised here and, across processes, by the log's own transaction (base_version)."""
        with self._lock:
            for _attempt in range(6):
                head = self.log.head()
                new = next_state(self.log.head_state(), summary)
                try:
                    version = self.log.commit(new, base_version=head, source="episode", at=summary.get("at"))
                    break
                except DeltaConflictError:          # another process wrote between the read and the commit: read again
                    continue
            else:
                raise RuntimeError("the state log kept changing under this writer (6 attempts)")
            every = anchor_every()
            if persistence is not None and every and version % every == 0:
                self.log.anchor_to_audit(persistence, self.name)
            return version

    def show(self) -> Dict[str, Any]:
        head = self.log.head()
        return {"name": self.name, "version": head, "state": self.log.state_at(head), "sizes": self.log.sizes()}

    def at(self, version: int) -> Dict[str, Any]:
        return self.log.state_at(version)

    def verify(self, persistence: Any = None) -> Dict[str, Any]:
        return self.log.verify_against_audit(persistence, self.name) if persistence is not None else self.log.verify()

    def close(self) -> None:
        self.log.close()


def summarise(loop: Any, result: Dict[str, Any], stopped_reason: str, verified: bool) -> Dict[str, Any]:
    """Numbers and hashes only. Each part is best effort: a part that cannot be read is left out, not guessed."""
    steps = result.get("steps") or []
    summary: Dict[str, Any] = {
        "episode_id": str(getattr(loop, "_episode_id", "") or ""), "stopped_reason": stopped_reason, "iterations": int(result.get("iterations") or 0),
        "verified": bool(verified), "tool_calls": sum(1 for s in steps if isinstance(s, dict) and s.get("tool_name")),
        "cost_usd": float(((result.get("cost") or {}).get("cost_usd")) or 0.0), "at": time.time()}
    growth = result.get("growth") or {}
    if growth.get("G") is not None:
        summary["growth_G"] = growth["G"]
    persistence = getattr(loop, "_persistence", None)
    try:
        from rct_control_plane import audit_chain, memory_eventlog
        with persistence._connect() as conn:
            head = audit_chain.chain_head(conn)
            if head:
                summary["audit"] = {"seq": int(head["seq"]), "row_hash": str(head["row_hash"])}
        mem_head = memory_eventlog.MemoryEventLog(persistence).head()
        summary["memory"] = {"events": int(mem_head["seq"]), "head_hash": str(mem_head["hash"])}
    except Exception:                                   # noqa: BLE001 - a part that cannot be read is left out
        pass
    try:
        summary["skills"] = int(loop._skill_library.count())
    except Exception:                                   # noqa: BLE001
        pass
    return summary


def record_for_loop(loop: Any, result: Dict[str, Any], stopped_reason: str, verified: bool) -> Dict[str, Any]:
    """The call the loop makes at the end of an episode. Never raises."""
    if not enabled():
        return {"enabled": False}
    try:
        persistence = getattr(loop, "_persistence", None)
        log = AgentStateLog.for_namespace(loop.namespace, persistence)
        if log is None:
            return {"enabled": True, "skipped": "no file database, so there is nowhere durable to write"}
        return {"enabled": True, "version": log.record_episode(summarise(loop, result, stopped_reason, verified), persistence)}
    except Exception as exc:                            # noqa: BLE001 - the log must never change an episode's outcome
        return {"enabled": True, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def list_logs(persistence: Any) -> List[Dict[str, Any]]:
    base = base_dir_for(persistence)
    if base is None or not base.exists():
        return []
    out = []
    for p in sorted(base.glob("*.db")):
        try:
            log = VersionedDeltaLog(str(p), initial_state=None)
            out.append({"name": p.stem, "versions": log.head(), "bytes": p.stat().st_size})
            log.close()
        except Exception as exc:                        # noqa: BLE001
            out.append({"name": p.stem, "error": f"{type(exc).__name__}"})
    return out


def close_all() -> None:
    with _REGISTRY_LOCK:
        for log in _LOGS.values():
            try:
                log.close()
            except Exception:                           # noqa: BLE001
                pass
        _LOGS.clear()
