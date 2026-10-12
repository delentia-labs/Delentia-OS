"""
Round 74: what does it cost to reach an HTTP service through the agent's gate (OpenAPI bridge + external MCP hub) instead of calling it directly? A direct GET is the floor.

    python scripts/bridge_overhead_probe.py --base-url http://127.0.0.1:8013 --path /health --tool get_health --calls 30

Three numbers, in milliseconds (median and p95): the direct call; a call through the bridge when every call starts a new bridge process (the default for an external server); and through the bridge with a persistent
session ("persistent": true, the owner's choice). It does not run the FDIA gate or the audit chain (that is the governed loop's ~300 ms per episode, measured by runtime_latency_probe.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))


def summarise(times):
    times = sorted(times)
    return {"median_ms": round(1000 * statistics.median(times), 1), "p95_ms": round(1000 * times[int(0.95 * (len(times) - 1))], 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--path", default="/health")
    ap.add_argument("--tool", default="get_health")
    ap.add_argument("--calls", type=int, default=30)
    args = ap.parse_args()
    import httpx
    from rct_control_plane import external_mcp as xm
    from test_governed_autonomous_loop_real import _FakeMCP

    result = {"service": args.base_url, "calls": args.calls}
    with httpx.Client(timeout=10.0) as client:
        client.get(args.base_url + args.path)
        times = []
        for _ in range(args.calls):
            t = time.perf_counter()
            client.get(args.base_url + args.path)
            times.append(time.perf_counter() - t)
    result["direct"] = summarise(times)
    work = Path(tempfile.mkdtemp(prefix="bridge-probe-"))
    for label, persistent in (("through_the_bridge_new_process_each_call", False), ("through_the_bridge_persistent_session", True)):
        spec = {"command": sys.executable, "args": ["-m", "rct_control_plane.openapi_mcp_bridge", "--name", "svc", "--base-url", args.base_url], "env_vars": ["PYTHONPATH"], "read_only_tools": [args.tool], "timeout_s": 90,
                "persistent": persistent}
        (work / "mcp_servers.json").write_text(json.dumps({"servers": {"svc": spec}}), encoding="utf-8")
        os.environ[xm.CONFIG_ENV] = str(work / "mcp_servers.json")
        os.environ["PYTHONPATH"] = str(ROOT)
        xm.clear_cache()
        hub = xm.maybe_wrap(_FakeMCP())

        async def go():
            await hub.list_tools()
            await hub.call_tool("mcp__svc__" + args.tool, {})                                  # warm-up (starts the session when persistent)
            times = []
            for _ in range(args.calls):
                t = time.perf_counter()
                out = await hub.call_tool("mcp__svc__" + args.tool, {})
                times.append(time.perf_counter() - t)
                assert json.loads(out.content[0].text)["data"]["status"] < 500
            return times
        result[label] = summarise(asyncio.run(go()))
        xm.shutdown_pool()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
