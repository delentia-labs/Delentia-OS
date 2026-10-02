"""
Tool Forge: ALGO-39 Genesis grown from a scaffold into a governed way to gain a new capability (Round 54).

What Genesis did before: write a README and a .gitignore (`algo_39_genesis_engine`) and, given a spec, ask the model for
one function and run it once (`algo_39_genesis_synthesize_module`). Nothing decided WHEN a new capability was needed,
nothing kept what was made, nothing let a human accept it, and the agent could never call it. The master document says
the kernel "synthesises a new tool when it finds the system cannot do the task"; this is that loop, with the safety the
rest of the system has:

  1. GAP       find_gaps(): goals the agent finished but did not satisfy (the intent check said "not aligned": a refusal,
               "none of the tools can do that") and that came back more than once. Evidence from RCTDB, not a guess.
  2. PROPOSE   propose(): a spec, a function, and a smoke test that must contain at least two assertions that really call
               the function. The code is checked statically BEFORE it is run (allowed imports only, no files, network,
               eval, dunder access), then run in a separate Python process with a scrubbed environment and a timeout.
               A proposal that fails any step is kept as REJECTED_*, never deleted.
  3. APPROVE   request_activation(): a human has to sign, with an approver key, the exact code hash (approvals.py:
               Ed25519, roles and several signatures if the owner's policy says so). The agent cannot approve its own tool.
  4. USE       run(): the activated tool runs in its own process, one function call, JSON in and JSON out, the file's hash
               re-checked on every call. Disabled tools stay on record.

Scope, said plainly: PURE FUNCTIONS only (text, numbers, dates, small data transformations). A forged tool cannot read
a file, open a socket or import anything outside a short list. The static check is a speed bump and the separate process
with a timeout is the real limit; this is not a jail against a determined attacker who can also get a human to sign.
Model-written tests can be vacuous, which is why the human signs the code and the test together, by hash.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_IMPORTS = frozenset({
    "math", "json", "re", "datetime", "statistics", "itertools", "collections", "string", "decimal", "fractions",
    "textwrap", "typing", "functools", "operator", "unicodedata", "hashlib", "base64", "bisect", "heapq", "calendar", "difflib",
})
FORBIDDEN_NAMES = frozenset({
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars", "breakpoint", "exit", "quit",
    "getattr", "setattr", "delattr", "hasattr", "memoryview", "help", "dir", "type", "super", "object", "classmethod", "staticmethod",
})
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
MAX_CODE_CHARS = 8000
MAX_OUTPUT_CHARS = 20_000
RUN_TIMEOUT_S = 10.0
ACTIVATE_TOOL = "forge_activate_tool"          # the tool name recorded in the approval, so a signature binds to this action
MIN_ASSERTS = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forge_proposals (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    spec          TEXT NOT NULL,
    code          TEXT NOT NULL,
    smoke_test    TEXT NOT NULL,
    code_sha256   TEXT NOT NULL,
    status        TEXT NOT NULL,
    verification  TEXT NOT NULL DEFAULT '{}',
    gap           TEXT NOT NULL DEFAULT '{}',
    approval_id   TEXT,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS forged_tools (
    name          TEXT PRIMARY KEY,
    proposal_id   TEXT NOT NULL,
    code_sha256   TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    spec          TEXT NOT NULL,
    approval_id   TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    activated_at  REAL NOT NULL,
    calls         INTEGER NOT NULL DEFAULT 0
);
"""


class ForgeError(ValueError):
    pass


# ------------------------------------------------------------------ static check

def static_check(code: str, function_name: str) -> List[str]:
    """Reasons this code may not be run or activated; empty = it passed. Pure-function module: imports from a short
    list, function definitions and constants, no dunder access, no file/eval/exec names."""
    problems: List[str] = []
    if not code.strip():
        return ["the code is empty"]
    if len(code) > MAX_CODE_CHARS:
        return [f"the code is longer than {MAX_CODE_CHARS} characters"]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error on line {exc.lineno}"]
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if function_name not in defined:
        problems.append(f"it does not define a function named {function_name}")
    for top in tree.body:
        if isinstance(top, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            continue
        if isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str):
            continue
        if isinstance(top, ast.Assign) and all(isinstance(t, ast.Name) for t in top.targets) and isinstance(top.value, (ast.Constant, ast.Tuple, ast.List, ast.Dict, ast.Set)):
            continue
        problems.append(f"line {top.lineno}: only imports, functions and constants may sit at module level")
    problems.extend(_walk_problems(tree))
    return sorted(set(problems))


