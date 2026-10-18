"""
Master workflow W11 (research/master_workflows.py), the whole job in one run: "prove what happened, hand it over, forget a person".

The order of a real handover, with real parts and nothing mocked except the model's decisions:
  1  two people work through real governed episodes (an audit key signs; sealing is on; one write waits for a signature each)
  2  the head is anchored at a witness (a real git repository with a real bare remote)
  3  an outsider is handed a proof bundle and checks it with the STANDALONE verifier in another process, given only the public key
  4  the bundle is altered by one character: the verifier refuses it
  5  someone with the host cuts the newest rows of the chain: the chain alone does not notice (a documented limit), the witness does
  6  a backup is made, restored into a clean directory, and verified by a fresh process with no private key
  7  one person asks to be forgotten: an approver signs, the key is destroyed, the tables are scrubbed, the file is vacuumed
  8  the raw database file is scanned: no byte of that person's words; the other person's words are still readable; both chains still verify; the witness still agrees
  9  what the erasure cannot reach is stated by the test: a backup made BEFORE the erasure still holds the person's words in readable tables
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from rct_control_plane import approvals, audit_chain, audit_text, backup
from rct_control_plane import audit_witness as aw
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _scripted_decide

ROOT = Path(__file__).resolve().parents[2]
ALICE = "ALICEWORDS-landlord-Somchai-081-234-5678"
BOB = "BOBWORDS-supplier-Pakwell-02-555-0147"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


class Tools(_FakeMCP):
    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in ("delentia_remember", "delentia_write_repo_file")]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return {"ok": True, "echo": json.dumps(args, ensure_ascii=False)}


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def episode(p, tmp_path, monkeypatch, who, words):
    steps = [{"action": "call_tool", "tool_name": "delentia_remember", "tool_args": {"content": f"{words} is a contact"}, "reasoning": f"I will note {words}", "final_answer": None},
             {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": f"notes/{who}.md", "content_text": f"text {words}"}, "reasoning": "write it", "final_answer": None},
             {"action": "finish", "reasoning": "done", "final_answer": f"Noted {words}", "tool_name": None, "tool_args": {}}]
    fake, _ = _scripted_decide(steps)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = GovernedAutonomousLoop(mcp_server=Tools(), persistence=p, kernel=_FakeKernel(), skill_library=SkillLibrary(db_path=str(tmp_path / f"{who}_skills.db")), max_iterations=6, namespace=who)
    real = loop._assess_data

    def assess(goal, clarity, compiled):
        evidence = real(goal, clarity, compiled)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    result = asyncio.run(loop.run(f"Please remember {words} and write it down"))
    asyncio.run(AgentMemory(who, p).store(f"{who}: {words}", MemoryType.FACT, importance=0.7))
    return result


def raw_bytes(p):
    with p._connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    path = p.db_path
    return b"".join(open(f, "rb").read() for f in (path, path + "-wal", path + "-shm") if os.path.exists(f))


def fresh_process_probe(db_path, public_hex, home):
    probe = ("import sys, json; sys.path.insert(0, %r)\n"
             "from rct_control_plane.persistence import ControlPlanePersistence\n"
             "from rct_control_plane import audit_chain\n"
             "p = ControlPlanePersistence(db_path=%r)\n"
             "with p._connect() as conn:\n"
             "    report = audit_chain.verify_audit_chain(conn, public_key_hex=%r)\n"
             "    head = audit_chain.chain_head(conn)\n"
             "print(json.dumps({'ok': report.ok, 'rows': report.chained_rows, 'signed': report.signed_rows, 'head': head['row_hash'] if head else None}))\n") % (str(ROOT), str(db_path), public_hex)
    env = {k: v for k, v in os.environ.items() if k not in ("DELENTIA_AUDIT_SIGNING_KEY",)}
    env.update({"DELENTIA_HOME": str(home), "PYTHONIOENCODING": "utf-8"})
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env, timeout=300)
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_w11_the_whole_handover_in_order(tmp_path, monkeypatch):
    for var in (me.ENABLE_ENV, er.SEAL_ENV, audit_text.MODE_ENV, approvals.APPROVERS_ENV, aw.WITNESSES_ENV, aw.URL_ENV, aw.KEY_ID_ENV, audit_chain.PUBKEY_ENV):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("DELENTIA_HOME", str(home))
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "none.json"))
    audit_key = tmp_path / "audit" / "audit.pem"
    public = audit_chain.generate_signing_key(str(audit_key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(audit_key))
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(bare))
    anchors = tmp_path / "anchors"
    anchors.mkdir()
    git("init", "-q", "-b", "main", cwd=str(anchors))
    git("remote", "add", "origin", str(bare), cwd=str(anchors))
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{"type": "git", "name": "ledger", "path": str(anchors), "remote": "origin", "branch": "main", "key_id": "host-1"}]))
    p = ControlPlanePersistence(db_path=str(home / "agentic.db"))

    # 1 a day of work by two people
    assert episode(p, tmp_path, monkeypatch, "alice", ALICE)
    assert episode(p, tmp_path, monkeypatch, "bob", BOB)
    with p._connect() as conn:
        report = audit_chain.verify_audit_chain(conn, public_key_hex=public)
        assert report.ok and report.signed_rows == report.chained_rows >= 6

    # 2 the head is anchored at the witness
    with p._connect() as conn:
        anchored = aw.anchor_all(conn)
        assert anchored and all(a["ok"] for a in anchored), anchored
        head_at_anchor = audit_chain.chain_head(conn)
        assert aw.check_witnesses(conn)[0]["ok"] is True

    # 3 an outsider verifies a bundle with the standalone tool, given only the public key
    with p._connect() as conn:
        bundle = aw.export_proof(conn)
    bundle_path = tmp_path / "handover" / "bundle.json"
    bundle_path.parent.mkdir()
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    verifier = [sys.executable, str(ROOT / "scripts" / "verify_audit_bundle.py"), str(bundle_path), "--pubkey", public]
    ok = subprocess.run(verifier, capture_output=True, text=True, timeout=120, cwd=str(tmp_path / "handover"))
    assert ok.returncode == 0, ok.stdout[-600:] + ok.stderr[-300:]

    # 4 one character changed in a row of the bundle: refused
    altered = json.loads(bundle_path.read_text(encoding="utf-8"))
    altered["rows"][2]["action"] = altered["rows"][2]["action"] + "x"
    altered_path = tmp_path / "handover" / "altered.json"
    altered_path.write_text(json.dumps(altered), encoding="utf-8")
    refused = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit_bundle.py"), str(altered_path), "--pubkey", public], capture_output=True, text=True, timeout=120)
    assert refused.returncode != 0

    # 5 the newest rows are cut on a COPY: the chain alone cannot tell, the witness can
    cut_db = tmp_path / "cut" / "agentic.db"
    cut_db.parent.mkdir()
    with p._connect() as src, sqlite3.connect(str(cut_db)) as dst:
        src.backup(dst)
    with sqlite3.connect(str(cut_db)) as conn:
        newest = conn.execute("SELECT seq, audit_id FROM audit_chain ORDER BY seq DESC LIMIT 2").fetchall()
        for seq, audit_id in newest:
            conn.execute("DELETE FROM audit_chain WHERE seq = ?", (seq,))
            conn.execute("DELETE FROM audit_trail WHERE id = ?", (audit_id,))
    cut = ControlPlanePersistence(db_path=str(cut_db))
    with cut._connect() as conn:
        assert audit_chain.verify_audit_chain(conn, public_key_hex=public).ok is True          # the documented limit: a shorter chain is still a valid chain
        assert aw.check_witnesses(conn)[0]["ok"] is False                                      # the outside copy remembers a longer one

    # 6 a backup comes back on a clean machine and verifies with the PUBLIC key only
    archive = tmp_path / "off-host" / "state.zip"
    archive.parent.mkdir()
    made = backup.create_backup(str(archive))
    assert made["includes_keys"] is False
    clean = tmp_path / "clean-machine"
    restored = backup.restore_backup(str(archive), str(clean))
    assert restored["restored"] >= 1
    seen = fresh_process_probe(clean / "home" / "agentic.db", public, clean / "home")
    assert seen["ok"] is True and seen["signed"] == seen["rows"] and seen["head"] == head_at_anchor["row_hash"]
    restored_raw = (clean / "home" / "agentic.db").read_bytes()

    # 7 alice asks to be forgotten: an approver signs over her name and the current head of her memory log
    pem = tmp_path / "outside" / "approver.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(pem)))
    bob_before = raw_bytes(p)
    assert ALICE.encode() in bob_before and BOB.encode() in bob_before
    sig = er.sign_erase(str(pem), "alice", me.MemoryEventLog(p).head()["hash"])
    erased = er.erase_person(p, "alice", "asked to be forgotten", sig["public_key"], sig["signature"])
    assert erased["erased"] and erased["vacuumed"]

    # 8 the raw file: none of her words; his are still there; both chains and the witness agree
    raw = raw_bytes(p)
    assert b"ALICEWORDS" not in raw and b"Somchai" not in raw and b"081-234-5678" not in raw
    assert BOB.encode() in raw
    with p._connect() as conn:
        assert audit_chain.verify_audit_chain(conn, public_key_hex=public).ok is True
        assert me.MemoryEventLog(p).verify()["ok"] is True
        assert aw.check_witnesses(conn)[0]["ok"] is True

    # 9 what erasure cannot reach, stated rather than hidden: a backup made before it still holds her words in readable tables
    assert b"ALICEWORDS" in restored_raw
