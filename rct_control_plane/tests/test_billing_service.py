"""
Round 45 item C (group 4): real tests for billing_service.py - 0% coverage
before this file. Confirmed genuinely used: rct_control_plane/api.py imports
BILLING_SERVICE, swarm_hr_engine.py imports generate_promptpay_emvco directly.
Pure Python (CRC-16 bit math, EMVCo string formatting, dict bookkeeping) - no
mocking needed anywhere in this module.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.billing_service import (
    crc16_ccitt, generate_promptpay_emvco, InvoiceRecord, BillingService,
)


class TestCrc16Ccitt:
    def test_matches_the_standard_ccitt_false_reference_vector(self):
        # "123456789" -> 0x29B1 is the well-known reference test vector
        # for CRC-16/CCITT-FALSE - confirms this is a real, correct
        # implementation of the named algorithm, not just "some checksum".
        assert crc16_ccitt("123456789") == "29B1"

    def test_is_deterministic(self):
        assert crc16_ccitt("hello") == crc16_ccitt("hello")

    def test_different_input_produces_different_checksum(self):
        assert crc16_ccitt("hello") != crc16_ccitt("hellp")

    def test_output_is_always_four_hex_digits(self):
        for s in ("", "a", "a" * 200):
            result = crc16_ccitt(s)
            assert len(result) == 4
            int(result, 16)  # raises if not valid hex


class TestGeneratePromptpayEmvco:
    def test_ten_digit_local_number_gets_thailand_country_code(self):
        payload = generate_promptpay_emvco("0812345678")
        assert "0066812345678" in payload

    def test_dashes_in_phone_number_are_stripped(self):
        assert generate_promptpay_emvco("081-234-5678") == generate_promptpay_emvco("0812345678")

    def test_non_standard_target_is_used_as_is(self):
        # A national ID or e-wallet target (not a 10-digit local phone
        # number) should NOT get the "0066" country-code substitution.
        payload = generate_promptpay_emvco("1234567890123")
        assert "0066" not in payload
        assert "1234567890123" in payload

    def test_amount_is_embedded_when_positive(self):
        with_amount = generate_promptpay_emvco("0812345678", 100.50)
        without_amount = generate_promptpay_emvco("0812345678")
        assert "100.50" in with_amount
        assert "54" in with_amount  # EMVCo amount tag
        assert len(with_amount) > len(without_amount)

    def test_zero_or_none_amount_is_omitted(self):
        assert generate_promptpay_emvco("0812345678", 0) == generate_promptpay_emvco("0812345678")
        assert generate_promptpay_emvco("0812345678", None) == generate_promptpay_emvco("0812345678")

    def test_negative_amount_is_omitted(self):
        assert generate_promptpay_emvco("0812345678", -5.0) == generate_promptpay_emvco("0812345678")

    def test_payload_ends_with_a_real_crc16_of_its_own_prefix(self):
        payload = generate_promptpay_emvco("0812345678", 50.0)
        prefix, checksum = payload[:-4], payload[-4:]
        assert crc16_ccitt(prefix) == checksum


class TestInvoiceRecord:
    def test_defaults_to_paid_status(self):
        inv = InvoiceRecord("INV-1", "PRO", 590.0, "a@example.com")
        assert inv.status == "PAID"

    def test_signedai_seal_has_the_expected_shape(self):
        inv = InvoiceRecord("INV-1", "PRO", 590.0, "a@example.com")
        assert inv.signedai_seal.startswith("ED25519-")
        assert len(inv.signedai_seal) == len("ED25519-") + 20

    def test_seal_is_deterministic_for_the_same_invoice_id_and_amount(self):
        inv1 = InvoiceRecord("INV-1", "PRO", 590.0, "a@example.com")
        inv2 = InvoiceRecord("INV-1", "PRO", 590.0, "b@example.com")  # different email
        assert inv1.signedai_seal == inv2.signedai_seal  # seal only depends on id+amount

    def test_seal_differs_for_different_amounts(self):
        inv1 = InvoiceRecord("INV-1", "PRO", 590.0, "a@example.com")
        inv2 = InvoiceRecord("INV-1", "PRO", 2900.0, "a@example.com")
        assert inv1.signedai_seal != inv2.signedai_seal

    def test_to_dict_contains_all_real_fields(self):
        inv = InvoiceRecord("INV-1", "PRO", 590.0, "a@example.com", promptpay_id="0899999999")
        d = inv.to_dict()
        assert d["invoice_id"] == "INV-1"
        assert d["tier"] == "PRO"
        assert d["amount_thb"] == 590.0
        assert d["customer_email"] == "a@example.com"
        assert d["promptpay_id"] == "0899999999"
        assert "qr_payload" in d and d["qr_payload"]
        assert "signedai_seal" in d


class TestBillingService:
    @pytest.fixture
    def service(self):
        return BillingService()

    def test_defaults_to_pro_tier(self, service):
        assert service.current_tier == "PRO"

    def test_create_invoice_uses_the_real_tier_price(self, service):
        invoice = service.create_invoice("ENTERPRISE", "a@example.com")
        assert invoice.amount_thb == service.tier_quotas["ENTERPRISE"]["monthly_price_thb"]
        assert invoice.tier == "ENTERPRISE"

    def test_create_invoice_is_case_insensitive(self, service):
        invoice = service.create_invoice("pro", "a@example.com")
        assert invoice.tier == "PRO"

    def test_create_invoice_falls_back_to_pro_for_unknown_tier(self, service):
        invoice = service.create_invoice("PLATINUM_DELUXE", "a@example.com")
        assert invoice.tier == "PRO"

    def test_create_invoice_is_stored_and_retrievable(self, service):
        invoice = service.create_invoice("FREE", "a@example.com")
        assert service.invoices[invoice.invoice_id] is invoice

    def test_invoice_ids_are_unique_across_calls(self, service):
        inv1 = service.create_invoice("FREE", "a@example.com")
        inv2 = service.create_invoice("FREE", "a@example.com")
        assert inv1.invoice_id != inv2.invoice_id

    def test_deduct_tokens_increments_usage_for_the_current_tier(self, service):
        before = service.tier_quotas["PRO"]["tokens_used"]
        result = service.deduct_tokens(1000)
        assert service.tier_quotas["PRO"]["tokens_used"] == before + 1000
        assert result["tokens_spent"] == 1000
        assert result["current_tier"] == "PRO"

    def test_deduct_tokens_is_clamped_to_the_token_limit(self, service):
        limit = service.tier_quotas["PRO"]["token_limit"]
        result = service.deduct_tokens(limit * 10)
        assert result["tokens_used"] == limit
        assert result["percentage_used"] == 100.0

    def test_deduct_tokens_reports_correct_percentage(self, service):
        service.tier_quotas["PRO"]["tokens_used"] = 0
        result = service.deduct_tokens(service.tier_quotas["PRO"]["token_limit"] // 2)
        assert result["percentage_used"] == pytest.approx(50.0, abs=0.1)

    def test_get_billing_state_shape(self, service):
        service.create_invoice("PRO", "a@example.com")
        state = service.get_billing_state()
        assert state["current_tier"] == "PRO"
        assert "tiers" in state
        assert len(state["recent_invoices"]) == 1

    def test_get_billing_state_revenue_only_counts_paid_invoices(self, service):
        invoice = service.create_invoice("PRO", "a@example.com")
        invoice.status = "PENDING"  # simulate an unpaid invoice
        service.create_invoice("FREE", "b@example.com")  # amount 0, PAID
        state = service.get_billing_state()
        assert state["total_revenue_thb"] == 0  # the PRO invoice was excluded, FREE is worth 0

    def test_get_billing_state_shows_only_the_last_ten_invoices(self, service):
        for i in range(15):
            service.create_invoice("FREE", f"user{i}@example.com")
        state = service.get_billing_state()
        assert len(state["recent_invoices"]) == 10
