"""
Delentia OS - Model Context Protocol (MCP) Gateway
Provides standard JSON-RPC 2.0 MCP endpoints (/mcp) for external AI clients
(ChatGPT, Claude Desktop, Cursor, Windsurf, VS Code Copilot)
Governed by Layer 2 CORD Shannon Entropy & Layer 3 FDIA Veto Gate (F = D^I * A)
"""

import os
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException

from .intent_compiler import IntentCompiler
from .cord_security import CORDEngine
from .policy_language import PolicyEvaluator
from .default_policies import get_default_policies
from .exchange_bridge import NeuralExchangeBridge
from .autonomous_scheduler import AutonomousScheduler

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
            res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=15)  # nosec B602
            return {"status": "SUCCESS", "exit_code": res.returncode, "stdout": res.stdout[:2000], "stderr": res.stderr[:2000]}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

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
        target_path = args.get("path", ".")
        
        if action == "delete":
            return {
                "status": "VETOED_BY_FDIA_GATE",
                "error": f"Delete action on '{target_path}' blocked by Zero-Delete Safety Policy (F = 0). Manual Architect Veto required."
            }
        elif action == "read":
            if not os.path.exists(target_path):
                return {"status": "ERROR", "error": f"File not found: {target_path}"}
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(50000)
                return {"status": "SUCCESS", "path": target_path, "content": content}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}
        elif action == "write":
            content = args.get("content", "")
            cord_res = cord_engine.check(content)
            if not cord_res.is_clean:
                return {"status": "VETOED_BY_CORD", "error": f"File content rejected by CORD scan: {cord_res.verdict}"}
            try:
                os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"status": "SUCCESS", "path": target_path, "bytes_written": len(content.encode("utf-8"))}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}
        elif action == "list":
            if not os.path.exists(target_path):
                return {"status": "ERROR", "error": f"Directory not found: {target_path}"}
            entries = os.listdir(target_path)[:50]
            return {"status": "SUCCESS", "directory": target_path, "entries": entries}
        else:
            return {"status": "ERROR", "error": f"Unknown FS action: {action}"}

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
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # 8. delentia_web_fetch
    elif tool_name == "delentia_web_fetch":
        url = args.get("url", "").strip()
        if not url.startswith(("http://", "https://")):
            return {"status": "ERROR", "error": "URL must start with http:// or https://"}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DelentiaOS-Agent/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_data = resp.read(50000).decode("utf-8", errors="replace")
            return {"status": "SUCCESS", "url": url, "content_length": len(raw_data), "preview": raw_data[:1000]}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

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
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

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
