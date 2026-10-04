"""
Round 59: resource limits for the local shell sandbox.

The local sandbox runs a command as the same OS user as the agent, so it is NOT a jail and this module does not make it one: a command can still read what that user can read.
What it adds is a ceiling on how much damage a runaway or hostile command can do to the machine itself, and a guarantee that nothing it started outlives it:

  * memory: at most DELENTIA_SANDBOX_MEM_MB (default 2048; 0 = no limit). Windows: a Job Object memory limit; Linux/macOS: RLIMIT_AS;
  * processes (Windows): at most DELENTIA_SANDBOX_MAX_PROCS in the job (default 64; 0 = no limit), which stops a fork bomb; POSIX has no per-command process limit that does not
    also count the user's other processes, so none is set there;
  * CPU time (POSIX): the command's timeout plus a few seconds; file size: 512 MB per file; no core dumps;
  * Windows: the job is KILL_ON_JOB_CLOSE, so anything the command left running dies when the command's job is closed (after it ends, or if this process goes away). POSIX: the
    command already runs in its own session and the timeout path kills the whole process tree.

Known gap (Windows): a Microsoft Store python.exe started by the shell is launched by the Store's alias mechanism OUTSIDE the job (measured: it allocated past the ceiling),
so the memory ceiling does not bind that one launcher; PowerShell, cmd built-ins and ordinary python.exe installs are inside. Not covered: reading or writing files the user can, network access, the denylist/approval gates upstream are what decide WHAT may run. For a boundary that holds against a hostile command use
the `docker` or `ssh` backend.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Optional

MEM_ENV = "DELENTIA_SANDBOX_MEM_MB"
PROCS_ENV = "DELENTIA_SANDBOX_MAX_PROCS"
DEFAULT_MEM_MB = 2048
DEFAULT_PROCS = 64
MAX_FILE_BYTES = 512 * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def limits() -> dict:
    return {"mem_mb": _env_int(MEM_ENV, DEFAULT_MEM_MB), "max_procs": _env_int(PROCS_ENV, DEFAULT_PROCS)}


def posix_preexec(timeout_seconds: float) -> Callable[[], None]:
    """Runs in the child between fork and exec: its own session, then the limits. A limit that cannot be set (a hardened system) is skipped, never fatal."""
    mem_bytes = limits()["mem_mb"] * 1024 * 1024
    cpu_seconds = int(timeout_seconds) + 5

    def prepare() -> None:
        os.setsid()  # type: ignore[attr-defined,unused-ignore]
        try:
            import resource
        except ImportError:                                      # pragma: no cover - POSIX always has it
            return
        for which, value in ((getattr(resource, "RLIMIT_AS", None), mem_bytes), (getattr(resource, "RLIMIT_CPU", None), cpu_seconds),
                             (getattr(resource, "RLIMIT_FSIZE", None), MAX_FILE_BYTES), (getattr(resource, "RLIMIT_CORE", None), 0)):
            if which is None or (which == getattr(resource, "RLIMIT_AS", None) and value == 0):
                continue
            try:
                soft, hard = resource.getrlimit(which)  # type: ignore[attr-defined,unused-ignore]
                cap = value if hard in (-1, resource.RLIM_INFINITY) else min(value, hard)  # type: ignore[attr-defined,unused-ignore]
                resource.setrlimit(which, (cap, hard))  # type: ignore[attr-defined,unused-ignore]
            except (ValueError, OSError):
                continue
    return prepare


# ---------------------------------------------------------------------------- Windows Job Objects

def windows_job() -> Optional[Any]:
    """A Job Object with the memory and process limits and KILL_ON_JOB_CLOSE, or None (not Windows, or the call failed: the command then runs as before)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    kernel32 = getattr(ctypes, "windll", None)
    if kernel32 is None:
        return None
    kernel32 = kernel32.kernel32

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("Basic", BasicLimits), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    configured = limits()
    flags = 0x2000                                               # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info = ExtendedLimits()
    if configured["max_procs"]:
        flags |= 0x8                                             # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        info.Basic.ActiveProcessLimit = configured["max_procs"]
    if configured["mem_mb"]:
        flags |= 0x200                                           # JOB_OBJECT_LIMIT_JOB_MEMORY
        info.JobMemoryLimit = configured["mem_mb"] * 1024 * 1024
    info.Basic.LimitFlags = flags
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    if not kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):   # 9 = JobObjectExtendedLimitInformation
        kernel32.CloseHandle(wintypes.HANDLE(job))
        return None
    return job


def assign_to_job(job: Any, proc: Any) -> bool:
    if job is None or sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32                            # type: ignore[attr-defined]
    return bool(kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(proc._handle))))


def close_job(job: Any) -> None:
    """Closing the handle ends every process still in the job (KILL_ON_JOB_CLOSE)."""
    if job is None or sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(job))     # type: ignore[attr-defined]
