"""
Round 82, finding N6: the warm-recall replay goes through the gate like any other tool call.

Warm recall (opt-in) answers a goal it answered before, without a model call, after replaying the read-only calls that answer rested on and comparing their results by hash. That replay called
the tool server DIRECTLY: no owner policy, no denied-path check, no pause. So an owner who forbade reading a folder after the answer was stored still had the old answer served, and the
file was read again behind the policy's back. Found by reading `_warm_lookup`; reproduced here first (these tests fail on the previous code), fixed by sending every replayed call through
`_pre_dispatch_gate` with the CURRENT policy. A refusal is a cache miss: the episode runs normally, and is judged normally.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import approvals, envelope
from test_warm_recall_round51_real import GOAL, World, _loop, kernel, model  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in (envelope.PAUSED_ENV, approvals.APPROVERS_ENV, "DELENTIA_FDIA_POLICY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_ENVELOPE_PAUSE_FILE", str(tmp_path / "pause"))
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")


def forbid_reading(tmp_path, monkeypatch, pattern):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"version": "1.0.0", "policy_id": "n6", "default_fallback_A": 1, "rules": [
        {"rule_id": "R-NO-READ", "intent_patterns": ["read_repo_file"], "action_type": "CONDITIONAL", "assigned_A": 1, "denied_paths": [pattern]}]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(policy))


def test_a_path_the_owner_forbids_after_the_answer_was_stored_is_not_replayed(tmp_path, kernel, model, monkeypatch):  # noqa: F811
    world = World()
    cold = asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    assert cold["stopped_reason"] == "llm_finished"
    forbid_reading(tmp_path, monkeypatch, "pyproject.toml")                       # the owner changes their mind
    reads_before = [c for c in world.calls if c[0] == "delentia_read_repo_file"]
    model["i"] = 0
    again = asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    assert again["stopped_reason"] != "warm_recall"                               # the stored answer is not served ...
    assert (again.get("warm_recall") or {}).get("hit") is not True
    reads_after = [c for c in world.calls if c[0] == "delentia_read_repo_file"]
    assert len(reads_after) == len(reads_before), "the forbidden file was read again by the replay"      # ... and the file was not touched behind the policy's back


def test_a_pause_stops_the_replay_too(tmp_path, kernel, model, monkeypatch):  # noqa: F811
    world = World()
    asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    reads_before = len(world.calls)
    envelope.pause("maintenance", by="owner")
    model["i"] = 0
    again = asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    assert again["stopped_reason"] != "warm_recall"
    assert len(world.calls) == reads_before


def test_with_nothing_forbidden_the_replay_still_hits(tmp_path, kernel, model, monkeypatch):  # noqa: F811
    world = World()
    asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    warm = asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    assert warm["stopped_reason"] == "warm_recall" and warm["warm_recall"]["hit"] is True


def test_the_replay_leaves_a_gate_row_in_the_audit_trail(tmp_path, kernel, model, monkeypatch):  # noqa: F811
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"version": "1.0.0", "policy_id": "n6-allow", "default_fallback_A": 1, "rules": [
        {"rule_id": "R-READ", "intent_patterns": ["read_repo_file"], "action_type": "ALLOW", "assigned_A": 1}]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(policy))
    world = World()
    loop = _loop(tmp_path, kernel, world)
    asyncio.run(loop.run(GOAL))
    with loop._persistence._connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'").fetchone()[0]
    warm = asyncio.run(_loop(tmp_path, kernel, world).run(GOAL))
    assert warm["stopped_reason"] == "warm_recall"
    with loop._persistence._connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'").fetchone()[0]
    assert after > before                                                          # the replayed read was judged by the gate and left its row
