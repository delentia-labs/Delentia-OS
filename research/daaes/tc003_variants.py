"""
TC-003 variants: many different broken `ledgercalc` packages, each with the SAME independent oracle, from a seed.

Why. The original fixture has five defects in one fixed combination. That is enough to test the oracle and not enough to tell two models apart (a screen on one task is noise). Here a variant
is the reference package with k of 18 catalogued defects put back, k = 2..6 by seed, so there are thousands of different tasks of graded difficulty, all judged by hidden tests the agent
never sees and by a reference package that passes every one of them.

What keeps it honest (each is a test, and `audit()` runs the first two on demand):
  * the reference package passes the whole hidden suite;
  * every catalogued defect, alone, makes the hidden suite fail ("killed"): a defect no test sees would be an impossible or a free task;
  * a variant is valid only if the reference differs from it, the visible tests do NOT reveal every defect of it (some are found only by reading and reasoning) and the hidden suite fails on it;
  * the same seed always gives the same variant (no hash(), no clock);
  * defects that edit the same lines are in one `slot`, so a variant never carries two edits of the same statement.

Difficulty is not claimed to be calibrated: k and the share of defects the visible tests reveal are recorded with each variant, and a ranking of models must report per k.
"""
from __future__ import annotations

import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from research.daaes import tc003_fixture as fx


@dataclass(frozen=True)
class Mutation:
    id: str
    file: str
    old: str
    new: str
    slot: str
    what: str


PRICING = "ledgercalc/pricing.py"
REFUNDS = "ledgercalc/refunds.py"
VALIDATION = "ledgercalc/validation.py"

MUTATIONS: Tuple[Mutation, ...] = (
    Mutation("M01", PRICING, "    discounted = max(subtotal - _d(discount), Decimal(0))\n    return (discounted * (1 + _d(tax_rate))).quantize(CENT, rounding=ROUND_HALF_UP)",
             "    taxed = subtotal * (1 + _d(tax_rate))\n    return max(taxed - _d(discount), Decimal(0)).quantize(CENT, rounding=ROUND_HALF_UP)", "lt_calc", "tax is added before the discount comes off"),
    Mutation("M02", PRICING, "    return (discounted * (1 + _d(tax_rate))).quantize(CENT, rounding=ROUND_HALF_UP)",
             "    return (discounted * (1 + _d(tax_rate))).quantize(CENT, rounding=ROUND_HALF_EVEN)", "lt_calc", "half cents round to even instead of up"),
    Mutation("M10", PRICING, "    discounted = max(subtotal - _d(discount), Decimal(0))", "    discounted = subtotal - _d(discount)", "lt_calc", "a discount larger than the subtotal gives a negative line"),
    Mutation("M11", PRICING, '    if _d(discount) < 0:\n        raise ValueError("discount must not be negative")\n', "", "lt_discount_check", "a negative discount is accepted"),
    Mutation("M03", PRICING, '    if quantity == 0:\n        return Decimal("0.00")\n    return (_d(subtotal) / quantity)', "    return (_d(subtotal) / quantity)", "avg_guard", "average price of zero units divides by zero"),
    Mutation("M16", PRICING, "    return (_d(subtotal) / quantity).quantize(CENT, rounding=ROUND_HALF_UP)", "    return (_d(subtotal) / quantity).quantize(CENT, rounding=ROUND_DOWN)", "avg_round", "average price rounds down"),
    Mutation("M14", PRICING, 'def order_total(lines):\n    return sum((line_total(*line) for line in lines), Decimal("0.00")).quantize(CENT)',
             'def order_total(lines):\n    return sum(line_total(*line) for line in lines).quantize(CENT)', "order_empty", "an empty order is not zero money"),
    Mutation("M17", PRICING, "    return value if isinstance(value, Decimal) else Decimal(str(value))", "    return value if isinstance(value, Decimal) else Decimal(value)", "money_str", "a float is converted by its binary value"),
    Mutation("M20", PRICING, "def line_total(unit_price, quantity, discount=0, tax_rate=0):", "def line_total(unit_price, quantity, tax_rate=0, discount=0):", "lt_signature", "the discount and tax parameters swapped places"),
    Mutation("M06", VALIDATION, "isinstance(quantity, bool) or quantity < 0:\n        raise ValueError(\"quantity must be a non-negative integer\")", "isinstance(quantity, bool) or quantity <= 0:\n        raise ValueError(\"quantity must be a non-negative integer\")",
             "vq", "zero quantity is refused"),
    Mutation("M07", VALIDATION, " or isinstance(quantity, bool) or quantity < 0:", " or quantity < 0:", "vq", "True is accepted as a quantity"),
    Mutation("M08", VALIDATION, "    if rate < 0 or rate > 1:", "    if rate < 0 or rate >= 1:", "vr", "a rate of exactly 1 is refused"),
    Mutation("M09", VALIDATION, "    if rate < 0 or rate > 1:", "    if rate <= 0 or rate > 1:", "vr", "a rate of exactly 0 is refused"),
    Mutation("M04", REFUNDS, '    if amount < 0:\n        raise ValueError("refund must not be negative")\n', "", "vf_negative", "a negative refund is accepted"),
    Mutation("M13", REFUNDS, "    if amount > paid:\n        raise ValueError(\"refund exceeds payment\")", "    if amount >= paid:\n        raise ValueError(\"refund exceeds payment\")", "vf_equal", "refunding exactly what was paid is refused"),
    Mutation("M05", REFUNDS, '    if quantity == 0:\n        return Decimal("0.00")\n    total = line_total', "    total = line_total", "rf_total", "refunding nothing from nothing divides by zero"),
    Mutation("M12", REFUNDS, "    if refund_quantity > quantity:", "    if refund_quantity >= quantity:", "rf_all", "refunding the whole line is refused"),
    Mutation("M18", REFUNDS, "    total = line_total(unit_price, quantity, discount, tax_rate)", "    total = line_total(unit_price, quantity, 0, tax_rate)", "rf_total", "a refund ignores the discount that was given"),
)

