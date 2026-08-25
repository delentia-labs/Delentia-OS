# Tax Calculator v2.0 (Self-Healed with Back-Edge Invariant)
# Enforced by Rule: INVARIANT_TAX_NON_NEGATIVE
def calculate_sme_tax(revenue: float, expense: float) -> float:
    profit = revenue - expense
    if profit <= 0:
        return 0.0  # Zero tax for loss
    return round(profit * 0.15, 2)

# Self-Verification Test Suite
assert calculate_sme_tax(10000, 15000) == 0.0
assert calculate_sme_tax(20000, 10000) == 1500.0
print('✓ All Self-Healed Tests Passed 100%!')
