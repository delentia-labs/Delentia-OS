"""
Round 61 (D7): hooks - a person's own code at two points of the loop, allowed to make the system STRICTER and never looser.

Hermes lets a plugin sit in front of a tool call and rewrite the call or approve it. Here a hook is code a human has read and signed, and the design rule is the one the whole project runs on:
a hook can only TIGHTEN.

  pre_tool_call(tool_name, args) -> None | "pass" | {"action": "block" | "require_signature", "reason": "..."}
      Runs before every tool call, in front of the FDIA gate. It can refuse the call (block) or demand a human signature for it (require_signature). It cannot allow anything the gate
      refuses, cannot skip a signature, cannot change the arguments. A hook that crashes, times out, returns something else, or whose file no longer matches the signed hash is treated as
      `require_signature`: when in doubt, ask the person.
  transform_tool_result(tool_name, text) -> text
      Runs on every text a tool returned, after the injection screen. The edit must be a SHRINKING one: the result is the input with some stretches deleted or replaced by "[redacted]"; any
      other output (a rewrite, an addition, a reorder) is refused and the whole text is withheld. A hook can hide data from the model; it cannot put words in the tool's mouth.

How a hook gets in: it is a pure-function module (the same static rules as a forged tool: a short list of imports, no files, no eval, no dunder access, 8,000 characters), proposed with `delentia hooks
propose`, checked and probed in another process, and put forward as a signed approval over the SHA-256 of the exact code. Nothing runs until a human with an approver key signs; the file is re-hashed
before every use. Hooks run in their own process with a clean environment and a time limit, so a hook cannot reach a key, a file or the network.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane import tool_forge as forge

POINTS = ("pre_tool_call", "transform_tool_result")
ACTIVATE_TOOL = "hook_activate"                      # the tool name in the approval, so a signature binds to this action only
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
MAX_CODE_CHARS = 8000
RUN_TIMEOUT_S = 4.0
MAX_ARGS_CHARS = 200_000
MAX_LEAVES = 40
MIN_LEAF_CHARS = 8
REDACTED = "[redacted]"
MAX_MARKERS = 50
ENV = "DELENTIA_HOOKS"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_hooks (
    name          TEXT PRIMARY KEY,
    description   TEXT NOT NULL,
    code          TEXT NOT NULL,
    code_sha256   TEXT NOT NULL,
    points        TEXT NOT NULL,
    status        TEXT NOT NULL,
    approval_id   TEXT,
    file_path     TEXT,
    verification  TEXT NOT NULL DEFAULT '{}',
    created_at    REAL NOT NULL,
    activated_at  REAL
);
"""


class HookError(ValueError):
    pass


def hooks_dir() -> Path:
    from rct_control_plane import data_home
    home = data_home.data_home()
    target = (home if home is not None else Path(tempfile.gettempdir()) / "delentia-hooks") / "hooks"
    target.mkdir(parents=True, exist_ok=True)
    return target


def enabled() -> bool:
    return (os.environ.get(ENV) or "on").strip().lower() not in ("off", "0", "false", "no")


# ------------------------------------------------------------------ static check and the rule for an edit

def defined_points(code: str) -> List[str]:
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [p for p in POINTS if any(isinstance(n, ast.FunctionDef) and n.name == p for n in tree.body)]


def static_check(code: str) -> List[str]:
    """Reasons this code may not become a hook; empty = it passed (the forge's rules, plus at least one hook point defined)."""
    if len(code) > MAX_CODE_CHARS:
        return [f"the code is longer than {MAX_CODE_CHARS} characters"]
    points = defined_points(code)
    if not points:
        return [f"it defines none of the hook functions: {', '.join(POINTS)}"]
    return forge.static_check(code, points[0])


def is_shrinking_edit(original: str, edited: str) -> bool:
    """True when `edited` is `original` with stretches deleted and/or replaced by "[redacted]" - and nothing else. Checked by removing the markers and testing that what is left is a
    subsequence of the original (every kept character comes from the original, in order)."""
    if not isinstance(edited, str):
        return False
    if edited.count(REDACTED) > MAX_MARKERS:
        return False
    rest = edited.replace(REDACTED, "")
    if len(rest) > len(original):
        return False
    it = iter(original)
    return all(ch in it for ch in rest)


