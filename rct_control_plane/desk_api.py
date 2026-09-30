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
                        "notary_receipt", "notary_gap", "intent_loop_pillars")


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
    upper = _next_start_id(conn, start) or 2**62      # the pillar report is written just after the end row
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
        "data_evidence": s.get("data_evidence"),
        "pillars": next((_loads(r["changes"]) for r in rows if r["entity_type"] == "intent_loop_pillars"), None),
        "warm_recall": s.get("warm_recall"),
        "growth": ({"delta": (_loads(end["changes"]) or {}).get("mee_delta"), "G": (_loads(end["changes"]) or {}).get("mee_g")}
                   if end is not None else None),
        "events": [{"id": r["id"], "type": r["entity_type"], "action": r["action"],
                    "at": r["created_at"], "data": _loads(r["changes"])} for r in rows if r["entity_type"] != "intent_loop_pillars"],
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
                "governance_violation, session_id, created_at, uses, successes, failures, reinforced, archived "
                "FROM skills ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        out = []
        for r in rows:
            item = {k: r[k] for k in r.keys() if k != "solution"}
            item["solution"] = _loads(r["solution"])
            item["governance_violation"] = bool(r["governance_violation"])
            item["archived"] = bool(r["archived"])
            item["reliability"] = round((r["successes"] + 1) / (r["uses"] + 2), 4)
            out.append(item)
        return {"count": lib.count(), "skills": out}

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

    @router.get("/growth")
    async def growth(limit: int = Query(60, ge=1, le=300)) -> Dict[str, Any]:
        """MEE growth per namespace (G, episodes), the recent episodes with the
        D that gated them and the growth step they earned, and how the skill
        library is doing (reuse, reliability, archived)."""
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            ledgers = []
            for row in conn.execute("SELECT key, value, updated_at FROM states WHERE namespace = 'mee_growth' ORDER BY updated_at DESC").fetchall():
                value = _loads(row["value"]) or {}
                session = value.get("session") or {}
                ledgers.append({
                    "namespace": row["key"], "G": session.get("g_current"), "resilience": session.get("resilience"),
                    "growth_ratio": session.get("total_growth_ratio"), "episodes": value.get("episodes", 0),
                    "verified_episodes": value.get("verified_episodes", 0), "updated_at": row["updated_at"],
                })
            runs = conn.execute(
                "SELECT id, experiment_id, timestamp, metrics, jitna_state FROM experiment_runs "
                "WHERE algorithm_id LIKE 'governed_loop/%' ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            recent = []
            for r in runs:
                m = _loads(r["metrics"]) or {}
                ns = (_loads(r["jitna_state"]) or {}).get("namespace")
                recent.append({
                    "run_id": r["id"], "experiment_id": r["experiment_id"], "at": r["timestamp"], "namespace": ns,
                    "D": m.get("data_D"), "growth_delta": m.get("growth_delta"), "G": m.get("growth_G"),
                    "iterations": m.get("iterations"), "finished": m.get("finished"), "aligned": m.get("aligned_with_intent"),
                    "skills_injected": m.get("skills_injected"), "cost_usd": m.get("cost_usd"), "duration_s": m.get("duration_s"),
                })
        lib = _skills()
        with sqlite3.connect(lib.db_path) as sk:
            sk.row_factory = sqlite3.Row
            stats = sk.execute("SELECT COUNT(*) n, SUM(archived) archived, SUM(uses > 0) reused, SUM(reinforced - 1) repeats "
                               "FROM skills").fetchone()
            best = sk.execute("SELECT id, problem_statement, uses, successes, failures, reinforced FROM skills WHERE archived = 0 "
                              "AND uses > 0 ORDER BY (successes + 1.0) / (uses + 2.0) DESC, uses DESC LIMIT 5").fetchall()
        from rct_control_plane.intent_loop import evolution_report
        persistence = _kernel()._persistence
        evolution = [evolution_report(persistence, item["namespace"]) for item in ledgers[:5]]
        return {
            "ledgers": ledgers, "recent": recent, "evolution": evolution,
            "skills": {"total": stats["n"] or 0, "archived": stats["archived"] or 0, "reused": stats["reused"] or 0,
                       "merged_repeats": stats["repeats"] or 0,
                       "most_reliable": [{**dict(b), "reliability": round((b["successes"] + 1) / (b["uses"] + 2), 4)} for b in best]},
        }

    @router.get("/pipeline")
    async def pipeline(limit: int = Query(40, ge=1, le=300)) -> Dict[str, Any]:
        """The 41 algorithms as pipeline stages: what each one is, whether the
        pipeline is on, and what the last episodes recorded for each."""
        from rct_control_plane import algorithm_pipeline as ap
        adapters = [{"algo_id": a.algo_id, "name": a.name, "stage": a.stage, "phase": a.phase,
                     "needs_llm": a.llm, "needs_network": a.network, "writes_files": a.writes} for a in ap.ADAPTERS]
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, actor, changes, created_at FROM audit_trail WHERE entity_type = 'algorithm_pipeline' "
                                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        runs = []
        aggregate: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            changes = _loads(row["changes"]) or {}
            runs.append({"id": row["id"], "namespace": row["actor"], "at": row["created_at"],
                         **{k: changes.get(k) for k in ("algorithms", "ok", "not_triggered", "errors", "total_ms", "advice_lines")}})
            for key, info in (changes.get("by_algorithm") or {}).items():
                algo_id, stage = key.split(":", 1)
                agg = aggregate.setdefault(f"{algo_id}:{stage}", {"algo_id": algo_id, "stage": stage, "ok": 0, "not_triggered": 0, "error": 0, "ms": []})
                agg[info.get("status", "error")] = agg.get(info.get("status", "error"), 0) + 1
                if info.get("status") == "ok":
                    agg["ms"].append(float(info.get("ms") or 0.0))
                if info.get("status") == "ok":
                    agg["effect"] = info.get("effect")
                else:
                    agg.setdefault("effect", info.get("effect"))
        table = []
        for agg in aggregate.values():
            ms = agg.pop("ms")
            agg["mean_ms"] = round(sum(ms) / len(ms), 2) if ms else None
            table.append(agg)
        table.sort(key=lambda a: (ap.STAGES.index(a["stage"]) if a["stage"] in ap.STAGES else 99, a["algo_id"]))
        return {
            "enabled": os.environ.get("DELENTIA_ALGORITHM_PIPELINE", "").strip() in ("1", "true", "yes"),
            "algorithms": len({a["algo_id"] for a in adapters}), "adapters": adapters, "runs": runs, "by_algorithm": table,
        }

    @router.get("/memories")
    async def memories(namespace: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            if namespace:
                rows = conn.execute("SELECT id, namespace, memory_type, content, importance, created_at, accessed_count "
                                    "FROM memories WHERE namespace = ? ORDER BY created_at DESC LIMIT ?", (namespace, limit)).fetchall()
            else:
                rows = conn.execute("SELECT id, namespace, memory_type, content, importance, created_at, accessed_count "
                                    "FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            spaces = [dict(r) for r in conn.execute("SELECT namespace, COUNT(*) AS n FROM memories GROUP BY namespace ORDER BY n DESC").fetchall()]
        return {"memories": [dict(r) for r in rows], "namespaces": spaces}

    @router.post("/memories")
    async def remember(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Give the agent a fact about the user's world. This is data the user
        owns: it feeds recall, the retrieval algorithms and D."""
        from rct_control_plane.agent_memory import AgentMemory, MemoryType
        content = str(payload.get("content", "")).strip()
        if not content or len(content) > 4000:
            raise HTTPException(status_code=400, detail="'content' must be 1-4000 characters")
        try:
            kind = MemoryType(str(payload.get("memory_type", "fact")))
        except ValueError:
            raise HTTPException(status_code=400, detail="unknown memory_type") from None
        namespace = str(payload.get("namespace") or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk"))
        importance = max(0.0, min(1.0, float(payload.get("importance", 0.7))))
        memory_id = await AgentMemory(namespace, _kernel()._persistence).store(content, kind, importance=importance)
        return {"memory_id": memory_id, "namespace": namespace}

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
