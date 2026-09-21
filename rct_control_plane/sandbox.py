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
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

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

# Round 37: closes a real gap found via direct incident, not
# speculation - a real local-LLM-driven test (test_scheduler_real.py's
# reminder goal, dispatched through the real Ollama-backed
# AutonomousLoop) produced a shell command starting with "echo" that
# redirected output into `rct_control_plane/algorithm_kernel_41.py`,
# truncating the entire 41-algorithm kernel file to 2 lines. Prefix-only
# matching against _DENYLISTED_PREFIXES/_MEDIUM_RISK_PREFIXES cannot
# catch this - the command's PREFIX ("echo") is completely benign; the
# danger is the file-write REDIRECT that can appear anywhere in the
# string. Recovered via `git checkout` (the corruption was
# working-tree-only, never committed) - this pattern now pauses for
# approval instead of executing silently. Deliberately does NOT flag
# `2>&1`/`>&2`-style file-descriptor redirects (extremely common and
# not a file-write risk) via the `(?!&)` negative lookahead.
_FILE_WRITE_REDIRECT_PATTERN = re.compile(r">{1,2}(?!&)")

# Round 38: a second, real gap found via a dedicated re-audit the Round
# 37 incident motivated - classify_command_risk() only ever checked the
# PREFIX of the whole command string. `echo hi; rm -rf /` does not
# START WITH "rm -rf", so it sailed through as "safe" even though a
# real denylisted command is chained onto it. Same story for `&&`/`||`/
# `|`, and for `$(...)`/backtick command substitution, which can smuggle
# an arbitrary command inside an outer command that itself looks benign
# (e.g. `echo $(rm -rf /)`). Splits the command into every real
# sub-command a shell would actually execute and classifies each one
# independently - the overall risk is the worst risk found across all
# of them, with "denied" short-circuiting immediately.
_COMMAND_SEPARATOR_PATTERN = re.compile(r"&&|\|\||;|\n|\|")
_SUBSTITUTION_PATTERN = re.compile(r"\$\(([^)]*)\)|`([^`]*)`")

# Round 39: a THIRD escape class found via a dedicated re-audit,
# reproduced directly (not speculation) - `run_sandboxed`'s CWD-scoping
# fix (Round 38 Gap 3) sets the SUBPROCESS's INITIAL working directory
# via Popen(cwd=...), but a real `cd <path> && ...` command changes the
# SHELL's own current directory for everything that follows it in the
# same command line, completely overriding that. Confirmed by direct
# reproduction: `cd C:\...\Delentia-OS && python -c "open('file.py',
# 'w').write(...)"` - no `>` character, no denylisted/medium-risk
# prefix on any `&&`-split sub-command - classified "safe" and executed
# by default, writing a real file into the real repo root. Any `cd `
# sub-command (to anywhere - not just a specific dangerous path, since
# ANY directory change invalidates the CWD-scoping guarantee for every
# subsequent relative path) now needs approval.
_CD_COMMAND_PATTERN = re.compile(r"^cd(\s|$)", re.IGNORECASE)


def _split_into_subcommands(command: str) -> List[str]:
    parts = [p for p in _COMMAND_SEPARATOR_PATTERN.split(command)]
    for match in _SUBSTITUTION_PATTERN.finditer(command):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        if inner:
            parts.append(inner)
    return [p.strip() for p in parts if p.strip()]


def classify_command_risk(command: str) -> str:
    """Returns "denied" (any real sub-command matches
    _DENYLISTED_PREFIXES), "needs_approval" (any real sub-command
    matches _MEDIUM_RISK_PREFIXES, contains a real file-write redirect,
    or changes directory via `cd`), or "safe" only if every real
    sub-command is safe."""
    worst = "safe"
    for sub in _split_into_subcommands(command):
        sub_stripped = sub.lower()
        for prefix in _DENYLISTED_PREFIXES:
            if sub_stripped.startswith(prefix.lower()):
                return "denied"
        for prefix in _MEDIUM_RISK_PREFIXES:
            if sub_stripped.startswith(prefix.lower()):
                worst = "needs_approval"
        if _FILE_WRITE_REDIRECT_PATTERN.search(sub):
            worst = "needs_approval"
        if _CD_COMMAND_PATTERN.match(sub_stripped):
            worst = "needs_approval"
    return worst


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


