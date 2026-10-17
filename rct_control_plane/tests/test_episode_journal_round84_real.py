"""
Round 84: episode-level resume. A governed episode writes a durable journal (episode_journal.py): the intent of a tool call BEFORE it is dispatched, its result after, the end of the episode. After a crash,
`resume_interrupted` starts a NEW governed episode for the same goal, told which steps already ran; it never replays a result and never runs a side effect again on its own.

"The process dies" is simulated in-process by a BaseException raised from inside a tool (the loop's `except Exception` does not catch it, so no end row is written, exactly what a kill leaves); the same
cases with a real process termination are in test_episode_resume_process_round84_real.py.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from research.daaes import delentia_session as ds
from rct_control_plane import episode_journal
from rct_control_plane.agent_factory import build_governed_loop
from rct_control_plane.persistence import ControlPlanePersistence


class Crash(BaseException):
    """What a killed process looks like from inside: nothing after this line runs."""


class World:
    """read_repo_file (reads), save_exchange_file (changes something: appends a durable receipt), crawl_url (outside text)."""

    def __init__(self, root: Path, crash_on=None, crash_after_effect=False):
        self.root, self.crash_on, self.crash_after_effect = Path(root), crash_on, crash_after_effect
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipts = self.root / "receipts.jsonl"
        self.calls = []

    async def list_tools(self):
        return [ds._Tool("delentia_read_repo_file"), ds._Tool("delentia_save_exchange_file"), ds._Tool("delentia_crawl_url")]

    def effects(self):
        return [json.loads(line)["op"] for line in self.receipts.read_text(encoding="utf-8").splitlines()] if self.receipts.exists() else []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        n = len(self.calls)
        if name == "delentia_save_exchange_file":
            if self.crash_on == n and not self.crash_after_effect:
                raise Crash()                                              # killed before the effect
            with open(self.receipts, "a", encoding="utf-8") as f:
                f.write(json.dumps({"op": args.get("filename")}) + "\n")
            if self.crash_on == n and self.crash_after_effect:
                raise Crash()                                              # killed after the effect, before the result was recorded
            return ds._Result({"ok": True, "saved": args.get("filename")})
        if name == "delentia_crawl_url":
            return ds._Result({"ok": True, "text": "a page from outside"})
        if self.crash_on == n:
            raise Crash()
        return ds._Result({"ok": True, "content": "contents of " + str(args.get("relative_path"))})


def call(tool, args, why="step"):
    return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": why}


FINISH = {"action": "finish", "reasoning": "done", "final_answer": "all done", "tool_name": None, "tool_args": {}}
GOAL = "Process the three orders and save a receipt file for each"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    monkeypatch.delenv("DELENTIA_EPISODE_JOURNAL", raising=False)
    home = tmp_path / "home"
    ctx = ds.data_home(home)
    ctx.__enter__()
    persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
    yield tmp_path, persistence
    ctx.__exit__(None, None, None)


def make_loop(persistence, world, namespace="alice"):
    loop = build_governed_loop(ds.NullKernel(), namespace=namespace, max_iterations=12, persistence=persistence, mcp_server=world, conversation_turns=0)
    loop._route_enabled = False                                           # type: ignore[attr-defined]
    return loop


def run_episode(persistence, world, decisions, namespace="alice"):
    loop = make_loop(persistence, world, namespace)
    with ds.scripted_model(decisions) as state:
        try:
            result = asyncio.run(loop.run(GOAL))
        except Crash:
            result = None
    return loop, result, state


def resume(persistence, world, episode_id, decisions, namespace="alice", **kw):
    loop = make_loop(persistence, world, namespace)
    with ds.scripted_model(decisions) as state:
        out = asyncio.run(loop.resume_interrupted(episode_id, **kw))
    return loop, out, state


def three_saves(extra=()):
    return [call("delentia_read_repo_file", {"relative_path": "orders.csv"}), *[call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{i}.txt", "content": "x"}) for i in (1, 2, 3)], *extra, FINISH]


def test_a_normal_episode_leaves_begin_intent_result_end_and_the_text_is_sealed(env):
    tmp, persistence = env
    world = World(tmp / "w")
    loop, result, _ = run_episode(persistence, world, three_saves())
    assert result["stopped_reason"] == "llm_finished" and world.effects() == ["order-1.txt", "order-2.txt", "order-3.txt"]
    journal = episode_journal.EpisodeJournal(persistence)
    ep = journal.load(loop._episode_id)
    assert ep.chain_ok and ep.ended and ep.goal == GOAL and [s.state for s in ep.steps] == ["done"] * 4
    assert [s.tool for s in ep.steps] == ["delentia_read_repo_file"] + ["delentia_save_exchange_file"] * 3
    raw = sqlite3.connect(persistence.db_path if hasattr(persistence, "db_path") else str(tmp / "home" / "agentic.db")).execute("SELECT group_concat(payload) FROM episode_journal").fetchone()[0]
    assert "Process the three orders" not in raw and "order-1.txt" not in raw, "goal and arguments must be sealed, not stored in the clear"


def test_the_intent_is_on_disk_before_the_tool_runs(env):
    tmp, persistence = env
    seen = {}

    class Spy(World):
        async def call_tool(self, name, args):
            if name == "delentia_save_exchange_file" and "at_call" not in seen:
                ep = episode_journal.EpisodeJournal(persistence)
                seen["at_call"] = [(s.tool, s.state) for s in ep.load(loop._episode_id).steps]
            return await super().call_tool(name, args)
    world = Spy(tmp / "w")
    loop = make_loop(persistence, world)
    with ds.scripted_model(three_saves()):
        asyncio.run(loop.run(GOAL))
    assert seen["at_call"][-1] == ("delentia_save_exchange_file", "dangling"), seen


def test_a_crash_in_a_read_only_tool_resumes_without_asking_and_repeats_nothing_that_was_done(env):
    tmp, persistence = env
    world = World(tmp / "w", crash_on=1)                                  # the very first call (a read) dies
    loop, result, _ = run_episode(persistence, world, three_saves())
    assert result is None
    ep = episode_journal.EpisodeJournal(persistence).load(loop._episode_id)
    assert not ep.ended and [s.state for s in ep.steps] == ["dangling"]
    world2 = World(tmp / "w")
    contexts = []
    follow = [lambda g, h, ctx: (contexts.append(ctx), call("delentia_read_repo_file", {"relative_path": "orders.csv"}))[1],
              *[call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{i}.txt", "content": "x"}) for i in (1, 2, 3)], FINISH]
    _, out, _ = resume(persistence, world2, loop._episode_id, follow)
    assert out["resumed"] is True and out["resumed_from"] == loop._episode_id and out["stopped_reason"] == "llm_finished"
    assert world2.effects() == ["order-1.txt", "order-2.txt", "order-3.txt"]
    assert "interrupted" in contexts[0] and "OUTCOME UNKNOWN" in contexts[0] and "only reads" in contexts[0]


@pytest.mark.parametrize("after_effect", [False, True])
def test_a_crash_in_a_tool_that_changes_something_is_never_rerun_on_its_own(env, after_effect):
    tmp, persistence = env
    world = World(tmp / "w", crash_on=3, crash_after_effect=after_effect)  # read, save 1, then save 2 dies (before or after its effect)
    loop, result, _ = run_episode(persistence, world, three_saves())
    assert result is None and world.effects() == (["order-1.txt", "order-2.txt"] if after_effect else ["order-1.txt"])
    world2 = World(tmp / "w")
    _, refused, state = resume(persistence, world2, loop._episode_id, three_saves())
    assert refused["resumed"] is False and "unknown outcome" in refused["reason"]
    assert [u["tool"] for u in refused["unknown"]] == ["delentia_save_exchange_file"] and refused["completed"][0]["tool"] == "delentia_read_repo_file"
    assert world2.calls == [] and state["i"] == 0, "nothing ran and no model was asked"
    # a person looks at the world, says to go on; the continuation checks the receipt FIRST and only does what is missing
    effects_seen = world2.effects()
    todo = [n for n in (1, 2, 3) if f"order-{n}.txt" not in effects_seen]
    follow = [call("delentia_read_repo_file", {"relative_path": "receipts.jsonl"}), *[call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{n}.txt", "content": "x"}) for n in todo], FINISH]
    _, out, _ = resume(persistence, world2, loop._episode_id, follow, allow_unknown=True)
    assert out["resumed"] is True
    assert sorted(world2.effects()) == ["order-1.txt", "order-2.txt", "order-3.txt"], "every order done"
    assert len(world2.effects()) == 3, "and none done twice"


def test_one_resume_each_and_only_for_the_person_it_belongs_to_and_only_while_unfinished(env):
    tmp, persistence = env
    world = World(tmp / "w", crash_on=1)
    loop, _, _ = run_episode(persistence, world, three_saves())
    eid = loop._episode_id
    stranger = resume(persistence, World(tmp / "w"), eid, [FINISH], namespace="mallory")[1]
    assert stranger["resumed"] is False and "someone else" in stranger["reason"]
    first = resume(persistence, World(tmp / "w"), eid, [FINISH])[1]
    assert first["resumed"] is True
    second = resume(persistence, World(tmp / "w"), eid, [FINISH])[1]
    assert second["resumed"] is False and "already resumed" in second["reason"]
    done_loop, done_result, _ = run_episode(persistence, World(tmp / "w2"), [FINISH])
    ended = resume(persistence, World(tmp / "w2"), done_loop._episode_id, [FINISH])[1]
    assert ended["resumed"] is False and "already ended" in ended["reason"]
    assert resume(persistence, World(tmp / "w"), "no-such-id", [FINISH])[1]["resumed"] is False


def test_a_journal_that_was_edited_is_refused(env):
    tmp, persistence = env
    loop, _, _ = run_episode(persistence, World(tmp / "w", crash_on=1), three_saves())
    with persistence._connect() as conn:
        conn.execute("UPDATE episode_journal SET payload = replace(payload, 'dangling', 'done') WHERE episode_id = ? AND kind = 'intent'", (loop._episode_id,))
        conn.execute("UPDATE episode_journal SET prev_hash = 'forged' WHERE episode_id = ? AND seq = 2", (loop._episode_id,))
    out = resume(persistence, World(tmp / "w"), loop._episode_id, [FINISH])[1]
    assert out["resumed"] is False and "does not verify" in out["reason"]


def test_an_episode_that_had_read_outside_text_resumes_tainted(env):
    tmp, persistence = env
    plan = [call("delentia_crawl_url", {"url": "https://example.org/page"}), call("delentia_read_repo_file", {"relative_path": "a"}), call("delentia_read_repo_file", {"relative_path": "b"}), FINISH]
    world = World(tmp / "w", crash_on=3)
    loop, _, _ = run_episode(persistence, world, plan)
    ep = episode_journal.EpisodeJournal(persistence).load(loop._episode_id)
    assert ep.taint, "the journal remembers that outside text had been read"
    seen = []
    follow = [lambda g, h, ctx: (seen.append(resumed_loop._episode_taint), FINISH)[1]]
    resumed_loop = make_loop(persistence, World(tmp / "w"))
    with ds.scripted_model(follow):
        asyncio.run(resumed_loop.resume_interrupted(loop._episode_id))
    assert seen and seen[0], "the continuation starts tainted, exactly as the original was"


def test_interrupted_lists_only_episodes_whose_process_is_gone_or_silent(env, monkeypatch):
    tmp, persistence = env
    loop, _, _ = run_episode(persistence, World(tmp / "w", crash_on=1), three_saves())
    journal = episode_journal.EpisodeJournal(persistence)
    assert journal.interrupted("alice", stale_after=3600) == [] or all(e.episode_id != loop._episode_id for e in journal.interrupted("alice", stale_after=3600)), "this very process is alive and was just active"
    monkeypatch.setattr(episode_journal, "_alive", lambda pid, started: False)
    assert [e.episode_id for e in journal.interrupted("alice")] == [loop._episode_id]
    assert journal.interrupted("bob") == []
    resume(persistence, World(tmp / "w"), loop._episode_id, [FINISH])
    assert journal.interrupted("alice") == [], "a resumed episode is no longer listed"


def test_a_journal_write_failure_never_stops_the_episode_and_is_audited(env, monkeypatch):
    tmp, persistence = env

    def boom(self, *a, **k):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(episode_journal.EpisodeJournal, "_append", boom)
    world = World(tmp / "w")
    loop, result, _ = run_episode(persistence, world, three_saves())
    assert result["stopped_reason"] == "llm_finished" and len(world.effects()) == 3
    with persistence._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'episode_journal' AND action = 'journal_gap'").fetchone()[0] == 1


def test_the_journal_can_be_switched_off_and_then_nothing_is_written_or_resumable(env, monkeypatch):
    tmp, persistence = env
    monkeypatch.setenv("DELENTIA_EPISODE_JOURNAL", "off")
    loop, _, _ = run_episode(persistence, World(tmp / "w", crash_on=1), three_saves())
    with persistence._connect() as conn:
        exists = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'episode_journal'").fetchone()[0]
        assert exists == 0 or conn.execute("SELECT COUNT(*) FROM episode_journal").fetchone()[0] == 0
    assert resume(persistence, World(tmp / "w"), loop._episode_id, [FINISH])[1]["resumed"] is False


def test_erasing_a_person_leaves_no_trace_of_their_goal_in_the_journal(env, monkeypatch):
    from rct_control_plane import approvals, memory_erasure as er, memory_eventlog as me
    tmp, persistence = env
    loop, _, _ = run_episode(persistence, World(tmp / "w", crash_on=1), three_saves())
    other, _, _ = run_episode(persistence, World(tmp / "w3"), [FINISH], namespace="bob")
    pem = tmp / "outside" / "approver.pem"
    public = approvals.generate_approver_key(str(pem))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    log = me.MemoryEventLog(persistence)
    sig = er.sign_erase(str(pem), "alice", log.head()["hash"])
    er.erase_person(persistence, "alice", "the person asked", sig["public_key"], sig["signature"])
    raw = sqlite3.connect(str(tmp / "home" / "agentic.db")).execute("SELECT group_concat(payload) FROM episode_journal WHERE namespace = 'alice'").fetchone()[0] or ""
    assert "Process the three orders" not in raw and "order-1.txt" not in raw
    journal = episode_journal.EpisodeJournal(persistence)
    assert journal.load(other._episode_id).goal == GOAL, "someone else's journal is untouched"


def test_a_running_process_is_not_called_interrupted_on_a_machine_without_psutil(monkeypatch):
    """CI found it: without psutil the journal could not read a start time, said 'not alive' for a LIVE process, and a running episode would have been offered for a second run."""
    monkeypatch.setitem(sys.modules, "psutil", None)                    # `import psutil` now raises ImportError
    me = os.getpid()
    assert episode_journal._exists(me) and episode_journal._alive(me, None)
    assert episode_journal._alive(me, episode_journal._proc_start(me)), "same process, whatever it reports as its start"
    import subprocess
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not episode_journal._exists(child.pid) and not episode_journal._alive(child.pid, None), "a process that has finished is gone"
    assert not episode_journal._alive(None, None) and not episode_journal._alive(0, None)


def test_when_two_claims_both_get_written_the_first_one_wins_and_the_second_is_told_no(env):
    """CI found it (Python 3.10, two real processes): both claimers read the journal before either wrote, both inserted a 'resumed' row (different seq numbers, so the UNIQUE key did not stop them), the
    fold let the LATER row take the claim, and both were told they had won: the episode would have run twice. The first row in order now decides."""
    tmp, persistence = env
    loop, _, _ = run_episode(persistence, World(tmp / "w", crash_on=1), three_saves())
    journal = episode_journal.EpisodeJournal(persistence)
    ep = journal.load(loop._episode_id)
    journal._append(ep.episode_id, ep.namespace, "resumed", {"by": "claimer-a"})          # what a racing claimer's insert looks like: written without having seen the other
    journal._append(ep.episode_id, ep.namespace, "resumed", {"by": "claimer-b"})
    assert journal.load(ep.episode_id).resumed_by == "claimer-a"
    assert journal.claim_resume(ep.episode_id, ep.namespace, "claimer-c") is False
    assert journal.load(ep.episode_id).resumed_by == "claimer-a"
