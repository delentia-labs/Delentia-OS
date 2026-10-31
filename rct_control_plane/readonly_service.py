"""Opt-in, single-workspace budget service. No generic agent routes or writes.

Policy is operator-owned startup configuration, never request data. This is an
API boundary, not OS isolation against an operator modifying files/hard links.
"""
from __future__ import annotations

import os
import json
import sqlite3
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import Field
from starlette.responses import JSONResponse

from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.evidence_assessment import EvidenceDecision
from rct_control_plane.evidence_requirement import parse_requirement
from rct_control_plane.verified_budget import QuoteEvidence, digest, strict_json

ROUTE = "/v1/agent/readonly/budget"


class BudgetRequest(PlanItem):
    schema_version: Literal["1"]
    executor_version: Literal["verified_budget_v1"]
    workspace_id: str = Field(min_length=1, max_length=80)
    budget: str = Field(min_length=1, max_length=100)
    evidence: QuoteEvidence


class ConfirmRequest(PlanItem):
    schema_version: Literal["1"]
    version: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicReceipt(PlanItem):
    component_id: str
    contract_id: str
    namespace: str
    run_version: int
    plan_sha256: str
    ordinal: int
    previous_sha256: str
    output: dict[str, Any]
    output_sha256: str
    recorded_ns: str
    hashed_payload_json: str
    receipt_sha256: str


class PublicContract(PlanItem):
    id: str
    actor: str
    workspace_id: str
    version: int
    state: Literal["plan_ready", "waiting_for_input", "running", "waiting_for_clarification", "criteria_satisfied", "interrupted"]
    plan_sha256: str
    policy_sha256: str
    plan: dict[str, Any]
    differences: list[dict[str, Any]]
    receipts: list[PublicReceipt]
    execution_status: Literal["not_started", "partial", "incomplete", "complete"]
    report: dict[str, Any] | None
    verified: bool
    evidence_decision: EvidenceDecision | None = None


class BudgetResult(PlanItem):
    schema_version: Literal["1"] = "1"
    executor_version: Literal["verified_budget_v1"] = "verified_budget_v1"
    verification_scope: Literal["document_bytes_and_same_currency_arithmetic"] = "document_bytes_and_same_currency_arithmetic"
    contract: PublicContract


class ServiceError(PlanItem):
    schema_version: Literal["1"] = "1"
    error: Literal["unauthenticated", "forbidden", "not_found", "conflict", "invalid_request", "unavailable", "unsupported_platform", "request_failed"]


def error_response(status):
    code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict",
            400: "invalid_request", 422: "invalid_request", 503: "unavailable", 501: "unsupported_platform"}.get(status, "request_failed")
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(ServiceError(error=code).model_dump(), status, headers=headers)


class ServicePolicy(PlanItem):
    schema_version: Literal["1"]
    policy_version: int = Field(default=1, ge=1)
    workspace_id: str = Field(min_length=1, max_length=80)
    workspace_root: str
    actor_files: dict[str, list[str]]
    evidence_requirements: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)

    def binding_payload(self):
        # Preserve existing policy digests when the optional gate is absent.
        return self.model_dump(exclude={"evidence_requirements"} if not self.evidence_requirements else set())


def load_policy(location: str | None = None) -> ServicePolicy | None:
    location = location or os.environ.get("DELENTIA_READONLY_POLICY")
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
    for actor, files in policy.evidence_requirements.items():
        if actor not in policy.actor_files or set(files) - set(policy.actor_files[actor]):
            raise ValueError("evidence requirements must belong to authorized actor files")
        for relative, value in files.items():
            requirement = parse_requirement(value)
            if any(o.locator != relative for o in requirement.observations):
                raise ValueError("evidence observation locator differs from authorized file")
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
            or (scope.get("method") == "GET" and re.fullmatch(ROUTE + r"/[0-9a-f]{32}", scope.get("path", "")))
            or (scope.get("method") == "POST" and re.fullmatch(ROUTE + r"/[0-9a-f]{32}/confirm", scope.get("path", "")))
        )
        if not allowed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4403})
            else:
                await error_response(403)(scope, receive, send)
            return
        rejected = False
        started = False

        async def normalized_send(message):
            nonlocal rejected, started
            if message["type"] == "http.response.start":
                started = True
                if message["status"] >= 400:
                    rejected = True
                    await error_response(message["status"])(scope, receive, send)
                    return
            if not rejected:
                await send(message)
        try:
            await self.app(scope, receive, normalized_send)
        except sqlite3.Error:
            if started:
                raise
            # A persistence error must not become a success or trigger replay.
            await error_response(503)(scope, receive, send)


