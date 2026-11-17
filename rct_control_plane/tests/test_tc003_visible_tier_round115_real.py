"""TC-003 visible tier (research/TC003_HEADROOM_CRITERIA_R115.md): rules V1 to V3, free, no model."""
import pytest

from research.daaes import tc003_fixture as fx
from research.daaes import tc003_variants as v

BASE = v.VISIBLE_TIER_BASE


def test_there_are_seven_distinct_combinations_two_and_three_defects():
    combos = [tuple(m.id for m in c) for c in v.visible_combinations()]
    assert combos == [("M01", "M09"), ("M01", "M20"), ("M02", "M09"), ("M02", "M20"), ("M09", "M20"), ("M01", "M09", "M20"), ("M02", "M09", "M20")]
    assert len(set(combos)) == 7 and {len(c) for c in combos} == {2, 3}
    for c in v.visible_combinations():
        assert len({m.slot for m in c}) == len(c)                     # never two edits of one statement
        assert all(m.id in v.VISIBLE for m in c)


def test_seeds_5000_to_5006_give_the_seven_and_the_same_seed_the_same_defects():
    seen = [tuple(m.id for m in v.pick(BASE + i)) for i in range(7)]
    assert len(set(seen)) == 7
    assert [tuple(m.id for m in v.pick(BASE + 7 + i)) for i in range(7)] == seen          # modulo 7
    assert tuple(m.id for m in v.pick(BASE + 3)) == tuple(m.id for m in v.pick(BASE + 3))


def test_seeds_below_the_base_are_unchanged():
    expected = {1700: ["M02", "M18"], 1705: ["M09", "M13"]}                                   # read from the R2-2 results of 2026-11-15
    for seed, ids in expected.items():
        assert [m.id for m in v.pick(seed)] == ids
    assert v.describe(1700)["tier"] == "mixed" and v.build(1700).id == "variant-1700-k2"


def test_the_fixture_and_description_name_the_tier():
    for i in range(7):
        d = v.describe(BASE + i)
        assert d["tier"] == "visible" and d["k"] in (2, 3)
        assert v.build(BASE + i).id == f"variant-v{BASE + i}-k{d['k']}"


@pytest.fixture(scope="module")
def reference_package():
    return dict(fx.REFERENCE, **{"ledgercalc/__init__.py": fx.INIT})


def test_every_combination_is_valid_the_reference_passes_and_the_variant_fails_both_suites(reference_package):
    hidden = v.hidden_suite()
    ref_h, ref_p = v.failing(reference_package, hidden)
    assert ref_h == [] and ref_p == []
    for i in range(7):
        fixture = v.build(BASE + i)
        h, p = v.failing(dict(fixture.buggy), hidden)
        assert h, f"seed {BASE + i}: the hidden suite does not fail on the variant"
        assert p, f"seed {BASE + i}: the visible suite does not fail on the variant (a defect only reading would find)"


def test_every_defect_of_the_tier_alone_is_shown_by_the_visible_tests(reference_package):
    hidden = v.hidden_suite()
    for mid in sorted(v.VISIBLE):
        mutation = next(m for m in v.MUTATIONS if m.id == mid)
        h, p = v.failing(v.apply(reference_package, [mutation]), hidden)
        assert h and p, f"{mid}: killed by hidden {bool(h)}, shown by the visible tests {bool(p)}"
