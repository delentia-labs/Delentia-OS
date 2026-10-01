"""
Delentia OS - Model Context Protocol (MCP) Gateway
Provides standard JSON-RPC 2.0 MCP endpoints (/mcp) for external AI clients
(ChatGPT, Claude Desktop, Cursor, Windsurf, VS Code Copilot)
Governed by Layer 2 CORD Shannon Entropy & Layer 3 FDIA Veto Gate (F = D^I * A)
"""

import ipaddress
import logging
import os
import shlex
import socket
import sys
import json
import subprocess
from urllib.parse import urlsplit
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException

from .intent_compiler import IntentCompiler
from .cord_security import CORDEngine
from .policy_language import PolicyEvaluator
from .default_policies import get_default_policies
from .exchange_bridge import NeuralExchangeBridge
from .autonomous_scheduler import AutonomousScheduler

logger = logging.getLogger(__name__)

# MCP Specification Constants
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "delentia-os-mcp-gateway"
SERVER_VERSION = "2.0.0"

mcp_router = APIRouter(prefix="/mcp", tags=["Model Context Protocol (MCP)"])

# Initialize Internal Engines
compiler = IntentCompiler()
cord_engine = CORDEngine()
exchange_bridge = NeuralExchangeBridge()
scheduler = AutonomousScheduler()

policy_evaluator = PolicyEvaluator()
for p in get_default_policies():
    policy_evaluator.add_rule(p)

# ============================================================================
# MCP TOOL DEFINITIONS (Layer 9 Universal Adapter Catalog - 10 Core Tools)
# ============================================================================

DELENTIA_MCP_TOOLS = [
    {
        "name": "delentia_compile_intent",
        "description": "Compile natural language intent into a structured, validated Delentia Intent with risk profile in <1ms.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "natural_language": {"type": "string", "description": "The natural language instruction or user goal"},
                "user_tier": {"type": "string", "enum": ["FREE", "PRO", "ENTERPRISE", "INTERNAL"], "default": "PRO"}
            },
            "required": ["natural_language"]
        }
    },
    {
        "name": "delentia_fdia_gate_eval",
        "description": "Evaluate safety governance using the master FDIA Gate equation (F = D^I * A). Computes architect veto status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent_type": {"type": "string", "description": "Intent classification"},
                "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "default": "MEDIUM"},
                "architect_approval": {"type": "integer", "enum": [0, 1], "default": 1}
            },
            "required": ["intent_type"]
        }
    },
    {
        "name": "delentia_cord_entropy_scan",
        "description": "Scan text/code for prompt injection, jailbreaks, and high Shannon entropy (Base64/Hex obfuscation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {"type": "string", "description": "Code snippet or prompt text to scan"}
            },
            "required": ["payload"]
        }
    },
    {
        "name": "delentia_execute_safe_shell",
        "description": "Execute terminal commands protected by CORD Entropy scan and FDIA Zero-Delete safety rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run on local machine"},
                "cwd": {"type": "string", "description": "Working directory path", "default": "."}
            },
            "required": ["command"]
        }
    },
    {
        "name": "delentia_system_health",
        "description": "Query 10-layer Delentia OS kernel status, active microservices, and memory statistics.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "delentia_workspace_fs",
        "description": "Safe filesystem operations (read, write, list) with Zero-Delete protection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "list", "delete"], "description": "FS action"},
                "path": {"type": "string", "description": "Relative or absolute file path"},
                "content": {"type": "string", "description": "File content for write action"}
            },
            "required": ["action", "path"]
        }
    },
    {
        "name": "delentia_git_ops",
        "description": "Perform Git operations (status, diff, log, commit) with audit logging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "diff", "log", "commit"], "description": "Git action"},
                "message": {"type": "string", "description": "Commit message if action is commit"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "delentia_web_fetch",
        "description": "Fetch content or text summary from public web URLs safely.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch content from"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "delentia_cron_scheduler",
        "description": "Manage autonomous scheduled background tasks (list, trigger, register).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "trigger"], "description": "Scheduler action"},
                "task_id": {"type": "string", "description": "Task ID to trigger (if action is trigger)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "delentia_neural_exchange",
        "description": "Manage files and assets in the /exchange directory bridge with SHA-256 integrity verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "save", "read"], "description": "Exchange action"},
                "category": {"type": "string", "enum": ["projects", "audio", "video", "logs", "datasets", "podcasts", "all"], "default": "all"},
                "filename": {"type": "string", "description": "Filename for save or read"},
                "content": {"type": "string", "description": "Text content to save"}
            },
            "required": ["action"]
        }
    }
]