def public_result(contract, actor, policy):
    receipts = contract.get("execution_receipts", [])
    complete = contract.get("execution_status") == "complete" and contract["state"] == "criteria_satisfied"
    if complete and len(receipts) != len(contract["plan"]["components"]):
        raise HTTPException(409, "complete state lacks component receipts")
    # The digest covers the stored plan including the server workspace. It is
    # an opaque confirmation token here, not a hash of this redacted view.
    plan = {k: v for k, v in contract["plan"].items() if k != "workspace"}
    return BudgetResult(contract=PublicContract(
        id=contract["id"], actor=actor, workspace_id=policy.workspace_id,
        version=contract["version"], state=contract["state"], plan_sha256=contract["plan_sha256"],
        policy_sha256=digest(policy.binding_payload()), plan=plan,
        differences=contract.get("differences", []), receipts=[{
            **r, "recorded_ns": str(r["recorded_ns"]),
            "hashed_payload_json": json.dumps({k: v for k, v in r.items() if k != "receipt_sha256"},
                sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        } for r in receipts],
        execution_status=contract.get("execution_status", "not_started"),
        report=contract.get("execution_report"), verified=complete,
        evidence_decision=contract.get("evidence_decision"),
    ))


def install_route(app, policy: ServicePolicy | None, loop_factory):
    if policy is None:
        return
    from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
    policy_path = os.environ.get("DELENTIA_READONLY_POLICY")
    policy_hash = digest(policy.binding_payload())

    def authorize(request):
        # Reread the pinned operator policy on every operation. Changes revoke
        # access immediately; activating the replacement requires a restart.
        try:
            current = load_policy(policy_path)
        except (OSError, ValueError):
            raise HTTPException(503, "service policy unavailable") from None
        if current is None or digest(current.binding_payload()) != policy_hash:
            raise HTTPException(409, "policy changed; restart service")
        actor = getattr(request.state, "delentia_user", None)
        if not actor or actor == "shared" or actor not in policy.actor_files:
            raise HTTPException(403, "actor not authorized")
        return actor

    def backend(actor):
        loop = loop_factory(actor)
        return loop, IntentContractStore(loop._persistence, actor)

    def authorized_contract(store, contract_id, actor):
        try:
            contract = store.get(contract_id)
        except IntentContractError:
            raise HTTPException(404, "contract unavailable") from None
        expected = {"profile": "readonly_budget_v1", "actor": actor,
                    "workspace_id": policy.workspace_id, "workspace_root": str(Path(policy.workspace_root).resolve()),
                    "executor": "verified_budget_v1", "policy_sha256": policy_hash}
        if contract.get("service_binding") != expected:
            raise HTTPException(403, "contract does not belong to this profile/policy")
        plan = contract["plan"]
        semantic = plan.get("semantic_planning", {})
        if (plan["workspace"] != expected["workspace_root"] or semantic.get("executor") != expected["executor"]
                or semantic.get("quote_evidence", {}).get("relative_path") not in policy.actor_files[actor]):
            raise HTTPException(403, "contract source or executor no longer authorized")
        return contract

    @app.post(ROUTE, response_model=BudgetResult)
    async def budget(payload: BudgetRequest, request: Request):
        actor = authorize(request)
        from rct_control_plane.verified_budget import supports_verified_reads
        if not supports_verified_reads():
            raise HTTPException(501, "verified reads require a POSIX backend with no-follow support")
        if (payload.workspace_id != policy.workspace_id
                or payload.evidence.relative_path not in policy.actor_files[actor]):
            raise HTTPException(403, "workspace/file not authorized")
        from rct_control_plane.semantic_plan import validate_budget
        try:
            validate_budget(payload.budget)
        except ValueError:
            raise HTTPException(422, "invalid same-currency budget") from None
        requirement = policy.evidence_requirements.get(actor, {}).get(payload.evidence.relative_path)
        if requirement is not None:
            parsed = parse_requirement(requirement)
            if any(o.sha256 != payload.evidence.sha256 for o in parsed.observations):
                raise HTTPException(409, "evidence differs from operator-bound observation")
        _, store = backend(actor)
        # Persist binding in the same INSERT as the plan: no unbound-contract
        # window, no second write that can attach authority to a generic plan.
        binding = {"profile": "readonly_budget_v1", "actor": actor, "workspace_id": policy.workspace_id,
                   "workspace_root": str(Path(policy.workspace_root).resolve()),
                   "executor": "verified_budget_v1", "policy_sha256": policy_hash}
        contract = store.create("Compare quote with budget", [{"kind": "json_object"}],
            Path(policy.workspace_root), {"semantic_plan": {
                "budget": payload.budget, "quote_evidence": payload.evidence.model_dump(),
            }}, service_binding=binding, evidence_requirement=requirement)
        return public_result(contract, actor, policy)

    @app.get(ROUTE + "/{contract_id}", response_model=BudgetResult)
    async def status(contract_id: str, request: Request):
        actor = authorize(request)
        _, store = backend(actor)
        return public_result(authorized_contract(store, contract_id, actor), actor, policy)

    @app.post(ROUTE + "/{contract_id}/confirm", response_model=BudgetResult)
    async def confirm(contract_id: str, payload: ConfirmRequest, request: Request):
        actor = authorize(request)
        from rct_control_plane.verified_budget import supports_verified_reads
        if not supports_verified_reads():
            raise HTTPException(501, "verified reads require a POSIX backend with no-follow support")
        loop, store = backend(actor)
        contract = authorized_contract(store, contract_id, actor)
        if (contract["version"] != payload.version or contract["plan_sha256"] != payload.plan_sha256
                or contract["state"] != "plan_ready"):
            raise HTTPException(409, "confirm the current unexecuted plan version/digest")
        try:
            # Existing CAS claim prevents two concurrent confirmations from
            # dispatching twice. Running/interrupted contracts cannot replay.
            await loop.continue_intent(contract_id, payload.version)
        except IntentContractError:
            raise HTTPException(409, "contract changed; reload status") from None
        return public_result(authorized_contract(store, contract_id, actor), actor, policy)


@asynccontextmanager
async def readonly_lifespan(app):
    """No general scheduler, gateway pollers, cron delivery or model warmup."""
    yield
