"""
Round 55: tools from OTHER MCP servers, through the same gate as the built-in ones.

Hermes can use any MCP server. This runtime can too, with one difference that matters: an external tool is code and data
this project did not write, so everything about it is treated as untrusted until the owner says otherwise.

What the owner writes (``~/.delentia/mcp_servers.json`` or ``DELENTIA_MCP_SERVERS``)::

    {"servers": {
        "notes": {"command": "python", "args": ["notes_server.py"],
                  "env_vars": ["NOTES_TOKEN"],                   # NAMES of variables to pass on, never values
                  "read_only_tools": ["read_note"],              # the owner's word that these only read
                  "tools_sha256": "<digest from `delentia mcp inspect notes`>"},   # optional pin
        "docs":  {"url": "https://mcp.example.com/mcp", "headers_env": {"Authorization": "DOCS_MCP_AUTH"}}}}

What the runtime does with them:
  * names are ``mcp__<server>__<tool>`` so an external tool can never take the name of a built-in one;
  * every external tool is judged by the FDIA gate (and by the owner's policy, whose zero-trust fallback applies to a name it
    has no rule for) and every call is audited and notarised like any other;
  * a tool NOT listed in ``read_only_tools`` waits for a human signature on every call, so a server cannot make the agent
    change something just by offering a tool. A server's own "readOnlyHint" is ignored: it is the server's claim, not the owner's;
  * what comes back is third-party content: screened for instructions aimed at the model before the model reads it, and given
    the small model's second opinion when that is on;
  * tool descriptions go into the prompt, so they are screened too (a poisoned description is the known way to attack an agent
    through a tool list): a tool whose description carries an instruction is dropped and reported, never shown to the model;
  * ``tools_sha256`` pins the tool list: if the server's tools change after the owner looked at them, they are hidden until
    the owner re-pins (a server that turns hostile after being trusted);
  * a local server starts with a minimal environment plus only the variables the owner named, so it does not inherit
    credentials; a remote server must be https (or loopback) and its header values come from named variables;
  * a slow or dead server costs one timeout, not the episode, and its error is a normal tool error.

Not done: a persistent connection per server (each call opens a short session; fine for a few calls per episode, slow for
chatty servers), OAuth for remote servers, MCP resources/prompts, and sampling requests from a server (always refused).

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

PREFIX = "mcp__"
CONFIG_ENV = "DELENTIA_MCP_SERVERS"
DEFAULT_TIMEOUT_S = 30.0
MAX_TIMEOUT_S = 300.0
LIST_CACHE_TTL_S = 300.0
MAX_RESULT_CHARS = 200_000
MAX_DESCRIPTION_CHARS = 500
MAX_SCHEMA_CHARS = 6_000
MAX_TOOLS_PER_SERVER = 64

_SERVER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")        # no underscore: "__" separates server from tool
_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")


class ExternalMCPError(ValueError):
    """The configuration is not usable. Nothing from the file is exposed (fail closed)."""


@dataclass
class ServerSpec:
    name: str
    command: str = ""
    args: List[str] = field(default_factory=list)
    cwd: str = ""
    env_vars: List[str] = field(default_factory=list)
    url: str = ""
    headers_env: Dict[str, str] = field(default_factory=dict)
    read_only_tools: frozenset = frozenset()
    # Round 58: tools the owner vouches for as unable to send data anywhere (a local file reader). Only these keep working in an episode that has read outside text
    # (the taint gate); every other external tool then waits for a signature, because "read-only" says it changes nothing, not that it sends nothing.
    taint_exempt_tools: frozenset = frozenset()
    tools_sha256: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    enabled: bool = True
    region: str = ""                  # two-letter country code the owner declares for a remote server (data-sovereignty policy)


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "mcp_servers.json"


def _parse_server(name: str, raw: Any) -> ServerSpec:
    if not _SERVER_NAME.match(name):
        raise ExternalMCPError(f"server name {name!r}: use 1-24 lower-case letters, digits or '-' (no underscore)")
    if not isinstance(raw, dict):
        raise ExternalMCPError(f"server {name!r}: must be an object")
    known = {"command", "args", "cwd", "env_vars", "url", "headers_env", "read_only_tools", "taint_exempt_tools", "tools_sha256", "timeout_s", "enabled", "region"}
    extra = set(raw) - known
    if extra:
        # A field called "env" or "token" would invite a pasted secret; refuse unknown fields rather than ignore them.
        raise ExternalMCPError(f"server {name!r}: unknown field(s) {sorted(extra)}; credentials are passed as NAMES in env_vars / headers_env")
    command, url = str(raw.get("command") or "").strip(), str(raw.get("url") or "").strip()
    if bool(command) == bool(url):
        raise ExternalMCPError(f"server {name!r}: give exactly one of command (a local process) or url (a remote server)")
    args = raw.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ExternalMCPError(f"server {name!r}: args must be a list of strings")
    env_vars = raw.get("env_vars") or []
    if not isinstance(env_vars, list) or not all(isinstance(v, str) and _ENV_NAME.match(v) for v in env_vars):
        raise ExternalMCPError(f"server {name!r}: env_vars must list variable NAMES like NOTES_TOKEN, not values")
    headers_env = raw.get("headers_env") or {}
    if not isinstance(headers_env, dict) or not all(_HEADER_NAME.match(str(h)) and isinstance(v, str) and _ENV_NAME.match(v)
                                                    for h, v in headers_env.items()):
        raise ExternalMCPError(f"server {name!r}: headers_env maps a header name to the NAME of an environment variable")
    if url:
        low = url.lower()
        loopback = re.match(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", low)
        if not (low.startswith("https://") or loopback):
            raise ExternalMCPError(f"server {name!r}: a remote url must be https (plain http only for loopback)")
    ro = raw.get("read_only_tools") or []
    if not isinstance(ro, list) or not all(isinstance(t, str) and _TOOL_NAME.match(t) for t in ro):
        raise ExternalMCPError(f"server {name!r}: read_only_tools must list tool names")
    exempt = raw.get("taint_exempt_tools") or []
    if not isinstance(exempt, list) or not all(isinstance(t, str) and _TOOL_NAME.match(t) for t in exempt):
        raise ExternalMCPError(f"server {name!r}: taint_exempt_tools must list tool names")
    if set(exempt) - set(ro):
        raise ExternalMCPError(f"server {name!r}: taint_exempt_tools may only name tools that are also in read_only_tools")
    pin = str(raw.get("tools_sha256") or "").strip().lower()
    if pin and not re.fullmatch(r"[0-9a-f]{64}", pin):
        raise ExternalMCPError(f"server {name!r}: tools_sha256 must be a 64-character hex digest (see `delentia mcp inspect`)")
    try:
        timeout = float(raw.get("timeout_s", DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError) as exc:
        raise ExternalMCPError(f"server {name!r}: timeout_s must be a number") from exc
    return ServerSpec(name=name, command=command, args=list(args), cwd=str(raw.get("cwd") or ""), env_vars=list(env_vars), url=url,
                      headers_env={str(h): v for h, v in headers_env.items()}, read_only_tools=frozenset(ro), taint_exempt_tools=frozenset(exempt), tools_sha256=pin,
                      timeout_s=max(1.0, min(timeout, MAX_TIMEOUT_S)), enabled=bool(raw.get("enabled", True)),
                      region=str(raw.get("region") or "").strip().upper())


def load_servers(path: Optional[Path] = None) -> Dict[str, ServerSpec]:
    """The configured servers. No file = no servers. A file that cannot be read or has any invalid entry raises, so the
    caller exposes nothing rather than a half-checked list."""
    p = path or config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExternalMCPError(f"{p} cannot be read: {exc}") from exc
    servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        raise ExternalMCPError(f'{p}: expected {{"servers": {{...}}}}')
    return {name: _parse_server(name, raw) for name, raw in servers.items()}


def enabled_servers() -> Tuple[Dict[str, ServerSpec], str]:
    """(servers that are on, error text). A broken config gives no servers and says why."""
    try:
        return {n: s for n, s in load_servers().items() if s.enabled}, ""
    except ExternalMCPError as exc:
        return {}, str(exc)


# ---------------------------------------------------------------------------------------------------------------- names

def is_external(tool_name: str) -> bool:
    return isinstance(tool_name, str) and tool_name.startswith(PREFIX)


def qualified(server: str, tool: str) -> str:
    return f"{PREFIX}{server}__{tool}"


def split(tool_name: str) -> Optional[Tuple[str, str]]:
    if not is_external(tool_name):
        return None
    rest = tool_name[len(PREFIX):]
    server, sep, tool = rest.partition("__")
    return (server, tool) if sep and server and tool else None


def needs_approval(tool_name: str) -> bool:
    """An external tool waits for a human signature unless the owner listed it as read-only. A name that is not in the
    configuration at all also waits (it cannot run anyway)."""
    parts = split(tool_name)
    if parts is None:
        return False
    servers, _ = enabled_servers()
    spec = servers.get(parts[0])
    return spec is None or parts[1] not in spec.read_only_tools


def taint_exempt(tool_name: str) -> bool:
    """Did the owner vouch that this external tool cannot send data out, so it may run even after the episode read outside text?"""
    parts = split(tool_name)
    if parts is None:
        return False
    servers, _ = enabled_servers()
    spec = servers.get(parts[0])
    return spec is not None and parts[1] in spec.taint_exempt_tools


# ---------------------------------------------------------------------------------------------------------------- tool lists

_LIST_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]], List[str]]] = {}
LAST_ERRORS: Dict[str, str] = {}


def tools_digest(tools: List[Dict[str, Any]]) -> str:
    """Digest of what a server offers (names, descriptions, schemas), the thing the owner pins."""
    canonical = sorted(({"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("input_schema", {})}
                        for t in tools), key=lambda t: t["name"])
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clean_tool(server: str, raw: Any, screen: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    name = str(getattr(raw, "name", "") or "")
    if not _TOOL_NAME.match(name):
        return None, f"{server}: tool name {name!r} is not allowed"
    description = str(getattr(raw, "description", "") or "")
    schema = getattr(raw, "input_schema", None) or getattr(raw, "inputSchema", None) or {"type": "object", "properties": {}}
    schema_text = json.dumps(schema, default=str)
    if len(schema_text) > MAX_SCHEMA_CHARS:
        return None, f"{server}.{name}: input schema is larger than {MAX_SCHEMA_CHARS} characters"
    # The description and the schema are read by the model as part of the tool menu: treat both as third-party text.
    for label, text in (("description", description), ("input schema", schema_text)):
        hard = [f for f in screen.check(text, trusted=False) if f.severity == "hard"]
        if hard:
            return None, f"{server}.{name}: dropped, its {label} carries an instruction aimed at the model ({', '.join(sorted({f.pattern_id for f in hard}))})"
    return {"name": name, "description": description[:MAX_DESCRIPTION_CHARS], "input_schema": schema}, ""


def _stdio_params(spec: ServerSpec) -> Any:
    from mcp import StdioServerParameters
    from mcp.client.stdio import get_default_environment
    env = dict(get_default_environment())
    for var in spec.env_vars:
        if var in os.environ:
            env[var] = os.environ[var]
    command = sys.executable if spec.command in ("python", "python3") else spec.command
    return StdioServerParameters(command=command, args=list(spec.args), env=env, cwd=spec.cwd or None)


class _Session:
    """One short MCP session with a configured server (stdio process or streamable HTTP)."""

    def __init__(self, spec: ServerSpec):
        self.spec = spec
        self._stack: Any = None
        self.session: Any = None

    async def __aenter__(self) -> Any:
        from contextlib import AsyncExitStack
        from mcp import ClientSession
        self._stack = AsyncExitStack()
        try:
            if self.spec.command:
                from mcp.client.stdio import stdio_client
                errlog = open(os.devnull, "w")
                self._stack.callback(errlog.close)
                read, write = await self._stack.enter_async_context(stdio_client(_stdio_params(self.spec), errlog=errlog))
            else:
                import httpx2                          # the MCP SDK's own HTTP client package (a plain httpx client is refused by its type check)
                from mcp.client.streamable_http import streamable_http_client
                headers = {h: os.environ[v] for h, v in self.spec.headers_env.items() if v in os.environ}
                client = httpx2.AsyncClient(headers=headers, timeout=self.spec.timeout_s, follow_redirects=False)
                await self._stack.enter_async_context(client)
                streams = await self._stack.enter_async_context(streamable_http_client(self.spec.url, http_client=client))
                read, write = streams[0], streams[1]
            # No sampling / elicitation / roots callbacks: a server cannot ask this agent to call a model or read a directory.
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            return self.session
        except BaseException:
            await self._stack.aclose()
            raise

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()


async def list_server_tools(spec: ServerSpec, *, force: bool = False) -> Tuple[List[Dict[str, Any]], List[str]]:
    """(cleaned tools, problems). Cached; a server that fails gives no tools and a problem, never an exception."""
    cached = _LIST_CACHE.get(spec.name)
    if cached and not force and time.time() - cached[0] < LIST_CACHE_TTL_S:
        return cached[1], cached[2]
    from rct_control_plane.injection_screen import InjectionScreen
    screen = InjectionScreen()
    problems: List[str] = []
    tools: List[Dict[str, Any]] = []
    try:
        async def fetch() -> Any:
            async with _Session(spec) as session:
                return await session.list_tools()
        listed = await asyncio.wait_for(fetch(), timeout=spec.timeout_s)
        raw_tools = list(getattr(listed, "tools", []))[:MAX_TOOLS_PER_SERVER]
        for raw in raw_tools:
            cleaned, problem = _clean_tool(spec.name, raw, screen)
            if cleaned is None:
                problems.append(problem)
            else:
                tools.append(cleaned)
        if spec.tools_sha256:
            seen = tools_digest(tools)
            if seen != spec.tools_sha256:
                problems.append(f"{spec.name}: the tools it offers changed since they were pinned "
                                f"(pinned {spec.tools_sha256[:12]}..., now {seen[:12]}...); hidden until `delentia mcp inspect {spec.name}` is reviewed and re-pinned")
                tools = []
    except asyncio.TimeoutError:
        problems.append(f"{spec.name}: no answer within {spec.timeout_s:g}s when listing tools")
        tools = []
    except Exception as exc:                                  # a dead server must not stop the agent
        problems.append(f"{spec.name}: could not list tools ({type(exc).__name__}: {str(exc)[:160]})")
        tools = []
    _LIST_CACHE[spec.name] = (time.time(), tools, problems)
    LAST_ERRORS[spec.name] = "; ".join(problems)
    return tools, problems


def clear_cache() -> None:
    _LIST_CACHE.clear()
    LAST_ERRORS.clear()


# ---------------------------------------------------------------------------------------------------------------- calls

def _shape_result(server: str, tool: str, result: Any) -> Dict[str, Any]:
    texts: List[str] = [t for t in (getattr(c, "text", None) for c in (getattr(result, "content", None) or [])) if isinstance(t, str)]
    payload: Dict[str, Any] = {"external_mcp": {"server": server, "tool": tool}, "is_error": bool(getattr(result, "is_error", False))}
    structured = getattr(result, "structured_content", None)
    joined = "\n".join(texts)
    if structured is not None:
        payload["data"] = structured
    elif len(texts) == 1:
        try:
            parsed = json.loads(texts[0])
            payload["data"] = parsed
        except ValueError:
            payload["text"] = texts[0]
    else:
        payload["text"] = joined
    rendered = json.dumps(payload, default=str)
    if len(rendered) > MAX_RESULT_CHARS:
        payload = {"external_mcp": payload["external_mcp"], "is_error": payload["is_error"], "truncated": True,
                   "text": rendered[:MAX_RESULT_CHARS]}
    return payload


async def call_external_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    parts = split(tool_name)
    servers, config_error = enabled_servers()
    if config_error:
        return {"error": f"external MCP configuration is not usable: {config_error}"}
    if parts is None or parts[0] not in servers:
        return {"error": f"unknown external tool {tool_name!r}"}
    spec = servers[parts[0]]
    if not isinstance(tool_args, dict):
        return {"error": "tool_args must be an object"}
    if spec.url:
        # The arguments are data leaving the machine for a remote server: the owner's sovereignty policy (if any) decides.
        from rct_control_plane.egress_policy import check_egress
        allowed, reason, _sent, _record = check_egress(spec.url, json.dumps(tool_args, default=str), region=spec.region, operator=f"MCP server {spec.name}")
        if not allowed:
            return {"error": f"the sovereignty policy does not allow sending these arguments to {spec.name}: {reason}", "refused_by": "sovereignty_policy"}
        if _sent != json.dumps(tool_args, default=str):
            return {"error": f"the sovereignty policy would redact these arguments for {spec.name}; arguments for a remote MCP server are not redacted, "
                             "so the call is refused", "refused_by": "sovereignty_policy"}
    tools, _ = await list_server_tools(spec)
    if parts[1] not in {t["name"] for t in tools}:
        # Only tools that were listed, cleaned and (if pinned) matched are callable; the model cannot reach a hidden one by name.
        return {"error": f"{parts[1]!r} is not an available tool of server {spec.name!r}"}
    if not isinstance(tool_args, dict):
        return {"error": "tool_args must be an object"}
    try:
        async def run() -> Any:
            async with _Session(spec) as session:
                return await session.call_tool(parts[1], tool_args)
        result = await asyncio.wait_for(run(), timeout=spec.timeout_s)
    except asyncio.TimeoutError:
        return {"error": f"server {spec.name!r} did not answer within {spec.timeout_s:g}s", "external_mcp": {"server": spec.name, "tool": parts[1]}}
    except Exception as exc:
        return {"error": f"server {spec.name!r} failed ({type(exc).__name__}: {str(exc)[:200]})", "external_mcp": {"server": spec.name, "tool": parts[1]}}
    return _shape_result(spec.name, parts[1], result)


class ExternalToolHub:
    """Wraps the built-in tool server: the loop sees one menu, built-in tools first, external tools after."""

    def __init__(self, base: Any):
        self._base = base

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    async def list_tools(self) -> List[Any]:
        tools = list(await self._base.list_tools())
        servers, config_error = enabled_servers()
        if config_error:
            LAST_ERRORS["_config"] = config_error
        for spec in servers.values():
            listed, _ = await list_server_tools(spec)
            for t in listed:
                waits = "" if t["name"] in spec.read_only_tools else " Waits for a human signature on every call."
                tools.append(SimpleNamespace(
                    name=qualified(spec.name, t["name"]),
                    description=f"[external MCP server '{spec.name}', third-party] {t['description']}{waits}",
                    input_schema=t["input_schema"]))
        return tools

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> Any:
        if is_external(name):
            payload = await call_external_tool(name, arguments or {})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload, default=str))])
        return await self._base.call_tool(name, arguments, *args, **kwargs)


def maybe_wrap(mcp_server: Any) -> Any:
    """The loop's entry: wraps only when at least one server is configured (or the config is broken, so the problem shows)."""
    if isinstance(mcp_server, ExternalToolHub):
        return mcp_server
    servers, error = enabled_servers()
    if not servers and not error:
        return mcp_server
    return ExternalToolHub(mcp_server)


def inspect_server(name: str) -> Dict[str, Any]:
    """For `delentia mcp inspect`: what a server offers, what was dropped and why, and the digest to pin."""
    servers = load_servers()
    if name not in servers:
        raise ExternalMCPError(f"no server named {name!r} in {config_path()}")
    spec = servers[name]
    pinned = spec.tools_sha256
    spec.tools_sha256 = ""                                    # list without the pin so the owner can see what is there
    try:
        tools, problems = asyncio.run(list_server_tools(spec, force=True))
    finally:
        spec.tools_sha256 = pinned
    return {"server": name, "digest": tools_digest(tools) if tools else "", "tools": tools, "problems": problems,
            "read_only_declared": sorted(spec.read_only_tools), "pinned": bool(pinned), "pin_matches": bool(pinned) and pinned == tools_digest(tools)}
