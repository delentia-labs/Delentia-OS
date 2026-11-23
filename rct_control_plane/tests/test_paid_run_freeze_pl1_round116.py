"""Round 116: the freeze knows the stages of Launch Proof Level 1, and each ceiling is the key limit the criteria's budget table names (option A for U1)."""
from __future__ import annotations

import re
from pathlib import Path

from research import paid_run_freeze

CRITERIA = Path(__file__).resolve().parents[2] / "research" / "LAUNCH_PL1_CRITERIA_R116.md"


def table_limits():
    """The key-limit column of the budget table, by stage, read from the criteria file itself so the two cannot drift apart."""
    limits = {}
    for line in CRITERIA.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and re.match(r"^(U0|U1|U2|R1|S1)\b", cells[0]):
            limits[cells[0]] = cells[2]
    return limits


def test_every_pl1_stage_ceiling_is_the_key_limit_of_the_criteria():
    t = table_limits()
    assert t["U0"] == "0.50" and paid_run_freeze.stage_ceiling("U0") == 0.50
    assert t["U1 haiku, option A / B"].split("/")[0].strip() == "3.20" and paid_run_freeze.stage_ceiling("U1") == 3.20, "U1 is option A (decision D-U)"
    assert t["U2 kimi probe"] == "0.40" and paid_run_freeze.stage_ceiling("U2-probe") == 0.40
    assert t["R1"] == "0.20" and paid_run_freeze.stage_ceiling("R1") == 0.20
    assert t["S1 haiku + kimi"].startswith("1.20") and paid_run_freeze.stage_ceiling("S1") == 1.20


def test_u2_itself_has_no_ceiling_until_the_probe_sets_one():
    assert paid_run_freeze.stage_ceiling("U2") is None


def test_the_freeze_accepts_u0_and_still_refuses_an_unknown_stage(monkeypatch):
    monkeypatch.setattr(paid_run_freeze, "code_state", lambda: {"sha": "0" * 40, "dirty": False})
    prices = {"anthropic/claude-haiku-5.5": {"in": 0.1, "out": 0.5}}
    ok = paid_run_freeze.problems_before_freezing(["anthropic/claude-haiku-5.5"], prices, ["U0"], 0.50, True)
    assert ok == []
    bad = paid_run_freeze.problems_before_freezing(["anthropic/claude-haiku-5.5"], prices, ["U9"], 0.50, True)
    assert any("stage U9 has no ceiling" in p for p in bad)
    over = paid_run_freeze.problems_before_freezing(["anthropic/claude-haiku-5.5"], prices, ["U0"], 0.40, True)
    assert any("add up to" in p for p in over), "a key limit below the stage ceiling is refused"
