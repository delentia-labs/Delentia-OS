"""TC-003 hidden-heavy tier H (research/EFFICACY_S07_CRITERIA_R115.md B1): free, no model."""
import pytest

from research.daaes import tc003_fixture as fx
from research.daaes import tc003_variants as v

BASE = v.HIDDEN_TIER_BASE


def test_the_three_tiers_are_named_by_seed_and_v_and_m_did_not_move():
    assert [v.tier_of(s) for s in (0, 4999, 5000, 5999, 6000, 99999)] == ["mixed", "mixed", "visible", "visible", "hidden", "hidden"]
    assert [m.id for m in v.pick(1700)] == ["M02", "M18"] and [m.id for m in v.pick(1705)] == ["M09", "M13"]            # M, as in the R2-2 results
    assert len({tuple(m.id for m in v.pick(5000 + i)) for i in range(7)}) == 7                                         # V: still seven distinct tasks


def test_every_h_seed_has_k_3_to_5_at_least_two_hidden_only_defects_one_visible_and_no_shared_slot():
    ks = set()
    for seed in range(BASE, BASE + 300):
        chosen = v.pick(seed)
        ks.add(len(chosen))
        assert 3 <= len(chosen) <= 5, seed
        assert sum(1 for m in chosen if m.id not in v.VISIBLE) >= 2, seed
        assert any(m.id in v.VISIBLE for m in chosen), seed                       # something to start from when the visible tests run
        assert len({m.slot for m in chosen}) == len(chosen), seed
        assert [m.id for m in chosen] == [m.id for m in v.pick(seed)]             # a pure function of the seed
    assert ks == {3, 4, 5}


def test_h_gives_many_distinct_tasks_and_names_them():
    assert len({tuple(m.id for m in v.pick(BASE + i)) for i in range(60)}) >= 40
    d = v.describe(BASE + 2)
    assert d["tier"] == "hidden" and v.build(BASE + 2).id == f"variant-h{BASE + 2}-k{d['k']}"


@pytest.fixture(scope="module")
def reference_package():
    return dict(fx.REFERENCE, **{"ledgercalc/__init__.py": fx.INIT})


def test_h_tasks_are_valid_the_hidden_suite_fails_and_something_is_hidden_from_the_visible_tests(reference_package):
    hidden = v.hidden_suite()
    for i in range(6):
        seed = BASE + i
        fixture = v.build(seed)
        h, p = v.failing(dict(fixture.buggy), hidden)
        assert h, f"seed {seed}: the hidden suite does not fail on the variant"
        hidden_only = [m for m in v.pick(seed) if m.id not in v.VISIBLE]
        assert len(hidden_only) >= 2
