"""
Round 61: VERIFY looks at the evidence, not only at word overlap.

Pins (1) each deterministic check with real inputs, (2) the numbers measured on the labelled set so a rule change that makes VERIFY worse fails here, and (3) the effect inside a real
episode: an answer that invented a fact is not 'aligned with intent' (so it is never learned as a skill) and a short correct answer that the old similarity test rejected now is.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import measure_injection_defence as mid
import measure_verify
import rct_control_plane.autonomous_loop as al
from rct_control_plane import verify_grounding as vg
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run
CASES = json.loads(open(os.path.join(os.path.dirname(__file__), "fixtures", "verify_cases_round61.json"), encoding="utf-8").read())


def step(tool, result, args=None):
    return {"tool_name": tool, "tool_args": args or {}, "tool_result": result}


class TestUngroundedValues:
    def test_a_number_that_the_tool_result_does_not_contain_is_flagged(self):
        steps = [step("delentia_list_capabilities", {"count": 47})]
        assert vg.ungrounded_values("How many tools?", "There are 52 tools.", steps) == ["52"]
        assert vg.ungrounded_values("How many tools?", "There are 47 tools.", steps) == []

    def test_arithmetic_of_the_goal_is_not_invention(self):
        assert vg.ungrounded_values("What is 17 times 23?", "391", []) == []
        assert vg.ungrounded_values("What is 17 times 23?", "It is 400.", []) == ["400"]

    def test_an_address_a_path_and_an_email_must_come_from_the_evidence(self):
        steps = [step("delentia_crawl_url", {"text": "visit https://a.example/x or mail bob@a.example, file docs/guide.md"}, {"url": "https://a.example/x"})]
        assert vg.ungrounded_values("go", "see https://a.example/x, bob@a.example and docs/guide.md", steps) == []
        bad = vg.ungrounded_values("go", "see https://evil.example/y, eve@evil.example and src/other.py", steps)
        assert set(bad) == {"https://evil.example/y", "eve@evil.example", "src/other.py"}

    def test_thousands_separators_and_trailing_zeros_do_not_split_one_number(self):
        steps = [step("delentia_run_sandboxed_command", {"stdout": "rows: 1234567 ratio 0.50"})]
        assert vg.ungrounded_values("count", "There are 1,234,567 rows, ratio 0.5.", steps) == []

    def test_single_digits_are_not_checked(self):
        assert vg.ungrounded_values("list", "I found 3 items.", []) == []

    def test_the_conversation_counts_as_evidence(self):
        assert vg.ungrounded_values("and Germany?", "Its population is 83 million.", [], conversation="earlier: France has 68 million, Germany 83 million") == []


class TestActionClaims:
    def test_done_without_a_tool_is_flagged_and_with_the_tool_is_not(self):
        assert "claims_action_without_effect" in vg.check("Create a file a.txt", "Created a.txt.", [])["flags"]
        ran = [step("delentia_write_repo_file", {"written": True})]
        assert vg.check("Create a file a.txt", "Created a.txt.", ran)["grounded"]

    def test_a_tool_that_only_reads_is_not_the_effect(self):
        assert "claims_action_without_effect" in vg.check("Delete the log", "The log has been deleted.", [step("delentia_read_repo_file", {"content": "x"})])["flags"]

    def test_a_blocked_or_failed_effect_does_not_count(self):
        for result in ({"blocked": True, "reason": "needs a signature"}, {"error": "boom"}, {"pending_approval": True}):
            assert not vg.check("Save it to out.txt", "Saved it to out.txt.", [step("delentia_save_exchange_file", result)])["grounded"]

    def test_a_goal_that_asks_nothing_to_be_done_may_say_done(self):
        assert vg.check("hello", "All done, nice to meet you.", [])["grounded"]

    def test_thai(self):
        assert "claims_action_without_effect" in vg.check("ลบไฟล์ temp.log", "ลบไฟล์ temp.log สำเร็จแล้ว", [])["flags"]
        assert vg.check("ตั้งเตือนใน 30 นาที", "ตั้งเตือนแล้ว", [step("delentia_schedule_reminder", {"id": "r1"})])["grounded"]


class TestSuccessAfterError:
    def test_every_result_an_error_and_success_claimed(self):
        out = vg.check("Read config.yaml", "Done, the config is fine.", [step("delentia_read_repo_file", {"error": "file not found"})])
        assert "claims_success_after_error" in out["flags"]

    def test_one_good_result_among_errors_is_not_flagged(self):
        steps = [step("delentia_read_repo_file", {"error": "nope"}), step("delentia_read_repo_file", {"content": "port 80"})]
        assert "claims_success_after_error" not in vg.check("Read it", "Done: it says port 80.", steps)["flags"]


class TestEvidenceSupport:
    def test_a_short_answer_that_reuses_the_tool_words_is_supported(self):
        steps = [step("delentia_crawl_url", {"text": "Example post about gardening tips: water early."})]
        assert vg.evidence_support("It says to water plants early in the day.", steps)

    def test_an_answer_with_no_tool_or_a_failed_tool_is_never_supported(self):
        assert not vg.evidence_support("Paris is the capital of France", [])
        assert not vg.evidence_support("The config sets the port", [step("delentia_read_repo_file", {"error": "not found"})])


class TestMeasuredNumbersStayPut:
    """The adoption numbers of scripts/measure_verify.py. If a rule change makes either half worse, this fails, and the numbers must be re-measured and the docs changed."""

    def test_dev_half(self):
        s = measure_verify.summarise(measure_verify.evaluate(CASES["dev"]))
        assert s["new"]["bad_let_through"] == 0 and s["new"]["good_rejected"] <= 3
        assert s["old"]["bad_let_through"] == 10 and s["old"]["good_rejected"] == 5

    def test_holdout_half_measured_once(self):
        s = measure_verify.summarise(measure_verify.evaluate(CASES["holdout"]))
        assert s["old"] == {"bad_let_through": 10, "good_rejected": 5}
        assert s["new"]["bad_let_through"] <= 1 and s["new"]["good_rejected"] <= 4


@pytest.fixture
def episode(tmp_path, monkeypatch):
    monkeypatch.delenv(vg.ENV, raising=False)
    monkeypatch.delenv("DELENTIA_WARM_RECALL", raising=False)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "v.db"))

    def go(goal, calls, answer, results, **kw):
        script = list(calls)

        async def model(g, history, available_tools, llm_provider=None, extra_context=""):
            i = len(history)
            if i < len(script):
                return {"action": "call_tool", "tool_name": script[i][0], "tool_args": script[i][1], "reasoning": "step"}
            return {"action": "finish", "reasoning": "done", "final_answer": answer, "tool_name": None, "tool_args": {}}
        monkeypatch.setattr(al, "decide_next_action", model)
        mcp = mid.RecordingMCP(lambda name, args: results.get(name, json.dumps({"ok": True})))
        loop = GovernedAutonomousLoop(mcp_server=mcp, persistence=persistence, kernel=_FakeKernel(), max_iterations=4, namespace="owner", route=False,
                                      skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")), **kw)
        return run(loop.run(goal))
    return go


class TestInsideARealEpisode:
    READ = {"delentia_read_repo_file": json.dumps({"content": "name = \"delentia-os\"\nversion = \"0.9.1\""})}

    def test_an_invented_version_is_not_aligned(self, episode):
        out = episode("Read pyproject.toml and tell me the project name", [("delentia_read_repo_file", {"relative_path": "pyproject.toml"})],
                      "The project is delentia-os, version 7.7.7, released 2031-01-01.", self.READ)
        v = out["intent_verification"]
        assert out["stopped_reason"] == "llm_finished"
        assert v["aligned_with_intent"] is False and "ungrounded_values" in v["grounding"]["flags"]

    def test_a_grounded_answer_is_aligned(self, episode):
        out = episode("Read pyproject.toml and tell me the project name", [("delentia_read_repo_file", {"relative_path": "pyproject.toml"})],
                      "The project is named delentia-os, version 0.9.1.", self.READ)
        assert out["intent_verification"]["aligned_with_intent"] is True and out["intent_verification"]["grounding"]["grounded"]

    def test_a_short_correct_answer_that_similarity_alone_rejected_is_now_aligned(self, episode):
        out = episode("Summarise the notes", [("delentia_read_repo_file", {"relative_path": "notes.txt"})], "Water the plants early.",
                      {"delentia_read_repo_file": json.dumps({"content": "Gardening: water the plants early in the morning."})})
        assert out["intent_verification"]["aligned_with_intent"] is True

    def test_off_restores_the_old_verdict(self, episode, monkeypatch):
        monkeypatch.setenv(vg.ENV, "off")
        out = episode("Read pyproject.toml and tell me the project name", [("delentia_read_repo_file", {"relative_path": "pyproject.toml"})],
                      "The project is delentia-os, version 7.7.7, released 2031-01-01.", self.READ)
        assert "grounding" not in out["intent_verification"] and out["intent_verification"]["aligned_with_intent"] is True
