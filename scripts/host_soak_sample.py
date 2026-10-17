"""
Round 84: sample a running local host (scripts/local_host.py) once a minute for hours, to see what an idle-to-light server does over time on this machine: resident memory, threads, open handles,
CPU, free RAM, battery, restarts, and how long an authenticated request takes. One CSV line per sample; nothing is changed on the host.

    python scripts/host_soak_sample.py --dir C:\\Users\\you\\delentia-host --hours 6 --out soak.csv [--every 60]

Every sample makes one GET /health (no token) and one GET /v1/desk/host/metrics (the token is read from the host folder by this script, sent only to the host's own loopback address, never printed or written).
A summary (first/last/min/max of memory, requests that failed, restarts) is printed at the end and written next to the CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

FIELDS = ["at", "healthy", "health_ms", "metrics_ms", "server_rss_mb", "server_threads", "server_handles", "cpu_percent", "free_ram_gb", "battery_percent", "on_battery", "unplanned_restarts", "error"]


def _get(url: str, token: Optional[str] = None, timeout: float = 15.0) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:                      # noqa: S310 - the host's own loopback address
        body = json.loads(response.read().decode("utf-8"))
    return {"body": body, "ms": round((time.perf_counter() - started) * 1000, 1)}


def sample(host_dir: Path, port: int, token: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "error": ""}
    base = f"http://127.0.0.1:{port}"
    try:
        health = _get(base + "/health")
        row.update({"healthy": health["body"].get("status") == "healthy", "health_ms": health["ms"]})
    except Exception as exc:                                                              # noqa: BLE001 - recorded, not hidden
        row.update({"healthy": False, "error": type(exc).__name__})
    try:
        metrics = _get(base + "/v1/desk/host/metrics", token)
        row["metrics_ms"] = metrics["ms"]
        proc = (metrics["body"].get("process") or {})
        row.update({"server_rss_mb": round((proc.get("rss_bytes") or 0) / 1e6, 1), "server_handles": proc.get("open_files"), "server_threads": proc.get("threads")})
    except Exception as exc:                                                              # noqa: BLE001
        row["error"] = (row["error"] + " " + type(exc).__name__).strip()
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import local_host as lh
        status = lh.status(host_dir)
        row.update({"cpu_percent": status.get("cpu_percent"), "free_ram_gb": status.get("system_free_ram_gb"), "battery_percent": status.get("battery_percent"), "on_battery": status.get("on_battery"),
                    "unplanned_restarts": status.get("unplanned_restarts")})
        row["server_rss_mb"] = row.get("server_rss_mb") or status.get("server_rss_mb")
        row["server_threads"] = row.get("server_threads") or status.get("server_threads")
    except Exception as exc:                                                              # noqa: BLE001
        row["error"] = (row["error"] + " status:" + type(exc).__name__).strip()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--every", type=float, default=60.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    host_dir = Path(args.dir)
    config = json.loads((host_dir / "host.json").read_text(encoding="utf-8"))
    token = (host_dir / "api_token.txt").read_text(encoding="utf-8").strip()
    out = Path(args.out)
    rows = []
    deadline = time.time() + args.hours * 3600
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        while time.time() < deadline:
            row = sample(host_dir, int(config.get("port", 8000)), token)
            rows.append(row)
            writer.writerow(row)
            handle.flush()
            time.sleep(args.every)
    mem = [r["server_rss_mb"] for r in rows if r.get("server_rss_mb")]
    summary = {"samples": len(rows), "failed_health": sum(1 for r in rows if not r.get("healthy")), "errors": sum(1 for r in rows if r.get("error")),
               "rss_mb": {"first": mem[0] if mem else None, "last": mem[-1] if mem else None, "min": min(mem) if mem else None, "max": max(mem) if mem else None},
               "unplanned_restarts_last": rows[-1].get("unplanned_restarts") if rows else None, "hours": args.hours}
    out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
