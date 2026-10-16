"""
Round 83, DAAES M0: the reference primitives of the supplied DAAES v0.1 package keep working inside Delentia's repository, and the durable run log + replay engine (research/daaes/events.py)
detect every tamper the specification lists (mutate, delete, reorder, duplicate, corrupt a hash, replace a snapshot), survive a torn write, redact secrets BEFORE they are logged, and replay
without any external call.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from copy import deepcopy

import pytest

from research.daaes import events as ev
from research.daaes.core import EventLog, IdempotentAPI, apply_event, canonical, digest, intent_violations, replay


# ---- the five tests of the supplied package, unchanged in meaning
def test_supplied_replay_matches_reference():
    log = EventLog(); log.append("state.delta", {"action": "set", "key": "x", "value": 3}); log.append("state.delta", {"action": "delete", "key": "y"})
    assert replay({"x": 1, "y": 9}, log.events) == {"x": 3}


def test_supplied_mutation_detected():
    log = EventLog(); log.append("state.delta", {"action": "set", "key": "x", "value": 3})
    forged = deepcopy(log.events); forged[0]["payload"]["value"] = 4
    with pytest.raises(ValueError):
        replay({}, forged)


def test_supplied_missing_event_detected():
    log = EventLog(); log.append("state.delta", {"action": "set", "key": "x", "value": 1}); log.append("state.delta", {"action": "set", "key": "x", "value": 2})
    with pytest.raises(ValueError):
        replay({}, log.events[1:])


def test_supplied_idempotent_commit():
    api = IdempotentAPI(); a = api.commit("k", {"cost": 2}); b = api.commit("k", {"cost": 2})
    assert a == b and len(api.committed) == 1
    with pytest.raises(ValueError):
        api.commit("k", {"cost": 3})


def test_supplied_intent_violation():
    initial = {"goal": "fix", "protected_constraints": ["no deletion"], "forbidden_actions": ["delete_production"]}
    final = {"goal": "fix", "protected_constraints": ["no deletion"]}
    assert intent_violations(initial, final, []) == [] and intent_violations(initial, final, [{"type": "delete_production"}])


# ---- the additions
def test_canonical_form_is_the_same_for_equal_values_written_differently():
    assert digest({"a": 1.0, "b": "é"}) == digest({"b": "é", "a": 1})              # integral float = int, NFC composed = decomposed
    assert digest({"a": -0.0}) == digest({"a": 0})
    with pytest.raises(ValueError):
        canonical({"a": float("nan")})


def test_event_log_says_which_link_broke():
    log = EventLog()
    for i in range(4):
        log.append("state.delta", {"action": "set", "key": "k", "value": i})
    assert log.verify_report()["ok"]
    mutated = deepcopy(log); mutated.events[1]["payload"]["value"] = 99
    assert mutated.verify_report() == {"ok": False, "at": 2, "reason": "bad_hash"}
    dropped = deepcopy(log); del dropped.events[1]
    assert dropped.verify_report()["reason"] == "bad_sequence"


def make_run(tmp_path, n=6):
    log = ev.RunLog(tmp_path / "events.jsonl", "run_1")
    log.emit("run.started", {"manifest": "m"}, intent_id="INT-1")
    for i in range(n):
        req = log.emit("tool.requested", {"tool": "mock_api", "input": {"operation_id": f"op-{i}", "n": i}}, intent_id="INT-1")
        out = {"status": "committed", "operation_id": f"op-{i}"}
        log.emit("tool.completed", {"output": out, "output_hash": digest(out)}, causation_id=req["event_id"], intent_id="INT-1")
    log.emit("run.completed", {"result": "ok"})
    return log


def test_a_run_log_is_durable_chained_and_verifies(tmp_path):
    log = make_run(tmp_path)
    loaded = ev.load(tmp_path / "events.jsonl")
    assert len(loaded) == len(log.events) == 14 and ev.verify(loaded)["ok"]
    assert loaded[2]["causation_id"] == loaded[1]["event_id"] and loaded[0]["prev_event_hash"] == "GENESIS"


@pytest.mark.parametrize("how", ["mutate_payload", "delete_event", "reorder_events", "duplicate_event", "corrupt_hash"])
def test_every_listed_tamper_is_detected(tmp_path, how):
    events = ev.load(make_run(tmp_path).path)
    damaged = ev.tamper(events, how, index=3)
    assert ev.verify(damaged)["ok"] is False


def test_a_replaced_snapshot_is_detected(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "r")
    log.emit("run.started", {})
    log.emit("checkpoint.committed", {"version": 1, "state": {"a": 1}, "state_hash": digest({"a": 1})})
    log.emit("run.completed", {})
    assert ev.verify(ev.tamper(log.events, "replace_snapshot"))["reason"] == "payload_altered"


def test_a_torn_last_line_is_not_acknowledged_and_is_reported(tmp_path):
    log = make_run(tmp_path, n=2)
    with open(log.path, "ab") as f:
        f.write(b'{"run_id":"run_1","sequence":99,"kind":"tool.requ')               # the process died in the middle of a write
    assert ev.torn_tail(log.path) is True
    assert ev.verify(ev.load(log.path))["ok"] is True and len(ev.load(log.path)) == len(log.events)


def test_secrets_are_redacted_before_they_are_logged(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "r")
    log.emit("tool.requested", {"tool": "x", "input": {"api_key": "sk-abcdefghijklmnop1234", "note": "token sk-abcdefghijklmnopqrstuv inside"}})
    raw = (tmp_path / "e.jsonl").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in raw and "[redacted]" in raw


def test_an_unknown_event_kind_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ev.RunLog(tmp_path / "e.jsonl", "r").emit("made.up", {})


def test_a_reopened_log_continues_the_chain(tmp_path):
    first = make_run(tmp_path, n=1)
    again = ev.RunLog(first.path, "run_1")
    again.emit("process.resumed", {"checkpoint": "c"})
    assert ev.verify(ev.load(first.path))["ok"] and len(ev.load(first.path)) == len(first.events) + 1


def test_an_external_anchor_catches_a_whole_log_rewrite_the_chain_alone_cannot(tmp_path):
    log = make_run(tmp_path)
    anchor = tmp_path / "outside" / "anchor.json"
    ev.anchor_head(log.events, tmp_path / "outside" / "key.pem", anchor)
    assert ev.verify_anchor(log.events, anchor)["ok"]
    forged = ev.RunLog(tmp_path / "forged.jsonl", "run_1")                              # an attacker builds a new, internally consistent log
    forged.emit("run.started", {"manifest": "other"})
    for i in range(13):
        forged.emit("tool.requested", {"tool": "mock_api", "input": {"operation_id": f"evil-{i}"}})
    assert ev.verify(forged.events)["ok"] is True                                         # the chain alone is fooled ...
    assert ev.verify_anchor(forged.events, anchor)["ok"] is False                          # ... the signed anchor is not
    assert "shorter" in ev.verify_anchor(log.events[:5], anchor)["reason"]


def test_r1_state_replay_equals_the_reference_and_refuses_a_damaged_chain(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "r")
    state = {"a": 1}
    for i, d in enumerate([{"action": "set", "key": "a", "value": 2}, {"action": "set", "key": "b", "value": 3}, {"action": "delete", "key": "a"}]):
        log.emit("memory.delta_committed", {"delta": d}, state_version_before=i, state_version_after=i + 1)
    assert ev.replay_r1(state, log.events, apply_event) == {"b": 3}
    with pytest.raises(ValueError):
        ev.replay_r1(state, ev.tamper(log.events, "delete_event", 1), apply_event)


def test_r2_tool_replay_uses_only_recorded_outputs_and_calls_nothing_outside(tmp_path):
    events = make_run(tmp_path, n=3).events
    outside = ev.NoExternalCalls()
    report = ev.replay_r2(events, outside)
    assert report["ok"] and report["external_attempts"] == 0 and sorted(report["committed_operations"]) == ["op-0", "op-1", "op-2"]
    forged = deepcopy(events); forged[2]["payload"]["output"]["status"] = "failed"
    assert ev.replay_r2(forged)["ok"] is False                                              # a recorded output that no longer matches its hash


def test_r3_decision_replay_reproduces_verdicts_and_notices_an_edited_one(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "r")
    for tool, verdict in (("read", "allow"), ("write", "ask"), ("rm", "deny")):
        p = log.emit("decision.proposed", {"tool": tool})
        log.emit("decision.authorized", {"verdict": verdict}, causation_id=p["event_id"])
    policy = lambda proposal: {"read": "allow", "write": "ask"}.get(proposal["tool"], "deny")           # noqa: E731
    assert ev.replay_r3(log.events, policy) == {"ok": True, "checked": 3, "mismatches": []}
    loosened = lambda proposal: "allow"                                                                  # noqa: E731
    assert ev.replay_r3(log.events, loosened)["ok"] is False
