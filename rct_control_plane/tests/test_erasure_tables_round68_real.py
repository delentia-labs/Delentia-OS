"""
Round 68: erasing a person from a database made by REAL governed episodes - the audit rows, the past-requests table and its full-text index, the approvals, the key-value states, the experiments.
Real SQLite, real AES-GCM, real Ed25519 approver keys, the real loop with a scripted model and recorded tools. Nothing in the gate, the stores or the erasure is mocked.

What is pinned: no byte of the database file holds the erased person's words; the other person's rows are identical and still readable; refusals change nothing; the audit chain and the memory
chain still verify; the Desk shows "[erased]"; and when sealing is switched off the report says plainly that the words are still in the chain.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import approvals, audit_chain, audit_text
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _scripted_decide

ALICE = "ALICEWORDS-landlord-Somchai-081-234-5678"
BOB = "BOBWORDS-supplier-Pakwell-02-555-0147"


class Tools(_FakeMCP):
    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in ("delentia_remember", "delentia_write_repo_file")]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return {"ok": True, "echo": json.dumps(args, ensure_ascii=False)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    for var in (me.ENABLE_ENV, er.SEAL_ENV, audit_text.MODE_ENV, approvals.APPROVERS_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "none.json"))
    p = ControlPlanePersistence(db_path=str(tmp_path / "shared.db"))
    return p, tmp_path


def episode(p, tmp_path, monkeypatch, who, words, ask_for_write=True):
    steps = [{"action": "call_tool", "tool_name": "delentia_remember", "tool_args": {"content": f"{words} is a contact"}, "reasoning": f"I will note {words}", "final_answer": None}]
    if ask_for_write:
        steps.append({"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": f"notes/{who}.md", "content_text": f"text {words}"}, "reasoning": "write it", "final_answer": None})
    steps.append({"action": "finish", "reasoning": "done", "final_answer": f"Noted {words}", "tool_name": None, "tool_args": {}})
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


def two_people(world, monkeypatch):
    p, tmp = world
    episode(p, tmp, monkeypatch, "alice", ALICE)
    episode(p, tmp, monkeypatch, "bob", BOB)
    return p, tmp


def approver(tmp, monkeypatch):
    pem = tmp / "outside" / "approver.pem"
    public = approvals.generate_approver_key(str(pem))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    return str(pem)


def file_bytes(p):
    with p._connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    path = p.db_path
    return b"".join(open(f, "rb").read() for f in (path, path + "-wal", path + "-shm") if os.path.exists(f))


def snapshot(p, namespace):
    """Every row of every namespaced table for one person, plus their audit rows as stored."""
    out = {}
    with p._connect() as conn:
        for entry in er._namespaced_tables(conn):
            out[entry["table"]] = sorted(conn.execute(f'SELECT * FROM "{entry["table"]}" WHERE namespace = ?', (namespace,)).fetchall())
        out["audit"] = conn.execute("SELECT entity_type, action, changes FROM audit_trail WHERE actor = ? ORDER BY id", (namespace,)).fetchall()
        out["memories"] = conn.execute("SELECT id, content FROM memories WHERE namespace = ? ORDER BY id", (namespace,)).fetchall()
    return out


def erase(p, tmp, who, pem):
    log = me.MemoryEventLog(p)
    sig = er.sign_erase(pem, who, log.head()["hash"])
    return er.erase_person(p, who, "asked to be forgotten", sig["public_key"], sig["signature"])


def test_before_the_erase_the_words_are_in_the_table_and_not_in_the_chain(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    raw = file_bytes(p)
    assert ALICE.encode() in raw                                          # the readable copies (past requests, memories, approvals) are there...
    with p._connect() as conn:
        for (changes,) in conn.execute("SELECT changes FROM audit_trail"):
            assert ALICE not in changes and BOB not in changes            # ...but no audit row holds anyone's words in the clear
        start = conn.execute("SELECT changes FROM audit_trail WHERE actor = 'alice' AND entity_type = 'governed_loop_episode_start'").fetchone()[0]
    assert audit_text.reveal("alice", json.loads(start)["goal"]) == f"Please remember {ALICE} and write it down"


def test_after_the_erase_no_byte_of_the_file_holds_the_persons_words_and_the_other_person_is_untouched(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    bob_before = snapshot(p, "bob")
    report = erase(p, tmp, "alice", pem)
    assert report["erased"] and report["vacuumed"]
    raw = file_bytes(p)
    assert b"ALICEWORDS" not in raw and b"Somchai" not in raw and b"081-234-5678" not in raw
    assert snapshot(p, "bob") == bob_before                                # row by row, including the audit rows as stored
    assert BOB.encode() in raw                                             # and bob's words are still there to read
    with p._connect() as conn:
        start = conn.execute("SELECT changes FROM audit_trail WHERE actor = 'bob' AND entity_type = 'governed_loop_episode_start'").fetchone()[0]
        assert audit_text.reveal("bob", json.loads(start)["goal"]) == f"Please remember {BOB} and write it down"
        alice_start = conn.execute("SELECT changes FROM audit_trail WHERE actor = 'alice' AND entity_type = 'governed_loop_episode_start'").fetchone()[0]
        assert audit_text.reveal("alice", json.loads(alice_start)["goal"]) == "[erased]"
    assert {t["table"] for t in report["other_tables_scrubbed"]} >= {"episode_log", "pending_actions"}
    assert report["not_erased"]["plain_audit_rows"] == 0 and report["not_erased"]["other_tables"] == []


def test_the_chains_still_verify_and_the_desk_shows_the_erased_marker(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    erase(p, tmp, "alice", pem)
    with p._connect() as conn:
        assert audit_chain.verify_audit_chain(conn).ok
        from rct_control_plane import desk_api
        sessions = [s for s in desk_api.list_sessions(conn) if s["namespace"] == "alice"]
        assert sessions and sessions[0]["goal"] == "[erased]"
        assert [s["goal"] for s in desk_api.list_sessions(conn) if s["namespace"] == "bob"] == [f"Please remember {BOB} and write it down"]
    log = me.MemoryEventLog(p)
    assert log.verify()["ok"] and log.verify_anchors()["ok"]


def test_a_refused_erase_changes_nothing(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    before = file_bytes(p)
    snap = snapshot(p, "alice")
    with pytest.raises(er.ErasureError):
        er.erase_person(p, "alice", "x", "ab" * 32, "cd" * 64)             # not a trusted key
    stale = er.sign_erase(pem, "alice", "0" * 64)
    with pytest.raises(er.ErasureError):
        er.erase_person(p, "alice", "x", stale["public_key"], stale["signature"])   # not this head
    assert snapshot(p, "alice") == snap and ALICE.encode() in file_bytes(p) and before


def test_a_waiting_approval_of_the_erased_person_can_no_longer_be_used(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    with p._connect() as conn:
        waiting = conn.execute("SELECT COUNT(*) FROM pending_actions WHERE namespace = 'alice' AND status = 'PENDING'").fetchone()[0]
    assert waiting >= 1
    erase(p, tmp, "alice", pem)
    with p._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_actions WHERE namespace = 'alice' AND status = 'PENDING'").fetchone()[0] == 0
        goal, args = conn.execute("SELECT goal, tool_args_json FROM pending_actions WHERE namespace = 'alice'").fetchone()
    assert goal == "[erased]" and json.loads(args) == {}


def test_the_full_text_index_forgets_the_words(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    erase(p, tmp, "alice", pem)
    with p._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM episode_log_fts WHERE episode_log_fts MATCH 'Somchai'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM episode_log_fts WHERE episode_log_fts MATCH 'Pakwell'").fetchone()[0] >= 1


def test_with_audit_sealing_switched_off_the_report_says_the_words_are_still_in_the_chain(world, monkeypatch):
    monkeypatch.setenv(audit_text.MODE_ENV, "plain")
    p, tmp = two_people(world, monkeypatch)
    pem = approver(tmp, monkeypatch)
    report = erase(p, tmp, "alice", pem)
    assert report["not_erased"]["plain_audit_rows"] >= 2                   # the goal row and the step rows
    assert ALICE.encode() in file_bytes(p) or b"Somchai" in file_bytes(p)    # the chain cannot be edited, so the words are there, and the report says so


def test_experiments_are_named_by_a_hash_of_the_goal_when_sealing_is_on(world, monkeypatch):
    p, tmp = two_people(world, monkeypatch)
    with p._connect() as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM experiments")]
    assert names and all(n.startswith("goal sha256:") for n in names) and all("Somchai" not in n for n in names)