def _walk_problems(tree: ast.AST) -> List[str]:
    problems: List[str] = []
    for walked in ast.walk(tree):
        node: Any = walked
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"line {node.lineno}: import {alias.name} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"line {node.lineno}: import from {node.module or '.'} is not allowed")
            if any(a.name == "*" for a in node.names):
                problems.append(f"line {node.lineno}: import * is not allowed")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"line {node.lineno}: the name {node.id} is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            problems.append(f"line {node.lineno}: access to {node.attr} is not allowed")
        elif isinstance(node, (ast.Global, ast.AsyncFunctionDef, ast.ClassDef, ast.Await, ast.Yield, ast.YieldFrom)):
            problems.append(f"line {node.lineno}: {type(node).__name__} is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            problems.append(f"line {node.lineno}: a string containing __ is not allowed (format strings can read attributes)")
    return problems


def smoke_check(smoke_test: str, function_name: str) -> List[str]:
    """The smoke test must be assertions that really call the function (a test that asserts nothing proves nothing)."""
    try:
        tree = ast.parse(smoke_test)
    except SyntaxError as exc:
        return [f"the smoke test has a syntax error on line {exc.lineno}"]
    asserts = [n for n in tree.body if isinstance(n, ast.Assert)]
    calling = [a for a in asserts if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == function_name for c in ast.walk(a))]
    problems = [] if len(calling) >= MIN_ASSERTS else [f"the smoke test needs at least {MIN_ASSERTS} assertions that call {function_name} (found {len(calling)})"]
    for stmt in tree.body:
        if not isinstance(stmt, (ast.Assert, ast.Import, ast.ImportFrom, ast.Assign)):
            problems.append(f"line {stmt.lineno}: a smoke test holds assertions only")
    # the test itself is held to the same import and name rules
    problems.extend(_walk_problems(tree))
    return sorted(set(problems))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ running code in its own process

_WRAPPER = r'''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("forged", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request = json.loads(sys.stdin.read() or "{}")
try:
    value = getattr(module, sys.argv[2])(**request.get("args", {}))
    sys.stdout.write(json.dumps({"ok": True, "result": value}, default=repr))
except Exception as exc:
    sys.stdout.write(json.dumps({"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:300]}))
'''


def _clean_env() -> Dict[str, str]:
    from rct_control_plane.sandbox import scrubbed_environment
    env = scrubbed_environment()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_python(args: List[str], stdin: str = "", timeout_s: float = RUN_TIMEOUT_S) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forge-run-") as cwd:
        try:
            done = subprocess.run([sys.executable, "-I", *args], input=stdin, capture_output=True, text=True, encoding="utf-8",
                                  timeout=timeout_s, cwd=cwd, env=_clean_env(), check=False)
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "timed_out": True, "stdout": "", "stderr": ""}
    return {"exit_code": done.returncode, "timed_out": False, "stdout": done.stdout[:MAX_OUTPUT_CHARS], "stderr": done.stderr[-2000:]}


def verify_code(code: str, smoke_test: str, function_name: str) -> Dict[str, Any]:
    """Static checks, then the smoke test in a separate process. Returns {passed, stage, ...}."""
    problems = static_check(code, function_name)
    if problems:
        return {"passed": False, "stage": "static_check", "problems": problems}
    problems = smoke_check(smoke_test, function_name)
    if problems:
        return {"passed": False, "stage": "smoke_check", "problems": problems}
    with tempfile.TemporaryDirectory(prefix="forge-verify-") as folder:
        path = Path(folder) / "candidate.py"
        path.write_text(f"{code}\n\n{smoke_test}\nprint('SMOKE_OK')\n", encoding="utf-8")
        ran = _run_python([str(path)])
    passed = ran["exit_code"] == 0 and "SMOKE_OK" in ran["stdout"]
    return {"passed": passed, "stage": "smoke_run", "timed_out": ran["timed_out"], "stdout": ran["stdout"][-500:], "stderr": ran["stderr"][-500:],
            "problems": [] if passed else ["the smoke test timed out" if ran["timed_out"] else "the smoke test failed: " + ran["stderr"][-200:]]}


# ------------------------------------------------------------------ gaps

def _tokens(text: str) -> set:
    from rct_control_plane.skill_library import _tokenize
    return set(_tokenize(text))


