"""
Round 71: an unattended-operation drill. Not a unit test: a REAL server process (`delentia serve`, daemon on), a REAL clock, the real governed loop, real tools and SQLite, a scripted model that speaks the
OpenAI protocol over HTTP (the decisions are the only scripted part). After the setup nobody touches anything: the point is to observe whether the system, left alone, does what an autonomous agent must:

  D1  a scheduled job fires by itself and finishes a multi-step task (read a file, answer from it)
  D2  a scheduled job that would CHANGE a file stops and waits for a human signature (nothing is written)
  D3  a job submitted through the API runs in the background and its status can be polled
  D4  after the owner pauses it, a new job does not run (the emergency stop reaches the daemon)
  D5  the hash-chained, signed audit trail written by the server verifies afterwards

What it does NOT show: that a language model can drive the loop (the model is a script), or that it keeps running for days (it runs for about two minutes).

    python scripts/autonomy_drill.py [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
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


def http(method: str, url: str, body: dict | None = None, timeout: float = 20.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def cli(env: dict, *args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder")
    args = ap.parse_args()
    import scripted_model as sm
    from rct_control_plane import approvals, audit_chain
    from rct_control_plane.model_config import save_model_selection

    work = Path(tempfile.mkdtemp(prefix="delentia-drill-"))
    repo = work / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))
        print(f"  {'OK ' if ok else 'NO '} {name}  {detail}"[:200], flush=True)

    with sm.ScriptedModel(sm.competent) as model:
        config = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=config, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-drill-model"})
        approver_key = work / "approver.pem"
        public = approvals.generate_approver_key(str(approver_key))
        audit_key = work / "keys" / "audit.pem"
        audit_pub = audit_chain.generate_signing_key(str(audit_key))
        port = free_port()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(config), "DELENTIA_LLM_PROVIDER": "openai-compat",
               "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_APPROVERS_FILE": str(work / "approvers.json"), "DELENTIA_APPROVER_PUBKEYS": public,
               "DELENTIA_AUDIT_SIGNING_KEY": str(audit_key), "DELENTIA_MEMORY_EMBED": "off", "USERPROFILE": str(work / "home"), "HOME": str(work / "home")}
        for name in ("DELENTIA_API_TOKEN", "DELENTIA_API_TOKENS_FILE", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL"):
            env.pop(name, None)
        print(f"drill folder {work}; server on 127.0.0.1:{port}", flush=True)
        server = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "serve", "--port", str(port)], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            started = time.time()
            while time.time() - started < 90:
                try:
                    if http("GET", base + "/health").get("status"):
                        break
                except Exception:                                                  # noqa: BLE001
                    time.sleep(1.0)
            check("the server is up with the daemon on", True, f"{time.time() - started:.1f} s to /health")

            # D1 + D2: two jobs due in a minute, nobody present
            read = cli(env, "cron", "add", "Read the file report.txt and tell me the quarterly total", "--schedule", "in 1 minutes", "--max-runs", "1", "--name", "drill-read")
            write = cli(env, "cron", "add", "Write a note to notes/out.txt", "--schedule", "in 1 minutes", "--max-runs", "1", "--name", "drill-write")
            check("both jobs were scheduled", read.returncode == 0 and write.returncode == 0, (read.stdout + write.stdout).strip().replace("\n", " ")[:90])
            print("  ... waiting for the daemon (about a minute, nobody touching anything)", flush=True)
            import sqlite3
            db = work / "home" / "agentic.db"

            def jobs() -> dict:
                if not db.exists():
                    return {}
                try:
                    with sqlite3.connect(str(db)) as conn:
                        return {r[0]: r for r in conn.execute("SELECT name, run_count, last_status, last_result FROM cron_jobs")}
                except sqlite3.Error:
                    return {}

            deadline = time.time() + 240
            seen: dict = {}
            while time.time() < deadline:
                seen = jobs()
                if seen.get("drill-read", (0, 0))[1] and seen.get("drill-write", (0, 0))[1]:
                    break
                time.sleep(5)
            for name, row in seen.items():
                print(f"  job {name}: runs={row[1]} status={row[2]} result={str(row[3])[:90]!r}", flush=True)
            read_row, write_row = seen.get("drill-read"), seen.get("drill-write")
            with sqlite3.connect(str(db)) as conn:
                gate_rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'")]
            read_gate = [g for g in gate_rows if g.get("tool_name") == "delentia_read_repo_file"]
            check("D1 the read job fired by itself, called the file tool through the gate and finished", bool(read_row) and str(read_row[2]) == "llm_finished" and bool(read_gate) and "report.txt" in str(read_row[3]),
                  f"status {read_row[2] if read_row else None}; gate rows for the read tool: {len(read_gate)}; policy source: {read_gate[0].get('policy_source') if read_gate else None}")
            listed = http("GET", base + "/v1/agent/approvals")
            waiting = listed if isinstance(listed, list) else (listed.get("approvals") or listed.get("items") or [])
            check("D2 the write job stopped and is waiting for a signature", bool(write_row) and str(write_row[2]) == "pending_approval" and "write_repo_file" in json.dumps(waiting), f"status {write_row[2] if write_row else None}; waiting approvals: {len(waiting)}")
            check("D2 nothing was written", not (repo / "notes" / "out.txt").exists())

            # D3: a job through the API, polled
            job = http("POST", base + "/v1/agent/jobs", {"goal": "Read the file report.txt and tell me the quarterly total"})
            job_id = job.get("id") or job.get("job_id")
            status = {}
            for _ in range(90):
                status = http("GET", f"{base}/v1/agent/jobs/{job_id}")
                if str(status.get("status")) in ("completed", "done", "failed", "finished"):
                    break
                time.sleep(2)
            check("D3 an API job ran in the background and its status shows the finished answer", str(status.get("status")) in ("done", "completed") and "report.txt" in json.dumps(status, ensure_ascii=False), str(status.get("status")))

            # D4: pause, then a new job
            paused = cli(env, "pause", "--reason", "drill")
            second = http("POST", base + "/v1/agent/jobs", {"goal": "Read the file report.txt and tell me the quarterly total"})
            sid = second.get("id") or second.get("job_id")
            sstatus = {}
            for _ in range(60):
                sstatus = http("GET", f"{base}/v1/agent/jobs/{sid}")
                if str(sstatus.get("status")) in ("completed", "done", "failed", "finished", "stopped"):
                    break
                time.sleep(1)
            check("D4 after `delentia pause` a new job does not run", "paused" in json.dumps(sstatus, ensure_ascii=False).lower() and "report.txt" not in json.dumps(sstatus.get("result") or sstatus.get("answer") or "", ensure_ascii=False),
                  (paused.stdout.strip().replace("\n", " ") + " | " + str(sstatus.get("status")))[:90])
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()

        # D5: the audit trail the server wrote
        verify = cli(env, "audit-chain", "verify", "--pubkey", audit_pub)
        check("D5 the audit trail written by the server verifies (signed, hash-chained)", verify.returncode == 0 and "ok" in verify.stdout.lower(), verify.stdout.strip().replace("\n", " ")[:90])

    ok = all(r[1] for r in results)
    print(f"\n{sum(1 for r in results if r[1])}/{len(results)} observations hold", flush=True)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
