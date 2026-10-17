"""
Round 84, valid-from / valid-to for a memory: a window the person set decides whether the model is shown it. Nothing is deleted; the audit view and the event log still hold it; a typo or an empty window
is refused when written; pinned rules obey the window too.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from rct_control_plane import memory_validity as mv
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    return ControlPlanePersistence(str(tmp_path / "m.db"))


def iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def store(memory, text, **kw):
    return asyncio.run(memory.store(text, MemoryType.FACT, **kw))


def test_the_bounds_are_inclusive_from_exclusive_to_and_a_date_alone_means_midnight_utc():
    start, end = mv.parse_bound("2026-11-01"), mv.parse_bound("2026-12-01T00:00:00Z")
    memory = {"context": {"valid_from": "2026-11-01", "valid_to": "2026-12-01"}}
    assert mv.is_valid_at(memory, start) and mv.is_valid_at(memory, end - 1) and not mv.is_valid_at(memory, start - 1) and not mv.is_valid_at(memory, end)
    assert mv.is_valid_at({"context": {}}, 1.0) and mv.is_valid_at({"context": None}, 1.0), "no window = always valid"
    assert mv.parse_bound("2026-11-01T09:00:00+07:00") == mv.parse_bound("2026-11-01T02:00:00Z")
    for bad in ("next friday", "2026-13-40", "soon"):
        with pytest.raises(ValueError):
            mv.parse_bound(bad)
    with pytest.raises(ValueError):
        mv.with_bounds({}, "2026-12-01", "2026-11-01")                                       # an empty window is a mistake, not a memory that never counts


def test_the_model_is_shown_only_what_is_valid_now_and_the_audit_view_still_has_the_rest(persistence):
    memory = AgentMemory("alice", persistence)
    always = store(memory, "The staging database is stg-db-1")
    current = store(memory, "The promotion price is 90 baht", valid_from=iso(-3), valid_to=iso(3))
    expired = store(memory, "The old price is 120 baht", valid_to=iso(-1))
    future = store(memory, "From next month the price is 150 baht", valid_from=iso(10))
    shown = {m["id"] for m in persistence.list_memories("alice")}
    assert shown == {always, current}
    assert {m["id"] for m in persistence.list_memories("alice", include_expired=True)} == {always, current, expired, future}
    assert {m["id"] for m in persistence.list_memories("alice", include_revoked=True)} == {always, current, expired, future}, "the audit view shows everything"
    recalled = asyncio.run(memory.recall("what is the price", limit=10))
    assert {m["id"] for m in recalled} == {always, current}, "recall goes through the same reader"
    scored = asyncio.run(memory.recall_scored("price", limit=10))
    assert expired not in {m["id"] for m in scored} and future not in {m["id"] for m in scored}


def test_a_typo_or_an_empty_window_is_refused_when_the_memory_is_written(persistence):
    memory = AgentMemory("alice", persistence)
    with pytest.raises(ValueError):
        store(memory, "x", valid_to="until friday")
    with pytest.raises(ValueError):
        store(memory, "x", valid_from=iso(5), valid_to=iso(1))
    assert persistence.list_memories("alice", include_revoked=True) == [], "nothing was stored"


def test_a_pinned_rule_obeys_its_window(persistence):
    memory = AgentMemory("alice", persistence)
    rule = store(memory, "Until the audit ends, never email customers.", valid_to=iso(1))
    assert persistence.pin_memory(rule, "alice", True, by="test")["ok"]
    assert [m["id"] for m in persistence.pinned_memories("alice")] == [rule]
    old = store(memory, "Last quarter's rule: approvals need two people.", valid_to=iso(-1))
    assert persistence.pin_memory(old, "alice", True, by="test")["ok"], "an expired memory can still be pinned in the table; it is just not shown"
    assert [m["id"] for m in persistence.pinned_memories("alice")] == [rule]
    assert [m["id"] for m in AgentMemory("alice", persistence).pinned()] == [rule]


def test_the_window_is_in_the_event_log_so_history_can_answer_what_was_believed_then(persistence):
    from rct_control_plane import memory_eventlog
    memory = AgentMemory("alice", persistence)
    mid = store(memory, "The price is 90 baht", valid_from="2026-01-01", valid_to="2026-02-01")
    state = memory_eventlog.MemoryEventLog(persistence).fold("alice")
    assert state[mid]["context"]["valid_from"] == "2026-01-01" and state[mid]["context"]["valid_to"] == "2026-02-01"
    assert mv.is_valid_at(state[mid], mv.parse_bound("2026-01-15")) and not mv.is_valid_at(state[mid], mv.parse_bound("2026-03-01"))


def test_the_command_line_stores_a_window_lists_it_and_hides_expired_by_default(persistence, tmp_path):
    from rct_control_plane.cli import cli
    db = str(tmp_path / "m.db")
    run = CliRunner()
    ok = run.invoke(cli, ["memory", "add", "The price is 90 baht", "--namespace", "bob", "--valid-from", iso(-1), "--valid-to", iso(5), "--db", db])
    assert ok.exit_code == 0 and "stored mem_" in ok.output
    gone = run.invoke(cli, ["memory", "add", "The old price is 120 baht", "--namespace", "bob", "--valid-to", iso(-2), "--db", db])
    assert gone.exit_code == 0
    bad = run.invoke(cli, ["memory", "add", "x", "--namespace", "bob", "--valid-to", "soon", "--db", db])
    assert bad.exit_code == 1 and "not an ISO date" in bad.output
    listed = run.invoke(cli, ["memory", "list", "--namespace", "bob", "--db", db]).output
    assert "90 baht" in listed and "valid from" in listed and "120 baht" not in listed
    everything = run.invoke(cli, ["memory", "list", "--namespace", "bob", "--expired", "--db", db]).output
    assert "120 baht" in everything and "EXPIRED" in everything