def valid_pre_verdict(value: Any) -> Optional[Dict[str, str]]:
    """The tightening a hook asked for, or None for 'pass'. Raises HookError for anything that is not a verdict."""
    if value is None or value == "pass":
        return None
    if isinstance(value, dict) and value.get("action") in ("block", "require_signature") and isinstance(value.get("reason", ""), str):
        return {"action": value["action"], "reason": (value.get("reason") or "")[:300] or f"a hook asked for {value['action']}"}
    if isinstance(value, dict) and value.get("action") == "pass":
        return None
    raise HookError("a hook returned something that is not a verdict")


# ------------------------------------------------------------------ running hook code in its own process

_WRAPPER = r'''
import importlib.util, json, sys
request = json.loads(sys.stdin.read() or "{}")
out = []
for hook in request["hooks"]:
    entry = {"name": hook["name"], "ok": True}
    try:
        spec = importlib.util.spec_from_file_location("hook_" + hook["name"], hook["file"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if request["point"] == "pre_tool_call":
            entry["value"] = module.pre_tool_call(request["tool_name"], request["args"]) if hasattr(module, "pre_tool_call") else None
        else:
            entry["values"] = [module.transform_tool_result(request["tool_name"], text) for text in request["texts"]] if hasattr(module, "transform_tool_result") else None
    except Exception as exc:
        entry = {"name": hook["name"], "ok": False, "error": type(exc).__name__ + ": " + str(exc)[:200]}
    out.append(entry)
sys.stdout.write(json.dumps(out, default=repr))
'''


