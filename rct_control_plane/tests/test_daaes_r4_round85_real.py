"""
Round 85, the code that measures TC-025 R4 (a live rerun varies; it is never required to be identical). The measurement code is tested with a scripted provider that varies on purpose; the real measurement with a
local model is a separate run that this test does not pretend to be.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from typing import List, Optional

import pytest

from research.daaes import r4


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")


def provider_with(variant: str):
    from rct_control_plane.llm_provider import LLMProvider
    replies: List[str] = {
        "steady": [json.dumps({"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "project/pyproject.toml"}, "reasoning": "read it"}),
                   json.dumps({"action": "finish", "reasoning": "done", "final_answer": "The project is ledgercalc, version 0.3.1."})],
        "wanders": [json.dumps({"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "project/README.md"}, "reasoning": "read the readme first"}),
                    json.dumps({"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "project/pyproject.toml"}, "reasoning": "then the file"}),
                    json.dumps({"action": "finish", "reasoning": "done", "final_answer": "ledgercalc 0.3.1"})],
        "wrong": [json.dumps({"action": "finish", "reasoning": "guess", "final_answer": "I think it is called ledger-tool, version 1.0."})],
    }[variant]

    class Scripted(LLMProvider):
        model = "scripted/variant"

        def __init__(self) -> None:
            self.queue = list(replies)

        async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
            return self.queue.pop(0)
    return Scripted()


def test_normalise_and_correctness_read_the_fixtures_own_numbers():
    assert r4.normalise("  The Project IS ledgercalc!!  v0.3.1 ") == "the project is ledgercalc v0.3.1"
    assert r4.correct("It is ledgercalc, version 0.3.1") and not r4.correct("ledgercalc, version 0.3.2") and not r4.correct(None)


def test_a_model_that_varies_is_reported_as_varying_with_intervals_and_never_as_identical(tmp_path):
    plan = ["steady", "steady", "steady", "wanders", "wrong"]
    result = r4.run(len(plan), lambda i: provider_with(plan[i - 1]), tmp_path)
    s = result["summary"]
    assert s["runs"] == 5 and s["distinct_sequences"] == 3 and s["sequence_stability"]["k"] == 3
    assert s["distinct_answers"] == 3 and s["answer_stability"]["k"] == 3
    assert s["correct"]["k"] == 4, "the wrong guess is the one the oracle rejects; the wandering run is still correct"
    low, high = s["correct"]["ci95"]
    assert 0.2 < low < 0.5 and 0.9 < high < 1.0, "five runs give a wide interval, not a measurement"
    assert s["stopped_reasons"] == {"llm_finished": 5}
    text = r4.render(result, "scripted/variant")
    assert "Not required to be identical" in text and "95% exact" in text and "wanders" not in text


def test_a_perfectly_steady_scripted_model_is_stable_in_every_measure(tmp_path):
    result = r4.run(3, lambda i: provider_with("steady"), tmp_path)
    s = result["summary"]
    assert s["sequence_stability"]["rate"] == 1.0 and s["answer_stability"]["rate"] == 1.0 and s["correct"]["rate"] == 1.0 and s["distinct_sequences"] == 1
    assert all(r["sequence"] == ["delentia_read_repo_file"] for r in result["rows"])