def find_gaps(persistence: Any, *, min_count: int = 2, limit: int = 2000) -> List[Dict[str, Any]]:
    """Goals the agent finished but did not satisfy, seen at least `min_count` times (by goal, not by user), grouped
    when their words largely overlap. Each group is evidence that something is missing, with the goals themselves."""
    with persistence._connect() as conn:
        rows = conn.execute(
            "SELECT e.name, r.metrics, r.jitna_state, r.timestamp FROM experiment_runs r JOIN experiments e ON e.id = r.experiment_id "
            "WHERE r.algorithm_id LIKE 'governed_loop/%' ORDER BY r.timestamp DESC LIMIT ?", (limit,)).fetchall()
    unmet: Dict[str, Dict[str, Any]] = {}
    for name, metrics_raw, state_raw, stamp in rows:
        try:
            metrics, state = json.loads(metrics_raw or "{}"), json.loads(state_raw or "{}")
        except ValueError:
            continue
        if metrics.get("finished") == 1 and metrics.get("aligned_with_intent") == 0 and not metrics.get("warm_recall"):
            slot = unmet.setdefault(name, {"goal": name, "count": 0, "users": set(), "last_seen": stamp, "first_seen": stamp})
            slot["count"] += 1
            slot["users"].add(state.get("namespace", ""))
            slot["first_seen"] = min(slot["first_seen"], stamp)
            slot["last_seen"] = max(slot["last_seen"], stamp)
    groups: List[Dict[str, Any]] = []
    for goal, data in sorted(unmet.items(), key=lambda kv: -kv[1]["count"]):
        words = _tokens(goal)
        for group in groups:
            overlap = len(words & group["_words"]) / max(1, len(words | group["_words"]))
            if overlap >= 0.5:
                group["count"] += data["count"]
                group["users"] |= data["users"]
                group["goals"].append(goal)
                group["_words"] |= words
                group["first_seen"], group["last_seen"] = min(group["first_seen"], data["first_seen"]), max(group["last_seen"], data["last_seen"])
                break
        else:
            groups.append({"goals": [goal], "count": data["count"], "users": set(data["users"]), "first_seen": data["first_seen"],
                           "last_seen": data["last_seen"], "_words": set(words)})
    out = []
    for g in groups:
        if g["count"] >= min_count:
            keywords = sorted(g.pop("_words"))[:8]
            out.append({"goals": g["goals"][:5], "count": g["count"], "users": len(g["users"]), "keywords": keywords,
                        "first_seen": g["first_seen"], "last_seen": g["last_seen"],
                        "gap_id": "gap-" + sha256(" ".join(sorted(g["goals"])))[:10]})
    return sorted(out, key=lambda g: -g["count"])


# ------------------------------------------------------------------ the forge

