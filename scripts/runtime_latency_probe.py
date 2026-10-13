"""
Round 74: how long does one governed episode take, end to end through the real HTTP API, and does it change when the machine is busy with something else (for example a 50-service mesh)?
A real `delentia serve`, a scripted model over HTTP (so model time is ~0 and what is measured is the runtime: gate, audit chain, tools, memory), N sequential `POST /v1/agent/run` calls.
Prints the median and p95 in milliseconds as JSON. Run it twice (idle machine, busy machine) and compare.

    python scripts/runtime_latency_probe.py --episodes 12 [--out file.json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def call(url: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=12)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    import scripted_model as sm
    from rct_control_plane import approvals, audit_chain
    from rct_control_plane.model_config import save_model_selection
    work = Path(tempfile.mkdtemp(prefix="latency-probe-"))
    repo = work / "repo"
    repo.mkdir()
    (repo / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")
    result = {}
    with sm.ScriptedModel(sm.competent) as model:
        config = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=config, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "latency-probe"})
        audit_key = work / "keys" / "audit.pem"
        audit_chain.generate_signing_key(str(audit_key))
        port = free_port()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(config), "DELENTIA_LLM_PROVIDER": "openai-compat",
               "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_AUDIT_SIGNING_KEY": str(audit_key), "DELENTIA_MEMORY_EMBED": "off",
               "DELENTIA_APPROVER_PUBKEYS": approvals.generate_approver_key(str(work / "approver.pem")), "USERPROFILE": str(work / "home"), "HOME": str(work / "home")}
        for name in ("DELENTIA_API_TOKEN", "DELENTIA_API_TOKENS_FILE", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL"):
            env.pop(name, None)
        server = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "serve", "--port", str(port)], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            started = time.time()
            while time.time() - started < 120:
                try:
                    urllib.request.urlopen(base + "/health", timeout=3).read()
                    break
                except Exception:                                                        # noqa: BLE001
                    time.sleep(0.5)
            result["seconds_to_health"] = round(time.time() - started, 1)
            call(base + "/v1/agent/run", {"goal": "Read the file report.txt and tell me the quarterly total"})        # warm-up, not counted
            times = []
            for _ in range(args.episodes):
                t = time.perf_counter()
                out = call(base + "/v1/agent/run", {"goal": "Read the file report.txt and tell me the quarterly total"})
                times.append(1000 * (time.perf_counter() - t))
                assert out.get("stopped_reason") == "llm_finished", out.get("stopped_reason")
            times.sort()
            result.update({"episodes": len(times), "median_ms": round(statistics.median(times)), "p95_ms": round(times[int(0.95 * (len(times) - 1))]), "max_ms": round(times[-1])})
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(result))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