# ============================================================================
# TOOL EXECUTION HANDLERS (Governed by FDIA & CORD)
# ============================================================================

# Round 52: the gateway's three powerful tools (shell, filesystem, fetch) were bounded only by a
# pattern denylist. They now have real boundaries, each a constant the operator can widen
# deliberately with an environment variable and nothing a caller can widen.
GATEWAY_ROOT_ENV = "DELENTIA_GATEWAY_ROOT"
GATEWAY_SHELL_ALLOW_ENV = "DELENTIA_GATEWAY_SHELL_ALLOW"          # extra executable names, comma separated
GATEWAY_FETCH_PRIVATE_ENV = "DELENTIA_GATEWAY_ALLOW_PRIVATE_FETCH"  # "1" lets fetch reach private/loopback addresses
_BLOCKED_NAME_PARTS = (".env", "_secret", "credentials.json", "vault_master.key", ".pem", "id_rsa")
# Executables the shell tool will start (no shell is involved: the command is split into
# arguments and run directly, so pipes, redirects and `&&` are not interpreted).
_SHELL_ALLOWED = {
    "git": "git", "python": sys.executable, "python3": sys.executable, "pytest": "pytest", "ruff": "ruff",
    "mypy": "mypy", "node": "node", "npm": "npm", "npx": "npx", "pip": "pip",
}


def _split_command(cmd: str) -> list:
    """Arguments of a command line. POSIX rules everywhere except Windows, where shlex keeps the
    quotes in a token, so one enclosing pair of matching quotes is removed to give the program
    what a Windows shell would have given it."""
    if os.name != "nt":
        return shlex.split(cmd)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in shlex.split(cmd, posix=False)]


def _workspace_root() -> str:
    configured = os.environ.get(GATEWAY_ROOT_ENV)
    return os.path.abspath(configured) if configured else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _in_workspace(path: str) -> Optional[str]:
    """The absolute path if it is inside the gateway workspace (lexically AND after following
    symlinks), else None. Relative paths are taken from the workspace root."""
    root = _workspace_root()
    candidate = os.path.normpath(os.path.join(root, path))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    real_root = os.path.realpath(root)
    real = os.path.realpath(candidate)
    if real != real_root and not real.startswith(real_root + os.sep):
        return None
    return candidate


def _blocked_name(path: str) -> bool:
    lowered = path.lower()
    return any(part in lowered for part in _BLOCKED_NAME_PARTS)


class _FetchTarget:
    """A validated destination: the exact IP address that was checked, plus the name to present."""

    def __init__(self, scheme: str, hostname: str, ip: str, port: int, path: str, ips: Optional[list] = None):
        self.scheme, self.hostname, self.ip, self.port, self.path = scheme, hostname, ip, port, path
        self.ips = ips or [ip]           # every address that passed the check, IPv4 first


