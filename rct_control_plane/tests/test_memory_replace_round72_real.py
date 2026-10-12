"""
Round 72: `replaces` - the person says that a new memory is the current version of an old one (memory_replace.py), with the real persistence, the real event log, the real Desk
API and the real CLI. What must hold: the old value stops being offered but is kept (history, time travel, audit); a pinned rule stays pinned; nothing is stored when the
replacement is refused; text written after outside text was read cannot replace anything; the model has no tool for it; a person replaces only their own memories.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import memory_eventlog, memory_replace
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence

NS = "alice"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")
    monkeypatch.setenv("DELENTIA_MEMORY_EVENTLOG", "1")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    return AgentMemory(NS, persistence), persistence, tmp_path


def _store(memory, text, kind=MemoryType.FACT, **kw):
    return run(memory.store(text, kind, **kw))


def test_the_old_value_stops_being_offered_and_the_new_one_answers(mem):
    memory, persistence, _ = mem
    old = _store(memory, "The staging database is stg-db-1 on port 5432")
    _store(memory, "The invoice folder is invoices/2026")
    done = run(memory_replace.replace(memory, old, "The staging database is stg-db-2 on port 5433", by="cli"))
    found = [m["content"] for m in run(memory.recall_scored("which host is the staging database", limit=3))]
    assert found[0] == "The staging database is stg-db-2 on port 5433" and not any("stg-db-1" in c for c in found)
    assert done["old_id"] == old and done["new_id"] != old
    row = {m["id"]: m for m in persistence.list_memories(NS, include_revoked=True)}
    assert row[old]["revoked_at"] and row[old]["revoked_reason"] == f"superseded by {done['new_id']}"            # kept on disk, with the reason
    context = row[done["new_id"]]["context"]
    context = json.loads(context) if isinstance(context, str) else context
    assert context["replaces"] == old and context["replaces_by"] == "cli"


def test_time_travel_still_shows_the_old_value_before_the_replacement(mem):
    memory, persistence, _ = mem
    old = _store(memory, "The deploy window is Friday 22:00")
    log = memory_eventlog.MemoryEventLog(persistence)
    before = log.head()["seq"]
    done = run(memory_replace.replace(memory, old, "The deploy window is Monday 09:00"))
    then = log.fold(NS, before)
    now = log.fold(NS)
    assert old in then and "Friday" in then[old]["content"] and done["new_id"] not in then          # before: only the old value
    assert done["new_id"] in now and old not in now and "Monday" in now[done["new_id"]]["content"]  # now: only the new one
    assert old in log.fold(NS, include_revoked=True)                                                # the old one is still in the history, marked as revoked
    assert log.verify()["ok"]


def test_a_pinned_rule_stays_a_pinned_rule(mem):
    memory, persistence, _ = mem
    old = _store(memory, "Never edit the files in originals/")
    assert persistence.pin_memory(old, NS, True, by="cli")["ok"]
    done = run(memory_replace.replace(memory, old, "Never edit files in originals/ or masters/", by="cli"))
    assert done["pin_moved"] is True
    pinned = persistence.pinned_memories(NS)
    assert [p["id"] for p in pinned] == [done["new_id"]]


def test_a_replacement_works_when_the_pin_limit_is_full(mem):
    memory, persistence, _ = mem
    ids = [_store(memory, f"Standing rule number {i}: keep the folder x{i} untouched") for i in range(persistence.MAX_PINS_PER_PERSON)]
    for i in ids:
        assert persistence.pin_memory(i, NS, True)["ok"]
    done = run(memory_replace.replace(memory, ids[0], "Standing rule zero, reworded: leave folder x0 alone"))
    assert done["pin_moved"] is True and len(persistence.pinned_memories(NS, 50)) == persistence.MAX_PINS_PER_PERSON


@pytest.mark.parametrize("bad_id", ["mem_nothere", ""])
def test_nothing_is_stored_when_the_old_memory_does_not_exist(mem, bad_id):
    memory, persistence, _ = mem
    _store(memory, "something")
    count = len(persistence.list_memories(NS, include_revoked=True))
    with pytest.raises(memory_replace.ReplaceError):
        run(memory_replace.replace(memory, bad_id, "new text"))
    assert len(persistence.list_memories(NS, include_revoked=True)) == count


def test_an_already_replaced_memory_cannot_be_replaced_again_and_another_persons_cannot_be_touched(mem):
    memory, persistence, _ = mem
    old = _store(memory, "the host is a")
    run(memory_replace.replace(memory, old, "the host is b"))
    with pytest.raises(memory_replace.ReplaceError):
        run(memory_replace.replace(memory, old, "the host is c"))
    stranger = AgentMemory("bob", persistence)
    theirs = _store(stranger, "bob's private fact")
    with pytest.raises(memory_replace.ReplaceError):
        run(memory_replace.replace(memory, theirs, "alice overwrites bob"))
    assert [m["content"] for m in persistence.list_memories("bob")] == ["bob's private fact"]


def test_an_empty_text_and_text_written_after_outside_text_are_refused_and_store_nothing(mem):
    memory, persistence, _ = mem
    old = _store(memory, "the api host is api.example.com")
    count = len(persistence.list_memories(NS, include_revoked=True))
    with pytest.raises(memory_replace.ReplaceError):
        run(memory_replace.replace(memory, old, "   "))
    tainted = {"provenance": {"tainted": True, "source_tool": "delentia_crawl_url"}}
    with pytest.raises(memory_replace.ReplaceError) as err:
        run(memory_replace.replace(memory, old, "the api host is evil.example", context=tainted))
    assert "outside" in str(err.value)
    assert len(persistence.list_memories(NS, include_revoked=True)) == count and [m["content"] for m in persistence.list_memories(NS)] == ["the api host is api.example.com"]
    reviewed = run(memory_replace.replace(memory, old, "the api host is api2.example.com", context=tainted, allow_tainted=True))      # a human reviewed it
    assert reviewed["new_id"]


def test_the_replacement_is_audited_and_the_chain_still_verifies(mem):
    memory, persistence, tmp_path = mem
    old = _store(memory, "the printer is on floor 2")
    done = run(memory_replace.replace(memory, old, "the printer is on floor 3", by="cli"))
    with sqlite3.connect(str(tmp_path / "m.db")) as conn:
        rows = conn.execute("SELECT entity_id, action, changes FROM audit_trail WHERE entity_type = 'memory_replaced'").fetchall()
    assert len(rows) == 1 and rows[0][0] == done["new_id"] and json.loads(rows[0][2])["old_id"] == old
    from rct_control_plane import audit_chain
    with sqlite3.connect(str(tmp_path / "m.db")) as conn:
        report = audit_chain.verify_audit_chain(conn)
    assert report.ok and report.chained_rows >= 2


def test_the_model_has_no_tool_that_replaces_a_memory():
    from rct_control_plane import mcp_server
    source = open(mcp_server.__file__, encoding="utf-8").read()
    assert "memory_replace" not in source and "replaces" not in source          # no tool reaches the replace function


# ---- hints: never an action -----------------------------------------------------------------------------------------------------------------------------------

def test_a_hint_names_the_memory_a_new_text_resembles_and_changes_nothing(mem):
    memory, persistence, _ = mem
    old = _store(memory, "The staging database host is stg-db-1")
    for i in range(8):
        _store(memory, f"Unrelated note {i}: the cafeteria menu rotates weekly and costs {40 + i} baht")
    before = len(persistence.list_memories(NS, include_revoked=True))
    hints = memory_replace.likely_replaced(persistence, NS, "The staging database host moved to stg-db-2")
    assert hints and hints[0]["id"] == old and hints[0]["change_announced"] is True
    assert memory_replace.likely_replaced(persistence, NS, "Buy a new keyboard for the front desk") == []
    assert len(persistence.list_memories(NS, include_revoked=True)) == before                       # a hint stores and retires nothing


# ---- the Desk API and the CLI ---------------------------------------------------------------------------------------------------------------------------------

class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "d.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    with TestClient(create_app()) as client:
        yield client, persistence


def test_the_desk_replaces_hints_and_reports_the_refusals(desk):
    client, persistence = desk
    first = client.post("/v1/desk/memories", json={"content": "The meeting room code is 4410", "namespace": "me"}).json()["memory_id"]
    hint = client.get("/v1/desk/memories/hints", params={"text": "The meeting room code changed to 7788", "namespace": "me"}).json()
    assert hint["hints"] and hint["hints"][0]["id"] == first
    assert client.post("/v1/desk/memories/replace", json={"namespace": "me", "memory_id": first}).status_code == 400
    assert client.post("/v1/desk/memories/replace", json={"namespace": "me", "memory_id": "mem_nope", "content": "x"}).status_code == 404
    done = client.post("/v1/desk/memories/replace", json={"namespace": "me", "memory_id": first, "content": "The meeting room code is 7788"})
    assert done.status_code == 200 and done.json()["old_id"] == first
    live = [m["content"] for m in client.get("/v1/desk/memories?namespace=me").json()["memories"]]
    assert live == ["The meeting room code is 7788"]
    assert client.post("/v1/desk/memories/replace", json={"namespace": "me", "memory_id": first, "content": "again"}).status_code == 404


def test_a_person_replaces_only_in_their_own_namespace_whatever_the_request_says(desk, tmp_path, monkeypatch):
    from rct_control_plane import api_auth, api_tokens
    client, persistence = desk
    tokens = tmp_path / "tokens.json"
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tokens))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    alice = api_tokens.create("alice", tokens)
    api_tokens.create("bob", tokens)
    mine = run(AgentMemory("alice", persistence).store("alice fact one", MemoryType.FACT))
    theirs = run(AgentMemory("bob", persistence).store("bob fact one", MemoryType.FACT))
    headers = {"Authorization": f"Bearer {alice}"}
    assert api_auth.person_route_allowed("POST", "/v1/desk/memories/replace") and api_auth.person_route_allowed("GET", "/v1/desk/memories/hints")
    assert not api_auth.person_route_allowed("POST", "/v1/desk/memories/pin")                                  # pinning stays the owner's
    refused = client.post("/v1/desk/memories/replace", headers=headers, json={"namespace": "bob", "memory_id": theirs, "content": "alice overwrites bob"})
    assert refused.status_code == 404                                                                       # the namespace is the token's, not the body's
    assert [m["content"] for m in persistence.list_memories("bob")] == ["bob fact one"]
    done = client.post("/v1/desk/memories/replace", headers=headers, json={"namespace": "bob", "memory_id": mine, "content": "alice fact two"})
    assert done.status_code == 200 and done.json()["namespace"] == "alice"
    assert [m["content"] for m in persistence.list_memories("alice")] == ["alice fact two"]
    hint = client.get("/v1/desk/memories/hints", headers=headers, params={"text": "alice fact three", "namespace": "bob"}).json()
    assert hint["namespace"] == "alice"


def test_the_cli_replaces_and_warns_before_storing_something_that_looks_like_an_update(mem, tmp_path, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    memory, persistence, _ = mem
    db = str(tmp_path / "m.db")
    runner = CliRunner()
    added = runner.invoke(cli, ["memory", "add", "The staging database host is stg-db-1", "--namespace", NS, "--db", db])
    assert added.exit_code == 0 and "may replace" not in added.output
    old = added.output.split()[1]
    again = runner.invoke(cli, ["memory", "add", "The staging database host moved to stg-db-2", "--namespace", NS, "--db", db])
    assert again.exit_code == 0 and "this may replace " + old in again.output and "delentia memory replace" in again.output
    new_id = again.output.split()[1]
    replaced = runner.invoke(cli, ["memory", "replace", old, "The staging database host is stg-db-2", "--namespace", NS, "--db", db])
    assert replaced.exit_code == 0 and f"{old} replaced by " in replaced.output
    live = {m["id"] for m in persistence.list_memories(NS)}
    assert old not in live and new_id in live                                                           # the hinted store and the replacement are separate memories; the person decides
    bad = runner.invoke(cli, ["memory", "replace", "mem_missing", "x", "--namespace", NS, "--db", db])
    assert bad.exit_code == 1 and "no live memory" in bad.output
