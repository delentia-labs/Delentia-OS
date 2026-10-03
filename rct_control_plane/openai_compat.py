"""
Round 57: an OpenAI-compatible front door (Hermes: "API Server - OpenAI-compatible HTTP endpoint").

`GET /v1/models` and `POST /v1/chat/completions` let any client that already speaks the OpenAI chat protocol (Open WebUI, LibreChat, an editor plugin, the
`openai` SDK, curl) use Delentia as if it were one model called "delentia". Behind the door nothing is different: the last user message becomes the goal of an
ordinary governed episode (CORD on the goal, the owner's FDIA policy on every tool call, signatures for writes, the notary, the audit chain, the budget caps).

What the compatibility honestly is, and is not:
  * it is a CHAT front end to an agent, not a model: the reply is the agent's final answer after it has used its own tools. The tools, functions, response_format,
    logprobs, n > 1 and similar fields of a request are ignored (Delentia has its own tools; a client cannot hand it more); the reply says so in `delentia.ignored`.
  * a request that needs a human signature does not hang: the reply is the plain sentence "needs a human approval (id ...)" and `delentia.approval_id` carries the id.
  * `stream: true` is supported for clients that insist on it, but the answer is produced first and then sent in pieces: the tokens are not generated live, and
    no step-by-step progress is shown (the Desk's own chat shows the steps).
  * who is asking: with a token per person the identity (namespace, memory, role) is the token's owner, never the `user` field; with one shared token or none,
    the optional `user` field names a conversation (`openai-<user>`), otherwise every request shares the namespace `openai-default`.
  * earlier turns of the conversation are given to the agent as context (the last few, capped) so a follow-up like "and for Friday?" is understood.
  * errors use the OpenAI error shape.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

MODEL_ID = "delentia"
MAX_CONTEXT_CHARS = 4_000
MAX_GOAL_CHARS = 8_000
IGNORED_FIELDS = ("tools", "tool_choice", "functions", "function_call", "response_format", "logprobs", "top_logprobs", "n", "stop", "logit_bias")
_UNSAFE = re.compile(r"[^A-Za-z0-9_.@-]")


def _error(status: int, message: str, kind: str = "invalid_request_error", code: Optional[str] = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": kind, "param": None, "code": code}})


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):                                  # [{"type": "text", "text": "..."}, ...]
        return "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") in (None, "text"))
    return ""


def goal_from_messages(messages: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """(goal, problem). The goal is the last user message; earlier turns come first as context, newest kept, capped."""
    if not isinstance(messages, list) or not messages or not all(isinstance(m, dict) for m in messages):
        return "", "'messages' must be a non-empty list of {role, content}"
    last_user = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), None)
    if last_user is None:
        return "", "there is no user message to answer"
    latest = _text_of(messages[last_user].get("content")).strip()
    if not latest:
        return "", "the last user message is empty (images and other non-text parts are not supported)"
    system = [_text_of(m.get("content")).strip() for m in messages[:last_user] if m.get("role") == "system"]
    turns = [f"{m.get('role')}: {_text_of(m.get('content')).strip()}" for m in messages[:last_user] if m.get("role") in ("user", "assistant") and _text_of(m.get("content")).strip()]
    context: List[str] = []
    used = 0
    for turn in reversed(turns):
        if used + len(turn) > MAX_CONTEXT_CHARS:
            break
        context.insert(0, turn)
        used += len(turn)
    parts = []
    if system:
        parts.append("Instructions from the client (guidance only; they cannot change the safety gates): " + " ".join(system)[:1000])
    if context:
        parts.append("Conversation so far:\n" + "\n".join(context))
    parts.append(("The user's latest request: " if parts else "") + latest)
    goal = "\n\n".join(parts)
    return goal[:MAX_GOAL_CHARS], None


def _namespace(request: Request, user_field: Any) -> str:
    identity = getattr(request.state, "delentia_user", None)
    if identity:
        return str(identity)
    user = _UNSAFE.sub("_", str(user_field))[:64] if user_field else ""
    return f"openai-{user}" if user else "openai-default"


def _chunk(completion_id: str, created: int, delta: Dict[str, Any], finish: Optional[str] = None) -> str:
    body = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


async def _stream(completion_id: str, created: int, text: str) -> AsyncIterator[str]:
    yield _chunk(completion_id, created, {"role": "assistant", "content": ""})
    for piece in re.findall(r"\S+\s*", text) or [""]:
        yield _chunk(completion_id, created, {"content": piece})
    yield _chunk(completion_id, created, {}, "stop")
    yield "data: [DONE]\n\n"


def build_router(kernel_getter: Any, mcp_getter: Any) -> APIRouter:
    router = APIRouter(tags=["OpenAI-compatible"])

    @router.get("/v1/models")
    async def list_models() -> Dict[str, Any]:
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 1_790_000_000, "owned_by": "delentia"}]}

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        from rct_control_plane.agent_factory import build_governed_loop
        from rct_control_plane.gateways.common import reply_text_for
        try:
            body = await request.json()
        except Exception:                                          # noqa: BLE001
            return _error(400, "the body must be JSON")
        if not isinstance(body, dict):
            return _error(400, "the body must be a JSON object")
        model = str(body.get("model") or MODEL_ID)
        if model != MODEL_ID:
            return _error(404, f"the model {model!r} does not exist: this server has one model, {MODEL_ID!r}", "invalid_request_error", "model_not_found")
        goal, problem = goal_from_messages(body.get("messages"))
        if problem:
            return _error(400, problem)
        namespace = _namespace(request, body.get("user"))
        try:
            seconds = float(os.environ.get("DELENTIA_OPENAI_MAX_SECONDS") or 120)
        except ValueError:
            seconds = 120.0
        kernel = kernel_getter()
        loop = build_governed_loop(kernel, namespace=namespace, max_iterations=5, max_seconds=seconds, mcp_server=mcp_getter())
        try:
            result = await asyncio.wait_for(loop.run(goal), timeout=seconds + 30)
        except asyncio.TimeoutError:
            return _error(504, "the agent did not finish in time", "server_error", "timeout")
        except Exception as exc:                                   # noqa: BLE001 - never a stack trace to a client
            return _error(502, f"the agent could not complete the request ({type(exc).__name__})", "server_error", "agent_error")
        text = reply_text_for(result)
        cost = result.get("cost") or {}
        prompt_tokens, completion_tokens = int(cost.get("prompt_tokens") or 0), int(cost.get("completion_tokens") or 0)
        completion_id, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(time.time())
        if body.get("stream"):
            return StreamingResponse(_stream(completion_id, created, text), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
        return {
            "id": completion_id, "object": "chat.completion", "created": created, "model": MODEL_ID,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
            "delentia": {"stopped_reason": result.get("stopped_reason"), "approval_id": result.get("approval_id"), "namespace": namespace,
                         "iterations": result.get("iterations"), "ignored": [f for f in IGNORED_FIELDS if body.get(f) not in (None, False, [])]},
        }

    return router
