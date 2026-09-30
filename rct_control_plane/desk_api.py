"""
Delentia Desk API (Round 50): the read-mostly endpoints behind the redesigned
Desk GUI (apps/gui). Every value comes from the runtime's own stores - the
audit trail, the skill library, RCTDB experiment runs, the model config, the
MCP tool registry and the daemon - never from placeholders. Where something is
not configured the response says so.

Writes are limited to what the CLI can already do locally: choosing the model
(`delentia model set`) and running a daemon task now. Approvals keep their own
signed endpoints (/v1/agent/approvals); nothing here can approve anything.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from rct_control_plane import data_home

CHANNELS = ("telegram", "discord", "slack", "line")
_TOKEN_ENV = {"telegram": "TELEGRAM_BOT_TOKEN", "discord": "DISCORD_BOT_TOKEN",
              "slack": "SLACK_BOT_TOKEN", "line": "LINE_CHANNEL_ACCESS_TOKEN"}
_EPISODE_EVENT_TYPES = ("autonomous_loop_step", "governed_loop_fdia_gate", "governed_loop_guard",
                        "notary_receipt", "notary_gap")


def _loads(value: Any) -> Any:
    if isinstance(value, (dict, list)) or value is None:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _kernel() -> Any:
    from rct_control_plane.mcp_server import _kernel as shared_kernel
    return shared_kernel


def _skills() -> Any:
    from rct_control_plane.skill_library import SkillLibrary
    return SkillLibrary()


def _connect() -> sqlite3.Connection:
    return _kernel()._persistence._connect()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Episodes (sessions) reconstructed from the audit trail
# ---------------------------------------------------------------------------

def _episode_summary(start: sqlite3.Row, end: Optional[sqlite3.Row]) -> Dict[str, Any]:
    s = _loads(start["changes"]) or {}
    e = _loads(end["changes"]) if end is not None else {}
    route = s.get("route") or {}
    verify = (e or {}).get("intent_verification") or {}
    return {
        "id": start["id"],
        "namespace": start["actor"],
        "goal": s.get("goal"),
        "started_at": start["created_at"],
        "ended_at": end["created_at"] if end is not None else None,
        "D": s.get("D"), "I": s.get("I"), "goal_F": s.get("goal_F"),
        "route": route.get("path"),
        "guard": (s.get("guard") or {}).get("cord_verdict"),
        "jitna_verified": s.get("jitna_verified"),
        "stopped_reason": (e or {}).get("stopped_reason") if end is not None else "running",
        "iterations": (e or {}).get("iterations"),
        "duration_s": (e or {}).get("duration_s"),
        "verified": verify.get("aligned_with_intent") if verify.get("applicable") else None,
        "similarity": verify.get("similarity_score"),
        "approval_id": (e or {}).get("approval_id"),
        "skill_extracted": (e or {}).get("skill_extracted"),
    }


def list_sessions(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    starts = conn.execute(
        "SELECT id, actor, changes, created_at FROM audit_trail WHERE entity_type = 'governed_loop_episode_start' "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for start in starts:
        end = _episode_end(conn, start)
        out.append(_episode_summary(start, end))
    return out


def _next_start_id(conn: sqlite3.Connection, start: sqlite3.Row) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM audit_trail WHERE entity_type = 'governed_loop_episode_start' AND actor = ? AND id > ? "
        "ORDER BY id LIMIT 1", (start["actor"], start["id"])).fetchone()
    return int(row[0]) if row else None


def _episode_end(conn: sqlite3.Connection, start: sqlite3.Row) -> Optional[sqlite3.Row]:
    bound = _next_start_id(conn, start)
    sql = ("SELECT id, changes, created_at FROM audit_trail WHERE entity_type = 'governed_loop_episode_end' "
           "AND actor = ? AND id > ?")
    params: List[Any] = [start["actor"], start["id"]]
    if bound is not None:
        sql += " AND id < ?"
        params.append(bound)
    row: Optional[sqlite3.Row] = conn.execute(sql + " ORDER BY id LIMIT 1", params).fetchone()
    return row


def get_session(conn: sqlite3.Connection, start_id: int) -> Optional[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    start = conn.execute(
        "SELECT id, actor, changes, created_at FROM audit_trail WHERE id = ? "
        "AND entity_type = 'governed_loop_episode_start'", (start_id,)).fetchone()
    if start is None:
        return None
    end = _episode_end(conn, start)
    upper = end["id"] if end is not None else (_next_start_id(conn, start) or 2**62)
    placeholders = ",".join("?" for _ in _EPISODE_EVENT_TYPES)
    rows = conn.execute(
        f"SELECT id, entity_type, action, changes, created_at FROM audit_trail WHERE actor = ? "
        f"AND id > ? AND id <= ? AND entity_type IN ({placeholders}) ORDER BY id",
        (start["actor"], start["id"], upper, *_EPISODE_EVENT_TYPES)).fetchall()
    s = _loads(start["changes"]) or {}
    summary = _episode_summary(start, end)
    summary.update({
        "rct7_steps": s.get("rct7_steps") or [],
        "route_detail": s.get("route") or {},
        "guard_detail": s.get("guard") or {},
        "jitna": {"packet_id": s.get("jitna_packet_id"), "content_hash": s.get("jitna_content_hash"),
                  "public_key": s.get("jitna_public_key"), "key_persistent": s.get("jitna_key_persistent")},
        "verification": ((_loads(end["changes"]) or {}).get("intent_verification") if end is not None else None),
        "events": [{"id": r["id"], "type": r["entity_type"], "action": r["action"],
                    "at": r["created_at"], "data": _loads(r["changes"])} for r in rows],
    })
    return summary


# ---------------------------------------------------------------------------
# Subagents (JITNA-distributed, see jitna_distributor.py)
# ---------------------------------------------------------------------------

def _subagent_run(row_id: str, created_at: Optional[str], before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row_id,
        "created_at": created_at,
        "agent_id": before.get("agent_id") or after.get("agent_id"),
        "goal": before.get("goal") or after.get("goal"),
        "success": bool(after.get("success")),
        "stopped_reason": after.get("stopped_reason"),
        "iterations": after.get("iterations"),
        "final_answer": after.get("final_answer"),
        "jitna": after.get("jitna"),
        "timed_out": bool(after.get("timed_out")),
        "error": after.get("error") or after.get("rejected"),
    }


def list_subagent_runs(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _kernel()._persistence.list_architect_decisions(limit=limit * 4)
    out = []
    for r in rows:
        if r.get("decision_type") != "jitna_subagent_result":
            continue
        out.append(_subagent_run(str(r.get("id")), r.get("created_at"),
                                 _loads(r.get("jitna_before")) or {}, _loads(r.get("jitna_after")) or {}))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_desk_router(daemon_state: Callable[[], Dict[str, Any]]) -> APIRouter:
    """daemon_state() returns {"scheduler": AutonomousScheduler|None,
    "gateways": {channel: gateway|None}} from api.py's daemon globals."""
    router = APIRouter(prefix="/v1/desk", tags=["Desk"])

    @router.get("/sessions")
    async def sessions(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        with _connect() as conn:
            return {"sessions": list_sessions(conn, limit)}

    @router.get("/sessions/{start_id}")
    async def session_detail(start_id: int) -> Dict[str, Any]:
        with _connect() as conn:
            found = get_session(conn, start_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no episode starts at audit row {start_id}")
        return found

    @router.get("/tools")
    async def tools() -> Dict[str, Any]:
        from rct_control_plane.governed_autonomous_loop import _ALWAYS_NEEDS_APPROVAL_TOOLS, RISKY_TOOLS
        from rct_control_plane.mcp_server import mcp
        listed = await mcp.list_tools()
        out = []
        for t in listed:
            gate = ("approval" if t.name in _ALWAYS_NEEDS_APPROVAL_TOOLS
                    else "fdia" if t.name in RISKY_TOOLS else "open")
            out.append({"name": t.name, "description": (t.description or "").strip(), "gate": gate})
        out.sort(key=lambda x: ({"approval": 0, "fdia": 1, "open": 2}[x["gate"]], x["name"]))
        return {"tools": out, "count": len(out)}

    @router.get("/skills")
    async def skills(limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
        lib = _skills()
        with sqlite3.connect(lib.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, problem_statement, solution, growth_ratio, delta, g_before, g_after, "
                "governance_violation, session_id, created_at FROM skills ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        return {"count": lib.count(), "skills": [
            {**{k: r[k] for k in r.keys() if k != "solution"}, "solution": _loads(r["solution"]),
             "governance_violation": bool(r["governance_violation"])} for r in rows]}

    @router.get("/models")
    async def models(catalog: Optional[str] = Query(None, pattern="^(openrouter|ollama)$"),
                     free: bool = False, search: Optional[str] = None) -> Dict[str, Any]:
        from rct_control_plane import model_config
        selection = model_config.resolve_model_selection()
        out: Dict[str, Any] = {"selection": selection.to_dict(),
                               "config_path": str(model_config.config_path()),
                               "openrouter_key_present": bool(os.getenv("OPENROUTER_API_KEY"))}
        if catalog == "openrouter":
            try:
                found = model_config.filter_models(model_config.list_openrouter_models())
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"OpenRouter catalog unreachable: {exc}") from exc
            if free:
                found = [m for m in found if (m.prompt_price_per_mtok or 0) == 0
                         and (m.completion_price_per_mtok or 0) == 0]
            if search:
                found = [m for m in found if search.lower() in m.id.lower()]
            out["catalog"] = [m.to_dict() for m in found[:200]]
        elif catalog == "ollama":
            try:
                out["catalog"] = [m.to_dict() for m in model_config.list_ollama_models()]
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}") from exc
        return out

    @router.post("/models")
    async def set_model(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane import model_config
        try:
            path = model_config.save_model_selection(str(payload.get("provider", "")), str(payload.get("model", "")))
        except model_config.ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"saved": str(path), "selection": model_config.resolve_model_selection().to_dict()}

    @router.get("/audit")
    async def audit(limit: int = Query(40, ge=1, le=500)) -> Dict[str, Any]:
        from rct_control_plane import audit_chain
        from rct_control_plane.autonomous_scheduler import ANCHOR_KEY_ID_ENV, ANCHOR_URL_ENV, anchor_configured
        from rct_control_plane.notary import NOTARY_URL_ENV
        with _connect() as conn:
            report = audit_chain.verify_audit_chain(conn, public_key_hex=os.getenv(audit_chain.PUBKEY_ENV))
            head = audit_chain.chain_head(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, entity_type, action, actor, created_at FROM audit_trail "
                                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {
            "chain": report.to_dict(), "head": head,
            "signing_key_configured": bool(os.getenv(audit_chain.SIGNING_KEY_ENV)),
            "notary": {"configured": bool(os.getenv(NOTARY_URL_ENV)), "url": os.getenv(NOTARY_URL_ENV)},
            "anchor": {"configured": anchor_configured(), "url": os.getenv(ANCHOR_URL_ENV),
                       "key_id": os.getenv(ANCHOR_KEY_ID_ENV)},
            "recent": [dict(r) for r in rows],
        }

    @router.get("/experiments")
    async def experiments(limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
        persistence = _kernel()._persistence
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT e.id, e.name, e.created_at, COUNT(r.id) AS runs, MAX(r.timestamp) AS last_run "
                "FROM experiments e LEFT JOIN experiment_runs r ON r.experiment_id = e.id "
                "GROUP BY e.id ORDER BY last_run DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["compare"] = persistence.compare_experiment_runs(r["id"]) if r["runs"] >= 2 else None
            out.append(item)
        return {"experiments": out}

    @router.get("/experiments/{experiment_id}")
    async def experiment_runs(experiment_id: str) -> Dict[str, Any]:
        persistence = _kernel()._persistence
        runs = persistence.get_experiment_runs(experiment_id)
        return {"experiment_id": experiment_id, "runs": runs,
                "compare": persistence.compare_experiment_runs(experiment_id) if len(runs) >= 2 else None}

    @router.get("/channels")
    async def channels() -> Dict[str, Any]:
        from rct_control_plane.agent_factory import SENDER_ALLOWLIST_ENV, allowed_senders
        gateways = daemon_state().get("gateways") or {}
        out = []
        for name in CHANNELS:
            allow = allowed_senders(name)
            gw = gateways.get(name)
            out.append({
                "channel": name,
                "token_present": bool(os.getenv(_TOKEN_ENV[name])),
                "running": bool(getattr(gw, "_is_running", False)) if gw is not None else False,
                "allowlist_env": SENDER_ALLOWLIST_ENV[name],
                # Counts only: sender ids are personal data and stay on the host.
                "allowlist": "everyone" if allow is None else ("nobody" if not allow else "listed"),
                "allowlist_count": None if allow is None else len(allow),
            })
        return {"channels": out}

    @router.post("/cron/{task_id}/run")
    async def run_task(task_id: str) -> Dict[str, Any]:
        scheduler = daemon_state().get("scheduler")
        if scheduler is None:
            raise HTTPException(status_code=409, detail="the daemon is not running (start it with `delentia serve`)")
        if task_id not in scheduler.tasks:
            raise HTTPException(status_code=404, detail=f"no task {task_id!r}")
        result: Dict[str, Any] = await scheduler.trigger_task_async(task_id)
        return result

    @router.get("/subagents")
    async def subagents(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
        return {"runs": list_subagent_runs(limit)}

    @router.post("/subagents/run")
    async def run_subagents(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fork-join over up to 3 goals through jitna_distributor: each goal goes
        to its own process in its own git worktree inside a signed JITNA request."""
        goals = payload.get("goals")
        if not isinstance(goals, list) or not goals or not all(isinstance(g, str) and g.strip() for g in goals):
            raise HTTPException(status_code=400, detail="'goals' must be a non-empty list of non-empty strings")
        if len(goals) > 3:
            raise HTTPException(status_code=400, detail="at most 3 subagents at a time")
        try:
            timeout = float(payload.get("timeout_seconds", 240))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="timeout_seconds must be a number") from None
        timeout = max(30.0, min(timeout, 900.0))
        from rct_control_plane.jitna_distributor import distribute_to_subagents
        outcomes = await distribute_to_subagents([g.strip() for g in goals], _kernel()._persistence, timeout_seconds=timeout)
        return {"runs": [_subagent_run(str(o.get("agent_id")), None, {"agent_id": o.get("agent_id"), "goal": o.get("goal")}, o)
                         for o in outcomes]}

    @router.get("/overview")
    async def overview() -> Dict[str, Any]:
        from rct_control_plane import model_config
        from rct_control_plane.approvals import PendingActionStore
        state = daemon_state()
        scheduler = state.get("scheduler")
        tasks = scheduler.list_tasks() if scheduler is not None else []
        verify = next((t for t in tasks if t["name"] == "audit_chain_verify"), None)
        with _connect() as conn:
            sessions_total = conn.execute(
                "SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_episode_start'").fetchone()[0]
        pending = PendingActionStore(_kernel()._persistence).list(status="PENDING", limit=500)
        return {
            "model": model_config.resolve_model_selection().to_dict(),
            "daemon": {"running": bool(scheduler is not None and scheduler._is_running), "tasks": len(tasks)},
            "audit_verify": {"status": verify["last_status"], "output": verify["last_output"]} if verify else None,
            "sessions_total": sessions_total,
            "approvals_pending": len(pending),
            "skills": _skills().count(),
            "storage": data_home.describe(),
        }

    return router
