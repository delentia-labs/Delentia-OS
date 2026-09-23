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
from typing import Any, Dict, List, Optional

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
    # Round 41: two Windows LOLBins that achieve the exact same effect
    # curl/wget exist to gate - fetching attacker-controlled content
    # over the network - and were simply absent from this list. Not a
    # new risk category, just an under-populated instance of an
    # already-recognized one (confirmed by direct reproduction:
    # classify_command_risk() returned "safe" for both before this).
    "certutil ", "bitsadmin ",
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
#
# Round 41: a dedicated, systematic (not reactive) re-audit found a
# real gap in this exact fix - cmd.exe's OTHER sequential separator, a
# BARE `&` (runs the next command unconditionally, unlike `&&` which
# requires the first to succeed - confirmed interactively: `echo first
# & echo second` runs both), was never added here. `echo hi & rm -rf /`
# is the identical "prefix-safe, chained-dangerous" shape Round 38 set
# out to close, just via the one separator that fix's regex omitted.
# The lookaround guards keep `2>&1`/`>&2`-style fd-duplication (already
# relied on staying intact by the existing file-write-redirect tests)
# from being torn apart: a `&` immediately preceded by `>` is part of
# that idiom, not a command separator, and `&&` itself is matched
# whole by the earlier alternative so its own two characters are never
# individually reconsidered as a lone `&`.
_COMMAND_SEPARATOR_PATTERN = re.compile(r"&&|\|\||;|\n|\||(?<!>)&(?!&)")
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
#
# Round 40: the SAME escape class, confirmed via direct reproduction to
# also work via `pushd` (Windows cmd.exe's other real directory-change
# builtin - `pushd C:\...\Delentia-OS && python -c "..."` classified
# "safe" and wrote a real file to the real repo root, identically to
# the `cd` case). `chdir` (an alias `cd` also accepts on Windows) is the
# same risk by construction, added proactively rather than waiting for
# a third reproduction of an already-understood pattern. A command that
# invokes PowerShell (`powershell`/`pwsh`) is ALSO flagged outright -
# not because PowerShell's own `Set-Location`/`cd`/`sl` builtins were
# individually reproduced as unsafe, but because this classifier's
# sub-command splitting (`_COMMAND_SEPARATOR_PATTERN`) assumes cmd.exe/
# POSIX shell quoting rules; a `-Command "..."` argument can contain
# `;`/`&&` that this splitter would incorrectly treat as top-level
# separators (PowerShell's own quoting is genuinely different), so this
# classifier's guarantees are honestly unverified for anything running
# inside a PowerShell invocation - refusing by default until that's
# properly audited is the honest choice, not silently trusting it.
#
# Round 41: a dedicated re-audit confirmed interactively (on this
# machine, non-destructively) that cmd.exe accepts all three of
# `cd..`, `cd/d <path>` and `pushd\<path>` with NO space after the
# keyword - real, working syntax the previous `(\s|$)` boundary never
# matched, silently exempting them from the Round 39/40 "any directory
# change needs approval" decision. Broadened to also accept `.`, `/`
# and `\` immediately after the keyword, while still requiring one of
# those characters (not just any character) so unrelated commands/
# filenames that merely start with "cd" (e.g. `cdrom-tool`) are not
# falsely flagged.
_CD_COMMAND_PATTERN = re.compile(r"^(cd|chdir|pushd)(\s|[./\\]|$)", re.IGNORECASE)
# Round 41: broadened from an anchored `^...` prefix match to a
# boundary-aware SEARCH anywhere in the sub-command. The prior anchored
# match only caught a bare `powershell`/`pwsh` as the literal first
# token, silently missing the same invocation via its full path (e.g.
# `"C:\Windows\...\powershell.exe" -Command ...`, confirmed by direct
# reproduction) or nested inside another shell (`cmd /c powershell
# ...`, also confirmed) - both completely defeat the Round 40 "refuse
# any PowerShell invocation by default" decision, since that decision
# was never reached. The boundary groups avoid matching "powershell"
# as a mere substring of an unrelated word (e.g. `mypowershellscript.txt`).
_POWERSHELL_INVOCATION_PATTERN = re.compile(
    r"(?:^|[\\/\s\"'])(powershell(?:\.exe)?|pwsh(?:\.exe)?)(?:[\s\"']|$)",
    re.IGNORECASE,
)
# Round 41: the Round 38 Gap 3 fix scopes RELATIVE paths to a scratch
# CWD via Popen(cwd=...) - a starting-point change only, not a jail.
# `..` walks back out of that scratch dir using completely ordinary OS
# path semantics; confirmed by direct reproduction (scratch dir
# monkeypatched to a throwaway tmp_path in the test, never the real
# repo) that a relative-path write containing `..` lands OUTSIDE the
# scratch dir. Bounded by path/quote/whitespace/start/end characters so
# ordinary text like `echo Loading...` is not falsely flagged.
_PARENT_DIR_TRAVERSAL_PATTERN = re.compile(r"(?:^|[\\/\s\"'])\.\.(?:[\\/\s\"']|$)")
# Round 41: NTFS directory junctions (`mklink /J`) need no admin rights
# on Windows (confirmed interactively) and were not covered by any
# existing pattern. A "safe"-classified `mklink` inside the scratch dir
# builds a bridge to anywhere on disk; a second, also
# "safe"-classified relative-path write then walks through it,
# defeating the one real containment property the local backend has
# (the same Gap 3 scratch-dir scoping the `..` fix above protects).
# `fsutil hardlink create` achieves a closely related effect (a second
# name for a file outside the scratch dir becomes reachable from
# inside it) and is flagged for the same reason.
_LINK_CREATION_PATTERN = re.compile(r"\bmklink\b|\bfsutil\s+hardlink\b", re.IGNORECASE)


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
    changes directory via `cd`/`chdir`/`pushd` - with or without a
    following space - invokes PowerShell (by name, full path, or
    nested inside another shell), contains a `..` parent-directory
    traversal, or creates a filesystem link/junction/hardlink), or
    "safe" only if every real sub-command is safe."""
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
        if _POWERSHELL_INVOCATION_PATTERN.search(sub_stripped):
            worst = "needs_approval"
        if _PARENT_DIR_TRAVERSAL_PATTERN.search(sub):
            worst = "needs_approval"
        if _LINK_CREATION_PATTERN.search(sub_stripped):
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

    popen_kwargs: Dict[str, Any] = {"cwd": _sandbox_cwd()}
    if os.name == "nt":
        # typeshed only declares subprocess.CREATE_NEW_PROCESS_GROUP under
        # its win32 platform stub, so a linux-targeted mypy run (this
        # repo's CI runs on ubuntu-latest) sees no such attribute even
        # though this branch only executes on real Windows. getattr with a
        # fallback keeps the real Windows behavior identical while giving
        # mypy something it can type on every platform.
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    # Bandit B602 (subprocess with shell=True) flags this - correctly
    # identifying that shell=True is in use, but this is this module's
    # actual, deliberate purpose: _run_local is the sandbox's own command
    # executor, called only after classify_command_risk() has already
    # gated the command (denylisted prefixes refused above; risky
    # patterns routed to the approval flow before ever reaching this
    # function - see this module's own docstring and the Round 37-41
    # escape-class fixes for that real security boundary). shell=True is
    # required to support the shell syntax (pipes, redirects, chaining)
    # this sandbox is specifically built to classify and gate - switching
    # to shell=False + an argv list would not add safety here, it would
    # just break the feature, since the actual control is the
    # classification gate upstream, not shell-string avoidance.
    proc = subprocess.Popen(  # nosec B602 - see comment above
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
    popen_kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        # See _run_local's identical comment: getattr keeps real Windows
        # behavior while staying typeable on CI's linux-targeted mypy run.
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