# Extra hidden tests, written so that every catalogued defect is killed by at least one test. They are appended to the original hidden suite for variants only.
EXTRA_HIDDEN = '''from decimal import Decimal

import pytest

from ledgercalc import average_unit_price, line_total, order_total, refund_amount, validate_quantity, validate_rate, validate_refund


def test_a_boolean_is_not_a_quantity():
    with pytest.raises(ValueError):
        validate_quantity(True)


def test_a_tax_rate_of_exactly_one_is_allowed_and_of_exactly_zero_too():
    assert line_total("10.00", 1, 0, "1") == Decimal("20.00")
    assert validate_rate(0) == 0 and validate_rate(1) == 1


def test_refunding_exactly_what_was_paid_is_allowed():
    assert validate_refund("10.00", "10.00") == Decimal("10.00")


def test_average_price_rounds_half_up_not_down():
    assert average_unit_price("2.00", 3) == Decimal("0.67")


def test_a_float_price_is_taken_as_written_not_by_its_binary_value():
    assert line_total(2.675, 1) == Decimal("2.68")


def test_a_refund_carries_its_share_of_the_discount_and_the_tax():
    assert refund_amount("10.00", 2, 1, "4.00", "0.10") == Decimal("8.80")


def test_the_parameters_keep_their_order():
    assert line_total("10.00", 2, "5.00", "0.10") == Decimal("16.50")


def test_a_whole_order_with_a_discount_larger_than_one_line_floors_per_line():
    assert order_total([("1.00", 1, "5.00", 0), ("3.00", 1, 0, 0)]) == Decimal("3.00")
'''


def hidden_suite() -> Dict[str, str]:
    return {**fx.HIDDEN_TESTS, "hidden_tests/test_variants.py": EXTRA_HIDDEN}


def apply(files: Dict[str, str], mutations: List[Mutation]) -> Dict[str, str]:
    out = dict(files)
    for m in mutations:
        text = out[m.file]
        if text.count(m.old) != 1:
            raise ValueError(f"{m.id}: its text occurs {text.count(m.old)} times in {m.file}, expected exactly once")
        out[m.file] = text.replace(m.old, m.new)
    return out


def _compatible(chosen: List[Mutation], candidate: Mutation) -> bool:
    return all(c.slot != candidate.slot for c in chosen)


