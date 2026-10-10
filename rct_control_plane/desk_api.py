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

from fastapi import APIRouter, HTTPException, Query, Request, Response

from rct_control_plane import data_home

CHANNELS = ("telegram", "discord", "slack", "line", "whatsapp", "signal", "email")
_TOKEN_ENV = {"telegram": "TELEGRAM_BOT_TOKEN", "discord": "DISCORD_BOT_TOKEN",
              "slack": "SLACK_BOT_TOKEN", "line": "LINE_CHANNEL_ACCESS_TOKEN",
              "whatsapp": "WHATSAPP_ACCESS_TOKEN", "signal": "SIGNAL_NUMBER", "email": "DELENTIA_EMAIL_PASSWORD"}
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

    @router.get("/sessions/search")
    async def sessions_search(request: Request, q: str = Query("", max_length=200), limit: int = Query(10, ge=1, le=25)) -> Dict[str, Any]:
        """Search the signed-in person's own past episodes (goal and answer)."""
        from rct_control_plane.session_search import SessionLog
        owner = getattr(request.state, "delentia_user", None) or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk")
        log = SessionLog(_kernel()._persistence)
        return {"owner": owner, "query": q, "episodes": log.search(owner, q, limit=limit), "indexed": log.count(owner), "fts": log.fts}

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
        from rct_control_plane import external_mcp
        from rct_control_plane.governed_autonomous_loop import is_risky_tool, needs_signature_always
        from rct_control_plane.mcp_server import mcp
        listed = await external_mcp.maybe_wrap(mcp).list_tools()
        out = []
        for t in listed:
            gate = ("approval" if needs_signature_always(t.name)
                    else "fdia" if is_risky_tool(t.name) else "open")
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
            item["bundled"] = bool(r["session_id"] and str(r["session_id"]).startswith("bundled:"))   # Round 55: a starter playbook, not learned
            item["imported"] = bool(r["session_id"] and str(r["session_id"]).startswith("imported:"))   # Round 57: somebody else's SKILL.md
            out.append(item)
        return {"count": lib.count(), "skills": out}

    @router.post("/skills/import")
    async def skills_import(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Import a SKILL.md (pasted text, or an https address). A person's act, never the agent's; refused if the injection screen finds anything."""
        from rct_control_plane import skill_format
        text, source = payload.get("text"), str(payload.get("source") or "pasted in the Desk")
        try:
            if payload.get("url"):
                source = str(payload["url"])
                import asyncio as _asyncio
                text = await _asyncio.to_thread(skill_format.fetch, source)
            parsed = skill_format.parse(str(text or ""))
            if not payload.get("reviewed"):
                # Step one: show what would be imported. The caller shows the text to a person and repeats the call with reviewed=true.
                return {"preview": {"name": parsed.name, "description": parsed.description, "version": parsed.version, "tags": parsed.tags,
                                    "instructions": parsed.body, "source": source, "screen_findings": skill_format.screen(parsed)},
                        "needs_review": True}
            outcome = skill_format.install(_skills(), parsed, source, reviewed=True)
        except skill_format.SkillFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return outcome

    @router.get("/skills/{skill_id}/export")
    async def skills_export(skill_id: str) -> Dict[str, Any]:
        from rct_control_plane import skill_format
        record = _skills().get_skill(skill_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"no skill {skill_id!r}")
        return {"skill_id": skill_id, "skill_md": skill_format.export(record)}

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

    @router.get("/models/setup")
    async def model_setup() -> Dict[str, Any]:
        """Everything the model-setup page draws in one call: the current choice (never a secret,
        only whether a key is present), the data-location verdict for the saved endpoint, and the
        country -> provider -> model starting points."""
        from rct_control_plane import model_setup, provider_presets
        return {**model_setup.current_view(), "presets": provider_presets.catalog()}

    @router.post("/models/test")
    async def test_model_endpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ask an OpenAI-compatible endpoint which models it serves. No prompt is sent. The
        data-location policy is checked first and a blocked endpoint is not contacted. The key
        in the body (if any) is used for this one request and never stored or returned."""
        from rct_control_plane import model_setup
        endpoint = payload.get("endpoint")
        if not isinstance(endpoint, dict):
            raise HTTPException(status_code=400, detail="'endpoint' must be an object with base_url, kind, region")
        api_key = payload.get("api_key")
        if api_key is not None and not isinstance(api_key, str):
            raise HTTPException(status_code=400, detail="'api_key' must be a string")
        return await model_setup.probe_endpoint(endpoint, api_key or None)

    @router.post("/models")
    async def set_model(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane import model_config, model_setup
        endpoint = payload.get("endpoint")
        if endpoint is not None and not isinstance(endpoint, dict):
            raise HTTPException(status_code=400, detail="'endpoint' must be an object")
        try:
            return model_setup.apply_selection(
                str(payload.get("provider", "")), str(payload.get("model", "")), endpoint=endpoint,
                profile=(str(payload["profile"]).strip() if payload.get("profile") else None),
                api_key=(str(payload["api_key"]) if payload.get("api_key") else None))
        except (model_config.ModelConfigError, model_setup.SetupError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    # ------------------------------------------------------------------
    # Round 57: persistent cron jobs (cron_jobs.py). The Desk user creates jobs directly (they are the human); the agent can only propose one
    # through delentia_cron_create, which waits for a signature.
    # ------------------------------------------------------------------
    def _cron_service() -> Any:
        from rct_control_plane.cron_jobs import CronService
        return CronService(_kernel()._persistence)

    def _cron_owner(request: Request) -> str:
        return getattr(request.state, "delentia_user", None) or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk")

    @router.get("/webhooks")
    async def webhooks_view() -> Dict[str, Any]:
        """The webhook routes (never their secrets): which are open, which are not served and why, and the latest deliveries."""
        from rct_control_plane import webhook_triggers as wt
        routes, problems = wt.load_routes()
        with _connect() as conn:
            try:
                recent = [{"route": r[0], "action": r[1], "at": r[2]} for r in conn.execute(
                    "SELECT entity_id, action, created_at FROM audit_trail WHERE entity_type = 'webhook' ORDER BY id DESC LIMIT 30").fetchall()]
            except Exception:
                recent = []
        return {"routes": [{"name": r.name, "verify": r.verify, "mode": r.mode, "events": r.events, "open": wt.secret_of(r) is not None, "secret_env": r.secret_env,
                            "deliver": r.deliver, "max_per_minute": r.max_per_minute} for r in routes.values()], "problems": problems, "recent": recent, "path": str(wt.config_path())}

    @router.get("/tasks")
    async def tasks_view() -> Dict[str, Any]:
        """Every task and the latest background jobs, for the owner (people see only their own through /v1/agent/tasks and /v1/agent/jobs)."""
        import sqlite3
        from rct_control_plane.task_board_runtime import get_board
        persistence = _kernel()._persistence
        jobs: List[Dict[str, Any]] = []
        with persistence._connect() as conn:
            conn.row_factory = sqlite3.Row
            try:
                jobs = [{k: r[k] for k in ("id", "namespace", "status", "stopped", "steps", "last_tool", "created_at", "finished_at", "approval_id")}
                        for r in conn.execute("SELECT * FROM agent_jobs ORDER BY created_at DESC LIMIT 30").fetchall()]
            except sqlite3.OperationalError:
                jobs = []                                          # no job has ever been submitted on this store
        return {"tasks": [{**t, "goal": t["goal"][:200]} for t in get_board(persistence).list(limit=50)], "jobs": jobs}

    @router.post("/tasks/{task_id}/cancel")
    async def task_cancel(task_id: str) -> Dict[str, Any]:
        from rct_control_plane.task_board import TaskError
        from rct_control_plane.task_board_runtime import get_board
        try:
            return get_board(_kernel()._persistence).cancel(task_id)
        except TaskError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _desk_task(fn_name: str, task_id: str, **kwargs: Any) -> Any:
        from rct_control_plane.task_board import TaskError
        from rct_control_plane.task_board_runtime import get_board
        try:
            return getattr(get_board(_kernel()._persistence), fn_name)(task_id, **kwargs)
        except TaskError as exc:
            raise HTTPException(status_code=404 if "no such task" in str(exc) else 409, detail=str(exc)) from exc

    @router.post("/tasks/{task_id}/start")
    async def task_start(task_id: str) -> Dict[str, Any]:
        return _desk_task("start", task_id)

    @router.put("/tasks/{task_id}/plan")
    async def task_plan(task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _desk_task("edit_plan", task_id, steps=[str(x) for x in payload.get("steps", [])] if isinstance(payload.get("steps"), list) else [])

    @router.post("/tasks/{task_id}/replan")
    async def task_replan(task_id: str) -> Dict[str, Any]:
        return _desk_task("replan", task_id)

    @router.get("/envelope")
    async def envelope_status() -> Dict[str, Any]:
        """Is the agent paused, what are the spending and flood limits, and how much of them has been used (envelope.py)."""
        from rct_control_plane import envelope, owner_notify
        return {**envelope.status(_kernel()._persistence), "owner_alerts": owner_notify.status()}

    @router.post("/envelope/pause")
    async def envelope_pause(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        """Pausing needs no signature: nothing starts and no tool runs, from any entry point, until it is lifted."""
        from rct_control_plane import envelope
        owner = getattr(request.state, "delentia_user", None) or "desk"
        return {"paused": envelope.pause(str(payload.get("reason", "")), by=f"desk:{owner}", persistence=_kernel()._persistence)}

    @router.post("/envelope/resume")
    async def envelope_resume(payload: Dict[str, Any], request: Request, response: Response) -> Dict[str, Any]:
        """Lifting a pause needs a signed approval when any approver is configured (closing is free, opening is signed): the first call answers 202 with the action to sign."""
        from rct_control_plane import envelope
        persistence = _kernel()._persistence
        owner = getattr(request.state, "delentia_user", None) or "desk"
        approval_id = str(payload.get("approval_id") or "").strip() or None
        try:
            return {"resumed": envelope.resume(by=f"desk:{owner}", persistence=persistence, approval_id=approval_id)}
        except envelope.ResumeRefused as exc:
            if approval_id is None and envelope.status(persistence)["resume_needs_signature"]:
                response.status_code = 202
                return {"pending_signature": True, **envelope.request_resume(persistence, requested_by=f"desk:{owner}")}
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.get("/pairing")
    async def pairing_view() -> Dict[str, Any]:
        """Who asked to be let in, and who is. A request is let in only by a signed approval (Approvals page or `delentia approvals approve <code>`)."""
        from rct_control_plane import pairing
        return pairing.state(_kernel()._persistence)

    @router.post("/pairing/revoke")
    async def pairing_revoke(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        """Closing a door needs no signature (like pausing a job); opening one always does."""
        from rct_control_plane import pairing
        owner = getattr(request.state, "delentia_user", None) or "desk"
        done = pairing.revoke(str(payload.get("channel", "")), str(payload.get("sender_id", "")), actor=f"desk:{owner}", persistence=_kernel()._persistence)
        if not done:
            raise HTTPException(status_code=404, detail="that person was not let in by pairing")
        return {"revoked": True}

    @router.get("/cron/jobs")
    async def cron_jobs_list(request: Request) -> Dict[str, Any]:
        from rct_control_plane import cron_jobs, nl_schedule
        return {"jobs": _cron_service().list(_cron_owner(request)), "owner": _cron_owner(request),
                "delivery": {ch: cron_jobs.allowed_recipients(ch) for ch in cron_jobs.DELIVERY_CHANNELS},
                "limits": {"max_jobs": cron_jobs.MAX_JOBS_PER_NAMESPACE, "min_interval_s": nl_schedule.MIN_INTERVAL_S,
                           "fails_before_off": cron_jobs.MAX_FAIL_STREAK, "hourly_cap_env": cron_jobs.HOURLY_CAP_ENV},
                "timezone": nl_schedule.default_timezone_name() or "this machine's local zone", "forms": list(nl_schedule.FORMS)}

    @router.post("/cron/parse")
    async def cron_parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        """What a schedule text means and its next five runs, so a person sees it before anything is saved."""
        import time as _time
        from datetime import datetime
        from rct_control_plane import nl_schedule
        now = _time.time()
        try:
            schedule = nl_schedule.parse(str(payload.get("text", "")), now=now)
            runs = nl_schedule.upcoming(schedule, now, 5)
            zone = nl_schedule._tz(schedule.tz)
        except nl_schedule.ScheduleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"kind": schedule.kind, "meaning": nl_schedule.describe(schedule), "timezone": schedule.tz or "local",
                "upcoming": [datetime.fromtimestamp(t, zone).strftime("%a %Y-%m-%d %H:%M %Z") for t in runs]}

    @router.post("/cron/jobs")
    async def cron_job_create(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        from rct_control_plane.cron_jobs import CronError
        deliver = payload.get("deliver") if isinstance(payload.get("deliver"), dict) else None
        try:
            job = _cron_service().create(_cron_owner(request), str(payload.get("goal", "")), str(payload.get("schedule", "")), name=str(payload.get("name", "")),
                                         deliver=deliver, created_by=f"desk:{_cron_owner(request)}",
                                         max_runs=int(payload["max_runs"]) if payload.get("max_runs") else None)
        except (CronError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job": job}

    @router.post("/cron/jobs/{job_id}/{action}")
    async def cron_job_action(job_id: str, action: str, request: Request) -> Dict[str, Any]:
        from rct_control_plane.cron_jobs import CronError
        service, owner = _cron_service(), _cron_owner(request)
        try:
            if action in ("enable", "pause"):
                return {"job": service.set_enabled(job_id, action == "enable", actor=f"desk:{owner}", namespace=owner)}
            if action == "run":
                job = service._owned(job_id, owner)
                from rct_control_plane import cron_jobs
                ran = await service.run_job(_kernel(), job, cron_jobs.deliver_via_gateways)
                return {"job": ran}
        except CronError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail="actions: enable, pause, run")

    @router.delete("/cron/jobs/{job_id}")
    async def cron_job_delete(job_id: str, request: Request) -> Dict[str, Any]:
        from rct_control_plane.cron_jobs import CronError
        try:
            return {"job": _cron_service().delete(job_id, actor=f"desk:{_cron_owner(request)}", namespace=_cron_owner(request))}
        except CronError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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
        from rct_control_plane.intent_loop import evolution_report, intent_profile
        persistence = _kernel()._persistence
        evolution = [evolution_report(persistence, item["namespace"]) for item in ledgers[:5]]
        profiles = [intent_profile(persistence, item["namespace"]) for item in ledgers[:5]]
        return {
            "ledgers": ledgers, "recent": recent, "evolution": evolution, "profiles": profiles,
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
    async def memories(request: Request, namespace: Optional[str] = None, limit: int = Query(100, ge=1, le=500), include_revoked: bool = False) -> Dict[str, Any]:
        owner = getattr(request.state, "delentia_user", None)
        if owner and owner != "shared":
            namespace = owner                    # Round 54: with a token per person nobody reads another person's memory
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            if namespace:
                rows = conn.execute("SELECT id, namespace, memory_type, content, importance, created_at, accessed_count, revoked_at, revoked_reason "
                                    "FROM memories WHERE namespace = ? AND (revoked_at IS NULL OR ?) ORDER BY created_at DESC LIMIT ?", (namespace, 1 if include_revoked else 0, limit)).fetchall()
            else:
                rows = conn.execute("SELECT id, namespace, memory_type, content, importance, created_at, accessed_count, revoked_at, revoked_reason "
                                    "FROM memories WHERE (revoked_at IS NULL OR ?) ORDER BY created_at DESC LIMIT ?", (1 if include_revoked else 0, limit)).fetchall()
            spaces = [dict(r) for r in conn.execute("SELECT namespace, COUNT(*) AS n FROM memories WHERE revoked_at IS NULL GROUP BY namespace ORDER BY n DESC").fetchall()]
        if owner and owner != "shared":
            spaces = [s for s in spaces if s["namespace"] == owner]       # other people's namespace names are not shown either
        return {"memories": [dict(r) for r in rows], "namespaces": spaces}

    @router.post("/memories")
    async def remember(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
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
        owner = getattr(request.state, "delentia_user", None)
        if owner and owner != "shared":
            namespace = owner                                                 # Round 54: a person writes only to their own memory
        importance = max(0.0, min(1.0, float(payload.get("importance", 0.7))))
        memory_id = await AgentMemory(namespace, _kernel()._persistence).store(content, kind, importance=importance)
        return {"memory_id": memory_id, "namespace": namespace}

    @router.post("/memories/revoke")
    async def revoke_memory(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        """Round 65: stop the agent using a memory. The row stays on disk for the audit (Zero-Delete) but no reader returns it
        again. A person revokes only their own; the owner names the namespace."""
        memory_id = str(payload.get("memory_id") or "").strip()
        if not memory_id:
            raise HTTPException(status_code=400, detail="'memory_id' is required")
        namespace = str(payload.get("namespace") or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk"))
        owner = getattr(request.state, "delentia_user", None)
        if owner and owner != "shared":
            namespace = owner
        if not _kernel()._persistence.revoke_memory(memory_id, namespace, str(payload.get("reason") or "")):
            raise HTTPException(status_code=404, detail="no such memory in this namespace (or it was already revoked)")
        return {"memory_id": memory_id, "namespace": namespace, "revoked": True}

    @router.get("/sovereignty")
    async def sovereignty(limit: int = Query(50, ge=1, le=300)) -> Dict[str, Any]:
        """The data-residency policy (or its absence), where the selected model would
        send data, and the recent decisions from the audit trail. Read-only: the policy
        is a security setting, changed with `delentia sovereignty set`, not from here."""
        from rct_control_plane import residency
        info = residency.describe()
        with _connect() as conn:
            decisions = residency.recent_decisions(conn, limit)
        info["decisions"] = decisions
        info["counts"] = {a: sum(1 for d in decisions if d["action"] == a) for a in ("allow", "redact", "block")}
        return info

    @router.post("/sovereignty")
    async def set_sovereignty(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Write the data-residency policy (what `delentia sovereignty set` writes). Refused while the
        policy comes from DELENTIA_HOME_REGION in the environment, because the environment wins and a
        saved file would silently do nothing."""
        from core.regional_adapter.sovereignty import SovereigntyPolicy, validate_region
        from rct_control_plane import residency
        if (os.environ.get(residency.HOME_REGION_ENV) or "").strip():
            raise HTTPException(status_code=409, detail=f"The policy is set by {residency.HOME_REGION_ENV} in the server's "
                                "environment, which overrides the saved file. Change it there.")
        try:
            home = validate_region(str(payload.get("home_region", "")))
            extra = [validate_region(str(r)) for r in (payload.get("allowed_regions") or [])]
            policy = SovereigntyPolicy(
                home_region=home, allowed_regions=[home, *[r for r in extra if r != home]],
                allow_cross_border=bool(payload.get("allow_cross_border", False)),
                pii_policy=str(payload.get("pii_policy", "block")), legal_basis=str(payload.get("legal_basis", ""))[:300],
                tenant_id=str(payload.get("tenant_id", "default"))[:64] or "default")
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        path = residency.save_policy(policy)
        return {"saved": str(path), **residency.describe()}

    # ------------------------------------------------------------------
    # Round 54: the owner's policy for A in F = D^I x A
    # ------------------------------------------------------------------
    async def _tool_gate_labels() -> List[Dict[str, Any]]:
        from rct_control_plane import external_mcp
        from rct_control_plane.governed_autonomous_loop import is_risky_tool, needs_signature_always
        from rct_control_plane.mcp_server import mcp
        listed = await external_mcp.maybe_wrap(mcp).list_tools()
        return [{"name": t.name, "description": (t.description or "").strip()[:160],
                 "built_in": ("always a signature" if needs_signature_always(t.name)
                              else "FDIA gate" if is_risky_tool(t.name) else "open")} for t in sorted(listed, key=lambda t: t.name)]

    def _approver_summary() -> List[Dict[str, Any]]:
        from rct_control_plane.approvals import trusted_approver_keys, trusted_approver_roles
        roles = trusted_approver_roles()
        return [{"name": name, "role": roles.get(key), "key_prefix": key[:12]} for key, name in trusted_approver_keys().items()]

    @router.get("/fdia")
    async def fdia_state() -> Dict[str, Any]:
        from rct_control_plane import fdia_policy, signedai_jury
        from rct_control_plane.governed_autonomous_loop import FDIA_GATE_THRESHOLD
        path = fdia_policy.policy_path()
        policy, error = None, ""
        try:
            policy = fdia_policy.load_policy()
        except ValueError:
            # The reason is on the host (`delentia fdia show`); the response carries a fixed message, not the exception text.
            error = "cannot read the policy file, or it is invalid (run `delentia fdia show` on the host for the reason)"
        jury_path = signedai_jury.config_path()
        return {
            "path": str(path), "exists": path.exists(), "error": error,
            "policy": policy.to_dict() if policy is not None else None,
            "digest": policy.digest() if policy is not None else None,
            "built_in": {"threshold": FDIA_GATE_THRESHOLD,
                         "rules": ["a risky tool needs F >= the threshold", "repo writes always need a human signature",
                                   "a denied shell command or an unsafe write path is A = 0",
                                   "the policy can tighten these, never loosen them"]},
            "tools": await _tool_gate_labels(),
            "approvers": _approver_summary(),
            "jury": {"configured": jury_path.exists(), "path": str(jury_path)},
            "limits": {"max_rules": fdia_policy.MAX_RULES, "action_types": list(fdia_policy.ACTION_TYPES),
                       "jury_tiers": list(fdia_policy.JURY_TIERS), "risk_levels": list(fdia_policy.RISK_LEVELS)},
        }

    @router.get("/fdia/template/{name}")
    async def fdia_template(name: str) -> Dict[str, Any]:
        from rct_control_plane import fdia_policy
        if name not in ("balanced", "strict"):
            raise HTTPException(status_code=404, detail="templates: balanced, strict")
        return {"policy": fdia_policy.template(name, [t["name"] for t in await _tool_gate_labels()])}

    @router.post("/fdia/validate")
    async def fdia_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane import fdia_policy
        policy, errors = fdia_policy.validate_policy(payload.get("policy"))
        return {"valid": policy is not None, "errors": errors, "digest": policy.digest() if policy is not None else None}

    @router.post("/fdia/evaluate")
    async def fdia_evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
        """What the policy does with one call, and F. `policy` (a draft not saved yet) takes precedence over the file."""
        from rct_control_plane import fdia_policy
        from rct_control_plane.governed_autonomous_loop import FDIA_GATE_THRESHOLD, fdia_score
        tool = str(payload.get("tool_name", "")).strip()
        if not tool:
            raise HTTPException(status_code=400, detail="tool_name is required")
        args = payload.get("tool_args") or {}
        if not isinstance(args, dict):
            raise HTTPException(status_code=400, detail="tool_args must be an object")
        try:
            D = min(1.0, max(0.0, float(payload.get("D", 1.0))))
            I = min(10.0, max(0.0, float(payload.get("I", 1.0))))        # noqa: E741
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="D and I must be numbers") from exc
        if payload.get("policy") is not None:
            policy, errors = fdia_policy.validate_policy(payload["policy"])
            if policy is None:
                raise HTTPException(status_code=400, detail="the draft policy is invalid: " + "; ".join(errors[:5]))
        else:
            try:
                policy = fdia_policy.load_policy()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if policy is None:
            F = fdia_score(D, I, 1.0)
            return {"policy": None, "A": 1.0, "F": F, "threshold": FDIA_GATE_THRESHOLD, "outcome": "no policy: the built-in gate applies",
                    "reason": "no policy file; only the built-in rules apply (see built_in)"}
        result = fdia_policy.evaluate(policy, tool, args, principal=str(payload.get("principal", ""))[:128],
                                      approved=bool(payload.get("approved", False)))
        threshold = max(FDIA_GATE_THRESHOLD, policy.custom_safety_threshold)
        F = fdia_score(D, I, 1.0 if result.needs_signature else result.A)
        if result.A <= 0 and not result.needs_signature:
            outcome = "blocked"
        elif result.needs_signature:
            outcome = "waits for signature" if F >= threshold else "blocked (F below threshold)"
        else:
            from rct_control_plane.governed_autonomous_loop import is_risky_tool
            judged = is_risky_tool(tool) or result.action_type != "ALLOW"
            outcome = "allowed" if (F >= threshold or not judged) else "blocked (F below threshold)"
        return {**result.to_dict(), "F": F, "threshold": threshold, "outcome": outcome, "D": D, "I": I}

    def _policy_change_needs_signature() -> bool:
        """Round 54: changing the owner's rules is itself an act of the Architect. On a server that has an API token (a host)
        it needs a signature from a trusted approver; on a token-less loopback developer machine it does not, unless asked
        (DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE=1)."""
        from rct_control_plane import api_tokens
        explicit = (os.environ.get("DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE") or "").strip().lower()
        if explicit in ("1", "true", "yes", "on"):
            return True
        if explicit in ("0", "false", "no", "off"):
            return False
        return bool(os.environ.get("DELENTIA_API_TOKEN")) or api_tokens.per_user_mode()

    def _signature_gate(request: Request, payload: Dict[str, Any], tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """None = go ahead (no signature needed, or a valid signed approval for exactly this change was presented and is
        now used up). A dict = answer with it (HTTP 202) because the change is waiting for a signature."""
        from rct_control_plane.approvals import ApprovalError, PendingActionStore
        if not _policy_change_needs_signature():
            return None
        store = PendingActionStore(_kernel()._persistence)
        approval_id = str(payload.get("approval_id") or "").strip()
        owner = getattr(request.state, "delentia_user", None) or "desk"
        if not approval_id:
            roles = [r.strip() for r in (os.environ.get("DELENTIA_POLICY_APPROVER_ROLES") or "").split(",") if r.strip()]
            record = store.create(namespace=owner, goal=f"Owner policy change: {tool_name}", tool_name=tool_name, tool_args=args,
                                  reason="changing the rules for A needs a human signature", approver_roles=roles or None)
            return {"pending_signature": True, "approval_id": record.approval_id, "action_sha256": record.action_sha256, "args": args,
                    "how": f"sign it on the machine that holds the approver key: delentia approvals approve {record.approval_id} --key <key>; "
                           "then send the same request again with approval_id"}
        existing = store.get(approval_id)
        if existing is None or existing.tool_name != tool_name or existing.tool_args != args:
            raise HTTPException(status_code=403, detail="that approval is not for this exact change")
        try:
            store.claim_for_execution(approval_id)
        except ApprovalError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        request.state.claimed_approval = approval_id          # set by the server only, never read from the body
        return None

    def _record_policy_decision(what: str, before: Optional[str], after: Optional[str], who: str, approval_id: Optional[str]) -> None:
        import time as _time
        try:
            _kernel()._persistence.save_architect_decision(
                f"policy-{what}-{int(_time.time() * 1000)}", "policy_change", f"owner policy {what} by {who}"
                + (f" (signed approval {approval_id})" if approval_id else " (no signature was required on this host)"),
                {"digest": before}, {"digest": after, "approval_id": approval_id, "by": who})
        except Exception:               # the change and its audit row already exist
            pass

    @router.put("/fdia/policy")
    async def fdia_save(payload: Dict[str, Any], request: Request, response: Response) -> Dict[str, Any]:
        from rct_control_plane import fdia_policy
        policy, errors = fdia_policy.validate_policy(payload.get("policy"))
        if policy is None:
            raise HTTPException(status_code=400, detail="the policy is invalid: " + "; ".join(errors[:8]))
        waiting = _signature_gate(request, payload, "fdia_policy_change", {"policy_sha256": policy.digest(), "rules": len(policy.rules)})
        if waiting is not None:
            response.status_code = 202
            return waiting
        before = None
        try:
            existing = fdia_policy.load_policy()
            before = existing.digest() if existing is not None else None
        except ValueError:
            before = "unreadable"
        path = fdia_policy.save_policy(policy)
        claimed = getattr(request.state, "claimed_approval", None)
        if claimed:
            from rct_control_plane.approvals import PendingActionStore
            PendingActionStore(_kernel()._persistence).mark_executed(claimed, {"saved": str(path), "digest": policy.digest()})
        _kernel()._persistence.append_audit(
            entity_type="fdia_policy", entity_id=policy.policy_id, action="policy_saved",
            actor=getattr(request.state, "delentia_user", None) or "desk",
            changes={"digest_before": before, "digest_after": policy.digest(), "rules": len(policy.rules), "path": str(path), "approval_id": claimed})
        _record_policy_decision("saved", before, policy.digest(), getattr(request.state, "delentia_user", None) or "desk", claimed)
        return {"saved": str(path), "digest": policy.digest(), "rules": len(policy.rules)}

    @router.post("/fdia/policy/disable")
    async def fdia_disable(request: Request, response: Response, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Stop using the policy without deleting it: the file is renamed, never removed (Zero-Delete)."""
        import time as _time
        from rct_control_plane import fdia_policy
        path = fdia_policy.policy_path()
        if not path.exists():
            raise HTTPException(status_code=404, detail="there is no policy file")
        body = payload if payload is not None else {}
        waiting = _signature_gate(request, body, "fdia_policy_disable", {"file": path.name})
        if waiting is not None:
            response.status_code = 202
            return waiting
        archived = path.with_name(f"{path.name}.disabled-{int(_time.time())}")
        path.rename(archived)
        claimed = getattr(request.state, "claimed_approval", None)
        if claimed:
            from rct_control_plane.approvals import PendingActionStore
            PendingActionStore(_kernel()._persistence).mark_executed(claimed, {"archived_as": str(archived)})
        _kernel()._persistence.append_audit(entity_type="fdia_policy", entity_id=path.name, action="policy_disabled",
                                            actor=getattr(request.state, "delentia_user", None) or "desk",
                                            changes={"archived_as": str(archived), "approval_id": claimed})
        _record_policy_decision("disabled", None, None, getattr(request.state, "delentia_user", None) or "desk", claimed)
        return {"archived_as": str(archived)}

    # ------------------------------------------------------------------
    # Round 54: Tool Forge (tool_forge.py) - gaps, proposals, signed activation, forged tools
    # ------------------------------------------------------------------
    def _forge() -> Any:
        from rct_control_plane.tool_forge import ToolForge
        return ToolForge(_kernel()._persistence)

    def _approval_state(approval_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not approval_id:
            return None
        from rct_control_plane.approvals import PendingActionStore
        record = PendingActionStore(_kernel()._persistence).get(approval_id)
        if record is None:
            return None
        return {"approval_id": record.approval_id, "status": record.status, "action_sha256": record.action_sha256,
                "required_signatures": record.required_signatures, "signatures_collected": record.signatures_collected}

    @router.get("/forge")
    async def forge_state() -> Dict[str, Any]:
        from rct_control_plane import tool_forge
        forge = _forge()
        return {
            "gaps": tool_forge.find_gaps(_kernel()._persistence),
            "proposals": [{**p.to_dict(with_code=False), "approval": _approval_state(p.approval_id)} for p in forge.list_proposals()],
            "tools": forge.list_tools(include_disabled=True),
            "limits": {"allowed_imports": sorted(tool_forge.ALLOWED_IMPORTS), "min_asserts": tool_forge.MIN_ASSERTS,
                       "run_timeout_s": tool_forge.RUN_TIMEOUT_S, "max_code_chars": tool_forge.MAX_CODE_CHARS},
        }

    @router.get("/forge/proposals/{proposal_id}")
    async def forge_proposal(proposal_id: str) -> Dict[str, Any]:
        proposal = _forge().get(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="no such proposal")
        return {**proposal.to_dict(), "approval": _approval_state(proposal.approval_id)}

    @router.post("/forge/propose")
    async def forge_propose(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Writes (the model) or takes (`code`) a candidate tool and checks it. A model call when no code is given."""
        from rct_control_plane.tool_forge import ForgeError
        code = payload.get("code")
        try:
            proposal = await _forge().propose(str(payload.get("name", "")).strip(), str(payload.get("spec", "")).strip(),
                                              str(payload.get("smoke_test", "")), code=str(code) if code else None,
                                              gap=payload.get("gap") if isinstance(payload.get("gap"), dict) else None)
        except ForgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"the model could not write the tool: {type(exc).__name__}") from exc
        return proposal.to_dict(with_code=False)

    @router.post("/forge/proposals/{proposal_id}/request")
    async def forge_request(proposal_id: str, request: Request) -> Dict[str, Any]:
        from rct_control_plane.tool_forge import ForgeError
        try:
            record = _forge().request_activation(proposal_id, namespace=getattr(request.state, "delentia_user", None) or "forge")
        except ForgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"approval_id": record.approval_id, "action_sha256": record.action_sha256,
                "how": f"sign it where the approver key is: delentia approvals approve {record.approval_id} --key <key> (or paste the signed JSON on the Approvals page), then activate"}

    @router.post("/forge/activate")
    async def forge_activate(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane.approvals import ApprovalError
        try:
            return _forge().activate(str(payload.get("approval_id", "")).strip())
        except ApprovalError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/forge/tools/{name}/off")
    async def forge_off(name: str) -> Dict[str, Any]:
        if not _forge().deactivate(name):
            raise HTTPException(status_code=404, detail="no active tool with that name")
        return {"turned_off": name}

    @router.post("/forge/tools/{name}/run")
    async def forge_run(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            raise HTTPException(status_code=400, detail="args must be an object")
        return _forge().run(name, args)

    # ------------------------------------------------------------------
    # Round 62: hooks, the skill curator, memory suggestions and trajectories. The owner's pages; nothing here can approve or sign.
    # ------------------------------------------------------------------
    def _hooks() -> Any:
        from rct_control_plane.hooks import HookRegistry
        return HookRegistry(_kernel()._persistence)

    @router.get("/hooks")
    async def hooks_state() -> Dict[str, Any]:
        from rct_control_plane import hooks
        listed = _hooks().list()
        return {"enabled": hooks.enabled(), "hooks": [{**h, "approval": _approval_state(h.get("approval_id"))} for h in listed],
                "limits": {"points": list(hooks.POINTS), "max_code_chars": hooks.MAX_CODE_CHARS, "run_timeout_s": hooks.RUN_TIMEOUT_S,
                           "allowed_imports": sorted(hooks.forge.ALLOWED_IMPORTS)}}

    @router.get("/hooks/{name}")
    async def hook_detail(name: str) -> Dict[str, Any]:
        found = next((h for h in _hooks().list(include_code=True) if h["name"] == name), None)
        if found is None:
            raise HTTPException(status_code=404, detail="no such hook")
        return {**found, "approval": _approval_state(found.get("approval_id"))}

    @router.post("/hooks/propose")
    async def hook_propose(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane.hooks import HookError
        try:
            return _hooks().propose(str(payload.get("name", "")).strip(), str(payload.get("code", "")), str(payload.get("description", "")))
        except HookError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/hooks/activate")
    async def hook_activate(payload: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane.approvals import ApprovalError
        try:
            return _hooks().activate(str(payload.get("approval_id", "")).strip())
        except ApprovalError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/hooks/{name}/request")
    async def hook_request(name: str, request: Request) -> Dict[str, Any]:
        from rct_control_plane.hooks import HookError
        try:
            record = _hooks().request_activation(name, namespace=getattr(request.state, "delentia_user", None) or "hooks")
        except HookError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"approval_id": record.approval_id, "action_sha256": record.action_sha256,
                "how": f"sign it where the approver key is: delentia approvals approve {record.approval_id} --key <key>, then activate"}

    @router.post("/hooks/{name}/disable")
    async def hook_disable(name: str) -> Dict[str, Any]:
        if not _hooks().disable(name):
            raise HTTPException(status_code=404, detail="no active hook with that name")
        return {"disabled": name}

    @router.get("/curator")
    async def curator_state() -> Dict[str, Any]:
        from rct_control_plane import skill_curator
        library = _skills()
        report = skill_curator.review(library)
        return {**report, "archived": [s.to_dict() | {"solution": None} for s in library.list_archived(100)], "kinds_with_evidence": list(skill_curator.EVIDENCE_KINDS)}

    @router.post("/curator/apply")
    async def curator_apply(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        from rct_control_plane import skill_curator
        kinds = skill_curator.EVIDENCE_KINDS + (("stale",) if payload.get("include_stale") else ())
        return skill_curator.apply(_skills(), _kernel()._persistence, kinds)

    @router.post("/curator/skills/{skill_id}/unarchive")
    async def curator_unarchive(skill_id: str) -> Dict[str, Any]:
        if not _skills().unarchive(skill_id):
            raise HTTPException(status_code=404, detail="no archived skill with that id")
        return {"unarchived": skill_id}

    @router.get("/suggestions")
    async def suggestions_state(status: str = Query("pending")) -> Dict[str, Any]:
        """What the runtime offered to remember for people (memory_nudge.py): the owner sees that and what, and may throw one away; only the person it came from can keep it (in chat)."""
        from rct_control_plane import memory_nudge
        if status not in ("pending", "accepted", "dismissed", "expired"):
            raise HTTPException(status_code=400, detail="unknown status")
        rows = memory_nudge.MemoryCandidates(_kernel()._persistence).list(None, status, limit=100)
        return {"enabled": memory_nudge.enabled(), "status": status, "suggestions": [{k: r[k] for k in ("id", "namespace", "text", "kind", "status", "created_at")} for r in rows]}

    @router.post("/suggestions/{candidate_id}/dismiss")
    async def suggestion_dismiss(candidate_id: str) -> Dict[str, Any]:
        from rct_control_plane import memory_nudge
        try:
            return memory_nudge.MemoryCandidates(_kernel()._persistence).dismiss(candidate_id, None)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/trajectories")
    async def trajectories_state(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
        from rct_control_plane import trajectories
        recent = []
        for row in list(trajectories._rows())[-limit:][::-1]:
            recent.append({"id": row.get("id"), "at": row.get("at"), "person": row.get("person"), "model": row.get("model"), "goal": str(row.get("goal"))[:160],
                           "tools": [s["tool"] for s in row.get("steps", [])], "stopped_reason": row.get("stopped_reason"), "verified": row.get("verified"), "tainted": row.get("tainted")})
        return {"recording": trajectories.enabled(), "directory": str(trajectories.directory()), "stats": trajectories.stats(), "recent": recent,
                "how": "set DELENTIA_RECORD_TRAJECTORIES=1 on the host to record; `delentia trajectories export <file> --exclude-tainted` writes JSON Lines"}

    # ------------------------------------------------------------------
    # Round 56: governance in one place (governance_view.py). Read-only: nothing here approves, signs or changes a setting.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Round 57: checkpoints of files the agent wrote (checkpoints.py). Reading is open; a rollback is a write, so it is the signed-in person's act and is audited.
    # ------------------------------------------------------------------
    def _checkpoints() -> Any:
        from rct_control_plane.checkpoints import CheckpointStore
        return CheckpointStore(_kernel()._persistence)

    @router.get("/checkpoints")
    async def checkpoints_list(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        store = _checkpoints()
        rows = store.list(limit=limit)
        for row in rows:
            for key in ("before_sha", "after_sha"):
                row[key] = (row[key] or "")[:16] or None
        return {"checkpoints": rows, "status": store.status()}

    @router.get("/checkpoints/{checkpoint_id}/diff")
    async def checkpoints_diff(checkpoint_id: int) -> Dict[str, Any]:
        from rct_control_plane.checkpoints import CheckpointError
        try:
            return {"diff": _checkpoints().diff(checkpoint_id)}
        except CheckpointError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/checkpoints/{checkpoint_id}/rollback")
    async def checkpoints_rollback(checkpoint_id: int, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from rct_control_plane.checkpoints import CheckpointError
        try:
            return _checkpoints().rollback(checkpoint_id, force=bool((payload or {}).get("force")))
        except CheckpointError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/governance")
    async def governance_overview() -> Dict[str, Any]:
        from rct_control_plane import governance_view
        with _connect() as conn:
            return governance_view.overview(conn)

    @router.get("/governance/events")
    async def governance_events(category: str = Query("attention"), q: Optional[str] = Query(None, max_length=80),
                                limit: int = Query(50, ge=1, le=300), before_id: Optional[int] = Query(None, ge=1)) -> Dict[str, Any]:
        from rct_control_plane import governance_view
        try:
            with _connect() as conn:
                return governance_view.events(conn, category=category, query=q, limit=limit, before_id=before_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/governance/events/{audit_id}")
    async def governance_event(audit_id: int) -> Dict[str, Any]:
        from rct_control_plane import governance_view
        with _connect() as conn:
            detail = governance_view.event_detail(conn, audit_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="no such audit row")
        return detail

    @router.get("/governance/signatures")
    async def governance_signatures(status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
        from rct_control_plane import governance_view
        if status is not None and status not in ("PENDING", "APPROVED", "REJECTED", "EXECUTED"):
            raise HTTPException(status_code=400, detail="status must be PENDING, APPROVED, REJECTED or EXECUTED")
        return governance_view.signature_ledger(_kernel()._persistence, status=status, limit=limit)

    @router.get("/governance/approvers")
    async def governance_approvers() -> Dict[str, Any]:
        from rct_control_plane import governance_view
        with _connect() as conn:
            return governance_view.approver_keys(conn)

    @router.get("/governance/identities")
    async def governance_identities() -> Dict[str, Any]:
        from rct_control_plane import governance_view
        return governance_view.identities()

    @router.get("/governance/decisions")
    async def governance_decisions(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
        """The human sign-offs RCTDB keeps in architect_decisions (signed approvals, signed rejections, policy changes)."""
        rows = _kernel()._persistence.list_architect_decisions(limit=limit * 4)
        kinds = ("signed_approval", "signed_rejection", "policy_change")
        out = [{"id": r.get("id"), "type": r.get("decision_type"), "description": r.get("description"), "at": r.get("created_at"),
                "before": _loads(r.get("jitna_before")), "after": _loads(r.get("jitna_after"))}
               for r in rows if r.get("decision_type") in kinds]
        return {"decisions": out[:limit]}

    @router.get("/governance/audit/verify")
    async def governance_verify() -> Dict[str, Any]:
        """Re-verify the whole chain (signatures too when the public key is known) and every episode's signature, now."""
        from rct_control_plane import governance_view
        with _connect() as conn:
            return governance_view.verify_deep(conn)

    @router.get("/governance/audit/witnesses")
    async def governance_witnesses() -> Dict[str, Any]:
        """How well the log is protected right now (which witnesses hold a recent head, how many rows are newer than the newest anchor)."""
        from rct_control_plane import audit_witness
        with _connect() as conn:
            return audit_witness.status(conn)

    @router.post("/governance/audit/check-witnesses")
    async def governance_check_witnesses() -> Dict[str, Any]:
        """Ask every configured witness what it holds and compare it with this chain (the addresses come from the host's configuration, never from the request)."""
        import asyncio as _asyncio
        from rct_control_plane import audit_witness
        try:
            def run() -> Any:
                with _connect() as conn:
                    return audit_witness.check_witnesses(conn)
            report = await _asyncio.to_thread(run)
        except (audit_witness.WitnessError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="the witness configuration is unusable (see `delentia audit-chain witness-status` on the host)") from exc
        if not report:
            raise HTTPException(status_code=409, detail="no witness is configured (DELENTIA_AUDIT_WITNESSES); tier A3 is off")
        return {"witnesses": report, "ok": all(r["ok"] for r in report)}

    @router.post("/governance/audit/check-witness")
    async def governance_check_witness() -> Dict[str, Any]:
        """Compare every chain head the outside witness holds with this chain. The witness address is the host's own
        configuration (never taken from the request, so this cannot be pointed at another server)."""
        import httpx
        from rct_control_plane import governance_view
        from rct_control_plane.autonomous_scheduler import ANCHOR_KEY_ID_ENV, ANCHOR_URL_ENV
        url, key_id = os.getenv(ANCHOR_URL_ENV), os.getenv(ANCHOR_KEY_ID_ENV)
        if not url or not key_id:
            raise HTTPException(status_code=409, detail=f"no witness is configured ({ANCHOR_URL_ENV} and {ANCHOR_KEY_ID_ENV}); tier A3 is off")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                reply = await client.get(f"{url.rstrip('/')}/v1/audit/anchor/{key_id}", params={"limit": 1000})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"the witness could not be reached ({type(exc).__name__})") from exc
        if reply.status_code != 200:
            raise HTTPException(status_code=502, detail=f"the witness answered {reply.status_code}")
        with _connect() as conn:
            return {"witness": url, "key_id": key_id, **governance_view.check_witness(conn, reply.json())}

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
