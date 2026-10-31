"""
Round 106: stage P0 of the paid plan - the meter is compared with the provider's own figure before anything is trusted. Run here against the fake OpenRouter
(no key, no money): an honest provider passes; a provider that bills more than its replies show FAILS (the case this stage exists to catch); a usage figure that is
still moving or did not move is inconclusive; and every way of spending by accident is refused first.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import calibrate_meter_p0 as p0  # noqa: E402
import fake_openrouter  # noqa: E402

PRICE = {"in": 0.2, "out": 0.8}
MODEL = "cal/model"


def run_against(fake, tmp_path, monkeypatch, extra=()):
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", fake.base_url)
    out = tmp_path / "p0.json"
    code = p0.main([MODEL, "--price-in", "0.2", "--price-out", "0.8", "--calls", "22", "--prompt-tokens", "400", "--wait", "0", "--json", str(out), *extra],
                   env={"OPENROUTER_API_KEY": fake.key, "DELENTIA_RUN_LIVE_TESTS": "1"}, sleep=lambda s: None)
    return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else None


def test_an_honest_provider_passes_and_the_report_says_where_the_cost_came_from(tmp_path, monkeypatch):
    with fake_openrouter.FakeOpenRouter({MODEL: PRICE}) as fake:
        code, report = run_against(fake, tmp_path, monkeypatch)
    result = report["result"]
    assert code == 0 and result["verdict"] == "pass" and result["calls_completed"] == 22 and result["meter_vs_provider"] <= 0.001
    assert result["calls_with_provider_reported_cost"] == 22 and result["usage_settled"] is True
    assert report["meter"]["calls"] == 22 and fake.key not in json.dumps(report)


def test_a_provider_that_bills_more_than_its_replies_show_fails_the_rule(tmp_path, monkeypatch):
    with fake_openrouter.FakeOpenRouter({MODEL: PRICE}, hidden_markup=0.30) as fake:
        code, report = run_against(fake, tmp_path, monkeypatch)
    result = report["result"]
    assert code == 1 and result["verdict"] == "fail" and result["meter_vs_provider"] > p0.TOLERANCE and "more than 10%" in result["why"]


def test_a_markup_inside_the_tolerance_passes_and_just_outside_fails(tmp_path, monkeypatch):
    with fake_openrouter.FakeOpenRouter({MODEL: PRICE}, hidden_markup=0.05) as fake:
        assert run_against(fake, tmp_path, monkeypatch)[0] == 0
    with fake_openrouter.FakeOpenRouter({MODEL: PRICE}, hidden_markup=0.15) as fake:
        assert run_against(fake, tmp_path, monkeypatch)[0] == 1


@pytest.mark.parametrize("argv,env,needle", [
    ([MODEL, "--price-in", "0.2", "--price-out", "0.8"], {"DELENTIA_RUN_LIVE_TESTS": "1"}, "OPENROUTER_API_KEY"),
    ([MODEL, "--price-in", "0.2", "--price-out", "0.8"], {"OPENROUTER_API_KEY": "k"}, "DELENTIA_RUN_LIVE_TESTS"),
    ([MODEL], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "real price"),
    ([MODEL, "--price-in", "nan", "--price-out", "0.8"], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "real price"),
    ([MODEL, "--price-in", "-1", "--price-out", "0.8"], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "real price"),
    ([MODEL, "--price-in", "0.2", "--price-out", "0.8", "--calls", "10"], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "below the 20"),
    ([MODEL, "--price-in", "30", "--price-out", "150", "--calls", "40", "--prompt-tokens", "4000"], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "above --budget-usd"),
    ([MODEL, "--price-in", "0.2", "--price-out", "0.8", "--budget-usd", "0"], {"OPENROUTER_API_KEY": "k", "DELENTIA_RUN_LIVE_TESTS": "1"}, "budget-usd"),
])
def test_every_way_of_spending_by_accident_is_refused_before_anything_is_sent(argv, env, needle, capsys):
    with fake_openrouter.FakeOpenRouter({MODEL: PRICE}) as fake:
        import os
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = fake.base_url
        try:
            code = p0.main(argv, env=env)
        finally:
            os.environ.pop("DELENTIA_OPENROUTER_BASE_URL", None)
        assert code == 2 and needle in capsys.readouterr().err and fake.calls == 0


def test_a_usage_figure_that_never_settles_or_never_moves_is_not_a_verdict():
    summary = {"cost_usd": 0.01, "cost_known": True, "prompt_tokens": 1000, "completion_tokens": 100}
    moving = {"value": 0.0101, "settled": False, "reads": [0.0, 0.005, 0.0101]}
    assert p0.judge(summary, 22, 0.0, moving, 0.2, 0.8)["verdict"] == "inconclusive"
    flat = {"value": 0.0, "settled": True, "reads": [0.0, 0.0]}
    assert p0.judge(summary, 22, 0.0, flat, 0.2, 0.8)["verdict"] == "inconclusive"
    assert p0.judge(summary, 19, 0.0, {"value": 0.01, "settled": True, "reads": [0.01, 0.01]}, 0.2, 0.8)["verdict"] == "fail"           # fewer than 20 calls
    assert p0.judge({**summary, "cost_usd": None, "cost_known": False}, 22, 0.0, {"value": 0.01, "settled": True, "reads": [0.01]}, 0.2, 0.8)["verdict"] == "fail"


def test_settled_usage_reads_until_two_reads_agree():
    reads = iter([0.0, 0.004, 0.009, 0.009, 0.009])
    got = p0.settled_usage(lambda: next(reads), tries=8, wait=0, sleep=lambda s: None)
    assert got["settled"] is True and got["value"] == 0.009 and got["reads"] == [0.0, 0.004, 0.009, 0.009]
    always_moving = iter(range(100))
    assert p0.settled_usage(lambda: float(next(always_moving)), tries=3, wait=0, sleep=lambda s: None)["settled"] is False


def test_each_prompt_differs_from_the_first_characters_so_a_prefix_cache_cannot_cheapen_later_calls():
    a, b = p0.filler(0, 300), p0.filler(1, 300)
    assert a[:30] != b[:30] and a != b
    from rct_control_plane.llm_provider import _count_tokens
    assert 300 <= _count_tokens(a) <= 360
