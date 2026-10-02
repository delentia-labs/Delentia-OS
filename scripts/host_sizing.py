"""
Round 55: how big a machine does `delentia serve` need? Measured here, for free, before a host is rented.

Starts the real server (`delentia serve`, the same process a host would run) against a scripted model that speaks the OpenAI protocol, so
no paid or local model is needed and every number is the runtime's own cost: start-up time, resident memory idle and after load, how long a
governed episode takes with a model that answers instantly (so the figure is the runtime's overhead, not the model's), and what happens
when several episodes run at once.

    python scripts/host_sizing.py [--episodes 20] [--concurrent 6] [--json out.json]

It measures this machine (a Ryzen AI laptop-class CPU, 16 threads, 15.6 GB). A rented VPS will differ; the memory figures carry over, the
timings scale with the CPU. Nothing here says how fast a real model is: that dominates the wall-clock time of a real episode.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def tree_rss_mb(pid: int) -> float:
    import psutil
    try:
        proc = psutil.Process(pid)
        return round(sum(p.memory_info().rss for p in [proc, *proc.children(recursive=True)]) / 1e6, 1)
    except psutil.Error:
        return 0.0


async def run(args: argparse.Namespace) -> Dict[str, Any]:
    import httpx
    import scripted_model as sm
    work = Path(tempfile.mkdtemp(prefix="delentia-sizing-"))
    repo = work / "repo"
    (repo).mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "sample-service"\n', encoding="utf-8")
    port = free_port()
    out: Dict[str, Any] = {"machine": {"cpus": os.cpu_count()}}
    try:
        import psutil
        out["machine"]["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    except ImportError:
        pass
    with sm.ScriptedModel(sm.competent) as model:
        from rct_control_plane.model_config import save_model_selection
        cfg = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=cfg, endpoint={
            "base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted"})
        env = dict(os.environ, DELENTIA_HOME=str(work / "home"), DELENTIA_MODEL_CONFIG=str(cfg), DELENTIA_REPO_ROOT=str(repo),
                   DELENTIA_LLM_PROVIDER="openai-compat", DELENTIA_LLM_MODEL=model.model_id, PYTHONIOENCODING="utf-8")
        env.pop("DELENTIA_API_TOKEN", None)
        started = time.perf_counter()
        proc = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "serve", "--port", str(port)], cwd=str(ROOT), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                while True:
                    if proc.poll() is not None:
                        raise RuntimeError("the server exited during start-up")
                    try:
                        if (await client.get(f"{base}/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.perf_counter() - started > 300:
                        raise RuntimeError("the server did not answer /health within 300 s")
                    await asyncio.sleep(0.5)
                out["startup_seconds_to_health"] = round(time.perf_counter() - started, 1)
                await asyncio.sleep(3)
                out["rss_mb_idle_after_start"] = tree_rss_mb(proc.pid)

                latencies: List[float] = []
                for _ in range(100):
                    t = time.perf_counter()
                    await client.get(f"{base}/health")
                    latencies.append((time.perf_counter() - t) * 1000)
                out["health_ms"] = {"median": round(statistics.median(latencies), 1), "p95": round(sorted(latencies)[94], 1)}

                async def episode(i: int) -> Dict[str, Any]:
                    t = time.perf_counter()
                    resp = await client.post(f"{base}/v1/agent/run", json={"goal": "Read the file pyproject.toml and tell me the project name", "namespace": f"sizing-{i}"})
                    body = resp.json()
                    return {"seconds": time.perf_counter() - t, "ok": resp.status_code == 200 and "sample-service" in json.dumps(body, default=str),
                            "status": resp.status_code}

                model.reset()
                first = await episode(0)
                out["first_episode_seconds_cold"] = round(first["seconds"], 1)
                out["first_episode_ok"] = first["ok"]
                out["rss_mb_after_first_episode"] = tree_rss_mb(proc.pid)
                seq: List[Dict[str, Any]] = []
                for i in range(1, args.episodes + 1):
                    seq.append(await episode(i))
                times = [r["seconds"] for r in seq]
                out["sequential"] = {"episodes": len(seq), "ok": sum(r["ok"] for r in seq), "median_s": round(statistics.median(times), 2),
                                     "p95_s": round(sorted(times)[max(0, int(len(times) * 0.95) - 1)], 2)}
                out["rss_mb_after_sequential"] = tree_rss_mb(proc.pid)
                t0 = time.perf_counter()
                conc = await asyncio.gather(*[episode(100 + i) for i in range(args.concurrent)])
                out["concurrent"] = {"episodes": len(conc), "ok": sum(r["ok"] for r in conc), "wall_s": round(time.perf_counter() - t0, 2),
                                     "slowest_s": round(max(r["seconds"] for r in conc), 2), "statuses": sorted({r["status"] for r in conc})}
                out["rss_mb_after_concurrent"] = tree_rss_mb(proc.pid)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
    shutil.rmtree(work, ignore_errors=True)
    peak = max(v for k, v in out.items() if k.startswith("rss_mb"))
    out["peak_rss_mb"] = peak
    out["advice"] = ("Memory for the runtime alone peaked at about %.0f MB; add the model server's own memory if it runs on the same machine "
                     "(a 7B model in Ollama needs ~5 GB). A 2 GB host is too small with a local model, tight without one; 4 GB is comfortable "
                     "for the runtime plus channels when the model is remote." % peak)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--concurrent", type=int, default=6)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    text = json.dumps(result, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
