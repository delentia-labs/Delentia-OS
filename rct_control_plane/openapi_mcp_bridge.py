"""
Round 74: any HTTP service that publishes an OpenAPI document becomes a set of tools for the agent, through the gate the agent already has for MCP servers.

This is the open-core seam. The public runtime does not contain the private services and does not call them behind the owner's back; it has ONE generic way to use a service the owner points it at:

    ~/.delentia/mcp_servers.json
    {"servers": {"reflexion": {"command": "python",
                               "args": ["-m", "rct_control_plane.openapi_mcp_bridge", "--name", "reflexion", "--base-url", "http://127.0.0.1:9115"],
                               "read_only_tools": ["get_sessions", "get_health"]}}}

The bridge is a small MCP server (stdio) that reads <base-url>/openapi.json and offers one tool per operation (`get_sessions`, `post_start`, ...). Because it is an MCP server, EVERYTHING in external_mcp.py applies
without a line of new gate code: tools are named mcp__reflexion__<tool>; each call is judged by the FDIA gate and the owner's policy and audited; a tool the owner did not list in `read_only_tools` waits for a human
signature on every call (a service cannot make the agent change something just by offering an operation); results are screened as third-party content and taint the episode; descriptions are screened (a poisoned
OpenAPI summary drops that tool); the tool list can be pinned with `tools_sha256`.

What the bridge itself enforces:
  * it talks to ONE base URL (http only on loopback, otherwise https and --allow-remote), never follows a redirect, and URL-quotes every path value, so a path argument cannot steer the request to another host or path;
  * methods GET/POST/PUT/PATCH/DELETE only; the documentation routes of the service itself are skipped; at most --max-ops operations;
  * a bearer credential only from a NAMED environment variable (--auth-env), never from an argument;
  * the response is capped (100 KB) and returned as {"status", "body"}.
`--print-config` prints the server entry with `read_only_tools` set to the GET operations: GET is read-only by the HTTP rule, which is the OWNER's judgement to accept (a sloppy service can change state on a GET); review the list.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

MAX_BODY_CHARS = 100_000
SKIP_PATHS = ("/openapi", "/docs", "/redoc")
METHODS = ("get", "post", "put", "patch", "delete")
_TYPES = {"integer": int, "number": float, "boolean": bool, "string": str, "object": dict, "array": list}


class BridgeError(ValueError):
    pass


def check_base_url(url: str, allow_remote: bool = False) -> str:
    parts = urlsplit(url.strip())
    loopback = parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1")
    if not (loopback or (parts.scheme == "https" and allow_remote and parts.hostname)):
        raise BridgeError("the base URL must be http on this machine (127.0.0.1, localhost) or https with --allow-remote")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise BridgeError("the base URL must not carry credentials, a query or a fragment")
    return url.rstrip("/")


def tool_name(method: str, path: str, taken: set) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"\{([^}]*)\}", r"\1", path)).strip("_").lower() or "root"
    name = f"{method}_{slug}"[:56]
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}_{n}", n + 1
    taken.add(candidate)
    return candidate


def operations(spec: Dict[str, Any], max_ops: int = 80) -> List[Dict[str, Any]]:
    """[{name, method, path, summary, parameters: [{name, in, required, type}], body}] from an OpenAPI document."""
    out: List[Dict[str, Any]] = []
    taken: set = set()
    for path, item in sorted((spec.get("paths") or {}).items()):
        if any(path.startswith(skip) for skip in SKIP_PATHS) or not isinstance(item, dict):
            continue
        shared = item.get("parameters") or []
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict) or len(out) >= max_ops:
                continue
            params = []
            for p in list(shared) + list(op.get("parameters") or []):
                if isinstance(p, dict) and p.get("in") in ("path", "query") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(p.get("name", ""))):
                    schema = p.get("schema") or {}
                    params.append({"name": p["name"], "in": p["in"], "required": bool(p.get("required")) or p["in"] == "path", "type": schema.get("type", "string")})
            body = "application/json" in ((op.get("requestBody") or {}).get("content") or {})
            summary = " ".join(str(op.get("summary") or op.get("description") or "").split())[:400]
            out.append({"name": tool_name(method, path, taken), "method": method, "path": path, "summary": summary, "parameters": params, "body": body})
    return out


def build_request(base: str, op: Dict[str, Any], arguments: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any], Optional[Any]]:
    """(method, url, query, json body) for a call. Path values are URL-quoted completely, so they can neither add path segments nor change the host."""
    path = op["path"]
    query: Dict[str, Any] = {}
    for p in op["parameters"]:
        if p["name"] not in arguments or arguments[p["name"]] is None:
            if p["required"]:
                raise BridgeError(f"missing required argument {p['name']!r}")
            continue
        value = arguments[p["name"]]
        if p["in"] == "path":
            path = path.replace("{" + p["name"] + "}", quote(str(value), safe=""))
        else:
            query[p["name"]] = value
    return op["method"].upper(), base + path, query, (arguments.get("body") if op["body"] else None)


def _python_type(name: str) -> Any:
    return _TYPES.get(name, str)


def make_function(op: Dict[str, Any], call: Any) -> Any:
    """A function whose signature is the operation's parameters, so the MCP SDK derives the tool's input schema from it."""
    parameters = []
    for p in op["parameters"]:
        kind = _python_type(p["type"])
        parameters.append(inspect.Parameter(p["name"], inspect.Parameter.KEYWORD_ONLY, annotation=kind if p["required"] else Optional[kind], default=inspect.Parameter.empty if p["required"] else None))
    if op["body"]:
        parameters.append(inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[dict], default=None))

    def fn(**kwargs: Any) -> Any:
        return call(op, kwargs)
    fn.__signature__ = inspect.Signature(parameters)                              # type: ignore[attr-defined]
    fn.__annotations__ = {p.name: p.annotation for p in parameters}
    fn.__name__ = op["name"]
    return fn


def fetch_spec(base: str, openapi_url: Optional[str] = None) -> Dict[str, Any]:
    import httpx
    response = httpx.get(openapi_url or base + "/openapi.json", timeout=20.0, follow_redirects=False)
    response.raise_for_status()
    spec: Dict[str, Any] = response.json()
    return spec


def print_config(name: str, base: str, ops: List[Dict[str, Any]], python: str = "python") -> str:
    reads = [o["name"] for o in ops if o["method"] == "get"]
    return json.dumps({"servers": {name: {"command": python, "args": ["-m", "rct_control_plane.openapi_mcp_bridge", "--name", name, "--base-url", base],
                                          "read_only_tools": reads, "timeout_s": 60}}}, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--openapi-url", default="")
    ap.add_argument("--max-ops", type=int, default=80)
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--auth-env", default="", help="NAME of an environment variable holding a bearer token for the service")
    ap.add_argument("--print-config", action="store_true")
    args = ap.parse_args(argv)
    try:
        base = check_base_url(args.base_url, args.allow_remote)
        if args.auth_env and not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", args.auth_env):
            raise BridgeError("--auth-env takes the NAME of an environment variable, never the token")
        ops = operations(fetch_spec(base, args.openapi_url or None), args.max_ops)
    except (BridgeError, Exception) as exc:                                         # noqa: BLE001 - say why on stderr; stdout belongs to the protocol
        print(f"openapi bridge: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 2
    if args.print_config:
        print(print_config(args.name, base, ops))
        return 0

    import httpx
    from mcp.server.mcpserver import MCPServer
    server = MCPServer(f"openapi-{args.name}")
    token = os.environ.get(args.auth_env) if args.auth_env else None

    def call(op: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        method, url, query, body = build_request(base, op, arguments)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = httpx.request(method, url, params=query, json=body, headers=headers, timeout=30.0, follow_redirects=False)
        try:
            parsed: Any = response.json()
        except ValueError:
            parsed = response.text[:MAX_BODY_CHARS]
        text = json.dumps(parsed, ensure_ascii=False, default=str)
        if len(text) > MAX_BODY_CHARS:
            parsed = {"truncated": True, "text": text[:MAX_BODY_CHARS]}
        return {"status": response.status_code, "body": parsed}

    for op in ops:
        server.add_tool(make_function(op, call), name=op["name"], description=(op["summary"] + f" [{op['method'].upper()} {op['path']}]").strip())
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
