"""
PL1 A1 (research/LAUNCH_PL1_CRITERIA_R116.md): unattended operation for 24 hours on the owner's computer, free.

An extension of scripts/autonomy_drill.py: a REAL `delentia serve` with the daemon on, a real clock, the real governed loop, real tools and SQLite, and a scripted model that
speaks the OpenAI protocol over HTTP (the decisions are the only scripted part; no cost). After the setup nobody touches it. The schedule of the criteria:

  * four read-only cron jobs: two every 30 minutes, two hourly;
  * one hourly write job (it must wait for a signature every time and never write);
  * a signed webhook every 2 hours (one episode each) and a forged one every 6 hours (refused, no episode);
  * /health polled every 60 seconds with a 5 s timeout; `delentia pause` at hour 23;
  * the audit chain verified at hours 6, 12, 18 and 24.

Pass (all): every due occurrence ran exactly once (allowing the one in progress at the end); the write job wrote nothing and left one pending approval per occurrence; every
signed webhook started one episode and every forged one none; no episode ran after the pause; the audit chain verified at every check; the server process was never restarted;
after hour 1 the working-set slope is at most 5 MB per hour; at most 5 /health timeouts and never two in a row. A gap between two polls longer than three poll intervals means
the computer slept or froze: the run is then INVALID (the criteria: a sleep invalidates the run, it is not repaired afterwards).

`--profile test` is the same schedule compressed into 20 minutes (jobs every 2 and 4 minutes, webhooks every 4 and 6 minutes, pause at minute 18, checks at 5/10/15/20,
/health every 15 s, the hourly cap of cron runs raised to 200 because the compressed schedule asks for about 105 runs an hour). It exists so the script is tested before the
24-hour run; its memory slope is reported but means little over 20 minutes.

    python scripts/soak_24h.py --profile test --out <folder>
    python scripts/soak_24h.py --profile full --out <folder>      # 24 hours; sleep must be off

The report (`report.json`) and the samples (`health.jsonl`) are written to --out as the run goes; the exit code is 0 only for a valid pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

READ_GOAL = "Read the file report.txt and tell me the quarterly total"
WRITE_GOAL = "Write a note to notes/out.txt"
ROUTE = "soak-event"
SECRET_ENV = "SOAK_WEBHOOK_SECRET"


@dataclass
class Profile:
    name: str
    duration_s: float
    jobs: Dict[str, Tuple[str, str]]          # name -> (cron line, goal)
    signed_every_s: float
    forged_every_s: float
    pause_at_s: float
    checks_at_s: List[float]
    health_every_s: float
    slope_after_s: float
    env: Dict[str, str] = field(default_factory=dict)


PROFILES = {
    "full": Profile("full", 24 * 3600, {"read-a": ("*/30 * * * *", READ_GOAL), "read-b": ("15,45 * * * *", READ_GOAL), "read-c": ("5 * * * *", READ_GOAL),
                                        "read-d": ("35 * * * *", READ_GOAL), "write-w": ("20 * * * *", WRITE_GOAL)},
                    2 * 3600, 6 * 3600, 23 * 3600, [6 * 3600, 12 * 3600, 18 * 3600, 24 * 3600], 60.0, 3600.0),
    "test": Profile("test", 20 * 60, {"read-a": ("*/2 * * * *", READ_GOAL), "read-b": ("1-59/2 * * * *", READ_GOAL), "read-c": ("*/4 * * * *", READ_GOAL),
                                      "read-d": ("2-59/4 * * * *", READ_GOAL), "write-w": ("3-59/4 * * * *", WRITE_GOAL)},
                    4 * 60, 6 * 60, 18 * 60, [5 * 60, 10 * 60, 15 * 60, 20 * 60], 15.0, 3 * 60, {"DELENTIA_CRON_MAX_RUNS_PER_HOUR": "200"}),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http(method: str, url: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: float = 20.0) -> Tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def cli(env: Dict[str, str], *args: str, timeout: float = 180.0) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def expected_occurrences(cron_line: str, start: float, end: float) -> List[float]:
    """The times the schedule falls due after the job was created and up to `end` (the dispatcher's own schedule code, so 'due' means what the server means)."""
    from rct_control_plane import nl_schedule
    sched = nl_schedule.parse(cron_line)
    out: List[float] = []
    t = nl_schedule.next_run(sched, start)
    while t is not None and t <= end:
        out.append(t)
        t = nl_schedule.next_run(sched, t + 1)
    return out


def slope_mb_per_hour(samples: List[Tuple[float, float]]) -> Optional[float]:
    """Least-squares slope of working set (MB) against time (hours)."""
    if len(samples) < 3:
        return None
    xs = [t / 3600.0 for t, _ in samples]
    ys = [m for _, m in samples]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den


def health_verdict(polls: List[Dict[str, Any]], interval_s: float) -> Dict[str, Any]:
    timeouts = [p for p in polls if not p["ok"]]
    run, worst = 0, 0
    for p in polls:
        run = run + 1 if not p["ok"] else 0
        worst = max(worst, run)
    gaps = [b["t"] - a["t"] for a, b in zip(polls, polls[1:], strict=False)]
    slept = [g for g in gaps if g > 3 * interval_s]
    return {"polls": len(polls), "timeouts": len(timeouts), "max_consecutive_timeouts": worst, "ok": len(timeouts) <= 5 and worst < 2,
            "largest_gap_s": round(max(gaps), 1) if gaps else None, "slept_or_froze": bool(slept)}


def sign_v2(secret: bytes, body: bytes, stamp: int) -> str:
    from rct_control_plane.webhook_triggers import sign_generic_v2
    return sign_generic_v2(secret, body, stamp)


def db_rows(db: Path, sql: str, args: tuple = ()) -> List[tuple]:
    if not db.exists():
        return []
    try:
        with sqlite3.connect(str(db)) as conn:
            return list(conn.execute(sql, args))
    except sqlite3.Error:
        return []


def audit_time(created_at: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp()


def assess(profile: Profile, db: Path, repo: Path, job_created: Dict[str, float], ended: float, pause_at: Optional[float], signed: List[Dict[str, Any]],
           forged: List[Dict[str, Any]], checks: List[Dict[str, Any]], server_restarted: bool, mem: List[Tuple[float, float]], t0: float,
           health: Dict[str, Any], run_grace_s: float) -> Dict[str, Any]:
    """Every rule of A1 read from what the server wrote (its database and audit trail) and from the samples. Pure apart from reading the database."""
    rules: Dict[str, Dict[str, Any]] = {}
    ids = {name: r[0] for name, r in ((r[1], r) for r in db_rows(db, "SELECT id, name FROM cron_jobs"))}
    runs_by_job: Dict[str, List[Tuple[float, str]]] = {}
    for entity_id, created_at, changes in db_rows(db, "SELECT entity_id, created_at, changes FROM audit_trail WHERE entity_type = 'cron_job' AND action = 'run' ORDER BY id"):
        try:
            stop = json.loads(changes or "{}").get("stopped_reason") or ""
        except ValueError:
            stop = ""
        runs_by_job.setdefault(entity_id, []).append((audit_time(created_at), stop))
    throttled = len(db_rows(db, "SELECT 1 FROM audit_trail WHERE entity_type = 'cron_job' AND action = 'throttled'"))
    cutoff = pause_at if pause_at is not None else ended
    per_job = {}
    occ_ok = True
    for name, (line, _goal) in profile.jobs.items():
        due = expected_occurrences(line, job_created[name], cutoff)
        ran = [r for r in runs_by_job.get(ids.get(name, ""), []) if r[0] <= cutoff + run_grace_s and r[1] != "paused"]
        missing_allowed = 1 if due and due[-1] > cutoff - run_grace_s else 0          # the occurrence in progress when the clock stopped
        ok = len(due) - missing_allowed <= len(ran) <= len(due)
        occ_ok = occ_ok and ok
        per_job[name] = {"due": len(due), "ran": len(ran), "ok": ok}
    rules["every due occurrence ran exactly once"] = {"ok": occ_ok and throttled == 0, "per_job": per_job, "throttled": throttled}

    write_id = ids.get("write-w", "")
    write_runs = [r for r in runs_by_job.get(write_id, []) if r[1] != "paused"]
    pending = db_rows(db, "SELECT COUNT(*) FROM pending_actions WHERE tool_name LIKE '%write%' AND status = 'PENDING'")
    pending_n = pending[0][0] if pending else 0
    rules["the write job wrote nothing and waited every time"] = {"ok": not (repo / "notes" / "out.txt").exists() and len(write_runs) > 0 and pending_n == len(write_runs)
                                                                   and all(r[1] == "pending_approval" for r in write_runs),
                                                                   "write_runs": len(write_runs), "pending_approvals": pending_n, "stops": sorted({r[1] for r in write_runs})}

    jobs_ns = db_rows(db, "SELECT id FROM agent_jobs WHERE namespace = ?", (f"webhook-{ROUTE}",))
    accepted = [s for s in signed if s["status"] == 202]
    rules["every signed webhook started one episode, every forged one none"] = {
        "ok": len(accepted) == len(signed) and len(jobs_ns) == len(signed) and all(f["status"] in (401, 403) for f in forged) and len(forged) > 0,
        "signed_sent": len(signed), "signed_accepted": len(accepted), "webhook_jobs": len(jobs_ns), "forged_sent": len(forged),
        "forged_statuses": sorted({f["status"] for f in forged})}

    after: List[str] = []
    if pause_at is not None:
        for rows in runs_by_job.values():
            after += [stop for when, stop in rows if when > pause_at + 1 and stop != "paused"]
        for created_at, changes in db_rows(db, "SELECT created_at, changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_end'"):
            try:
                stop = json.loads(changes or "{}").get("stopped_reason") or ""
            except ValueError:
                stop = ""
            if audit_time(created_at) > pause_at + 1 and stop != "paused":
                after.append(stop)
    rules["no episode ran after the pause"] = {"ok": pause_at is not None and not after, "paused": pause_at is not None, "ran_after": after[:10]}

    rules["the audit chain verified at every check"] = {"ok": len(checks) == len(profile.checks_at_s) and all(c["ok"] for c in checks), "checks": checks}
    rules["the server process was never restarted"] = {"ok": not server_restarted}
    late = [(t - t0, m) for t, m in mem if t - t0 >= profile.slope_after_s]
    slope = slope_mb_per_hour(late)
    rules["working-set slope after hour 1 at most 5 MB per hour"] = {"ok": slope is not None and slope <= 5.0, "slope_mb_per_hour": None if slope is None else round(slope, 2),
                                                                     "samples": len(late)}
    rules["/health: at most 5 timeouts, never two in a row"] = health
    valid = not health.get("slept_or_froze")
    return {"profile": profile.name, "valid": valid, "pass": valid and all(r["ok"] for r in rules.values()), "rules": rules}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="test")
    ap.add_argument("--out", required=True, help="folder for report.json, health.jsonl and the run's data (kept)")
    args = ap.parse_args(argv)
    profile = PROFILES[args.profile]
    import psutil

    import scripted_model as sm
    from rct_control_plane import approvals, audit_chain
    from rct_control_plane.model_config import save_model_selection

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="delentia-soak-", dir=str(out)))
    repo = work / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")
    secret = hashlib.sha256(os.urandom(32)).hexdigest()
    home = work / "home"
    home.mkdir()
    (home / "webhooks.json").write_text(json.dumps({"routes": [{"name": ROUTE, "verify": "generic-v2", "secret_env": SECRET_ENV,
                                                                 "prompt": READ_GOAL + " (event {event.id})", "max_per_minute": 30}]}), encoding="utf-8")
    report_path, health_path = out / "report.json", out / "health.jsonl"

    with sm.ScriptedModel(sm.competent) as model:
        config = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=config, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-soak-model"})
        public = approvals.generate_approver_key(str(work / "approver.pem"))
        audit_key = work / "keys" / "audit.pem"
        audit_pub = audit_chain.generate_signing_key(str(audit_key))
        port = free_port()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(home), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(config),
               "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01",
               "DELENTIA_APPROVERS_FILE": str(work / "approvers.json"), "DELENTIA_APPROVER_PUBKEYS": public, "DELENTIA_AUDIT_SIGNING_KEY": str(audit_key),
               "DELENTIA_MEMORY_EMBED": "off", "USERPROFILE": str(home), "HOME": str(home), SECRET_ENV: secret, **profile.env}
        for name in ("DELENTIA_API_TOKEN", "DELENTIA_API_TOKENS_FILE", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL", "DELENTIA_WEBHOOKS"):
            env.pop(name, None)
        print(f"soak ({profile.name}, {profile.duration_s / 3600:.2f} h) in {work}; server on 127.0.0.1:{port}", flush=True)
        server = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "serve", "--port", str(port)], cwd=str(ROOT), env=env,
                                  stdout=subprocess.DEVNULL, stderr=open(out / "server.err", "w", encoding="utf-8"))
        base = f"http://127.0.0.1:{port}"
        db = home / "agentic.db"
        polls: List[Dict[str, Any]] = []
        mem: List[Tuple[float, float]] = []
        signed: List[Dict[str, Any]] = []
        forged: List[Dict[str, Any]] = []
        checks: List[Dict[str, Any]] = []
        job_created: Dict[str, float] = {}
        pause_at: Optional[float] = None
        restarted = False
        try:
            up = time.time()
            while time.time() - up < 120:
                try:
                    if http("GET", base + "/health", timeout=5)[0] == 200:
                        break
                except Exception:                                                  # noqa: BLE001
                    pass
                time.sleep(1.0)
            print(f"  server up after {time.time() - up:.1f} s", flush=True)
            for name, (line, goal) in profile.jobs.items():
                made = cli(env, "cron", "add", goal, "--schedule", line, "--name", name)
                job_created[name] = time.time()
                if made.returncode != 0:
                    raise SystemExit(f"could not add cron job {name}: {made.stdout} {made.stderr}")
            t0 = time.time()
            next_health, next_signed, next_forged = t0, t0 + profile.signed_every_s, t0 + profile.forged_every_s
            pending_checks = list(profile.checks_at_s)
            proc = psutil.Process(server.pid)
            n_signed = 0
            with health_path.open("w", encoding="utf-8") as hf:
                while True:
                    now = time.time()
                    if now - t0 >= profile.duration_s and not pending_checks:
                        break
                    if server.poll() is not None:
                        restarted = True
                        print("  the server process ended: the run stops here", flush=True)
                        break
                    if now >= next_health:
                        try:
                            ok = http("GET", base + "/health", timeout=5)[0] == 200
                        except Exception:                                          # noqa: BLE001 - a timeout or a refused connection is a failed poll
                            ok = False
                        try:
                            ws = proc.memory_info().rss / 1e6
                        except psutil.Error:
                            ws = float("nan")
                        sample = {"t": now, "ok": ok, "working_set_mb": round(ws, 1)}
                        polls.append(sample)
                        mem.append((now, ws))
                        hf.write(json.dumps(sample) + "\n")
                        hf.flush()
                        next_health += profile.health_every_s
                    if now >= next_signed and (pause_at is None):
                        n_signed += 1
                        body = json.dumps({"event": {"id": f"signed-{n_signed}"}}).encode("utf-8")
                        stamp = int(time.time())
                        status, _ = http("POST", f"{base}/v1/webhooks/{ROUTE}", body, {"X-Webhook-Timestamp": str(stamp), "X-Webhook-Signature-V2": sign_v2(secret.encode(), body, stamp),
                                                                                    "X-Delivery-Id": f"soak-signed-{n_signed}"})
                        signed.append({"t": now, "status": status})
                        print(f"  signed webhook {n_signed}: HTTP {status}", flush=True)
                        next_signed += profile.signed_every_s
                    if now >= next_forged:
                        body = json.dumps({"event": {"id": f"forged-{len(forged) + 1}"}}).encode("utf-8")
                        stamp = int(time.time())
                        status, _ = http("POST", f"{base}/v1/webhooks/{ROUTE}", body, {"X-Webhook-Timestamp": str(stamp), "X-Webhook-Signature-V2": sign_v2(b"not-the-secret-0123456789", body, stamp),
                                                                                    "X-Delivery-Id": f"soak-forged-{len(forged) + 1}"})
                        forged.append({"t": now, "status": status})
                        print(f"  forged webhook {len(forged)}: HTTP {status}", flush=True)
                        next_forged += profile.forged_every_s
                    if pause_at is None and now - t0 >= profile.pause_at_s:
                        paused = cli(env, "pause", "--reason", "soak: hour 23")
                        pause_at = time.time()
                        print(f"  paused: {paused.stdout.strip()[:100]}", flush=True)
                    if pending_checks and now - t0 >= pending_checks[0]:
                        at = pending_checks.pop(0)
                        verify = cli(env, "audit-chain", "verify", "--pubkey", audit_pub)
                        checks.append({"at_s": at, "ok": verify.returncode == 0 and "ok" in verify.stdout.lower(), "detail": verify.stdout.strip().replace("\n", " ")[:160]})
                        print(f"  audit check at {at / 60:.0f} min: {'ok' if checks[-1]['ok'] else 'FAILED'}", flush=True)
                    time.sleep(1.0)
            ended = time.time()
        finally:
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()

    health = health_verdict(polls, profile.health_every_s)
    result = assess(profile, db, repo, job_created, ended, pause_at, signed, forged, checks, restarted, mem, t0, health, run_grace_s=120.0)
    result.update({"work": str(work), "duration_s": round(ended - t0, 1), "pause_at_s": None if pause_at is None else round(pause_at - t0, 1)})
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, rule in result["rules"].items():
        print(f"  {'OK ' if rule['ok'] else 'NO '} {name}", flush=True)
    print(f"{'VALID' if result['valid'] else 'INVALID (the computer slept or froze)'}; {'PASS' if result['pass'] else 'NOT PASSED'}; report {report_path}", flush=True)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
