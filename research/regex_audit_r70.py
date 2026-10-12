"""
Round 70: every regular expression written as a literal in the runtime, against hostile text (criteria: research/round70_criteria.md section 4).

CodeQL found two ReDoS in our own code in Round 69 (a calculation-goal pattern of VERIFY: a 32,000-character goal took 16 s; the git rule of the shell floor: exponential). This finds that kind of pattern before the scanner does:
the runtime's `re.compile / search / match / sub / findall / split / fullmatch / finditer / subn` calls whose pattern is a string literal are collected from the source (AST, no imports, so nothing runs), and each
pattern is run against a set of hostile 20,000-character inputs in a child process that a watchdog kills when one run takes too long (a catastrophic pattern cannot be interrupted from inside Python).

    python research/regex_audit_r70.py            # prints the offenders (none = exit code 0)

Limits: patterns built at run time (22 f-strings or variables) are not covered; a hostile input I did not think of is not covered; the flags are the pattern's own.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "rct_control_plane"
N = 20_000
CALLS = ("compile", "search", "match", "sub", "findall", "split", "fullmatch", "finditer", "subn")
SLOW_S = 0.5            # a finished run slower than this is an offender
KILL_S = 3.0            # a run still going after this is killed and is an offender


def hostile_inputs(n: int = N) -> List[Tuple[str, str]]:
    return [("spaces", " " * n), ("digit then spaces", "0" + " " * n), ("letters", "a" * n), ("dots", "0." * (n // 2)), ("commas", "1," * (n // 2)), ("git options", "git " + "-c ! " * (n // 5)),
            ("a!", "a!" * (n // 2)), ("assign", "x=" * (n // 2)), ("dashes", "-" * n), ("url", "http://" + "a." * (n // 2)), ("newlines", "\n" * n), ("mixed words", "word " * (n // 5) + "!"),
            ("thai", "ก" * n), ("slashes", "/" * n), ("quotes", '"' * n), ("path", "a/" * (n // 2)), ("digits", "1" * n)]


def collect() -> List[Dict[str, object]]:
    given = os.environ.get("DELENTIA_REGEX_AUDIT_ITEMS")                                 # Round 72: research/regex_audit_r72.py hands the worker processes its own list (literal + built at import)
    if given and Path(given).exists():
        return list(json.loads(Path(given).read_text(encoding="utf-8"))) + [{"pattern": "__skipped__", "flags": 0, "where": ""}]
    seen: Dict[str, Dict[str, object]] = {}
    skipped = 0
    for path in sorted(SOURCE.glob("**/*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" and node.func.attr in CALLS):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    pattern = node.args[0].value
                    flags = 0
                    for kw in node.keywords:
                        if kw.arg == "flags":
                            try:
                                flags = int(eval(compile(ast.Expression(kw.value), "<f>", "eval"), {"re": re}))      # noqa: S307 - only `re.X | re.Y` expressions from our own source
                            except Exception:                                                                        # noqa: BLE001
                                flags = 0
                    if len(node.args) >= 3 and node.func.attr in ("search", "match", "fullmatch", "findall", "finditer", "split", "sub", "subn") and node.func.attr not in ("sub", "subn", "split"):
                        pass
                    key = f"{flags}|{pattern}"
                    seen.setdefault(key, {"pattern": pattern, "flags": flags, "where": f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"})
                else:
                    skipped += 1
    items = list(seen.values())
    items.append({"pattern": "__skipped__", "flags": skipped, "where": "non-literal patterns"})
    return items


def _worker(start: int) -> int:
    items = [i for i in collect() if i["pattern"] != "__skipped__"]
    inputs = hostile_inputs()
    for index in range(start, len(items)):
        item = items[index]
        try:
            compiled = re.compile(str(item["pattern"]), int(item["flags"]))                          # type: ignore[arg-type]
        except re.error:
            print(f"SKIP {index}", flush=True)
            continue
        worst, worst_name = 0.0, ""
        for name, text in inputs:
            print(f"RUN {index} {name}", flush=True)
            started = time.perf_counter()
            compiled.search(text)
            took = time.perf_counter() - started
            if took > worst:
                worst, worst_name = took, name
        print(f"DONE {index} {worst:.4f} {worst_name}", flush=True)
    return 0


def _kill_tree(proc: "subprocess.Popen[str]") -> None:
    """A Microsoft Store python.exe is a launcher in front of the real interpreter: killing the launcher alone leaves the runaway pattern running."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.kill()


def audit(kill_s: float = KILL_S, slow_s: float = SLOW_S) -> Dict[str, object]:
    import queue
    import threading
    items = [i for i in collect() if i["pattern"] != "__skipped__"]
    offenders: List[Dict[str, object]] = []
    start, checked, worst_overall = 0, 0, 0.0
    while start < len(items):
        proc = subprocess.Popen([sys.executable, str(Path(__file__)), "--worker", str(start)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=str(ROOT))
        q: "queue.Queue[str]" = queue.Queue()

        def pump(stream=proc.stdout, out=q) -> None:                                                  # type: ignore[no-untyped-def]
            for line in stream:
                out.put(line.rstrip("\n"))
            out.put("")
        threading.Thread(target=pump, daemon=True).start()
        last_line_at, current, killed = time.perf_counter(), None, False
        while True:
            try:
                line = q.get(timeout=0.05)
            except queue.Empty:
                if time.perf_counter() - last_line_at > kill_s:
                    _kill_tree(proc)
                    killed = True
                    break
                continue
            if line == "":
                break
            last_line_at = time.perf_counter()
            parts = line.split()
            if parts[0] == "RUN":
                current = (int(parts[1]), " ".join(parts[2:]))
            elif parts[0] == "DONE":
                checked += 1
                took = float(parts[2])
                worst_overall = max(worst_overall, took)
                if took > slow_s:
                    offenders.append({**items[int(parts[1])], "seconds": took, "input": " ".join(parts[3:]), "killed": False})
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
        if killed and current is not None:
            offenders.append({**items[current[0]], "seconds": kill_s, "input": current[1], "killed": True})
            start = current[0] + 1
            continue
        break
    return {"patterns": len(items), "checked": checked, "offenders": offenders, "worst_seconds": round(worst_overall, 4)}


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        raise SystemExit(_worker(int(sys.argv[2])))
    report = audit()
    print(f"{report['patterns']} literal patterns, {report['checked']} fully run, slowest {report['worst_seconds']} s on 20,000 characters")
    for o in report["offenders"]:                                                                      # type: ignore[union-attr]
        print(f"OFFENDER {o['where']}  {o['seconds']:.2f}s{' (killed)' if o['killed'] else ''} on '{o['input']}': {str(o['pattern'])[:100]}")
    raise SystemExit(1 if report["offenders"] else 0)
