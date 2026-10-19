"""
Round 90: the readiness snapshot (scripts/readiness_snapshot.py) is generated from facts and must stay consistent with the documents it summarises: the checkpoint in TESTING_CANONICAL.md,
the gate table in RELEASE_LEVELS.md and the number of agent tools. A stale snapshot fails this test, so the status cannot drift silently again (the 7,109 figure stayed in five documents
for a week after the suite grew to 7,820).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import json

import readiness_snapshot as rs


def test_the_committed_snapshot_agrees_with_the_documents():
    assert rs.check() == 0


def test_the_snapshot_reads_the_gates_and_never_invents_one_as_met():
    gates = rs.gate_facts()["gates"]
    assert len(gates) >= 12
    by_name = {g["gate"]: g for g in gates}
    assert by_name["G-model"]["status_word"] == "not met"                        # nothing here may turn a gate green by itself
    assert by_name["G-tests"]["status_word"] == "met"
    assert all(g["status_text"] for g in gates)


def test_the_offline_build_renders_and_says_where_it_came_from(tmp_path, monkeypatch):
    snap = rs.build(offline=True)
    text = rs.render(snap)
    assert "Do not edit by hand" in text and "Readiness snapshot" in text
    assert snap["latest_completed_ci_on_main"] is None and snap["offline"] is True
    assert snap["master_workflows"]["live_result_with_a_capable_model"] == 0       # no workflow has a live result with a capable model (a fact the snapshot repeats, never improves)
    assert snap["tools"]["unclassified_for_taint"] == []
    json.dumps(snap)                                                               # serialisable
