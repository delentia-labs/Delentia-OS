"""Opt-in, single-workspace budget service. No generic agent routes or writes.

Policy is operator-owned startup configuration, never request data. This is an
API boundary, not OS isolation against an operator modifying files/hard links.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import Field
from starlette.responses import JSONResponse

from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.verified_budget import QuoteEvidence, strict_json

ROUTE = "/v1/agent/readonly/budget"


class BudgetRequest(PlanItem):
    schema_version: Literal["1"]
    executor_version: Literal["verified_budget_v1"]
    workspace_id: str = Field(min_length=1, max_length=80)
    budget: str = Field(min_length=1, max_length=100)
    evidence: QuoteEvidence


class BudgetResult(PlanItem):
    schema_version: Literal["1"] = "1"
    executor_version: Literal["verified_budget_v1"] = "verified_budget_v1"
    verification_scope: Literal["document_bytes_and_same_currency_arithmetic"] = "document_bytes_and_same_currency_arithmetic"
    result: dict[str, Any]


class ServicePolicy(PlanItem):
    schema_version: Literal["1"]
    workspace_id: str = Field(min_length=1, max_length=80)
    workspace_root: str
    actor_files: dict[str, list[str]]


def load_policy() -> ServicePolicy | None:
    location = os.environ.get("DELENTIA_READONLY_POLICY")
    if not location:
        return None
    policy = ServicePolicy.model_validate(strict_json(Path(location).read_text(encoding="utf-8")))
    from rct_control_plane.intent_contract import _file
    from rct_control_plane.mcp_server import REPO_ROOT
    root = Path(policy.workspace_root)
    if not root.is_absolute() or root.is_symlink() or root.resolve() != REPO_ROOT:
        raise ValueError("read-only policy root must match the process workspace")
    if not policy.actor_files or any(not actor or actor == "shared" or not paths for actor, paths in policy.actor_files.items()):
        raise ValueError("read-only policy requires named actors and explicit files")
    for paths in policy.actor_files.values():
        for relative in paths:
            _file(root, relative)
    return policy


class ReadOnlyBoundary:
    def __init__(self, app, policy: ServicePolicy):
        self.app = app
        self.policy = policy

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        allowed = scope["type"] == "http" and (
            (scope.get("method") == "GET" and scope.get("path") == "/health")
            or (scope.get("method") == "POST" and scope.get("path") == ROUTE)
        )
        if not allowed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4403})
            else:
                await JSONResponse({"schema_version": "1", "error": "route_outside_readonly_profile"}, 403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def install_route(app, policy: ServicePolicy | None, runner):
    if policy is None:
        return

    @app.post(ROUTE, response_model=BudgetResult)
    async def budget(payload: BudgetRequest, request: Request):
        actor = getattr(request.state, "delentia_user", None)
        if (not actor or actor == "shared" or actor not in policy.actor_files
                or payload.workspace_id != policy.workspace_id
                or payload.evidence.relative_path not in policy.actor_files[actor]):
            raise HTTPException(403, "actor/workspace/file not authorized")
        from rct_control_plane.semantic_plan import validate_budget
        try:
            validate_budget(payload.budget)
        except ValueError as exc:
            raise HTTPException(422, "invalid same-currency budget") from exc
        # Fixed intent and criteria: callers cannot select a different planner,
        # tool, executor, namespace, or a general-agent fallback.
        result = await runner({
            "goal": "Compare quote with budget",
            "acceptance_criteria": [{"kind": "json_object"}],
            "planning_context": {"semantic_plan": {
                "budget": payload.budget, "quote_evidence": payload.evidence.model_dump(),
            }},
        }, request)
        return BudgetResult(result=result)


@asynccontextmanager
async def readonly_lifespan(app):
    """No general scheduler, gateway pollers, cron delivery or model warmup."""
    yield