def _safe_tail(stderr: str) -> str:
    """The last line of a process's error output, with file paths removed and clipped: enough to see what went wrong, nothing that maps the host."""
    lines = [ln.strip() for ln in (stderr or "").strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else "no error text"
    return re.sub(r"(?:[A-Za-z]:\\|/)[^\s\"']+", "<path>", last)[:160]


def _run(point: str, hooks: List[Dict[str, str]], payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Runs the hooks' code for one point in a separate process. Returns (entries, problem); a problem means no entry can be trusted."""
    with tempfile.TemporaryDirectory(prefix="hook-run-") as cwd:
        wrapper = Path(cwd) / "wrapper.py"
        wrapper.write_text(_WRAPPER, encoding="utf-8")
        request = json.dumps({"point": point, "hooks": hooks, **payload}, default=str)
        try:
            done = subprocess.run([sys.executable, "-I", str(wrapper)], input=request, capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_S,
                                  cwd=cwd, env=forge._clean_env(), check=False)
        except subprocess.TimeoutExpired:
            return [], f"the hooks did not finish within {RUN_TIMEOUT_S:g} seconds"
    if done.returncode != 0:
        return [], "the hook process failed: " + _safe_tail(done.stderr)
    try:
        entries = json.loads(done.stdout)
    except ValueError:
        return [], "the hook process answered with something unreadable"
    return entries if isinstance(entries, list) else [], None


# ------------------------------------------------------------------ the registry

class HookRegistry:
    def __init__(self, persistence: Any):
        self._p = persistence
        with self._p._connect() as conn:
            conn.executescript(_SCHEMA)

    # ---- reading
    def _rows(self, where: str = "", args: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        import sqlite3
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM agent_hooks" + (f" WHERE {where}" if where else "") + " ORDER BY name", args).fetchall()
        return [dict(r) for r in rows]

    def list(self, include_code: bool = False) -> List[Dict[str, Any]]:
        out = []
        for row in self._rows():
            row["points"] = json.loads(row["points"])
            row["verification"] = json.loads(row["verification"])
            if not include_code:
                row.pop("code", None)
            out.append(row)
        return out

    def active(self) -> List[Dict[str, Any]]:
        return self._rows("status = 'ACTIVE'")

    def has_active(self) -> bool:
        with self._p._connect() as conn:
            return conn.execute("SELECT 1 FROM agent_hooks WHERE status = 'ACTIVE' LIMIT 1").fetchone() is not None

    def _audit(self, action: str, name: str, changes: Dict[str, Any]) -> None:
        try:
            self._p.append_audit(entity_type="agent_hook", entity_id=name, action=action, actor="hooks", changes=changes)
        except Exception:                                                  # noqa: BLE001
            pass

    # ---- proposing, signing, activating
    def propose(self, name: str, code: str, description: str = "") -> Dict[str, Any]:
        """Check the code and probe it in another process. A PROPOSED hook is stored (its code and hash); nothing can run it yet."""
        if not NAME_PATTERN.match(name or ""):
            raise HookError("a hook name is 3-41 characters: a lowercase letter, then lowercase letters, digits or _")
        problems = static_check(code)
        points = defined_points(code)
        verification: Dict[str, Any] = {"static": "passed" if not problems else "failed", "problems": problems, "probe": None}
        if not problems:
            verification["probe"] = self._probe(name, code, points)
            problems = verification["probe"]["problems"]
            verification["problems"] = problems
        status = "PROPOSED" if not problems else "REJECTED"
        sha = forge.sha256(code)
        with self._p._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO agent_hooks (name, description, code, code_sha256, points, status, approval_id, file_path, verification, created_at, activated_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL)",
                         (name, (description or "")[:300], code, sha, json.dumps(points), status, json.dumps(verification), time.time()))
        self._audit(status.lower(), name, {"code_sha256": sha, "points": points, "problems": problems[:5]})
        return {"name": name, "status": status, "code_sha256": sha, "points": points, "verification": verification}

    def _probe(self, name: str, code: str, points: List[str]) -> Dict[str, Any]:
        """Run each defined point on harmless probe inputs: it must not crash, must answer in time, and its answer must be a valid tightening / shrinking edit."""
        problems: List[str] = []
        with tempfile.TemporaryDirectory(prefix="hook-probe-") as folder:
            path = Path(folder) / "candidate.py"                              # a fixed file name: the hook's own name never becomes part of a path here
            path.write_text(code + "\n", encoding="utf-8")
            hook = [{"name": "candidate", "file": str(path)}]
            if "pre_tool_call" in points:
                for tool, args in (("delentia_read_repo_file", {"relative_path": "a.txt"}), ("delentia_run_sandboxed_command", {"command": "ls"}), ("delentia_remember", {"content": "x"})):
                    entries, problem = _run("pre_tool_call", hook, {"tool_name": tool, "args": args})
                    if problem or not entries or not entries[0].get("ok"):
                        problems.append(f"pre_tool_call failed on a probe: {problem or (entries[0].get('error') if entries else 'no answer')}")
                        break
                    try:
                        valid_pre_verdict(entries[0].get("value"))
                    except HookError as exc:
                        problems.append(f"pre_tool_call: {exc}")
                        break
            if "transform_tool_result" in points:
                samples = ["hello world 123 token=abcDEF456 contact bob@example.org", "line one\nline two\nline three", "x" * 200]
                entries, problem = _run("transform_tool_result", hook, {"tool_name": "delentia_read_repo_file", "texts": samples})
                if problem or not entries or not entries[0].get("ok"):
                    problems.append(f"transform_tool_result failed on a probe: {problem or (entries[0].get('error') if entries else 'no answer')}")
                else:
                    for original, edited in zip(samples, entries[0].get("values") or [], strict=False):
                        if not is_shrinking_edit(original, edited):
                            problems.append("transform_tool_result returned something that is not the input with parts deleted or replaced by [redacted]")
                            break
        return {"problems": problems, "points": points}

    def request_activation(self, name: str, namespace: str = "hooks") -> Any:
        """The signed-approval request: the digest the human signs covers the name, the points and the hash of the exact code."""
        row = next(iter(self._rows("name = ?", (name,))), None)
        if row is None:
            raise HookError(f"no hook named {name!r}")
        if row["status"] != "PROPOSED":
            raise HookError(f"hook {name} is {row['status']}; only a PROPOSED hook (one that passed its checks) can be put forward")
        from rct_control_plane.approvals import PendingActionStore
        record = PendingActionStore(self._p).create(
            namespace=namespace, goal=f"Activate the hook {name} ({', '.join(json.loads(row['points']))}): {row['description']}", tool_name=ACTIVATE_TOOL,
            tool_args={"name": name, "code_sha256": row["code_sha256"], "points": json.loads(row["points"])},
            reason="a hook runs in front of every tool call or on every tool result; it can only tighten, but it needs a human signature on the exact code")
        with self._p._connect() as conn:
            conn.execute("UPDATE agent_hooks SET status = 'AWAITING_APPROVAL', approval_id = ? WHERE name = ?", (record.approval_id, name))
        self._audit("awaiting_approval", name, {"approval_id": record.approval_id, "code_sha256": row["code_sha256"]})
        return record

    def activate(self, approval_id: str) -> Dict[str, Any]:
        """After a human has signed: re-verify every signature, re-hash the code as stored NOW, re-check it, write the file, switch the hook on."""
        from rct_control_plane.approvals import ApprovalError, PendingActionStore
        store = PendingActionStore(self._p)
        action = store.claim_for_execution(approval_id)
        if action.tool_name != ACTIVATE_TOOL:
            raise ApprovalError(f"approval {approval_id} is not a hook activation")
        name = action.tool_args["name"]
        row = next(iter(self._rows("name = ?", (name,))), None)
        if row is None or forge.sha256(row["code"]) != action.tool_args["code_sha256"]:
            raise ApprovalError("the hook no longer matches what was signed")
        problems = static_check(row["code"])
        if problems:
            raise ApprovalError("the hook no longer passes its checks: " + "; ".join(problems))
        if not NAME_PATTERN.match(str(name)):
            raise ApprovalError("the hook name in the approval is not a valid hook name")
        base = hooks_dir().resolve()
        path = (base / f"{name}.py").resolve()
        if path.parent != base:                                            # the name cannot step out of the hooks folder
            raise ApprovalError("the hook name in the approval is not a valid hook name")
        path.write_text(row["code"] + "\n", encoding="utf-8")
        with self._p._connect() as conn:
            conn.execute("UPDATE agent_hooks SET status = 'ACTIVE', file_path = ?, activated_at = ?, code_sha256 = ? WHERE name = ?", (str(path), time.time(), forge.sha256(row["code"] + "\n"), name))
        result = {"name": name, "file": str(path), "approval_id": approval_id, "code_sha256": action.tool_args["code_sha256"]}
        store.mark_executed(approval_id, result)
        self._audit("activated", name, result)
        return result

    def disable(self, name: str) -> bool:
        """Turning a hook OFF needs no signature - it only removes a tightening the person chose - but the row, the code and the file stay."""
        with self._p._connect() as conn:
            changed = conn.execute("UPDATE agent_hooks SET status = 'DISABLED' WHERE name = ? AND status = 'ACTIVE'", (name,)).rowcount
        if changed:
            self._audit("disabled", name, {})
        return bool(changed)

    # ---- using the hooks
    def _runnable(self) -> Tuple[List[Dict[str, str]], List[str]]:
        """(hooks whose file still has the signed hash, names whose file does not)."""
        good, bad = [], []
        for row in self.active():
            try:
                text = Path(row["file_path"]).read_text(encoding="utf-8")
            except (OSError, TypeError):
                bad.append(row["name"])
                continue
            if forge.sha256(text) != row["code_sha256"]:
                bad.append(row["name"])
                continue
            good.append({"name": row["name"], "file": row["file_path"]})
        return good, bad

    def pre_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """None = no hook objects. Otherwise {"action": "block" | "require_signature", "reason": ..., "hook": name}. Doubt is resolved by asking: every failure mode is require_signature."""
        rows = [r for r in self.active() if "pre_tool_call" in json.loads(r["points"])]
        if not rows:
            return None
        good, bad = self._runnable()
        if any(r["name"] in bad for r in rows):
            name = next(r["name"] for r in rows if r["name"] in bad)
            self._audit("hash_mismatch_refused", name, {"tool_name": tool_name})
            return {"action": "require_signature", "reason": f"the file of hook {name} no longer matches the code a person signed, so a person must sign this call", "hook": name}
        wanted = [h for h in good if h["name"] in {r["name"] for r in rows}]
        try:
            rendered = json.dumps(args, ensure_ascii=False, default=str)
        except Exception:                                                  # noqa: BLE001
            rendered = ""
        if not rendered or len(rendered) > MAX_ARGS_CHARS:
            return {"action": "require_signature", "reason": "the arguments are too large for the hooks to judge, so a person must sign this call", "hook": wanted[0]["name"] if wanted else "?"}
        entries, problem = _run("pre_tool_call", wanted, {"tool_name": tool_name, "args": json.loads(rendered)})
        if problem:
            self._audit("pre_tool_call_failed", wanted[0]["name"] if wanted else "?", {"problem": problem[:200], "tool_name": tool_name})
            return {"action": "require_signature", "reason": f"the hooks could not be run ({problem}), so a person must sign this call", "hook": wanted[0]["name"] if wanted else "?"}
        strongest: Optional[Dict[str, str]] = None
        for entry in entries:
            hook = str(entry.get("name"))
            try:
                if not entry.get("ok"):
                    raise HookError(str(entry.get("error") or "the hook failed"))
                verdict = valid_pre_verdict(entry.get("value"))
            except HookError as exc:
                self._audit("pre_tool_call_error", hook, {"error": str(exc)[:200], "tool_name": tool_name})
                verdict = {"action": "require_signature", "reason": f"hook {hook} failed ({str(exc)[:120]}), so a person must sign this call"}
            if verdict is None:
                continue
            verdict = {**verdict, "hook": hook}
            if strongest is None or (verdict["action"] == "block" and strongest["action"] != "block"):
                strongest = verdict
        if strongest is not None:
            self._audit("pre_tool_call_" + strongest["action"], strongest["hook"], {"tool_name": tool_name, "reason": strongest["reason"][:200]})
        return strongest

    def transform(self, tool_name: str, texts: List[str]) -> Tuple[List[str], List[str]]:
        """Run every active transform hook over `texts` (in order, each on the previous one's output). Returns (new texts, notes). An edit that is not a shrinking one - or a hook that fails -
        withholds that text altogether: the safe default for a text a hook wanted to change."""
        rows = [r for r in self.active() if "transform_tool_result" in json.loads(r["points"])]
        if not rows or not texts:
            return texts, []
        good, bad = self._runnable()
        notes: List[str] = []
        current = list(texts)
        for row in rows:
            name = row["name"]
            if name in bad:
                self._audit("hash_mismatch_refused", name, {"tool_name": tool_name})
                return [f"[withheld: the file of hook {name} no longer matches the code a person signed]"] * len(texts), [f"hook {name}: file changed"]
            hook = [h for h in good if h["name"] == name]
            entries, problem = _run("transform_tool_result", hook, {"tool_name": tool_name, "texts": current})
            entry = entries[0] if entries else {}
            if problem or not entry.get("ok") or not isinstance(entry.get("values"), list) or len(entry["values"]) != len(current):
                self._audit("transform_failed", name, {"tool_name": tool_name, "problem": (problem or str(entry.get("error")) or "bad answer")[:200]})
                return [f"[withheld: hook {name} could not be run on this result]"] * len(texts), [f"hook {name}: failed"]
            changed = 0
            nxt: List[str] = []
            for original, edited in zip(current, entry["values"], strict=True):
                if edited == original:
                    nxt.append(original)
                elif is_shrinking_edit(original, edited):
                    nxt.append(edited)
                    changed += 1
                else:
                    nxt.append(f"[withheld: hook {name} returned an edit that adds or reorders text]")
                    self._audit("transform_refused", name, {"tool_name": tool_name, "input_sha256": forge.sha256(original)})
                    notes.append(f"hook {name}: invalid edit withheld")
            current = nxt
            if changed:
                notes.append(f"hook {name}: edited {changed} text(s)")
                self._audit("transform_applied", name, {"tool_name": tool_name, "texts_changed": changed})
        return current, notes

