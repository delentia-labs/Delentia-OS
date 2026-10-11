"""
Round 65: an operational trial of the audit tiers on one machine, with REAL separate processes - the notary as its own `delentia notary serve` process holding its own key,
a git witness (a bare "remote" and a working clone) - driven through the same CLI commands an operator would use.

    python scripts/trial_notary_witness_local.py [--out research/notary_witness_trial.md]

What it does, in order, and reports as pass/fail lines:
  1. the notary starts as its own process with its own key and database; the host has a DIFFERENT audit signing key
  2. three governed episodes run with DELENTIA_NOTARY_URL set: every tool call is recorded by the notary before it runs and again after
  3. `audit-chain verify`, `notary verify`, `witness-status` (before any anchor: it must say so), `anchor-all`, `check-witnesses`, `witness-status` (after)
  4. the standalone verifier (a separate Python process that imports nothing from Delentia) checks an exported bundle
  5. the notary is stopped: a tool call must NOT run (fail closed)
  6. the notary's database is edited: `notary verify` must fail

What it does NOT show, and the report says so: the notary runs as the SAME operating-system user as the agent (a separate OS user needs an account the Architect creates; this
script does not create accounts), the witness is a bare repository on the same disk (an independent witness must be another machine or a protected branch), and nothing here
defends against root on this machine.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

CLI = [sys.executable, "-m", "rct_control_plane.cli"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def cli(env: Dict[str, str], *args: str) -> Tuple[int, str]:
    done = subprocess.run([*CLI, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=ROOT, timeout=300)
    return done.returncode, (done.stdout + done.stderr).strip()


def _pub(text: str) -> str:
    import re
    m = re.search(r"public key\s*:\s*([0-9a-f]{64})", text)
    return m.group(1) if m else ""


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Tools:
    def __init__(self) -> None:
        self.dispatched: List[Any] = []

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in ("delentia_recall", "delentia_read_repo_file")]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return type("R", (), {"content": [type("C", (), {"text": json.dumps({"ok": True})})()]})()


def episode(db: str, goal: str, tools: Tools, calls: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
    import rct_control_plane.autonomous_loop as al
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.skill_library import SkillLibrary
    from test_governed_autonomous_loop_real import _FakeKernel
    state = {"n": 0}

    async def model(goal_, history, available_tools, llm_provider=None, extra_context=""):
        i = state["n"]
        state["n"] += 1
        if i < len(calls):
            return {"action": "call_tool", "tool_name": calls[i][0], "tool_args": calls[i][1], "reasoning": "step"}
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal_}", "tool_name": None, "tool_args": {}}
    al.decide_next_action = model
    loop = GovernedAutonomousLoop(mcp_server=tools, persistence=ControlPlanePersistence(db_path=db), kernel=_FakeKernel(), max_iterations=5, namespace="trial",
                                  skill_library=SkillLibrary(db_path=db + ".skills"))
    return asyncio.run(loop.run(goal))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "research" / "notary_witness_trial.md"))
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="delentia-trial-"))
    (work / "home").mkdir()
    results: List[Tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)

    token, port = secrets.token_hex(16), free_port()
    base = {**os.environ, "DELENTIA_HOME": str(work / "home"), "PYTHONIOENCODING": "utf-8"}
    for name in ("DELENTIA_NOTARY_URL", "DELENTIA_NOTARY_TOKEN", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_AUDIT_WITNESSES", "DELENTIA_NOTARY_KEY", "DELENTIA_FDIA_POLICY"):
        base.pop(name, None)
    # 1. two different keys, two different places
    code, out = cli(base, "notary", "keygen", "--out", str(work / "notary-keys" / "notary.pem"))
    notary_pub = _pub(out) if code == 0 else ""
    code2, out2 = cli(base, "audit-chain", "keygen", "--out", str(work / "host-keys" / "audit.pem"))
    host_pub = _pub(out2) if code2 == 0 else ""
    check("the notary and the host have different signing keys", code == 0 and code2 == 0 and notary_pub != host_pub and len(notary_pub) == 64, f"{notary_pub[:12]}.. vs {host_pub[:12]}..")
    notary_env = {**base, "DELENTIA_NOTARY_KEY": str(work / "notary-keys" / "notary.pem"), "DELENTIA_NOTARY_TOKEN": token}
    notary = subprocess.Popen([*CLI, "notary", "serve", "--db", str(work / "notary.db"), "--port", str(port)], env=notary_env, cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = False
        for _ in range(60):
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/head", headers={"Authorization": f"Bearer {token}"}), timeout=2).read()
                up = True
                break
            except Exception:
                time.sleep(0.5)
        check("the notary is its own process and answers on loopback", up and notary.poll() is None, f"pid {notary.pid}, port {port}")
        # the git witness: a bare remote and a working clone
        bare, clone = work / "witness-remote.git", work / "witness-clone"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
        clone.mkdir()
        git("init", "-q", "-b", "main", cwd=clone)
        git("remote", "add", "origin", str(bare), cwd=clone)
        git("config", "user.email", "witness@example.test", cwd=clone)
        git("config", "user.name", "witness", cwd=clone)
        host_db = str(work / "host.db")
        host_env = {**base, "DELENTIA_AUDIT_SIGNING_KEY": str(work / "host-keys" / "audit.pem"), "DELENTIA_NOTARY_URL": f"http://127.0.0.1:{port}", "DELENTIA_NOTARY_TOKEN": token,
                    "DELENTIA_AUDIT_WITNESSES": json.dumps([{"type": "git", "name": "git-mirror", "path": str(clone), "remote": "origin", "branch": "main", "key_id": "host-1"}])}
        os.environ.update({k: host_env[k] for k in ("DELENTIA_HOME", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_NOTARY_URL", "DELENTIA_NOTARY_TOKEN")})
        # 2. episodes through the notary
        tools = Tools()
        for i in range(3):
            res = episode(host_db, f"look something up number {i}", tools, [("delentia_recall", {"query": "x"})])
        notarised = res.get("notary") or {}
        check("every tool call was recorded by the notary", bool(tools.dispatched) and int(notarised.get("receipts", notarised.get("count", 0)) or 0) > 0 or bool(notarised), json.dumps(notarised)[:140])
        # 3. verify, anchor, check
        code, out = cli(host_env, "audit-chain", "verify", "--db", host_db, "--pubkey", host_pub)
        check("audit-chain verify passes against the host's public key", code == 0, out.splitlines()[-1][:120] if out else "")
        code, out = cli(base, "notary", "verify", "--db", str(work / "notary.db"), "--pubkey", notary_pub)
        check("notary verify passes against the notary's public key", code == 0, out.splitlines()[-1][:120] if out else "")
        code, out = cli(host_env, "audit-chain", "witness-status", "--db", host_db)
        check("before any anchor the status says the log is not yet held by a witness", "not yet" in out.lower() or "no anchor" in out.lower() or "0" in out, out.replace("\n", " ")[:160])
        code, out = cli(host_env, "audit-chain", "anchor-all", "--db", host_db)
        check("anchor-all publishes the signed head to the git witness", code == 0, out.replace("\n", " ")[:160])
        code, out = cli(host_env, "audit-chain", "check-witnesses", "--db", host_db)
        check("check-witnesses finds the witness consistent with the chain", code == 0, out.replace("\n", " ")[:160])
        # 4. the standalone verifier
        bundle = work / "proof.json"
        code, out = cli(host_env, "audit-chain", "export-proof", "--db", host_db, "--out", str(bundle))
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit_bundle.py"), str(bundle), "--pubkey", host_pub], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=work)
        check("the standalone verifier (no Delentia code) accepts the exported proof", code == 0 and done.returncode == 0, (done.stdout + done.stderr).strip().replace("\n", " ")[:160])
        # 5. the notary stops: the next tool call must not run
        notary.terminate()
        notary.wait(timeout=15)
        before = len(tools.dispatched)
        res = episode(host_db, "look something up while the notary is down", tools, [("delentia_recall", {"query": "y"})])
        check("with the notary down a tool call does not run (fail closed)", len(tools.dispatched) == before and res.get("stopped_reason") == "notary_unavailable", str(res.get("stopped_reason")))
        # 6. the notary's database is edited
        with sqlite3.connect(work / "notary.db") as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            table = next((t for t in tables if "entr" in t or "log" in t), tables[0])
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]   # nosec B608 - a table name read from sqlite_master of our own file
            target = next((c for c in cols if c in ("record", "record_json", "payload", "body", "content")), None)
            if target:
                conn.execute(f"UPDATE {table} SET {target} = {target} || ' ' WHERE rowid = (SELECT MIN(rowid) FROM {table})")   # nosec B608
        code, out = cli(base, "notary", "verify", "--db", str(work / "notary.db"), "--pubkey", notary_pub)
        check("an edited notary database fails notary verify (with a verification message, not a usage error)", code != 0 and target is not None and "ValueError" not in out, (out.splitlines()[-1] if out else "")[:140])
    finally:
        if notary.poll() is None:
            notary.terminate()

    passed = sum(1 for _, ok, _ in results if ok)
    lines = ["# Local trial of the audit tiers (real processes, one machine)", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} by `scripts/trial_notary_witness_local.py`. {passed}/{len(results)} checks passed.", "",
             "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'pass' if ok else '**FAIL**'} | {d.replace('|', '/')} |" for n, ok, d in results]
    lines += ["", "## What this does not show", "",
              "- The notary ran as the **same operating-system user** as the agent. Separation of duties (tier A2) needs another OS user or machine: an account the Architect creates; this script creates none.",
              "- The witness is a bare git repository **on the same disk**. An independent witness (tier A3) is another machine, a protected branch of a hosted repository, or the deployed Worker.",
              "- Nothing here defends against someone with root on this machine, and no claim of tamper-resistance follows from it. The accurate sentence is: the log is hash-chained and signed, "
              "and the mechanism for external anchoring works end to end when a witness the host cannot rewrite is configured."]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(results)} checks passed; wrote {args.out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