def _resolve_public_target(url: str) -> Optional[_FetchTarget]:
    """The destination for an http(s) URL if every address its host resolves to is public (or the operator
    allowed private ones), else None. The connection is made to the address checked here, so a second DNS
    answer (rebinding) cannot send the request somewhere else."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        return None
    checked = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if os.environ.get(GATEWAY_FETCH_PRIVATE_ENV) != "1" and (
                ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return None
        if str(ip) not in checked:
            checked.append(str(ip))
    if not checked:
        return None
    checked.sort(key=lambda text: ":" in text)          # IPv4 first
    path = parts.path or "/"
    return _FetchTarget(parts.scheme, parts.hostname, checked[0], port, path + (f"?{parts.query}" if parts.query else ""), checked)


def _fetch_pinned(target: _FetchTarget, limit: int = 50000) -> str:
    """GET the target over a connection to its validated IP. HTTPS presents the host name for SNI and
    certificate checks. Redirects are not followed (a redirect could point at a private address)."""
    import http.client
    import ssl
    raw = None
    last_error: Optional[OSError] = None
    for ip in target.ips:                                  # only addresses that passed the check
        try:
            raw = socket.create_connection((ip, target.port), timeout=10)
            break
        except OSError as exc:
            last_error = exc
    if raw is None:
        raise last_error or OSError("no address to connect to")
    if target.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(target.ip, target.port, timeout=10)
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=target.hostname)
    else:
        conn = http.client.HTTPConnection(target.ip, target.port, timeout=10)
        conn.sock = raw
    try:
        conn.request("GET", target.path, headers={"Host": target.hostname, "User-Agent": "DelentiaOS-Agent/2.0"})
        response = conn.getresponse()
        if 300 <= response.status < 400:
            raise ValueError("the server answered with a redirect, which is not followed")
        return response.read(limit).decode("utf-8", errors="replace")
    finally:
        conn.close()


def execute_delentia_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    # 1. delentia_compile_intent
    if tool_name == "delentia_compile_intent":
        nl = args.get("natural_language", "")
        tier = args.get("user_tier", "PRO")
        cord_res = cord_engine.check(nl)
        if not cord_res.is_clean:
            from .websocket_manager import WS_MANAGER
            WS_MANAGER.broadcast_sync(
                "SECURITY_VETO",
                {
                    "status": "VETOED_BY_CORD",
                    "error": f"CORD Security blocked input: {cord_res.verdict}",
                    "findings": [getattr(f, "pattern_id", str(f)) for f in cord_res.findings]
                },
                intent_id="malicious_attack"
            )
            return {
                "status": "VETOED_BY_CORD",
                "error": f"CORD Security blocked input: {cord_res.verdict}",
                "findings": [getattr(f, "pattern_id", str(f)) for f in cord_res.findings]
            }
        user_id = args.get("user_id", "mcp-client-01")
        compiled = compiler.compile(nl, user_id=user_id, user_tier=tier)
        intent_obj = compiled.intent if hasattr(compiled, "intent") and compiled.intent else None
        compiled_id = getattr(compiled, "intent_id", "compiled_intent")
        resolved_id = getattr(intent_obj, "id", compiled_id) if intent_obj else compiled_id
        return {
            "status": "SUCCESS",
            "intent_id": resolved_id,
            "intent_type": (intent_obj.intent_type.value if hasattr(intent_obj.intent_type, "value") else str(intent_obj.intent_type)) if intent_obj else "GENERAL",
            "risk_profile": (intent_obj.risk_profile.value if hasattr(intent_obj.risk_profile, "value") else str(intent_obj.risk_profile)) if intent_obj else "MEDIUM",
            "compilation_time_ms": compiled.compilation_time_ms if hasattr(compiled, "compilation_time_ms") else 0.5
        }

    # 2. delentia_fdia_gate_eval
    elif tool_name == "delentia_fdia_gate_eval":
        risk = args.get("risk_level", "MEDIUM")
        a_factor = int(args.get("architect_approval", 1))
        d_val = 0.9 if risk in ["LOW", "MEDIUM"] else 0.5
        i_val = 1.0
        fdia_score = (d_val ** i_val) * a_factor
        is_allowed = (a_factor == 1) and (fdia_score >= 0.5)
        return {
            "status": "APPROVED" if is_allowed else "VETOED_HARD_BLOCK",
            "equation": "F = D^I * A",
            "computed_f_score": round(fdia_score, 4),
            "a_factor": a_factor,
            "is_execution_allowed": is_allowed,
            "governance_decision": "Execute safely" if is_allowed else "Architect Veto: Execution blocked"
        }

    # 3. delentia_cord_entropy_scan
    elif tool_name == "delentia_cord_entropy_scan":
        payload = args.get("payload", "")
        cord_res = cord_engine.check(payload)
        return {
            "is_clean": cord_res.is_clean,
            "verdict": cord_res.verdict.value if hasattr(cord_res.verdict, "value") else str(cord_res.verdict),
            "shannon_entropy_score": round(cord_res.entropy_score, 4),
            "findings": [getattr(f, "pattern_id", str(f)) for f in cord_res.findings]
        }

    # 4. delentia_execute_safe_shell
    elif tool_name == "delentia_execute_safe_shell":
        cmd = args.get("command", "").strip()
        cwd = args.get("cwd", ".")
        destructive_patterns = ["rm -rf", "format", "del /f", "drop database", "shutdown", "mkfs"]
        if any(p in cmd.lower() for p in destructive_patterns):
            return {
                "status": "VETOED_BY_FDIA_GATE",
                "error": "Destructive command blocked by Zero-Delete Safety Policy (F = 0). Human approval required.",
                "command": cmd
            }
        cord_res = cord_engine.check(cmd)
        if not cord_res.is_clean:
            return {
                "status": "VETOED_BY_CORD",
                "error": f"Command contains suspicious patterns: {cord_res.verdict}"
            }
        try:
            argv = _split_command(cmd)
        except ValueError:
            return {"status": "ERROR", "error": "the command could not be split into arguments (unbalanced quote?)"}
        allowed = dict(_SHELL_ALLOWED)
        allowed.update({n.strip(): n.strip() for n in os.environ.get(GATEWAY_SHELL_ALLOW_ENV, "").split(",") if n.strip()})
        executable = allowed.get(os.path.basename(argv[0]).lower().removesuffix(".exe")) if argv else None
        if executable is None:
            return {"status": "VETOED_BY_SHELL_ALLOWLIST",
                    "error": f"only these programs can be started here: {', '.join(sorted(allowed))}. "
                             f"The operator can add more with {GATEWAY_SHELL_ALLOW_ENV}."}
        ws_root = _workspace_root()
        work_dir = os.path.normpath(os.path.join(ws_root, str(cwd)))
        if work_dir != ws_root and not work_dir.startswith(ws_root + os.sep):
            return {"status": "VETOED_BY_WORKSPACE_BOUNDARY", "error": "cwd must be a directory inside the gateway workspace"}
        real_ws_root = os.path.realpath(ws_root)
        work_dir = os.path.realpath(work_dir)
        if (work_dir != real_ws_root and not work_dir.startswith(real_ws_root + os.sep)) or not os.path.isdir(work_dir):
            return {"status": "VETOED_BY_WORKSPACE_BOUNDARY", "error": "cwd must be a directory inside the gateway workspace"}
        try:
            res = subprocess.run([executable, *argv[1:]], cwd=work_dir, capture_output=True, text=True, timeout=15)  # nosec B603
            return {"status": "SUCCESS", "exit_code": res.returncode, "stdout": res.stdout[:2000], "stderr": res.stderr[:2000]}
        except Exception:
            logger.exception("delentia tool failed")
            return {"status": "ERROR", "error": "the tool failed; the details are in the server log"}

    # 5. delentia_system_health
    elif tool_name == "delentia_system_health":
        return {
            "status": "healthy",
            "version": SERVER_VERSION,
            "engine": "Delentia 10-Layer Cognitive OS",
            "active_layers": ["L1_Transport", "L2_CORD_Security", "L3_FDIA_Gate", "L9_Universal_Adapter"],
            "total_mcp_tools": len(DELENTIA_MCP_TOOLS),
            "exchange_root": exchange_bridge.root_dir,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # 6. delentia_workspace_fs (Zero-Delete Protection)
    elif tool_name == "delentia_workspace_fs":
        action = args.get("action", "list")
        target_path = str(args.get("path", "."))

        if action == "delete":
            return {
                "status": "VETOED_BY_FDIA_GATE",
                "error": f"Delete action on '{target_path}' blocked by Zero-Delete Safety Policy (F = 0). Manual Architect Veto required."
            }
        if action not in ("read", "write", "list"):
            return {"status": "ERROR", "error": f"Unknown FS action: {action}"}

        # Round 52: one boundary for all three actions. The path is normalised and must still be
        # inside the workspace (lexically, then after following symlinks) before any file is touched.
        fs_root = _workspace_root()
        safe_path = os.path.normpath(os.path.join(fs_root, target_path))
        if safe_path != fs_root and not safe_path.startswith(fs_root + os.sep):
            return {"status": "VETOED_BY_WORKSPACE_BOUNDARY", "error": "the path is outside the gateway workspace"}
        fs_real_root = os.path.realpath(fs_root)
        safe_path = os.path.realpath(safe_path)
        if safe_path != fs_real_root and not safe_path.startswith(fs_real_root + os.sep):
            return {"status": "VETOED_BY_WORKSPACE_BOUNDARY", "error": "the path is outside the gateway workspace"}
        if action != "list" and _blocked_name(target_path):
            return {"status": "VETOED_BY_WORKSPACE_BOUNDARY", "error": "the path names secret material"}

        if action == "read":
            if not os.path.exists(safe_path):
                return {"status": "ERROR", "error": f"File not found: {target_path}"}
            try:
                with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(50000)
                return {"status": "SUCCESS", "path": target_path, "content": content}
            except Exception:
                logger.exception("delentia tool failed")
                return {"status": "ERROR", "error": "the tool failed; the details are in the server log"}
        if action == "write":
            content = args.get("content", "")
            cord_res = cord_engine.check(content)
            if not cord_res.is_clean:
                return {"status": "VETOED_BY_CORD", "error": f"File content rejected by CORD scan: {cord_res.verdict}"}
            try:
                os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"status": "SUCCESS", "path": target_path, "bytes_written": len(content.encode("utf-8"))}
            except Exception:
                logger.exception("delentia tool failed")
                return {"status": "ERROR", "error": "the tool failed; the details are in the server log"}
        if not os.path.isdir(safe_path):
            return {"status": "ERROR", "error": f"Directory not found: {target_path}"}
        return {"status": "SUCCESS", "directory": target_path, "entries": os.listdir(safe_path)[:50]}

    # 7. delentia_git_ops
    elif tool_name == "delentia_git_ops":
        action = args.get("action", "status")
        try:
            if action == "status":
                res = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, timeout=10)
                return {"status": "SUCCESS", "git_status": res.stdout}
            elif action == "diff":
                res = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, timeout=10)
                return {"status": "SUCCESS", "git_diff": res.stdout}
            elif action == "log":
                res = subprocess.run(["git", "log", "-n", "5", "--oneline"], capture_output=True, text=True, timeout=10)
                return {"status": "SUCCESS", "git_log": res.stdout}
            elif action == "commit":
                msg = args.get("message", "Automated commit by Delentia MCP Hub")
                subprocess.run(["git", "add", "-A"], capture_output=True, text=True, timeout=10)
                res = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, timeout=10)
                return {"status": "SUCCESS", "output": res.stdout}
            else:
                return {"status": "ERROR", "error": f"Unknown Git action: {action}"}
        except Exception:
            logger.exception("delentia tool failed")
            return {"status": "ERROR", "error": "the tool failed; the details are in the server log"}

    # 8. delentia_web_fetch
    elif tool_name == "delentia_web_fetch":
        url = str(args.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            return {"status": "ERROR", "error": "URL must start with http:// or https://"}
        target = _resolve_public_target(url)
        if target is None:
            return {"status": "VETOED_BY_NETWORK_BOUNDARY",
                    "error": "the address does not resolve, or resolves to a private, loopback or link-local address"}
        try:
            raw_data = _fetch_pinned(target)
            return {"status": "SUCCESS", "url": url, "content_length": len(raw_data), "preview": raw_data[:1000]}
        except Exception:
            logger.exception("delentia tool failed")
            return {"status": "ERROR", "error": "the tool failed; the details are in the server log"}

    # 9. delentia_cron_scheduler
    elif tool_name == "delentia_cron_scheduler":
        action = args.get("action", "list")
        if action == "list":
            return {"status": "SUCCESS", "tasks": scheduler.list_tasks()}
        elif action == "trigger":
            task_id = args.get("task_id", "")
            return scheduler.trigger_task(task_id)
        else:
            return {"status": "ERROR", "error": f"Unknown scheduler action: {action}"}

    # 10. delentia_neural_exchange
    elif tool_name == "delentia_neural_exchange":
        action = args.get("action", "list")
        if action == "list":
            category = args.get("category", "all")
            files = exchange_bridge.list_files(category)
            return {"status": "SUCCESS", "exchange_root": exchange_bridge.root_dir, "total_files": len(files), "files": files}
        elif action == "save":
            category = args.get("category", "projects")
            filename = args.get("filename", f"asset_{int(datetime.now().timestamp())}.txt")
            content = args.get("content", "").encode("utf-8")
            saved = exchange_bridge.save_file(category, filename, content)
            return saved
        elif action == "read":
            category = args.get("category", "projects")
            filename = args.get("filename", "")
            file_info = exchange_bridge.read_file(category, filename)
            if file_info is None:
                return {"status": "ERROR", "error": f"File not found in {category}/{filename}"}
            return {"status": "SUCCESS", "category": category, "filename": filename, "sha256_hash": file_info["sha256_hash"], "content": file_info["content"].decode("utf-8", errors="replace")}
        else:
            return {"status": "ERROR", "error": f"Unknown exchange action: {action}"}

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ============================================================================
# FASTAPI ROUTE HANDLERS
# ============================================================================

@mcp_router.get("")
async def get_mcp_info():
    """Get MCP Server Info and Capabilities"""
    return {
        "mcp_version": MCP_PROTOCOL_VERSION,
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False}
        },
        "total_tools": len(DELENTIA_MCP_TOOLS),
        "endpoint_jsonrpc": "/mcp"
    }

@mcp_router.get("/tools")
async def get_mcp_tools_list():
    """List all registered Delentia MCP Tools"""
    return {"total_tools": len(DELENTIA_MCP_TOOLS), "tools": DELENTIA_MCP_TOOLS}

@mcp_router.post("")
async def handle_mcp_jsonrpc(request: Request):
    """
    Handle Standard JSON-RPC 2.0 MCP Protocol requests
    Supports 'initialize', 'tools/list', 'tools/call'
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if not method:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid Request: missing method"}
        }

    # 1. Initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION
                }
            }
        }

    # 2. tools/list
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": DELENTIA_MCP_TOOLS
            }
        }

    # 3. tools/call
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        result_data = execute_delentia_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result_data, default=str, indent=2)
                    }
                ],
                "isError": "error" in result_data or result_data.get("status") in ["VETOED_BY_FDIA_GATE", "VETOED_BY_CORD"]
            }
        }

    # 4. Unknown Method
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }
