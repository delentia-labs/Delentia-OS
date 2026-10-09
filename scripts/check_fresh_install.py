"""
Does a clean machine get to a working demo? A receipt, not a promise. (Round 64, roadmap P5)

Creates a brand-new virtual environment in a temporary folder, installs the project into it, and then checks the things a first-time user would do. Every step's command, exit code,
duration and the last lines of its output go into a receipt (JSON) together with the git commit, the Python and OS versions and the date, so "it installs" is a file someone can read.

    python scripts/check_fresh_install.py                    # prints the plan, runs nothing
    python scripts/check_fresh_install.py --execute          # does it: DOWNLOADS the dependencies from PyPI (several hundred MB) - needs the owner's permission
    python scripts/check_fresh_install.py --execute --receipt receipts/windows-11.json

It never touches the real environment, the real ~/.delentia, or your data: the demo folder and the data home are temporary.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent


def plan(work: Path) -> List[Dict[str, Any]]:
    bin_dir = work / "venv" / ("Scripts" if os.name == "nt" else "bin")
    py = str(bin_dir / ("python.exe" if os.name == "nt" else "python"))
    env_note = "DELENTIA_HOME, HOME and USERPROFILE point at the temporary folder"
    return [
        {"name": "create a virtual environment", "cmd": [sys.executable, "-m", "venv", str(work / "venv")], "downloads": False},
        {"name": "install the project (pip downloads every dependency)", "cmd": [py, "-m", "pip", "install", "--quiet", str(ROOT)], "downloads": True, "timeout": 3600},
        {"name": "the command line starts", "cmd": [py, "-m", "rct_control_plane.cli", "version"], "downloads": False},
        {"name": "the demo folder can be made (" + env_note + ")", "cmd": [py, "-m", "rct_control_plane.cli", "demo", "init", "--dir", str(work / "demo")], "downloads": False},
        {"name": "the demo reports its status", "cmd": [py, "-m", "rct_control_plane.cli", "demo", "status", "--dir", str(work / "demo")], "downloads": False, "timeout": 900},
    ]


def run_step(step: Dict[str, Any], env: Dict[str, str]) -> Dict[str, Any]:
    started = time.time()
    try:
        done = subprocess.run(step["cmd"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=step.get("timeout", 600), cwd=str(ROOT))
        code, tail = done.returncode, (done.stdout + done.stderr).strip().splitlines()[-8:]
    except subprocess.TimeoutExpired:
        code, tail = -1, ["timed out"]
    return {"name": step["name"], "command": " ".join(step["cmd"]), "exit_code": code, "seconds": round(time.time() - started, 1), "output_tail": tail, "ok": code == 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="actually create the environment and install (downloads packages)")
    parser.add_argument("--receipt", default=None, help="where to write the JSON receipt")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="delentia-fresh-"))
    steps = plan(work)
    if not args.execute:
        print(f"plan (nothing is run; work folder would be {work}):")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step['name']}{'   [DOWNLOADS]' if step['downloads'] else ''}\n       {' '.join(step['cmd'])}")
        print("\nrun with --execute to do it (it downloads the dependencies from PyPI).")
        return 0
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    env = {**os.environ, "HOME": str(work / "home"), "USERPROFILE": str(work / "home"), "DELENTIA_HOME": str(work / "data"), "PYTHONIOENCODING": "utf-8"}
    results: List[Dict[str, Any]] = []
    for step in steps:
        outcome = run_step(step, env)
        results.append(outcome)
        print(("PASS " if outcome["ok"] else "FAIL ") + outcome["name"] + f" ({outcome['seconds']} s)")
        if not outcome["ok"]:
            break
    receipt = {"date": time.strftime("%Y-%m-%d %H:%M:%S %z"), "commit": commit, "python": sys.version.split()[0], "platform": platform.platform(), "steps": results,
               "all_passed": len(results) == len(steps) and all(r["ok"] for r in results)}
    if args.receipt:
        Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("date", "commit", "python", "platform", "all_passed")}, indent=2))
    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
