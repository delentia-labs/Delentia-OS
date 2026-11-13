"""
Round 113: the workflow screen WS-1 (research/WORKFLOW_SCREEN_CRITERIA_R113.md) has its own stage ceiling PW in the freeze tool, kept apart from the table of the day of 2026-11-12 (whose sum is pinned elsewhere).
These tests pin: PW is accepted with a budget that covers it and refused below it, an unknown stage is still refused, the old table did not move, and the criteria file says what the code enforces.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research import paid_run_freeze as pf  # noqa: E402

PRICES = {"anthropic/claude-haiku-5.5": {"in": 0.1, "out": 0.5}}
MODELS = ["anthropic/claude-haiku-5.5"]


def clean_tree(monkeypatch):
    monkeypatch.setattr(pf, "code_state", lambda: {"sha": "abc1234", "branch": "main", "dirty": False})


def test_the_workflow_stage_is_accepted_with_a_budget_that_covers_it(monkeypatch):
    clean_tree(monkeypatch)
    assert pf.problems_before_freezing(MODELS, PRICES, ["PW"], 3.0, True) == []
    assert pf.stage_ceiling("PW") == 3.00


def test_the_workflow_stage_is_refused_when_the_budget_is_below_its_ceiling(monkeypatch):
    clean_tree(monkeypatch)
    problems = pf.problems_before_freezing(MODELS, PRICES, ["PW"], 2.5, True)
    assert problems and "more than the budget" in problems[0]


def test_an_unknown_stage_is_still_refused_and_the_message_names_the_known_ones(monkeypatch):
    clean_tree(monkeypatch)
    problems = pf.problems_before_freezing(MODELS, PRICES, ["PX"], 3.0, True)
    assert problems and "no ceiling" in problems[0] and "PW" in problems[0] and "P4" in problems[0]


def test_the_table_of_the_paid_day_did_not_move():
    assert pf.STAGE_CEILINGS_USD == {"P0": 0.10, "P1": 5.00, "P1b": 1.50, "P2": 1.50, "P4": 4.00, "PR": 0.75}
    assert round(sum(pf.STAGE_CEILINGS_USD.values()), 2) == 12.85
    assert "PW" not in pf.STAGE_CEILINGS_USD


def test_the_criteria_file_states_what_the_code_enforces():
    text = (ROOT / "research" / "WORKFLOW_SCREEN_CRITERIA_R113.md").read_text(encoding="utf-8")
    assert "**$3.00**" in text and "anthropic/claude-haiku-5.5" in text and "--stages PW" in text
    for w in ("W03", "W06", "W08", "W09", "W10", "W12"):
        assert w in text
    assert "Not allowed" in text or "**Not allowed:**" in text
    assert "written on 2026-11-13, BEFORE any run" in text


def test_every_workflow_the_screen_names_has_a_live_runner():
    from research import live_workflows
    for w in ("W03", "W06", "W08", "W09", "W10", "W12"):
        assert w in live_workflows.RUNNERS
