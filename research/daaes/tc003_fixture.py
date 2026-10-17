"""
TC-003 fixture: the `ledgercalc` package with five seeded defects, its visible tests, and the hidden tests the agent never sees. (Specification section III.)

The package prices order lines in Decimal money. Behaviour (the reference, written in REFERENCE below):
  line_total(unit_price, quantity, discount=0, tax_rate=0): a FIXED amount `discount` comes off the subtotal first, never below zero, then tax is added on what is left; half-up to cents; Decimal.
  order_total(lines): sum of line totals (empty -> 0.00).   average_unit_price(subtotal, quantity): 0.00 for quantity 0.
  refund_amount(unit_price, quantity, refund_quantity, discount=0, tax_rate=0): the share of the line total that belongs to the refunded quantity.
  validate_refund(amount, paid): negative or above what was paid -> ValueError.   validate_quantity: integer >= 0.   validate_rate: 0 <= rate <= 1.

Seeded defects (BUGGY):
  BUG-01 tax is added before the discount comes off (tax on the full subtotal)
  BUG-02 float arithmetic and round(): 2.675 -> 2.67, sums drift
  BUG-03 validate_refund accepts a negative amount
  BUG-04 quantity 0 is rejected / divides by zero
  BUG-05 the trap: the public API must not change (signatures are part of the hidden contract), and fixing one function must not break its callers

The oracle writes this fixture fresh for every run; hidden tests and the answer key live outside the agent's workspace.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator

INIT = '''from .pricing import line_total, order_total, average_unit_price
from .refunds import refund_amount, validate_refund
from .validation import validate_quantity, validate_rate

__all__ = ["line_total", "order_total", "average_unit_price", "refund_amount", "validate_refund", "validate_quantity", "validate_rate"]
'''

BUGGY: Dict[str, str] = {
    "ledgercalc/__init__.py": INIT,
    "ledgercalc/validation.py": '''def validate_quantity(quantity):
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    return quantity


def validate_rate(rate):
    if rate < 0 or rate > 1:
        raise ValueError("rate must be between 0 and 1")
    return rate
''',
    "ledgercalc/pricing.py": '''from .validation import validate_quantity, validate_rate


def line_total(unit_price, quantity, discount=0, tax_rate=0):
    validate_quantity(quantity)
    validate_rate(tax_rate)
    if discount < 0:
        raise ValueError("discount must not be negative")
    subtotal = float(unit_price) * quantity
    taxed = subtotal * (1 + float(tax_rate))
    total = taxed - float(discount)
    return round(max(total, 0.0), 2)


def order_total(lines):
    return round(sum(line_total(*line) for line in lines), 2)


def average_unit_price(subtotal, quantity):
    return round(float(subtotal) / quantity, 2)
''',
    "ledgercalc/refunds.py": '''from .pricing import line_total
from .validation import validate_quantity


def refund_amount(unit_price, quantity, refund_quantity, discount=0, tax_rate=0):
    validate_quantity(quantity)
    validate_quantity(refund_quantity)
    if refund_quantity > quantity:
        raise ValueError("cannot refund more than was bought")
    total = line_total(unit_price, quantity, discount, tax_rate)
    return round(total * refund_quantity / quantity, 2)


def validate_refund(amount, paid):
    if amount > paid:
        raise ValueError("refund exceeds payment")
    return amount
''',
}

REFERENCE: Dict[str, str] = {
    "ledgercalc/validation.py": '''def validate_quantity(quantity):
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
        raise ValueError("quantity must be a non-negative integer")
    return quantity


def validate_rate(rate):
    if rate < 0 or rate > 1:
        raise ValueError("rate must be between 0 and 1")
    return rate
''',
    "ledgercalc/pricing.py": '''from decimal import ROUND_HALF_UP, Decimal

from .validation import validate_quantity, validate_rate

CENT = Decimal("0.01")


def _d(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def line_total(unit_price, quantity, discount=0, tax_rate=0):
    validate_quantity(quantity)
    validate_rate(_d(tax_rate))
    if _d(discount) < 0:
        raise ValueError("discount must not be negative")
    subtotal = _d(unit_price) * quantity
    discounted = max(subtotal - _d(discount), Decimal(0))
    return (discounted * (1 + _d(tax_rate))).quantize(CENT, rounding=ROUND_HALF_UP)


def order_total(lines):
    return sum((line_total(*line) for line in lines), Decimal("0.00")).quantize(CENT)


def average_unit_price(subtotal, quantity):
    if quantity == 0:
        return Decimal("0.00")
    return (_d(subtotal) / quantity).quantize(CENT, rounding=ROUND_HALF_UP)
''',
    "ledgercalc/refunds.py": '''from decimal import ROUND_HALF_UP, Decimal

from .pricing import CENT, _d, line_total
from .validation import validate_quantity


def refund_amount(unit_price, quantity, refund_quantity, discount=0, tax_rate=0):
    validate_quantity(quantity)
    validate_quantity(refund_quantity)
    if refund_quantity > quantity:
        raise ValueError("cannot refund more than was bought")
    if quantity == 0:
        return Decimal("0.00")
    total = line_total(unit_price, quantity, discount, tax_rate)
    return (total * refund_quantity / quantity).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_refund(amount, paid):
    amount, paid = _d(amount), _d(paid)
    if amount < 0:
        raise ValueError("refund must not be negative")
    if amount > paid:
        raise ValueError("refund exceeds payment")
    return amount
''',
}

PYPROJECT = '''[project]
name = "ledgercalc"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
'''

PUBLIC_TESTS: Dict[str, str] = {
    "tests/test_pricing.py": '''from decimal import Decimal

from ledgercalc import line_total, order_total


def test_discount_comes_off_before_tax():
    assert line_total("100.00", 2, "20.00", "0.07") == Decimal("192.60")


def test_money_is_decimal_and_rounds_half_up():
    assert line_total("2.675", 1) == Decimal("2.68")
    assert isinstance(line_total("1.10", 3), Decimal)


def test_order_total_adds_the_lines():
    assert order_total([("10.00", 1, 0, 0), ("5.50", 2, 0, "0.10")]) == Decimal("22.10")
''',
    "tests/test_refunds.py": '''from decimal import Decimal

import pytest

from ledgercalc import refund_amount, validate_refund


def test_partial_refund_is_proportional():
    assert refund_amount("10.00", 4, 1) == Decimal("10.00")


def test_a_refund_above_the_payment_is_refused():
    with pytest.raises(ValueError):
        validate_refund("50.00", "40.00")
''',
}

HIDDEN_TESTS: Dict[str, str] = {
    "hidden_tests/test_boundaries.py": '''from decimal import Decimal

import pytest

from ledgercalc import average_unit_price, line_total, refund_amount, validate_refund


def test_zero_quantity_is_a_zero_line():
    assert line_total("9.99", 0) == Decimal("0.00")


def test_average_price_of_zero_units_is_zero():
    assert average_unit_price("0.00", 0) == Decimal("0.00")


def test_a_discount_larger_than_the_subtotal_floors_at_zero():
    assert line_total("5.00", 2, "50.00", "0.2") == Decimal("0.00")


def test_half_cents_round_up_not_to_even():
    assert line_total("0.005", 1) == Decimal("0.01")
    assert line_total("1.005", 1) == Decimal("1.01")


def test_tax_applies_to_the_discounted_amount_only():
    assert line_total("100.00", 1, "40.00", "0.10") == Decimal("66.00")


def test_a_negative_refund_is_refused():
    with pytest.raises(ValueError):
        validate_refund("-1.00", "10.00")


def test_a_full_refund_of_a_line_returns_the_whole_total():
    assert refund_amount("19.99", 3, 3, "5.00", "0.07") == line_total("19.99", 3, "5.00", "0.07")


def test_refunding_nothing_from_nothing_is_zero():
    assert refund_amount("10.00", 0, 0) == Decimal("0.00")
''',
    "hidden_tests/test_regression.py": '''from decimal import Decimal

import pytest

from ledgercalc import line_total, order_total, validate_quantity, validate_rate, validate_refund


def test_an_empty_order_is_zero():
    assert order_total([]) == Decimal("0.00")


def test_negative_quantity_is_refused():
    with pytest.raises(ValueError):
        line_total("1.00", -1)
    with pytest.raises(ValueError):
        validate_quantity(-3)


def test_a_non_integer_quantity_is_refused():
    with pytest.raises(ValueError):
        validate_quantity(1.5)


def test_rates_outside_zero_to_one_are_refused():
    with pytest.raises(ValueError):
        validate_rate(1.2)
    with pytest.raises(ValueError):
        line_total("1.00", 1, 0, "1.5")


def test_a_negative_discount_is_refused():
    with pytest.raises(ValueError):
        line_total("1.00", 1, "-1.00")


def test_a_refund_above_the_payment_is_still_refused():
    with pytest.raises(ValueError):
        validate_refund("11.00", "10.00")


def test_many_small_lines_do_not_drift():
    assert order_total([("0.10", 1, 0, 0)] * 30) == Decimal("3.00")
''',
    "hidden_tests/test_api_contract.py": '''import inspect
from decimal import Decimal

import ledgercalc

EXPECTED = {
    "line_total": "(unit_price, quantity, discount=0, tax_rate=0)",
    "order_total": "(lines)",
    "average_unit_price": "(subtotal, quantity)",
    "refund_amount": "(unit_price, quantity, refund_quantity, discount=0, tax_rate=0)",
    "validate_refund": "(amount, paid)",
    "validate_quantity": "(quantity)",
    "validate_rate": "(rate)",
}


def test_every_public_signature_is_unchanged():
    for name, signature in EXPECTED.items():
        assert str(inspect.signature(getattr(ledgercalc, name))) == signature, name


def test_the_public_names_are_unchanged():
    assert sorted(ledgercalc.__all__) == sorted(EXPECTED)


def test_money_functions_return_decimal():
    assert isinstance(ledgercalc.line_total("1.00", 1), Decimal) and isinstance(ledgercalc.order_total([]), Decimal)
''',
}


@dataclass(frozen=True)
class Fixture:
    """Everything one TC-003 run needs: the buggy package the agent gets, the answer (reference), the visible tests and the hidden ones. The default is the original five-defect fixture;
    tc003_variants.py builds others from a seed."""
    id: str
    buggy: Dict[str, str]
    reference: Dict[str, str]
    public: Dict[str, str]
    hidden: Dict[str, str]
    pyproject: str


DEFAULT = Fixture("original", BUGGY, REFERENCE, PUBLIC_TESTS, HIDDEN_TESTS, PYPROJECT)
_active = [DEFAULT]


def active() -> Fixture:
    return _active[-1]


@contextmanager
def use(fixture: Fixture) -> Iterator[Fixture]:
    """Runs a block against another fixture and puts the previous one back, whatever happens (a helper that leaves a global changed breaks every later run)."""
    _active.append(fixture)
    try:
        yield fixture
    finally:
        _active.pop()