@dataclass
class Proposal:
    id: str
    name: str
    spec: str
    code: str
    smoke_test: str
    code_sha256: str
    status: str
    verification: Dict[str, Any] = field(default_factory=dict)
    gap: Dict[str, Any] = field(default_factory=dict)
    approval_id: Optional[str] = None
    created_at: float = 0.0

    def to_dict(self, with_code: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if not with_code:
            data.pop("code"), data.pop("smoke_test")
        return data


def forge_dir() -> Path:
    from rct_control_plane import data_home
    home = data_home.data_home()
    base = home if home is not None else Path(tempfile.gettempdir()) / "delentia-forge"
    target = base / "forged_tools"
    target.mkdir(parents=True, exist_ok=True)
    return target


class ToolForge:
    def __init__(self, persistence: Any):
        self._persistence = persistence
        with self._persistence._connect() as conn:
            conn.executescript(_SCHEMA)

    # ---- proposals -------------------------------------------------------
    def _save(self, p: Proposal) -> None:
        with self._persistence._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO forge_proposals (id, name, spec, code, smoke_test, code_sha256, status, verification, gap, approval_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p.id, p.name, p.spec, p.code, p.smoke_test, p.code_sha256, p.status, json.dumps(p.verification), json.dumps(p.gap), p.approval_id, p.created_at))

    @staticmethod
    def _from_row(row: Tuple[Any, ...]) -> Proposal:
        return Proposal(id=row[0], name=row[1], spec=row[2], code=row[3], smoke_test=row[4], code_sha256=row[5], status=row[6],
                        verification=json.loads(row[7] or "{}"), gap=json.loads(row[8] or "{}"), approval_id=row[9], created_at=row[10])

    _COLUMNS = "id, name, spec, code, smoke_test, code_sha256, status, verification, gap, approval_id, created_at"

    def get(self, proposal_id: str) -> Optional[Proposal]:
        with self._persistence._connect() as conn:
            row = conn.execute(f"SELECT {self._COLUMNS} FROM forge_proposals WHERE id = ?", (proposal_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_proposals(self, status: Optional[str] = None) -> List[Proposal]:
        query = f"SELECT {self._COLUMNS} FROM forge_proposals"
        params: Tuple[Any, ...] = ()
        if status:
            query, params = query + " WHERE status = ?", (status,)
        with self._persistence._connect() as conn:
            rows = conn.execute(query + " ORDER BY created_at DESC", params).fetchall()
        return [self._from_row(r) for r in rows]

    async def propose(self, name: str, spec: str, smoke_test: str, *, code: Optional[str] = None, provider: Any = None,
                      gap: Optional[Dict[str, Any]] = None) -> Proposal:
        """A candidate tool. `code` given = a human or another tool wrote it; otherwise the model writes it. Either way it
        is checked and run before it can be approved, and a failure is recorded, not hidden."""
        if not NAME_PATTERN.match(name):
            raise ForgeError("the tool name must be 3-41 characters: a lowercase letter, then lowercase letters, digits or _")
        if self.active_tool(name) is not None:
            raise ForgeError(f"a tool named {name} is already active")
        if not spec.strip() or len(spec) > 600:
            raise ForgeError("the spec must be 1-600 characters")
        source = "supplied"
        if code is None:
            from rct_control_plane.llm_provider import get_default_provider
            llm = provider or get_default_provider()
            prompt = (f"Write a single pure Python function named exactly `{name}` that: {spec}. Use only the standard library modules "
                      f"{', '.join(sorted(ALLOWED_IMPORTS))}; no file, network or system access. Return ONLY the code, no explanation, no markdown fences.")
            raw = await llm.complete(prompt, temperature=0.2)
            code = re.sub(r"^```(?:python)?\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()
            source = "model"
        verification = verify_code(code, smoke_test, name)
        verification["code_source"] = source
        status = "VERIFIED" if verification["passed"] else f"REJECTED_{verification['stage'].upper()}"
        proposal = Proposal(id=f"fp-{uuid.uuid4().hex[:10]}", name=name, spec=spec, code=code, smoke_test=smoke_test, code_sha256=sha256(code + "\n" + smoke_test),
                            status=status, verification=verification, gap=gap or {}, created_at=time.time())
        self._save(proposal)
        self._persistence.append_audit(entity_type="forge_proposal", entity_id=proposal.id, action=status.lower(), actor="forge",
                                       changes={"name": name, "code_sha256": proposal.code_sha256, "stage": verification["stage"], "source": source})
        return proposal

    # ---- approval --------------------------------------------------------
    def request_activation(self, proposal_id: str, namespace: str = "forge") -> Any:
        """Creates the signed-approval request. The digest the human signs covers the proposal id, the tool name and the
        hash of code plus test, so approving one thing cannot activate another."""
        proposal = self.get(proposal_id)
        if proposal is None:
            raise ForgeError(f"no proposal {proposal_id!r}")
        if proposal.status != "VERIFIED":
            raise ForgeError(f"proposal {proposal_id} is {proposal.status}; only a VERIFIED proposal can be put forward")
        from rct_control_plane.approvals import PendingActionStore
        record = PendingActionStore(self._persistence).create(
            namespace=namespace, goal=f"Activate the forged tool {proposal.name}: {proposal.spec}", tool_name=ACTIVATE_TOOL,
            tool_args={"proposal_id": proposal.id, "name": proposal.name, "code_sha256": proposal.code_sha256},
            reason="a new tool written by the agent's own system needs a human signature on the exact code")
        proposal.status, proposal.approval_id = "AWAITING_APPROVAL", record.approval_id
        self._save(proposal)
        return record

    def activate(self, approval_id: str) -> Dict[str, Any]:
        """Runs after a human has signed: re-verifies every signature (approvals.claim_for_execution), re-checks the hash
        of what is about to be installed, then installs it."""
        from rct_control_plane.approvals import ApprovalError, PendingActionStore
        store = PendingActionStore(self._persistence)
        action = store.claim_for_execution(approval_id)
        if action.tool_name != ACTIVATE_TOOL:
            raise ApprovalError(f"approval {approval_id} is not an activation request")
        proposal = self.get(action.tool_args["proposal_id"])
        # The hash is recomputed from the code and test as stored NOW; the column that holds the original hash is not trusted,
        # because a row edited after signing would otherwise carry its old hash.
        if (proposal is None or proposal.name != action.tool_args["name"]
                or sha256(proposal.code + "\n" + proposal.smoke_test) != action.tool_args["code_sha256"]):
            raise ApprovalError("the proposal no longer matches what was signed")
        again = verify_code(proposal.code, proposal.smoke_test, proposal.name)
        if not again["passed"]:
            raise ApprovalError("the proposal no longer passes its checks: " + "; ".join(again["problems"]))
        path = forge_dir() / f"{proposal.name}.py"
        path.write_text(proposal.code + "\n", encoding="utf-8")
        with self._persistence._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO forged_tools (name, proposal_id, code_sha256, file_path, spec, approval_id, active, activated_at, calls) "
                         "VALUES (?, ?, ?, ?, ?, ?, 1, ?, COALESCE((SELECT calls FROM forged_tools WHERE name = ?), 0))",
                         (proposal.name, proposal.id, sha256(proposal.code + "\n"), str(path), proposal.spec, approval_id, time.time(), proposal.name))
        proposal.status = "ACTIVE"
        self._save(proposal)
        result = {"name": proposal.name, "file": str(path), "approval_id": approval_id, "proposal_id": proposal.id}
        store.mark_executed(approval_id, result)
        self._persistence.append_audit(entity_type="forged_tool", entity_id=proposal.name, action="activated", actor="forge",
                                       changes={**result, "code_sha256": proposal.code_sha256})
        return result

    # ---- use -------------------------------------------------------------
    def active_tool(self, name: str) -> Optional[Dict[str, Any]]:
        with self._persistence._connect() as conn:
            row = conn.execute("SELECT name, proposal_id, code_sha256, file_path, spec, approval_id, active, activated_at, calls "
                               "FROM forged_tools WHERE name = ? AND active = 1", (name,)).fetchone()
        keys = ("name", "proposal_id", "code_sha256", "file_path", "spec", "approval_id", "active", "activated_at", "calls")
        return dict(zip(keys, row, strict=False)) if row else None

    def list_tools(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT name, spec, active, activated_at, calls, code_sha256 FROM forged_tools"
        if not include_disabled:
            query += " WHERE active = 1"
        with self._persistence._connect() as conn:
            rows = conn.execute(query + " ORDER BY name").fetchall()
        return [{"name": r[0], "spec": r[1], "active": bool(r[2]), "activated_at": r[3], "calls": r[4], "code_sha256": r[5]} for r in rows]

    def deactivate(self, name: str) -> bool:
        """Turns a tool off. The row, the file and the proposal stay (nothing is deleted)."""
        with self._persistence._connect() as conn:
            changed = conn.execute("UPDATE forged_tools SET active = 0 WHERE name = ? AND active = 1", (name,)).rowcount
        if changed:
            self._persistence.append_audit(entity_type="forged_tool", entity_id=name, action="deactivated", actor="forge", changes={})
        return bool(changed)

    def run(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool = self.active_tool(name)
        if tool is None:
            return {"ok": False, "error": f"no active forged tool named {name}", "available": [t["name"] for t in self.list_tools()]}
        path = Path(tool["file_path"])
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {"ok": False, "error": "the tool's file is missing; it was not run"}
        if sha256(text) != tool["code_sha256"]:
            self._persistence.append_audit(entity_type="forged_tool", entity_id=name, action="hash_mismatch_refused", actor="forge", changes={})
            return {"ok": False, "error": "the tool's file does not match the code a human signed; it was not run"}
        problems = static_check(text, name)
        if problems:
            return {"ok": False, "error": "the tool no longer passes the static check: " + "; ".join(problems[:3])}
        try:
            payload = json.dumps({"args": args or {}}, default=str)
        except (TypeError, ValueError):
            return {"ok": False, "error": "the arguments are not JSON"}
        ran = _run_python(["-c", _WRAPPER, str(path), name], stdin=payload)
        with self._persistence._connect() as conn:
            conn.execute("UPDATE forged_tools SET calls = calls + 1 WHERE name = ?", (name,))
        if ran["timed_out"]:
            return {"ok": False, "error": f"the tool ran longer than {RUN_TIMEOUT_S:.0f} s and was stopped"}
        try:
            outcome = json.loads(ran["stdout"])
        except ValueError:
            return {"ok": False, "error": "the tool produced no JSON result", "stderr": ran["stderr"][-300:]}
        return outcome if isinstance(outcome, dict) else {"ok": False, "error": "unexpected result shape"}
