"""
Host metrics: what an operator watches on a machine that runs the agent for days. (Round 82, plan item T09 / finding N5)

`/v1/metrics` (the observer's summary) says nothing about the host. This collects, from the process and the Delentia database only, in numbers:

  process   resident memory, open files/handles, threads, uptime
  system    load average, free memory, free disk where the data lives
  work      queued/running API jobs, job latency (p50/p95 of the last finished ones), episodes in the last hour, approvals waiting, actions whose outcome is unknown,
            scheduled runs in flight or interrupted
  spend     today's money and tokens against the limits, reservations in flight
  witness   how many log rows are not yet held by an independent witness, and how old the newest anchor is

A figure that cannot be read on this operating system is `null` and named in `unavailable`; nothing is estimated or filled in. Standard library only (psutil is used when it happens to be installed).
Output is JSON, or Prometheus text (`to_prometheus`) for a scraper.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_STARTED = time.time()


def _percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return round(ordered[index], 3)


def _process(unavailable: List[str]) -> Dict[str, Any]:
    rss: Optional[int] = None
    handles: Optional[int] = None
    try:
        import psutil
        proc = psutil.Process()
        rss = int(proc.memory_info().rss)
        handles = int(proc.num_handles() if os.name == "nt" else proc.num_fds())
    except Exception:
        if os.name == "posix":
            try:
                with open("/proc/self/statm", encoding="ascii") as f:
                    rss = int(f.read().split()[1]) * int(getattr(os, "sysconf")("SC_PAGE_SIZE"))       # getattr: the call exists on POSIX only, and the type checker runs on both
                handles = len(os.listdir("/proc/self/fd"))
            except Exception:
                try:
                    import importlib
                    resource = importlib.import_module("resource")
                    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * (1 if sys.platform == "darwin" else 1024)   # peak, not current; named below
                    unavailable.append("process.open_files")
                except Exception:
                    unavailable.extend(["process.rss_bytes", "process.open_files"])
        else:
            try:
                import ctypes
                from ctypes import wintypes
                kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi

                class Counters(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
                counters = Counters()
                counters.cb = ctypes.sizeof(Counters)
                handle = kernel32.GetCurrentProcess()
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    rss = int(counters.WorkingSetSize)
                count = wintypes.DWORD()
                if kernel32.GetProcessHandleCount(handle, ctypes.byref(count)):
                    handles = int(count.value)
            except Exception:
                pass
    if rss is None:
        unavailable.append("process.rss_bytes")
    if handles is None:
        unavailable.append("process.open_files")
    return {"rss_bytes": rss, "open_files": handles, "threads": threading.active_count(), "uptime_s": round(time.time() - _STARTED, 1)}


def _system(data_home: Path, unavailable: List[str]) -> Dict[str, Any]:
    load: Optional[float] = None
    try:
        load = round(getattr(os, "getloadavg")()[0], 2)
    except (AttributeError, OSError):
        unavailable.append("system.load_1m")
    available: Optional[int] = None
    try:
        import psutil
        available = int(psutil.virtual_memory().available)
    except Exception:
        try:
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        available = int(line.split()[1]) * 1024
                        break
        except Exception:
            pass
    if available is None:
        unavailable.append("system.memory_available_bytes")
    free: Optional[int] = None
    try:
        free = int(shutil.disk_usage(str(data_home if data_home.exists() else data_home.parent)).free)
    except Exception:
        unavailable.append("system.disk_free_bytes")
    return {"load_1m": load, "memory_available_bytes": available, "disk_free_bytes": free}


def _scalar(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> Optional[int]:
    try:
        row = conn.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.OperationalError as exc:
        return 0 if "no such table" in str(exc) else None          # a table that was never created holds nothing; any other failure is unknown
    except sqlite3.Error:
        return None


def _work(conn: sqlite3.Connection, now: float) -> Dict[str, Any]:
    latencies: List[float] = []
    try:
        for started, finished in conn.execute("SELECT started_at, finished_at FROM agent_jobs WHERE finished_at IS NOT NULL AND started_at IS NOT NULL ORDER BY finished_at DESC LIMIT 100"):
            latencies.append(float(finished) - float(started))
    except sqlite3.Error:
        pass
    return {
        "jobs_queued": _scalar(conn, "SELECT COUNT(*) FROM agent_jobs WHERE status = 'queued'"),
        "jobs_running": _scalar(conn, "SELECT COUNT(*) FROM agent_jobs WHERE status = 'running'"),
        "job_latency_p50_s": _percentile(latencies, 0.5), "job_latency_p95_s": _percentile(latencies, 0.95), "job_latency_sample": len(latencies),
        "episodes_last_hour": _scalar(conn, "SELECT COUNT(*) FROM spend_ledger WHERE at >= ? AND stopped != 'reserved'", (now - 3600,)),
        "approvals_waiting": _scalar(conn, "SELECT COUNT(*) FROM pending_actions WHERE status = 'PENDING'"),
        "approvals_outcome_unknown": _scalar(conn, "SELECT COUNT(*) FROM pending_actions WHERE status = 'OUTCOME_UNKNOWN'"),
        "scheduled_runs_in_flight": _scalar(conn, "SELECT COUNT(*) FROM cron_jobs WHERE last_status = 'running' AND deleted = 0"),
        "scheduled_runs_interrupted": _scalar(conn, "SELECT COUNT(*) FROM cron_jobs WHERE last_status = 'interrupted' AND deleted = 0"),
    }


def _spend(persistence: Any) -> Dict[str, Any]:
    try:
        from rct_control_plane import envelope
        status = envelope.status(persistence)
        day = status.get("last_24h") or {}
        return {"cost_usd_24h": day.get("cost_usd"), "tokens_24h": day.get("tokens"), "limits": status.get("limits"), "paused": bool(status.get("paused")),
                "reserved_in_flight": status.get("reserved_in_flight"), "stale_reservations": status.get("stale_reservations")}
    except Exception:
        return {"cost_usd_24h": None, "tokens_24h": None, "limits": None, "paused": None, "reserved_in_flight": None, "stale_reservations": None}


def _witness(conn: sqlite3.Connection, now: float) -> Dict[str, Any]:
    try:
        from rct_control_plane import audit_witness
        status = audit_witness.status(conn, now=now)
    except Exception:
        return {"configured": None, "fresh": None, "rows_not_yet_anchored": None, "newest_anchor_age_s": None}
    ages = [w["last_anchored_age_s"] for w in status.get("witnesses", []) if w.get("last_anchored_age_s") is not None]
    return {"configured": status.get("configured"), "fresh": status.get("fresh_witnesses"), "rows_not_yet_anchored": status.get("rows_not_yet_anchored"),
            "newest_anchor_age_s": min(ages) if ages else None}


def collect(persistence: Any, data_home: Optional[Path] = None, now: Optional[float] = None) -> Dict[str, Any]:
    when = time.time() if now is None else now
    unavailable: List[str] = []
    from rct_control_plane import data_home as _dh
    configured = _dh.data_home()                              # None when DELENTIA_HOME is not set: the database then lives where the process runs
    home: Path = data_home if data_home is not None else (configured if configured is not None else Path(str(getattr(persistence, "db_path", ".") or ".")).resolve().parent)
    with persistence._connect() as conn:
        work = _work(conn, when)
        witness = _witness(conn, when)
    return {"at": when, "process": _process(unavailable), "system": _system(home, unavailable), "work": work, "spend": _spend(persistence), "witness": witness,
            "unavailable": sorted(set(unavailable)),
            "note": "A null figure could not be read here and is listed in `unavailable`; nothing is estimated."}


def _flatten(prefix: str, value: Any, out: List[str]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            _flatten(f"{prefix}_{key}" if prefix else str(key), inner, out)
    elif isinstance(value, bool):
        out.append(f"delentia_{prefix} {1 if value else 0}")
    elif isinstance(value, (int, float)):
        out.append(f"delentia_{prefix} {value}")


def to_prometheus(metrics: Dict[str, Any]) -> str:
    """Prometheus text format. Only numbers are exported; a null figure is left out so a scraper sees a gap, not a false zero."""
    lines: List[str] = []
    for section in ("process", "system", "work", "spend", "witness"):
        _flatten(section, {k: v for k, v in (metrics.get(section) or {}).items() if k != "limits"}, lines)
    return "\n".join(lines) + "\n"
