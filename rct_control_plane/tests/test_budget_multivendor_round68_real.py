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
