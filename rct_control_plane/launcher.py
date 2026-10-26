"""
Round 101C: one double click that starts everything and opens the Desk (`delentia launch`), and one that stops it (`delentia launch --stop`).

For a person who installed the program with the Windows installer (or `pip install`) and does not want two terminals: it starts `delentia serve` and the Desk page server as background processes with no console window,
waits until both answer, and opens the browser at http://localhost:PORT. Their output goes to log files under the Delentia home (`logs/`), their process numbers to `run/`, so `--stop` can end exactly what this started.

What it does NOT do: it does not create approver keys, change settings, or start anything that was not already part of `serve` and `desk`; it does not print or store the API token (the loopback address needs none).
Standard library only.
"""
from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

API_PORT = 8000
DESK_PORT = 3010


def home() -> Path:
    from rct_control_plane import data_home
    base = data_home.data_home() or (Path.home() / ".delentia")
    base.mkdir(parents=True, exist_ok=True)
    return base


def healthy(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:                      # noqa: S310 - a loopback address the caller built
            return response.status == 200
    except Exception:                                                                      # noqa: BLE001 - not answering is the answer
        return False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)                    # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259                                               # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                                                                   # a finished child nobody has collected yet is a zombie: it answers kill(0) but is not running
        with open(f"/proc/{pid}/stat", "rb") as handle:
            return handle.read().rsplit(b")", 1)[1].split()[0] != b"Z"
    except (OSError, IndexError):
        return True


def start_detached(argv: List[str], log_file: Path, pid_file: Path, env: Optional[Dict[str, str]] = None) -> int:
    """Start `argv` with no window, output to `log_file`, remember its process number in `pid_file`."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000                     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    with open(log_file, "ab") as log:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env or os.environ.copy(), **kwargs)      # noqa: S603 - argv is built by this module
    pid_file.write_text(str(proc.pid), encoding="ascii")
    return proc.pid


def stop_pid_file(pid_file: Path, grace: float = 8.0) -> str:
    """'stopped', 'not running' or 'no record'. Only a process this module recorded is touched."""
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return "no record"
    if not pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        return "not running"
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)     # noqa: S603,S607 - fixed program, a number we wrote
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and pid_alive(pid):
        time.sleep(0.2)
    pid_file.unlink(missing_ok=True)
    return "stopped"


def wait_healthy(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if healthy(url):
            return True
        time.sleep(0.5)
    return False


def _lock_holder_gone(path: Path, stale_after: float) -> bool:
    """True when the process that wrote the lock has ended, or the lock is older than any start should take."""
    try:
        pid_text, stamp = path.read_text(encoding="ascii").split()
        return not pid_alive(int(pid_text)) or time.time() - float(stamp) > stale_after
    except FileNotFoundError:
        return False                                            # released while we looked: just try to take it
    except (OSError, ValueError):
        try:
            return time.time() - path.stat().st_mtime > stale_after       # unreadable or half-written: only age decides
        except OSError:
            return False


@contextlib.contextmanager
def launch_lock(run: Path, wait_seconds: float, stale_after: float = 600.0) -> Iterator[None]:
    """Only one start at a time. Two double clicks at once used to find nothing running and START TWO agents (the second one failed on the port or, worse, the first one's pid record was overwritten and
    `--stop` could no longer end it). The second click now waits here, then finds what the first started. A lock left by a process that died, or older than `stale_after`, is taken over."""
    run.mkdir(parents=True, exist_ok=True)
    path = run / "launch.lock"
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_holder_gone(path, stale_after):
                taken = path.with_name(f"launch.lock.stale-{os.getpid()}")
                try:
                    os.replace(str(path), str(taken))          # rename is atomic: of several takers only one moves the stale file
                    taken.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            if time.monotonic() > deadline:
                raise RuntimeError(f"another start of Delentia is still in progress ({path}). Wait a minute, or delete that file if you are sure nothing is starting") from None
            time.sleep(0.2)
            continue
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"{os.getpid()} {time.time()}")
        break
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def launch(api_port: int = API_PORT, desk_port: int = DESK_PORT, wait_seconds: float = 120.0, say=print) -> Dict[str, Any]:
    """Start (or find) the agent and the Desk. Returns {"url", "started": [...], "already": [...]}; raises RuntimeError with a sentence a person can act on."""
    from rct_control_plane import desk_assets
    if desk_assets.find_desk_root() is None:                    # say so BEFORE starting anything: a missing page is not worth a started agent
        raise RuntimeError(desk_assets.missing_message())
    base = home()
    with launch_lock(base / "run", wait_seconds + 90.0):
        return _launch_locked(base, api_port, desk_port, wait_seconds, say)


def _launch_locked(base: Path, api_port: int, desk_port: int, wait_seconds: float, say) -> Dict[str, Any]:
    logs, run = base / "logs", base / "run"
    started: List[str] = []
    already: List[str] = []
    api_health = f"http://127.0.0.1:{api_port}/health"
    if healthy(api_health):
        already.append("agent")
    else:
        say("Starting the agent (the first start takes about 20 seconds)...")
        start_detached([sys.executable, "-m", "rct_control_plane.cli", "serve", "--port", str(api_port)], logs / "serve.log", run / "serve.pid")
        started.append("agent")
        if not wait_healthy(api_health, wait_seconds):
            raise RuntimeError(f"the agent did not answer within {int(wait_seconds)} seconds. Look at {logs / 'serve.log'} for the reason")
    desk_url = f"http://localhost:{desk_port}"
    if healthy(f"http://127.0.0.1:{desk_port}/"):
        already.append("desk")
    else:
        say("Starting the Desk page...")
        start_detached([sys.executable, "-m", "rct_control_plane.cli", "desk", "--no-browser", "--port", str(desk_port), "--gateway", f"http://127.0.0.1:{api_port}"], logs / "desk.log", run / "desk.pid")
        started.append("desk")
        if not wait_healthy(f"http://127.0.0.1:{desk_port}/", 60):
            raise RuntimeError(f"the Desk page did not start. Look at {logs / 'desk.log'} for the reason (is port {desk_port} used by something else?)")
    return {"url": desk_url, "started": started, "already": already, "logs": str(logs)}


def stop(say=print) -> Dict[str, str]:
    run = home() / "run"
    result = {"desk": stop_pid_file(run / "desk.pid"), "agent": stop_pid_file(run / "serve.pid")}
    say(json.dumps(result))
    return result


def message_box(title: str, text: str) -> bool:
    """Show a message in a window when there is no console to print to (a double click on the Start-menu shortcut runs without one). False when there is nowhere to show it."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)                             # MB_ICONERROR
        return True
    except Exception:                                                                      # noqa: BLE001
        return False


def has_console() -> bool:
    return sys.stdout is not None and sys.stderr is not None
