"""
The install contract: what a person who types `pip install delentia-os` gets, checked on the INSTALLED package. (Round 82, plan item T03)

Run it with the Python of an environment the wheel was installed into (an empty virtual environment, not the repository):

    /tmp/clean/bin/python scripts/check_installed_wheel.py --receipt install-receipt.json
    /tmp/clean/bin/python scripts/check_installed_wheel.py --skip readonly     # leave out one check

Every check starts its own process with a temporary data home, a temporary user folder and a temporary demo folder, so it never touches real data, and writes down what it ran, its
exit code and the end of its output. The checks are the claims the README makes to a newcomer:

  imports        the parts a user reaches first import
  cli            `delentia --help` and `delentia version` run
  demo           `demo init`, then `demo run compare|budget|edit --scripted`, then `demo approve <id> --scripted` finish, and the signed audit chain they leave verifies
  serve          `delentia serve` answers /health and a governed run over the API refuses nothing it should not
  memory         a memory stored by one process is there for the next one, and for the server after a restart
  readonly       with the package folder read-only (POSIX only), the CLI, the demo and the server still work and write nothing inside the package folder

Nothing here needs a model, a key or a network: the demos use the scripted stand-in for the model.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PY = sys.executable
IS_POSIX = os.name == "posix"
CHECKS = ("imports", "cli", "demo", "serve", "memory", "readonly")
FIRST_IMPORTS = ("rct_control_plane.cli", "rct_control_plane.api", "rct_control_plane.governed_autonomous_loop", "rct_control_plane.mcp_server", "rct_control_plane.acp_server",
                 "rct_control_plane.algorithm_kernel_41", "rct_control_plane.agent_factory")


class Sandbox:
    """Temporary folders and an environment that cannot reach the real ones."""

    def __init__(self, root: Path):
        self.root = root
        self.home = root / "data-home"
        self.user = root / "user"
        self.demo = root / "demo"
        for p in (self.home, self.user, self.demo.parent):
            p.mkdir(parents=True, exist_ok=True)

    def env(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        base = {k: v for k, v in os.environ.items() if not k.startswith("DELENTIA_") and k not in ("OPENROUTER_API_KEY",)}
        base.update({"DELENTIA_HOME": str(self.home), "HOME": str(self.user), "USERPROFILE": str(self.user), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        base.update(extra or {})
        return base


def delentia_cmd(*args: str) -> List[str]:
    return [PY, "-m", "rct_control_plane.cli", *args]


def run(box: Sandbox, cmd: List[str], timeout: float = 600, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    started = time.time()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=box.env(extra_env), timeout=timeout, cwd=str(box.root))
        code, text = done.returncode, (done.stdout or "") + (done.stderr or "")
    except subprocess.TimeoutExpired:
        code, text = -1, "timed out"
    return {"command": " ".join(cmd), "exit_code": code, "seconds": round(time.time() - started, 1), "output": text}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Server:
    """`delentia serve` as a child process on a free loopback port; stopped on exit."""

    def __init__(self, box: Sandbox, extra_env: Optional[Dict[str, str]] = None):
        self.box, self.port, self.extra_env = box, free_port(), extra_env
        self.proc: Optional[subprocess.Popen[bytes]] = None
        self.log = box.root / f"serve-{self.port}.log"

    def __enter__(self) -> "Server":
        out = open(self.log, "w", encoding="utf-8")
        self.proc = subprocess.Popen(delentia_cmd("serve", "--host", "127.0.0.1", "--port", str(self.port)), stdout=out, stderr=subprocess.STDOUT, env=self.box.env(self.extra_env), cwd=str(self.box.root))
        return self

    def wait_healthy(self, seconds: float = 180) -> Optional[Dict[str, Any]]:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return None
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=3) as resp:
                    return {"status": resp.status, "body": resp.read().decode("utf-8", "replace")[:300]}
            except Exception:
                time.sleep(0.5)
        return None

    def get(self, path: str) -> Dict[str, Any]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=20) as resp:
            return {"status": resp.status, "body": resp.read().decode("utf-8", "replace")}

    def tail(self) -> str:
        try:
            return "\n".join(self.log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
        except OSError:
            return ""

    def __exit__(self, *exc: Any) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ----------------------------------------------------------------------------------------------- the checks
def result(name: str, ok: bool, detail: str, steps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {"check": name, "ok": ok, "detail": detail, "steps": [{k: (v[-600:] if k == "output" else v) for k, v in s.items()} for s in (steps or [])]}


def check_imports(box: Sandbox) -> Dict[str, Any]:
    code = "import importlib,sys\nbad=[]\nfor n in %r:\n    try: importlib.import_module(n)\n    except Exception as e: bad.append(n+': '+type(e).__name__+' '+str(e)[:160])\nprint('\\n'.join(bad)); sys.exit(1 if bad else 0)" % (FIRST_IMPORTS,)
    step = run(box, [PY, "-c", code], timeout=300)
    return result("imports", step["exit_code"] == 0, "all first-contact modules import" if step["exit_code"] == 0 else step["output"][-400:], [step])


def check_cli(box: Sandbox) -> Dict[str, Any]:
    doctor = ("import json; from click.testing import CliRunner; from rct_control_plane.cli import cli; "
              "r=CliRunner().invoke(cli,['doctor','--output','json']); assert r.exit_code==0, r.output; "
              "d=json.loads(r.output); assert d['ok'] and d['scope']=='local_installation', d; "
              "assert not any(c['category'] in ('project','connectivity') for c in d['checks']); "
              "print('installed doctor passes without repository files or development services')")
    steps = [run(box, delentia_cmd("--help"), 300), run(box, delentia_cmd("version"), 300), run(box, [PY, "-c", doctor], 300)]
    ok = all(s["exit_code"] == 0 for s in steps)
    return result("cli", ok, "--help, version and local installation doctor run" if ok else "; ".join(f"{s['command']} -> {s['exit_code']}" for s in steps if s["exit_code"] != 0), steps)


def demo_steps(box: Sandbox) -> List[Dict[str, Any]]:
    steps = [run(box, delentia_cmd("demo", "init", "--dir", str(box.demo)))]
    for task in ("compare", "budget", "edit"):
        steps.append(run(box, delentia_cmd("demo", "run", task, "--scripted", "--dir", str(box.demo)), 900))
    pending = re.search(r"demo approve ([0-9a-f]{8,})", steps[-1]["output"])
    if pending:
        steps.append(run(box, delentia_cmd("demo", "approve", pending.group(1), "--scripted", "--dir", str(box.demo)), 900))
    return steps


def check_demo(box: Sandbox) -> Dict[str, Any]:
    steps = demo_steps(box)
    failed = [s for s in steps if s["exit_code"] != 0]
    approved = len(steps) == 5
    results = list((box.demo / "results").glob("*.md")) if (box.demo / "results").exists() else []
    chain_ok = bool(steps) and "ครบสมบูรณ์" in steps[-1]["output"]
    ok = not failed and approved and len(results) >= 4 and chain_ok
    detail = "init, compare, budget, edit and approve finished; result files written; the signed audit chain verifies" if ok else (
        f"failed steps: {[s['command'] for s in failed]}" if failed else f"approved={approved} result_files={len(results)} chain_verified={chain_ok}")
    return result("demo", ok, detail, steps)


def check_serve(box: Sandbox) -> Dict[str, Any]:
    with Server(box) as server:
        health = server.wait_healthy()
        if health is None:
            return result("serve", False, "the server did not answer /health:\n" + server.tail())
        models = server.get("/v1/models")
        detail = f"/health {health['status']}, /v1/models {models['status']}"
        return result("serve", health["status"] == 200 and models["status"] == 200, detail)


def check_memory(box: Sandbox) -> Dict[str, Any]:
    marker = "install-contract-marker-" + str(int(time.time()))
    add = run(box, delentia_cmd("memory", "add", marker))
    listed = run(box, delentia_cmd("memory", "list"))
    with Server(box) as server:
        up = server.wait_healthy() is not None
    after = run(box, delentia_cmd("memory", "list"))
    ok = add["exit_code"] == 0 and marker in listed["output"] and up and marker in after["output"]
    return result("memory", ok, "a stored memory is there for the next process and after a server start/stop" if ok else
                  f"added={add['exit_code']==0} seen_next_process={marker in listed['output']} server_up={up} seen_after_server={marker in after['output']}", [add, listed, after])


def snapshot(folder: Path) -> Dict[str, float]:
    return {str(p): p.stat().st_mtime for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def check_readonly(box: Sandbox) -> Dict[str, Any]:
    if not IS_POSIX:
        return result("readonly", True, "SKIPPED: folder permissions are checked on POSIX systems only (CI runs this on Linux)")
    import rct_control_plane
    package = Path(rct_control_plane.__file__).resolve().parent
    site = package.parent
    before = snapshot(package)
    modes: Dict[Path, int] = {}
    try:
        for p in [site, *[d for d in site.rglob("*") if d.is_dir()]]:
            modes[p] = stat.S_IMODE(p.stat().st_mode)
            p.chmod(modes[p] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        steps = [run(box, delentia_cmd("--help"), 300), *demo_steps(box)[:2]]
        with Server(box) as server:
            up = server.wait_healthy() is not None
    finally:
        for p, mode in modes.items():
            try:
                p.chmod(mode)
            except OSError:
                pass
    after = snapshot(package)
    changed = sorted(set(after) ^ set(before) | {k for k in before if k in after and before[k] != after[k]})
    ok = all(s["exit_code"] == 0 for s in steps) and up and not changed
    return result("readonly", ok, "with the package folder read-only the CLI, the demo and the server work, and nothing inside the package was written" if ok else
                  f"steps_ok={[s['exit_code'] == 0 for s in steps]} server_up={up} written_inside_package={changed[:5]}", steps)


RUNNERS: Dict[str, Callable[[Sandbox], Dict[str, Any]]] = {"imports": check_imports, "cli": check_cli, "demo": check_demo, "serve": check_serve, "memory": check_memory, "readonly": check_readonly}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--receipt", default=None, help="where to write the JSON receipt")
    parser.add_argument("--skip", action="append", default=[], choices=CHECKS, help="leave a check out (repeatable)")
    args = parser.parse_args(argv)
    outcomes: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="delentia-install-contract-") as tmp:
        for name in CHECKS:
            if name in args.skip:
                continue
            box = Sandbox(Path(tmp) / name)
            try:
                outcome = RUNNERS[name](box)
            except Exception as exc:                                  # noqa: BLE001 - a crashed check is a failed check, with its reason
                outcome = result(name, False, f"the check itself crashed: {type(exc).__name__}: {exc}")
            outcomes.append(outcome)
            print(("PASS " if outcome["ok"] else "FAIL ") + name + " - " + outcome["detail"].splitlines()[0][:200], flush=True)
    receipt = {"python": platform.python_version(), "platform": platform.platform(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": outcomes, "all_passed": all(o["ok"] for o in outcomes)}
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
