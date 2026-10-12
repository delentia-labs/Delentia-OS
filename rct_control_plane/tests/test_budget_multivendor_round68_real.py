"""Round 68: the multi-vendor budget (research/budget_multivendor.py), computed from the committed OpenRouter snapshot. No network."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research")))

import json

import budget_multivendor as bm

SNAP = json.loads(bm.newest().read_text(encoding="utf-8"))["models"]


def test_eligibility_excludes_what_cannot_be_a_reproducible_interactive_run():
    ok = [m for m in SNAP if bm.eligible(m)]
    assert ok
    for m in ok:
        assert m["tools"] and m["text_in"] and m["text_out"] and m["context"] >= 32000 and m["in_per_m"] > 0 and m["out_per_m"] > 0
        assert ":batch" not in m["id"] and not m["id"].startswith("~") and ":free" not in m["id"] and not m["id"].startswith("openrouter/") and not m["expires"]


def test_the_shortlist_spans_many_vendors_and_is_reproducible():
    a, b = bm.shortlist(SNAP), bm.shortlist(SNAP)
    assert [m["id"] for m in a] == [m["id"] for m in b]
    vendors = {m["vendor"] for m in a}
    assert len(vendors) >= 5, vendors                                     # the criterion written before the run: at least five different vendors
    assert len({m["id"] for m in a}) == len(a)


def test_the_cost_of_an_episode_is_the_stated_formula():
    m = {"in_per_m": 1.0, "out_per_m": 2.0, "cache_read_per_m": 0.1}
    plain = bm.cost_per_episode(m, 8200)
    assert abs(plain - (6 * 8200 * 1.0 + 6 * 150 * 2.0) / 1e6) < 1e-12
    cached = bm.cost_per_episode(m, 8200, 0.9)
    assert cached < plain and abs(cached - (6 * 8200 * 0.1 * 1.0 + 6 * 8200 * 0.9 * 0.1 + 6 * 150 * 2.0) / 1e6) < 1e-12
    assert bm.cost_per_episode({"in_per_m": 1.0, "out_per_m": 2.0, "cache_read_per_m": None}, 8200, 0.9) == plain          # no published cache price: no discount assumed
    assert bm.cost_per_episode(m, 1500) < plain                                                                       # the compact menu is cheaper


def test_fit_budget_spreads_vendors_before_depth_and_never_exceeds_the_budget():
    short = bm.shortlist(SNAP)
    picked = bm.fit_budget(short, 5.0)
    spent = sum(bm.screen_cost(m) for m in picked) * bm.MARGIN
    assert spent <= 5.0 and len({m["vendor"] for m in picked}) >= 5
    first_per_vendor = {}
    for m in picked:
        first_per_vendor.setdefault(m["vendor"], m)
    assert len(first_per_vendor) >= len(picked) - len({m["vendor"] for m in picked})          # at most one extra per vendor
    assert bm.fit_budget(short, 0.0) == []
    assert len(bm.fit_budget(short, 50.0)) == len(short)


def test_the_orchestrator_accepts_the_wide_screening_tier_and_a_shortlist(tmp_path, capsys, monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
    import full_test_orchestrator as fto
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DELENTIA_RUN_LIVE_TESTS", raising=False)
    listing = tmp_path / "short.json"
    picked = bm.fit_budget(bm.shortlist(SNAP), 5.0)
    listing.write_text(json.dumps({"shortlist": picked}), encoding="utf-8")
    assert fto.MAX_MODELS["W"] >= len(picked)
    code = fto.main(["--tier", "W", "--shortlist-json", str(listing), "--budget-usd", "5"])
    out = capsys.readouterr().out
    assert code == 0 and f"Tier W: {len(picked)} model(s)" in out and "DRY RUN" in out and "nothing was sent" in out
    stages = fto.stages_for(picked[0]["id"], {}, tmp_path, "W")
    assert [s["name"] for s in stages] == ["k15"]                                        # the capability screen only
