"""Round 92: found by trying the Desk GUI against a throw-away backend (scripts/gui_test_rig_r92.py).

A first write on a fresh install is stopped by the FDIA gate (D is measured from the person's own data and there is none yet). The API already said what was missing
(`missing_data`), but the Desk's chat step event dropped it, so the person saw "F 0.47 is below 0.5" and no way to fix it. The event now carries the list.
"""
from types import SimpleNamespace

from rct_control_plane.desk_agent_stream import step_payload


def _step(result):
    return SimpleNamespace(tool_name="delentia_write_repo_file", tool_args={"relative_path": "notes/hello.md"}, tool_result=result,
                           llm_reasoning="write", iteration=1)


def test_blocked_step_carries_what_data_is_missing():
    payload = step_payload(_step({"fdia_blocked": True, "F": 0.4681, "reason": "F = 0.4681 is below the FDIA threshold 0.5",
                                  "missing_data": ["no stored memory relevant to this goal (store facts about it with delentia_remember)",
                                                   "no verified track record yet for this goal"]}))
    assert payload["kind"] == "blocked"
    assert payload["F"] == 0.4681
    assert payload["missing_data"] == ["no stored memory relevant to this goal (store facts about it with delentia_remember)",
                                       "no verified track record yet for this goal"]


def test_blocked_step_without_missing_data_gives_an_empty_list_not_none():
    payload = step_payload(_step({"fdia_blocked": True, "F": 0.2, "reason": "below threshold"}))
    assert payload["kind"] == "blocked"
    assert payload["missing_data"] == []


def test_other_steps_are_unchanged():
    payload = step_payload(_step({"pending_approval": True, "reason": "R-WRITE-FILES: needs 1 human signature(s)"}))
    assert payload["kind"] == "pending"
    assert "missing_data" not in payload
