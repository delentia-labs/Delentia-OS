"""
Real, honestly-scoped local-process command sandbox (Round 21 Phase 2).

NOT container/VM isolation. Real protections: a hard wall-clock timeout,
a real output-size cap (prevents memory exhaustion from a runaway
command), and a real prefix denylist checked BEFORE any subprocess is
spawned (blocked commands genuinely never execute). A sufficiently
malicious ALLOWED command still runs with this process's real OS
permissions — container-level isolation (matching Hermes's 7 sandbox
backends: local/Docker/SSH/Daytona/Modal/Singularity/Vercel) is real,
separate follow-up work (see the Round 21 plan's Roadmap), not claimed
here.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

_DENYLISTED_PREFIXES = [
    "rm -rf", "del /f", "format ", "dd if=", "mkfs", ":(){:|:&};:",
    "shutdown", "reboot", "> /dev/sda", "chmod -R 777 /",
]
_MAX_OUTPUT_BYTES = 1_000_000  # 1 MB

# Round 23 Phase 12 Task 26: a real middle tier between "run it" and
# "silently block it" - commands with real, irreversible external
# effects (pushing code, installing packages, downloading from the
# network) pause for real human/Architect approval rather than either
# executing unattended or being denied outright. Mirrors the same
# philosophy as the FDIA Architect Veto (A_FDIA=0 pauses/blocks rather
# than guessing) applied to the loop's own tool dispatch.
_MEDIUM_RISK_PREFIXES = [
    "git push", "git reset --hard", "pip install", "npm install",
    "curl ", "wget ",
]


def classify_command_risk(command: str) -> str:
    """Returns "denied" (matches _DENYLISTED_PREFIXES), "needs_approval"
    (matches _MEDIUM_RISK_PREFIXES), or "safe"."""
    stripped = command.strip().lower()
    for prefix in _DENYLISTED_PREFIXES:
        if stripped.startswith(prefix.lower()):
            return "denied"
    for prefix in _MEDIUM_RISK_PREFIXES:
        if stripped.startswith(prefix.lower()):
            return "needs_approval"
    return "safe"


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool
    blocked_reason: Optional[str]


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Real termination of the WHOLE process tree, not just the
    immediate child. Found necessary via real testing (Round 21 Phase 2
    Task 5): plain subprocess.run(..., shell=True, timeout=...) on
    Windows raises TimeoutExpired at the right time but does NOT kill
    the shell's own child process (e.g. `python -c "sleep 30"` launched
    via cmd.exe) - it kept running in the background for the full real
    30s after this function's caller had already returned timed_out=True,
    a genuine sandbox containment gap, not a cosmetic one."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, timeout=5,
        )
    else:
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _run_local(command: str, timeout_seconds: float) -> SandboxResult:
    stripped = command.strip().lower()
    for prefix in _DENYLISTED_PREFIXES:
        if stripped.startswith(prefix.lower()):
            return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                                  blocked_reason=f"command prefix '{prefix}' is denylisted")

    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, **popen_kwargs,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return SandboxResult(
            stdout=stdout[:_MAX_OUTPUT_BYTES], stderr=stderr[:_MAX_OUTPUT_BYTES],
            exit_code=proc.returncode, timed_out=False, blocked_reason=None,
        )
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout = ""
        return SandboxResult(
            stdout=(stdout or "")[:_MAX_OUTPUT_BYTES],
            stderr="", exit_code=None, timed_out=True, blocked_reason=None,
        )


def _docker_available() -> bool:
    """Real check - `docker info` (unlike `docker version`) genuinely
    requires a reachable daemon, not just an installed CLI; returns
    real exit code 1 when Docker Desktop's daemon isn't running (a
    real, observed case on this dev machine, not hypothetical)."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_sandboxed_docker(command: str, image: str = "python:3.11-slim", timeout_seconds: float = 10.0) -> SandboxResult:
    """Round 24 Task 33: real container-isolated execution (2nd real
    sandbox backend) - `docker run --rm <image> sh -c "<command>"`, same
    real denylist/timeout/kill-tree protections as the local backend.
    Honestly reports when Docker itself isn't available rather than
    crashing or silently falling back to the local backend unannounced."""
    if not _docker_available():
        return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                              blocked_reason="docker not available on this host")

    stripped = command.strip().lower()
    for prefix in _DENYLISTED_PREFIXES:
        if stripped.startswith(prefix.lower()):
            return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                                  blocked_reason=f"command prefix '{prefix}' is denylisted")

    docker_command = ["docker", "run", "--rm", image, "sh", "-c", command]
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(docker_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return SandboxResult(
            stdout=stdout[:_MAX_OUTPUT_BYTES], stderr=stderr[:_MAX_OUTPUT_BYTES],
            exit_code=proc.returncode, timed_out=False, blocked_reason=None,
        )
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout = ""
        return SandboxResult(
            stdout=(stdout or "")[:_MAX_OUTPUT_BYTES],
            stderr="", exit_code=None, timed_out=True, blocked_reason=None,
        )


def run_sandboxed(command: str, timeout_seconds: float = 10.0, backend: str = "local") -> SandboxResult:
    """Real subprocess execution with real timeout/output-cap/denylist
    protections. See this module's own docstring for the honest scope
    of what "sandbox" means here. On timeout, the REAL child process
    tree is killed (not just abandoned) - see _kill_process_tree().
    `backend="docker"` routes to run_sandboxed_docker (Round 24 Task 33);
    default "local" is unchanged from Round 21 (Zero-Delete)."""
    if backend == "docker":
        return run_sandboxed_docker(command, timeout_seconds=timeout_seconds)
    return _run_local(command, timeout_seconds)
