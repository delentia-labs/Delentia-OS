"""
Round 72: the regex audit of Round 70 covered the patterns written as string literals (302). A pattern built from pieces - "|".join(WORDS), an f-string, a name - was not covered (22 call sites).
This adds the ones that are compiled when a module is IMPORTED, whatever way they were built: every module of the runtime is imported in a child process with `re._compile` watched, and each pattern
the runtime compiles is recorded with the file that asked for it. Those patterns join the literal ones and go through the same hostile inputs and the same watchdog (research/regex_audit_r70.py).

Still not covered (listed by `uncovered()`): a pattern built from a variable INSIDE a function and compiled only when that function runs; a hostile input nobody thought of; the flags are the pattern's own.

    python research/regex_audit_r72.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
import regex_audit_r70 as base  # noqa: E402


def _collect_dynamic_child(out_path: str) -> int:
    """Run in a child process: import every runtime module and record the patterns the runtime compiled."""
    import importlib
    import pkgutil
    import re
    source = str(base.SOURCE.resolve())
    seen: Dict[str, Dict[str, Any]] = {}
    original = re._compile                                                                             # type: ignore[attr-defined]

    def spy(pattern: Any, flags: Any) -> Any:
        if isinstance(pattern, str):
            frame, depth = sys._getframe(1), 0
            while frame is not None and depth < 8:
                name = frame.f_code.co_filename
                if name.startswith(source) and os.sep + "tests" + os.sep not in name:
                    key = f"{int(flags)}|{pattern}"
                    seen.setdefault(key, {"pattern": pattern, "flags": int(flags), "where": f"{Path(name).relative_to(base.ROOT).as_posix()}:{frame.f_lineno}"})
                    break
                frame, depth = frame.f_back, depth + 1
        return original(pattern, flags)

    re._compile = spy                                                                                    # type: ignore[attr-defined]
    failed: List[str] = []
    import rct_control_plane
    for module in pkgutil.walk_packages(rct_control_plane.__path__, prefix="rct_control_plane."):
        if ".tests" in module.name or module.name.endswith(".__main__"):
            continue
        try:
            importlib.import_module(module.name)
        except BaseException as exc:                                                                    # noqa: BLE001 - an optional dependency may be missing; the module is then not covered
            failed.append(f"{module.name}: {type(exc).__name__}")
    re._compile = original                                                                               # type: ignore[attr-defined]
    named = re.compile(r"PATTERN|REGEX|(?:^|_)RE(?:_|$)|RULES")
    sources = 0

    def strings(value: Any, depth: int = 0) -> List[str]:
        if isinstance(value, str):
            return [value]
        if depth > 2:
            return []
        if isinstance(value, dict):
            return [s for v in list(value.values())[:200] for s in strings(v, depth + 1)] + [s for k in list(value)[:200] if isinstance(k, str) for s in [k]]
        if isinstance(value, (list, tuple, set, frozenset)):
            return [s for v in list(value)[:200] for s in strings(v, depth + 1)]
        return []

    def harvest(owner: Any, label: str, module_name: str) -> None:
        nonlocal sources
        for attr, value in list(vars(owner).items()):
            if not named.search(attr) or attr.startswith("__"):
                continue
            for text in strings(value):
                if 3 <= len(text) <= 2000:
                    key = f"0|{text}"
                    if key not in seen:
                        try:
                            re.compile(text)
                        except re.error:
                            continue                                                                       # not a regular expression (a word list, a sentence)
                        seen[key] = {"pattern": text, "flags": 0, "where": f"{module_name.replace('.', '/')}.py:{label}{attr}"}
                        sources += 1
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("rct_control_plane") or ".tests" in module_name:
            continue
        harvest(module, "", module_name)
        for cls in [v for v in list(vars(module).values()) if isinstance(v, type) and getattr(v, "__module__", "") == module_name]:
            harvest(cls, f"{cls.__name__}.", module_name)
    Path(out_path).write_text(json.dumps({"items": list(seen.values()), "failed_imports": failed}), encoding="utf-8")
    return 0


def collect_dynamic() -> Dict[str, Any]:
    out = Path(tempfile.mkdtemp(prefix="regex-dyn-")) / "dyn.json"
    env = {**os.environ, "DELENTIA_HOME": str(out.parent / "home"), "DELENTIA_MEMORY_EMBED": "off", "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(Path(__file__)), "--collect-dynamic", str(out)], cwd=str(base.ROOT), env=env, timeout=900, check=True, capture_output=True)
    return json.loads(out.read_text(encoding="utf-8"))


def all_items() -> Dict[str, Any]:
    """Literal patterns (source) + patterns compiled at import, de-duplicated by (flags, pattern)."""
    static = [i for i in base.collect() if i["pattern"] != "__skipped__"]
    dynamic = collect_dynamic()
    known = {f"{i['flags']}|{i['pattern']}" for i in static}
    added = [i for i in dynamic["items"] if f"{i['flags']}|{i['pattern']}" not in known]
    return {"items": static + added, "literal": len(static), "built_at_import": len(added), "failed_imports": dynamic["failed_imports"]}


def uncovered() -> List[str]:
    """Call sites whose pattern is not a literal: a name or an expression. Those compiled at import are covered by the dynamic part; the others are listed for a human."""
    import ast
    out: List[str] = []
    for path in sorted(base.SOURCE.glob("**/*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" and node.func.attr in base.CALLS
                    and node.args and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str))):
                out.append(f"{path.relative_to(base.ROOT).as_posix()}:{node.lineno}")
    return out


def audit_all(kill_s: float = base.KILL_S, slow_s: float = base.SLOW_S) -> Dict[str, Any]:
    """The Round 70 audit over the literal AND the import-time patterns. Same watchdog, same hostile inputs."""
    gathered = all_items()
    path = Path(tempfile.mkdtemp(prefix="regex-all-")) / "items.json"
    path.write_text(json.dumps(gathered["items"]), encoding="utf-8")
    os.environ["DELENTIA_REGEX_AUDIT_ITEMS"] = str(path)                  # the worker processes of the Round 70 audit read their list from here
    try:
        report = base.audit(kill_s, slow_s)
    finally:
        os.environ.pop("DELENTIA_REGEX_AUDIT_ITEMS", None)
    return {**report, "literal": gathered["literal"], "built_at_import": gathered["built_at_import"], "failed_imports": gathered["failed_imports"], "uncovered": uncovered()}


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--collect-dynamic":
        raise SystemExit(_collect_dynamic_child(sys.argv[2]))
    result = audit_all()
    print(f"{result['patterns']} patterns ({result['literal']} literal + {result['built_at_import']} built at import), {result['checked']} fully run, slowest {result['worst_seconds']} s on 20,000 characters")
    print(f"modules that could not be imported (not covered): {len(result['failed_imports'])}; call sites with a non-literal pattern: {len(result['uncovered'])}")
    for item in result["offenders"]:
        print(f"OFFENDER {item['where']}  {item['seconds']:.2f}s{' (killed)' if item['killed'] else ''} on '{item['input']}': {str(item['pattern'])[:100]}")
    raise SystemExit(1 if result["offenders"] else 0)
