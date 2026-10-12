"""
Round 66: the memory event log (memory_eventlog.py): real SQLite, real zstd, the real persistence writers. Nothing is mocked.

What is pinned: the log is off unless asked for; when on, replaying it gives exactly the table (also after a random workload with revocations); a damaged, removed or edited event or
checkpoint is named; a checkpoint shortens the replay without changing its result; any earlier moment can be rebuilt; the archive verifies without the database; the read-time
policies drop only what they promise to, store nothing and delete nothing.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from rct_control_plane import memory_eventlog as me
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(me.ENABLE_ENV, "1")
    monkeypatch.setenv(me.CHECKPOINT_ENV, "40")
    monkeypatch.delenv(me.POLICY_ENV, raising=False)


def new(tmp_path, name="m.db"):
    p = ControlPlanePersistence(db_path=str(tmp_path / name))
    return p, me.MemoryEventLog(p)


def workload(p, ids, rng, n, ns="alice"):
    for i in range(n):
        r = rng.random()
        if r < 0.45 or not ids:
            mid = f"m{len(ids):04d}"
            p.save_memory(mid, ns, rng.choice(["fact", "preference", "event", "conversation"]), f"note {rng.randrange(40)} about vendor {rng.randrange(9)}", {"i": i}, round(rng.random(), 2))
            ids.append(mid)
        elif r < 0.85:
            p.touch_memory(rng.choice(ids))
        else:
            p.revoke_memory(rng.choice(ids), ns, "test")


def test_the_log_can_be_switched_off_and_is_on_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv(me.ENABLE_ENV, raising=False)
    assert me.enabled() is True                                            # Round 67: on unless switched off
    monkeypatch.setenv(me.ENABLE_ENV, "off")
    p, log = new(tmp_path)
    p.save_memory("a", "alice", "fact", "x", {}, 0.5)
    p.touch_memory("a")
    assert log.head()["seq"] == 0 and log.stats("alice")["events"] == 0


def test_replaying_the_log_gives_exactly_the_table_after_a_random_workload(tmp_path, on):
    p, log = new(tmp_path)
    rng, ids = random.Random(7), []
    workload(p, ids, rng, 400)
    result = log.consistent_with_table("alice")
    assert result["ok"], result["differences"]
    assert result["items"] == len(ids) and log.verify()["ok"] and log.stats("alice")["checkpoints"] >= 5
    live_table = {m["id"] for m in p.list_memories("alice")}
    assert set(log.fold("alice")) == live_table                                         # the revoked ones are left out of both


def test_a_checkpoint_shortens_the_replay_without_changing_the_result(tmp_path, on):
    p, log = new(tmp_path)
    workload(p, [], random.Random(3), 250)
    with_cp = log.fold("alice", include_revoked=True)
    copy = tmp_path / "nocp.db"
    with sqlite3.connect(tmp_path / "m.db") as src, sqlite3.connect(copy) as dst:      # the backup API, not a file copy: the database may be in WAL mode and a plain copy would miss the newest writes
        src.backup(dst)
    with sqlite3.connect(copy) as conn:
        conn.execute("DELETE FROM memory_checkpoints")
    _, log2 = new(tmp_path, "nocp.db")
    assert log2.fold("alice", include_revoked=True) == with_cp
    assert log.stats("alice")["last_checkpoint_seq"] > 0


def test_any_earlier_moment_can_be_rebuilt(tmp_path, on):
    p, log = new(tmp_path)
    p.save_memory("a", "alice", "fact", "the budget is 15000", {}, 0.9)
    after_add = log.head()["seq"]
    p.save_memory("b", "alice", "fact", "the budget is now 12000", {}, 0.9)
    p.revoke_memory("a", "alice", "superseded")
    assert set(log.fold("alice")) == {"b"}                                            # now
    assert set(log.fold("alice", upto_seq=after_add)) == {"a"}                        # what it knew before the change
    assert log.fold("alice", upto_seq=after_add, include_revoked=True)["a"]["revoked_at"] is None
    assert log.fold("alice", include_revoked=True)["a"]["revoked_at"]                 # still recoverable for the audit


def test_people_do_not_see_each_others_memories_in_the_log(tmp_path, on):
    p, log = new(tmp_path)
    p.save_memory("a", "alice", "fact", "alice's", {}, 0.5)
    p.save_memory("b", "bob", "fact", "bob's", {}, 0.5)
    assert set(log.fold("alice")) == {"a"} and set(log.fold("bob")) == {"b"}
    assert p.revoke_memory("a", "bob") is False and set(log.fold("alice")) == {"a"}


def test_provenance_travels_with_the_event(tmp_path, on):
    p, log = new(tmp_path)
    p.save_memory("a", "alice", "fact", "from a page", {"provenance": {"tainted": True, "source_tool": "delentia_crawl_url"}}, 0.5)
    with p._connect() as conn:
        prov = json.loads(conn.execute("SELECT provenance FROM memory_events WHERE memory_id = 'a'").fetchone()[0])
    assert prov == {"tainted": True, "source_tool": "delentia_crawl_url"}


@pytest.mark.parametrize("damage", ["edit_event", "remove_event", "edit_checkpoint", "reorder"])
def test_damage_is_named_by_the_check(tmp_path, on, damage):
    p, log = new(tmp_path)
    workload(p, [], random.Random(11), 130)
    assert log.verify()["ok"]
    with sqlite3.connect(tmp_path / "m.db") as conn:
        if damage == "edit_event":
            conn.execute("UPDATE memory_events SET payload = payload || ' ' WHERE seq = (SELECT seq FROM memory_events WHERE kind = 'add' LIMIT 1 OFFSET 20)")      # any change to the stored text, sealed or not
        elif damage == "remove_event":
            conn.execute("DELETE FROM memory_events WHERE seq = 30")
        elif damage == "edit_checkpoint":
            conn.execute("UPDATE memory_checkpoints SET state_sha256 = 'zz' || substr(state_sha256, 3) WHERE id = 1")
        else:
            conn.execute("UPDATE memory_events SET prev_hash = (SELECT prev_hash FROM memory_events WHERE seq = 51) WHERE seq = 50")
    result = log.verify()
    assert not result["ok"] and result["problems"], damage
    if damage in ("edit_event", "remove_event", "reorder"):
        assert any("event" in x for x in result["problems"])


def test_an_edited_checkpoint_is_refused_not_trusted(tmp_path, on):
    p, log = new(tmp_path)
    workload(p, [], random.Random(5), 120)
    with sqlite3.connect(tmp_path / "m.db") as conn:
        conn.execute("UPDATE memory_checkpoints SET state_sha256 = ? WHERE namespace = 'alice'", ("f" * 64,))
    with pytest.raises(ValueError, match="does not match its hash"):
        log.fold("alice")


def test_the_archive_verifies_without_the_database_and_detects_tampering(tmp_path, on):
    p, log = new(tmp_path)
    workload(p, [], random.Random(2), 120)
    info = log.export_archive("alice", str(tmp_path / "alice.zst"))
    assert info["archive_bytes"] < info["raw_bytes"] and me.verify_archive(str(tmp_path / "alice.zst"))["ok"]
    blob = bytearray((tmp_path / "alice.zst").read_bytes())
    blob[len(blob) // 2] ^= 0xFF
    (tmp_path / "bad.zst").write_bytes(bytes(blob))
    assert not me.verify_archive(str(tmp_path / "bad.zst"))["ok"]
    import zstandard
    raw = zstandard.ZstdDecompressor().decompress((tmp_path / "alice.zst").read_bytes()).decode("utf-8").replace("vendor", "VENDOR", 1)
    (tmp_path / "edited.zst").write_bytes(zstandard.ZstdCompressor().compress(raw.encode("utf-8")))
    result = me.verify_archive(str(tmp_path / "edited.zst"))
    assert not result["ok"] and any("hash" in x or "final state" in x for x in result["problems"])


def test_turning_the_log_on_does_not_change_what_the_agent_sees(tmp_path, monkeypatch):
    def run(flag):
        if flag:
            monkeypatch.setenv(me.ENABLE_ENV, "1")
        else:
            monkeypatch.delenv(me.ENABLE_ENV, raising=False)
        p = ControlPlanePersistence(db_path=str(tmp_path / f"c{flag}.db"))
        workload(p, [], random.Random(9), 200)
        return sorted((m["id"], m["content"], m["accessed_count"]) for m in p.list_memories("alice"))
    assert run(0) == run(1)


# ---------------------------------------------------------------- Q2: what the model is shown
def memory(mid, content, kind="fact", importance=0.5, days_old=0.0):
    created = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return {"id": mid, "content": content, "memory_type": kind, "importance": importance, "created_at": created}


def test_none_changes_nothing_and_an_unknown_policy_is_none():
    c = [memory("a", "x"), memory("b", "x")]
    assert me.select_for_recall(c, "none") == c and me.select_for_recall(c, "bogus") == c and me.select_for_recall(c, None) == c


def test_dedupe_counts_the_same_text_once_and_keeps_the_newest():
    c = [memory("old", "Sort by price, lowest first.", days_old=5), memory("new", "sort by price lowest first", days_old=1), memory("other", "the approver is Somchai")]
    kept = {m["id"] for m in me.select_for_recall(c, "dedupe")}
    assert kept == {"new", "other"}


def test_expire_drops_only_old_low_importance_episodes(monkeypatch):
    monkeypatch.setenv(me.TTL_ENV, "30")
    c = [memory("old_chat", "hi", "conversation", 0.3, 90), memory("old_event", "met vendor", "event", 0.4, 90), memory("old_pinned", "key decision", "event", 0.95, 90),
         memory("old_fact", "port is 8443", "fact", 0.5, 400), memory("old_pref", "likes sorted tables", "preference", 0.5, 400), memory("new_chat", "hello", "conversation", 0.3, 2)]
    kept = {m["id"] for m in me.select_for_recall(c, "expire")}
    assert kept == {"old_pinned", "old_fact", "old_pref", "new_chat"}


def test_the_policy_is_applied_when_the_agent_recalls_but_nothing_is_deleted(tmp_path, monkeypatch):
    monkeypatch.delenv(me.ENABLE_ENV, raising=False)
    p = ControlPlanePersistence(db_path=str(tmp_path / "r.db"))
    mem = AgentMemory("alice", p)
    for _ in range(3):
        asyncio.run(mem.store("always sort the table from lowest to highest price", MemoryType.PREFERENCE, importance=0.8))
    monkeypatch.setenv(me.POLICY_ENV, "none")
    assert len(asyncio.run(mem.recall("sort the table by price", limit=5))) == 3
    monkeypatch.setenv(me.POLICY_ENV, "dedupe")
    assert len(asyncio.run(mem.recall("sort the table by price", limit=5))) == 1
    assert len(p.list_memories("alice")) == 3                                           # all three are still stored


def test_the_intent_loop_report_says_what_the_log_holds_and_which_policy_applies(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rct_control_plane.intent_loop import pillar_report
    monkeypatch.setenv(me.ENABLE_ENV, "off")
    monkeypatch.setenv(me.POLICY_ENV, "dedupe")
    p = ControlPlanePersistence(db_path=str(tmp_path / "i.db"))
    loop = SimpleNamespace(_persistence=p, namespace="alice", _episode_memory_scores=[], _episode_skills_injected=0, _episode_compressions=[], _episode_I=1.0)
    off = pillar_report({"steps": []}, loop)["memory"]["log"]
    assert off == {"enabled": False, "policy": "dedupe"}
    monkeypatch.setenv(me.ENABLE_ENV, "1")
    p.save_memory("a", "alice", "fact", "x", {}, 0.5)
    on = pillar_report({"steps": []}, loop)["memory"]["log"]
    assert on["enabled"] is True and on["events"] == 1 and on["live_memories"] == 1 and len(on["head"]) == 16 and on["policy"] == "dedupe"
    assert on["anchors"]["ok"] is True


def test_rctdb_can_replay_what_the_agent_knew_at_an_earlier_event(tmp_path, on):
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.rctdb_facade import RCTDBFacade
    p, log = new(tmp_path)
    p.save_memory("a", "alice", "fact", "first", {}, 0.5)
    mark = log.head()["seq"]
    p.save_memory("b", "alice", "fact", "second", {}, 0.5)
    facade = RCTDBFacade(p, None, AgentMemory("alice", p))
    assert set(facade.memory_state_at("alice")) == {"a", "b"} and set(facade.memory_state_at("alice", upto_seq=mark)) == {"a"}