# Round 38: a THIRD real gap found via direct incident reproduction (not
# speculation) - the file-write-redirect fix (Gap 1) and the chaining
# fix (Gap 2) both operate on the SHELL COMMAND STRING, one abstraction
# level above what actually happened here: a real local-LLM-driven test
# (a "say hello, no tool needed" goal - the same documented confusion
# pattern that makes this model misbehave) hallucinated a call to the
# sandboxed-command tool that overwrote algorithm_kernel_41.py a SECOND
# time, immediately after Gap 1/2's fix landed. The write almost
# certainly happened via a mechanism with no `>` character at all (e.g.
# `python -c "open('rct_control_plane/algorithm_kernel_41.py','w')..."`)
# - a regex over the command string can never enumerate every possible
# file-writing API in every possible interpreter. The durable fix is a
# different layer entirely: relative paths inside the sandboxed command
# now resolve against a dedicated scratch directory, NOT this process's
# real working directory (which, for `rct serve`/pytest, IS the real
# source tree) - so `open("rct_control_plane/algorithm_kernel_41.py",
# "w")` from INSIDE a sandboxed command now creates a harmless file
# under the scratch dir instead of touching the real kernel file. This
# does not stop an ABSOLUTE path write - real container/VM isolation
# (already disclosed above as separate follow-up work) is what closes
# that - but it closes the exact relative-path-escape class that both
# real incidents actually exhibited.
_SANDBOX_SCRATCH_DIR = os.path.join("workspace_output", "sandbox_scratch")


def _sandbox_cwd() -> str:
    os.makedirs(_SANDBOX_SCRATCH_DIR, exist_ok=True)
    return os.path.abspath(_SANDBOX_SCRATCH_DIR)


def _run_local(command: str, timeout_seconds: float) -> SandboxResult:
    stripped = command.strip().lower()
    for prefix in _DENYLISTED_PREFIXES:
        if stripped.startswith(prefix.lower()):
            return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                                  blocked_reason=f"command prefix '{prefix}' is denylisted")

    popen_kwargs = {"cwd": _sandbox_cwd()}
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


def run_sandboxed(
    command: str, timeout_seconds: float = 10.0, backend: str = "local", approved: bool = False,
) -> SandboxResult:
    """Real subprocess execution with real timeout/output-cap/denylist
    protections. See this module's own docstring for the honest scope
    of what "sandbox" means here. On timeout, the REAL child process
    tree is killed (not just abandoned) - see _kill_process_tree().
    `backend="docker"` routes to run_sandboxed_docker (Round 24 Task 33);
    default "local" is unchanged from Round 21 (Zero-Delete).

    Round 38: enforces classify_command_risk() HERE, at the one real
    entry point every caller shares - including the delentia_run_
    sandboxed_command MCP tool, which calls this function directly and
    has NO risk gate of its own. Before this, the only place that ever
    checked _MEDIUM_RISK_PREFIXES/the file-write-redirect pattern was
    AutonomousLoop.run()'s own pre-dispatch check - a real, confirmed
    bypass: any OTHER caller of the MCP tool (a direct MCP client, a
    future code path that doesn't route through AutonomousLoop) got
    ZERO medium-risk protection, only the hard denylist. A "denied"
    command is refused unconditionally; a "needs_approval" command is
    refused UNLESS the caller passes `approved=True`, meaning a real
    approval step already happened upstream (e.g. a human/Architect
    sign-off, or - for AutonomousLoop's own call sites, which already
    halt and never reach this function for a needs_approval command -
    this is defense in depth, not a behavior change for that path)."""
    risk = classify_command_risk(command)
    if risk == "denied":
        return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                              blocked_reason="command is denylisted (risk=denied)")
    if risk == "needs_approval" and not approved:
        return SandboxResult(stdout="", stderr="", exit_code=None, timed_out=False,
                              blocked_reason="command needs approval before running (risk=needs_approval) "
                                             "- call again with approved=True after explicit sign-off")
    if backend == "docker":
        return run_sandboxed_docker(command, timeout_seconds=timeout_seconds)
    return _run_local(command, timeout_seconds)