# The defects the VISIBLE tests reveal (checked against the real suites by audit() and by a test). A variant always has one of these, so the agent has something to start from when it runs
# the visible tests, and at least one defect that only reading and reasoning finds.
VISIBLE = frozenset({"M01", "M02", "M20", "M09"})


def pick(seed: int) -> List[Mutation]:
    """The defects of one variant: k = 2..6 by seed, drawn without replacement, never two edits of one slot, at least one the visible tests reveal and at least one they do not.
    A pure function of the seed."""
    rng = random.Random(f"tc003-variant-{seed}")
    k = 2 + (seed % 5)
    visible = [m for m in MUTATIONS if m.id in VISIBLE]
    hidden_only = [m for m in MUTATIONS if m.id not in VISIBLE]
    chosen: List[Mutation] = [rng.choice(visible)]
    rest = hidden_only[:]
    rng.shuffle(rest)
    chosen.append(next(m for m in rest if _compatible(chosen, m)))
    pool = [m for m in MUTATIONS if m not in chosen]
    rng.shuffle(pool)
    for m in pool:
        if len(chosen) == k:
            break
        if _compatible(chosen, m):
            chosen.append(m)
    return sorted(chosen, key=lambda m: m.id)


def build(seed: int) -> fx.Fixture:
    chosen = pick(seed)
    buggy = apply(fx.REFERENCE, chosen)
    buggy = {**fx.BUGGY, **buggy}                                    # __init__.py comes from the original fixture; the three modules from the mutated reference
    buggy["ledgercalc/__init__.py"] = fx.INIT
    return fx.Fixture(f"variant-{seed}-k{len(chosen)}", buggy, fx.REFERENCE, fx.PUBLIC_TESTS, hidden_suite(), fx.PYPROJECT)


def describe(seed: int) -> Dict[str, object]:
    chosen = pick(seed)
    return {"seed": seed, "k": len(chosen), "defects": [{"id": m.id, "file": m.file, "what": m.what} for m in chosen]}


# --------------------------------------------------------------------------------------------- running the suites (for the audit and the tests)
def run_suite(package: Dict[str, str], tests: Dict[str, str], targets: List[str]) -> Dict[str, str]:
    """pytest in a clean folder; returns {test id: outcome}. The package and the tests are written fresh, nothing from the repository is on the path."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        for rel, text in {**package, **tests, "pyproject.toml": fx.PYPROJECT}.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-rA", *targets], cwd=str(root), capture_output=True, text=True, timeout=180)
        outcomes: Dict[str, str] = {}
        for line in done.stdout.splitlines():
            for status in ("PASSED", "FAILED", "ERROR"):
                if line.startswith(status + " "):
                    outcomes[line.split(" ", 1)[1].split(" - ")[0].strip()] = status.lower()
        return outcomes


def failing(package: Dict[str, str], hidden: Optional[Dict[str, str]] = None, public: Optional[Dict[str, str]] = None) -> Tuple[List[str], List[str]]:
    """(hidden tests that fail, public tests that fail) for a package."""
    hidden = hidden if hidden is not None else hidden_suite()
    public = public if public is not None else fx.PUBLIC_TESTS
    h = run_suite(package, hidden, ["hidden_tests"])
    p = run_suite(package, public, ["tests"])
    return sorted(k for k, v in h.items() if v != "passed"), sorted(k for k, v in p.items() if v != "passed")


def audit() -> Dict[str, object]:
    """The reference passes everything; every single defect is killed by at least one hidden test. Used by `python -m research.daaes.tc003_variants` and by a test."""
    ref_h, ref_p = failing(dict(fx.REFERENCE, **{"ledgercalc/__init__.py": fx.INIT}))
    report: Dict[str, object] = {"reference_hidden_failures": ref_h, "reference_public_failures": ref_p, "mutations": {}}
    for m in MUTATIONS:
        package = apply(dict(fx.REFERENCE, **{"ledgercalc/__init__.py": fx.INIT}), [m])
        h, p = failing(package)
        report["mutations"][m.id] = {"killed_by_hidden": h[:4], "visible_to_public": bool(p), "what": m.what}     # type: ignore[index]
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), indent=2))
