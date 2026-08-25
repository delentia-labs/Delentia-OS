"""
Unit Tests for Phase 4: Monetization & Billing Gateways
Tests PromptPay Dynamic EMVCo QR and Stripe Checkout Gateways.
"""

from rct_control_plane.promptpay_billing import generate_promptpay_qr_payload, calculate_crc16
from rct_control_plane.stripe_billing import StripeBillingGateway, SUBSCRIPTION_TIERS


def test_promptpay_emvco_payload():
    res = generate_promptpay_qr_payload("0812345678", 500.0, "INV-2026-001")
    assert res["status"] == "AWAITING_PAYMENT"
    assert res["amount_thb"] == 500.0
    assert len(res["crc16"]) == 4
    assert res["emvco_payload"].endswith(res["crc16"])


def test_crc16_calculation():
    crc = calculate_crc16("000201010212")
    assert len(crc) == 4


def test_stripe_checkout_creation():
    gateway = StripeBillingGateway()
    session = gateway.create_checkout_session(user_id="user_whale", tier="PRO")
    assert session["status"] == "SESSION_CREATED"
    assert session["tier"] == "PRO"
    assert session["amount_usd"] == 29.0
    assert session["intent_quota"] == SUBSCRIPTION_TIERS["PRO"]["intent_quota"]
