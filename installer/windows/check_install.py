"""
Check an installed Delentia (Round 101E). Standard library only, so it runs with the Python the installer put next to it:

    "%LOCALAPPDATA%\\Programs\\Delentia\\python\\python.exe" "%LOCALAPPDATA%\\Programs\\Delentia\\check_install.py"

What it does, in order, and says for each step PASS, FAIL or SKIP with the reason:
  1. the files the installer leaves are there and the installer's own log ends with "done"
  2. the program imports and its version is the version of the wheel that was installed
  3. the Desk (the web pages) is inside the package
  4. the libraries it needs import
  5. it STARTS on two free ports with a throw-away data folder (your real ~/.delentia is not touched), the agent answers /health,
     the Desk answers with its title, the page's readiness call answers, and `launch --stop` ends exactly what was started
It writes everything to check_install_report.txt next to this file (UTF-8) so it can be sent to someone who helps. It never prints or stores a key.
Exit code 0 only when nothing failed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
LINES: List[str] = []
FAILED: List[str] = []


def say(text: str = "") -> None:
    LINES.append(text)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:                                   # a console code page that cannot show a letter must not stop the check
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def step(name: str, fn: Callable[[], Optional[str]]) -> None:
    """A step passes when `fn` returns normally (its return value is the evidence), fails when it raises, and is skipped when it returns "SKIP: reason"."""
    try:
        evidence = fn() or ""
    except Exception as err:                                     # noqa: BLE001 - the report must carry the reason of any failure
        FAILED.append(name)
        say(f"  FAIL  {name}: {err}")
        return
    if evidence.startswith("SKIP:"):
        say(f"  SKIP  {name}: {evidence[5:].strip()}")
    else:
        say(f"  PASS  {name}" + (f"  ({evidence})" if evidence else ""))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, timeout: float = 5.0) -> Tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=timeout) as response:                      # noqa: S310 - a loopback address built below
        return response.status, response.read()


def run(python: Path, args: List[str], env: dict, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run([str(python), *args], env=env, capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir(), encoding="utf-8", errors="replace")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-dir", type=Path, default=HERE, help="the folder the installer wrote (default: the folder of this file)")
    ap.add_argument("--python", type=Path, default=None, help="the Python to test (default: <app-dir>\\python\\python.exe)")
    ap.add_argument("--pause", action="store_true", help="wait for Enter at the end (for a double click)")
    ap.add_argument("--no-start", action="store_true", help="do not start the program (steps 1 to 4 only)")
    args = ap.parse_args(argv)
    app = args.app_dir.resolve()
    python = (args.python or app / "python" / "python.exe").resolve()
    scratch = Path(tempfile.mkdtemp(prefix="delentia-check-"))
    env = {**os.environ, "DELENTIA_HOME": str(scratch / "home"), "DELENTIA_UPDATE_CHECK": "off", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    env.pop("DELENTIA_API_TOKEN", None)
    state: dict = {}

    say(f"Delentia installation check  ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    say(f"  folder  {app}")
    say(f"  python  {python}")
    say("  data    a throw-away folder is used for this check; your own Delentia data is not touched")
    say()

    def files() -> str:
        if not python.is_file():
            raise RuntimeError(f"{python} is missing: the installer did not finish copying (run it again)")
        wheels = sorted((app / "wheel").glob("delentia_os-*.whl"))
        if not wheels:
            raise RuntimeError("the wheel folder is empty")
        state["wheel_version"] = wheels[-1].name.split("-")[1]
        log = app / "install.log"
        if not log.is_file():
            raise RuntimeError("install.log is missing: the installer's last step did not run")
        tail = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()][-1:]
        if not tail or not tail[0].rstrip().endswith("done"):
            raise RuntimeError(f"the installer's log does not end with 'done' (it ends with: {tail[0][:120] if tail else 'nothing'}). Read {log}")
        return f"wheel {wheels[-1].name}"

    def version() -> str:
        result = run(python, ["-m", "rct_control_plane.cli", "--version"], env)
        match = re.search(r"version\s+(\S+)", result.stdout)
        if result.returncode != 0 or not match:
            raise RuntimeError(f"`delentia --version` failed: {(result.stderr or result.stdout)[-300:]}")
        if "wheel_version" in state and match.group(1) != state["wheel_version"]:
            raise RuntimeError(f"installed version {match.group(1)} is not the installer's wheel {state['wheel_version']}")
        return match.group(1)

    def desk() -> str:
        result = run(python, ["-c", "from rct_control_plane import desk_assets; r = desk_assets.find_desk_root(); print(r if r else 'NONE')"], env)
        out = result.stdout.strip()
        if result.returncode != 0 or out in ("", "NONE"):
            raise RuntimeError("the web pages (Desk) are not inside the installed package")
        count = sum(1 for p in Path(out).rglob("*") if p.is_file())
        return f"{count} files"

    def libraries() -> str:
        code = "import importlib.util as u; names=['cryptography','fastapi','uvicorn','numpy','click','pydantic']; print(','.join(n for n in names if u.find_spec(n) is None))"
        result = run(python, ["-c", code], env)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-300:])
        if result.stdout.strip():
            raise RuntimeError(f"missing libraries: {result.stdout.strip()}")
        return "fastapi, uvicorn, numpy, cryptography, click, pydantic"

    def start_and_stop() -> str:
        if args.no_start:
            return "SKIP: --no-start"
        api, page = free_port(), free_port()
        started = run(python, ["-m", "rct_control_plane.cli", "launch", "--no-browser", "--api-port", str(api), "--desk-port", str(page)], env, timeout=240)
        try:
            if started.returncode != 0:
                raise RuntimeError(f"`launch` failed (code {started.returncode}): {(started.stderr or started.stdout)[-400:]}. Logs: {scratch / 'home' / 'logs'}")
            code, body = get(f"http://127.0.0.1:{api}/health")
            if code != 200 or b"healthy" not in body:
                raise RuntimeError(f"the agent answered {code} {body[:80]!r}")
            code, body = get(f"http://127.0.0.1:{page}/")
            if code != 200 or b"Delentia Desk" not in body:
                raise RuntimeError(f"the Desk page answered {code} and does not carry its title")
            code, body = get(f"http://127.0.0.1:{api}/v1/desk/readiness")
            if code != 200 or not json.loads(body.decode("utf-8")):
                raise RuntimeError(f"the readiness call answered {code}")
            return f"agent on {api}, Desk on {page}"
        finally:
            stopped = run(python, ["-m", "rct_control_plane.cli", "launch", "--stop"], env, timeout=120)
            time.sleep(1.0)
            state["stopped"] = stopped.stdout.strip()
            state["ports"] = (api, page)

    def really_stopped() -> str:
        if args.no_start or "ports" not in state:
            return "SKIP: nothing was started"
        for port in state["ports"]:
            try:
                get(f"http://127.0.0.1:{port}/", timeout=2.0)
            except Exception:                                    # noqa: BLE001 - not answering is the pass
                continue
            raise RuntimeError(f"something still answers on port {port} after `launch --stop`")
        return state.get("stopped", "")

    step("1  the installer's files and its log", files)
    step("2  the program starts and has the installed version", version)
    step("3  the Desk (web pages) is inside the package", desk)
    step("4  the libraries it needs import", libraries)
    step("5  it starts, answers, and stops cleanly", start_and_stop)
    step("6  nothing is left running", really_stopped)
    say()
    verdict = "ALL PASSED" if not FAILED else f"{len(FAILED)} FAILED: " + "; ".join(FAILED)
    say(f"Result: {verdict}")
    say("ผลการตรวจ: " + ("ผ่านทั้งหมด" if not FAILED else f"ไม่ผ่าน {len(FAILED)} ข้อ ดูรายงานข้างบน แล้วส่งไฟล์ check_install_report.txt ให้ผู้ช่วย"))
    try:
        (app / "check_install_report.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
        say(f"Report written to {app / 'check_install_report.txt'}")
    except OSError:
        report = Path(tempfile.gettempdir()) / "check_install_report.txt"
        report.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        say(f"Report written to {report}")
    shutil.rmtree(scratch, ignore_errors=True)
    if args.pause:
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
