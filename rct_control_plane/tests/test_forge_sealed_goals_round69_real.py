"""
Round 69: with a person's words sealed (Round 68), the Tool Forge still finds repeated unmet goals - it reads the goal back from the sealed field of the run - and an erased person's goals stop being evidence.
Round 68 named experiments by a hash of the goal and the forge lost the words of the goals (harness case C20 failed; nothing asserted it).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest

from rct_control_plane import audit_text, memory_erasure, tool_forge
from rct_control_plane.persistence import ControlPlanePersistence

GOAL = "Convert the quarterly invoice export into a Thai tax summary table"


@pytest.fixture
def persistence(tmp_path, monkeypatch):
    monkeypatch.setenv(memory_erasure.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.delenv(audit_text.MODE_ENV, raising=False)
    return ControlPlanePersistence(db_path=str(tmp_path / "p.db"))


def record(p, namespace, goal, run, sealed=True):
    experiment_id = f"exp-{abs(hash(goal)) % 10**8}"
    p.save_experiment(experiment_id, name=audit_text.experiment_label(goal), description="x")
    state = {"namespace": namespace, "jitna_verified": True}
    if sealed and audit_text.sealing_on():
        state["goal"] = audit_text.protect(namespace, {"goal": goal}, ("goal",))["goal"]
    p.save_experiment_run(f"run-{run}", experiment_id, algorithm_id="governed_loop/test", metrics={"finished": 1, "aligned_with_intent": 0, "warm_recall": 0}, jitna_state=state)


def test_the_experiment_name_is_a_hash_and_the_words_are_in_the_sealed_field(persistence):
    record(persistence, "alice", GOAL, 1)
    with persistence._connect() as conn:
        name, state = conn.execute("SELECT e.name, r.jitna_state FROM experiment_runs r JOIN experiments e ON e.id = r.experiment_id").fetchone()
    assert name.startswith("goal sha256:") and "invoice" not in name and "invoice" not in state
    assert audit_text.is_sealed_value(json.loads(state)["goal"])


def test_the_forge_reads_a_sealed_goal_back_and_groups_repeats_across_people(persistence):
    for i, who in enumerate(("alice", "bob", "carol")):
        record(persistence, who, GOAL, i)
    gaps = tool_forge.find_gaps(persistence, min_count=2)
    assert len(gaps) == 1 and gaps[0]["goals"] == [GOAL] and gaps[0]["count"] == 3 and gaps[0]["users"] == 3
    assert "invoice" in gaps[0]["keywords"] and "quarterly" in gaps[0]["keywords"]


def test_an_erased_person_no_longer_counts_as_evidence(persistence):
    for i, who in enumerate(("alice", "bob", "carol")):
        record(persistence, who, GOAL, i)
    assert memory_erasure._destroy_key("alice") is True
    gaps = tool_forge.find_gaps(persistence, min_count=2)
    assert len(gaps) == 1 and gaps[0]["count"] == 2 and gaps[0]["users"] == 2
    memory_erasure._destroy_key("bob")
    assert tool_forge.find_gaps(persistence, min_count=2) == []                        # one person left: not a repeated gap


def test_with_sealing_off_the_old_behaviour_is_unchanged(persistence, monkeypatch):
    monkeypatch.setenv(audit_text.MODE_ENV, "plain")
    for i, who in enumerate(("alice", "bob")):
        record(persistence, who, GOAL, i)
    gaps = tool_forge.find_gaps(persistence, min_count=2)
    assert len(gaps) == 1 and gaps[0]["goals"] == [GOAL]
