"""
Tests for Payment Engine — Agentic Metered Billing
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from rct_control_plane.payment_engine import (
    PAYMENT_ENGINE_VERSION,
    SubscriptionTier,
    TierPolicy,
    TIER_POLICIES,
    FDIAGateError,
    DailyLimitExceededError,
    StripeEventError,
    PaymentEngine,
    _stripe_create_usage_record,
)


# ============================================================
# Helpers
# ============================================================

def _engine(
    tier: SubscriptionTier = SubscriptionTier.PRO,
    stripe_item: str | None = None,
) -> PaymentEngine:
    return PaymentEngine(
        get_tier=lambda uid: tier,
        stripe_item_id_for=lambda uid: stripe_item,
    )


# ============================================================
# 1. Constants
# ============================================================

class TestConstants(unittest.TestCase):
    def test_version(self):
        self.assertEqual(PAYMENT_ENGINE_VERSION, "1.0")

    def test_three_tiers(self):
        self.assertEqual(len(TIER_POLICIES), 3)

    def test_community_free(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.COMMUNITY].monthly_price_usd, 0.0)

    def test_pro_price(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.PRO].monthly_price_usd, 49.0)

    def test_enterprise_price(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.ENTERPRISE].monthly_price_usd, 299.0)

    def test_enterprise_unlimited(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.ENTERPRISE].daily_intent_limit, 0)

    def test_community_limit(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.COMMUNITY].daily_intent_limit, 50)

    def test_pro_limit(self):
        self.assertEqual(TIER_POLICIES[SubscriptionTier.PRO].daily_intent_limit, 500)


# ============================================================
# 2. FDIA Gate
# ============================================================

class TestFDIAGate(unittest.TestCase):
    def test_community_no_fdia_gate(self):
        eng = _engine(SubscriptionTier.COMMUNITY)
        record = eng.meter_intent("u1", fdia_score=0.0)
        self.assertTrue(record.approved)

    def test_pro_passes_above_threshold(self):
        eng = _engine(SubscriptionTier.PRO)
        record = eng.meter_intent("u1", fdia_score=0.55)
        self.assertTrue(record.approved)

    def test_pro_fails_below_threshold(self):
        eng = _engine(SubscriptionTier.PRO)
        with self.assertRaises(FDIAGateError) as ctx:
            eng.meter_intent("u1", fdia_score=0.40)
        self.assertEqual(ctx.exception.tier, SubscriptionTier.PRO)
        self.assertAlmostEqual(ctx.exception.min_fdia, 0.50)

    def test_enterprise_fails_below_threshold(self):
        eng = _engine(SubscriptionTier.ENTERPRISE)
        with self.assertRaises(FDIAGateError):
            eng.meter_intent("u1", fdia_score=0.60)

    def test_enterprise_passes_at_threshold(self):
        eng = _engine(SubscriptionTier.ENTERPRISE)
        record = eng.meter_intent("u1", fdia_score=0.70)
        self.assertTrue(record.approved)

    def test_fdia_gate_error_message(self):
        eng = _engine(SubscriptionTier.PRO)
        with self.assertRaises(FDIAGateError) as ctx:
            eng.meter_intent("alice", fdia_score=0.10)
        self.assertIn("alice", str(ctx.exception))
        self.assertIn("pro", str(ctx.exception))


# ============================================================
# 3. Daily Limit
# ============================================================

class TestDailyLimit(unittest.TestCase):
    def test_community_limit_enforced(self):
        eng = _engine(SubscriptionTier.COMMUNITY)
        today = date.today().isoformat()
        # Manually set usage to limit
        eng._store._counts[("u1", today)] = 50
        with self.assertRaises(DailyLimitExceededError) as ctx:
            eng.meter_intent("u1", fdia_score=0.0)
        self.assertEqual(ctx.exception.limit, 50)

    def test_enterprise_no_limit(self):
        eng = _engine(SubscriptionTier.ENTERPRISE)
        today = date.today().isoformat()
        # Set usage very high
        eng._store._counts[("u1", today)] = 100_000
        # Should NOT raise DailyLimitExceededError
        record = eng.meter_intent("u1", fdia_score=0.75)
        self.assertIsNotNone(record)

    def test_pro_limit_increments(self):
        eng = _engine(SubscriptionTier.PRO)
        r = eng.meter_intent("u2", fdia_score=0.60)
        self.assertEqual(r.daily_usage, 1)
        r2 = eng.meter_intent("u2", fdia_score=0.60)
        self.assertEqual(r2.daily_usage, 2)

    def test_daily_limit_error_message(self):
        eng = _engine(SubscriptionTier.COMMUNITY)
        today = date.today().isoformat()
        eng._store._counts[("u3", today)] = 50
        with self.assertRaises(DailyLimitExceededError) as ctx:
            eng.meter_intent("u3", fdia_score=0.0)
        self.assertIn("u3", str(ctx.exception))


# ============================================================
# 4. Billing Record
# ============================================================

class TestBillingRecord(unittest.TestCase):
    def test_record_has_record_id(self):
        eng = _engine(SubscriptionTier.PRO)
        r = eng.meter_intent("u1", fdia_score=0.80)
        self.assertIsInstance(r.record_id, str)
        self.assertTrue(len(r.record_id) > 0)

    def test_record_tier_matches(self):
        eng = _engine(SubscriptionTier.ENTERPRISE)
        r = eng.meter_intent("u1", fdia_score=0.85)
        self.assertEqual(r.tier, SubscriptionTier.ENTERPRISE)

    def test_record_no_stripe_event_when_no_item(self):
        eng = _engine(SubscriptionTier.PRO, stripe_item=None)
        r = eng.meter_intent("u1", fdia_score=0.80)
        self.assertIsNone(r.stripe_event_id)

    def test_to_dict_serializable(self):
        import json
        eng = _engine(SubscriptionTier.PRO)
        r = eng.meter_intent("u1", fdia_score=0.80)
        d = r.to_dict()
        json.dumps(d)

    def test_to_dict_approved_true(self):
        eng = _engine(SubscriptionTier.PRO)
        r = eng.meter_intent("u1", fdia_score=0.80)
        d = r.to_dict()
        self.assertTrue(d["approved"])


# ============================================================
# 5. Stripe Integration (mocked)
# ============================================================

class TestStripeIntegration(unittest.TestCase):
    def test_stripe_called_when_item_id_provided(self):
        with patch(
            "rct_control_plane.payment_engine._stripe_create_usage_record",
            return_value="evt_abc123",
        ) as mock_stripe:
            eng = _engine(SubscriptionTier.PRO, stripe_item="si_test")
            r = eng.meter_intent("u1", fdia_score=0.80)
            mock_stripe.assert_called_once()
            self.assertEqual(r.stripe_event_id, "evt_abc123")

    def test_stripe_not_called_when_no_item(self):
        with patch(
            "rct_control_plane.payment_engine._stripe_create_usage_record"
        ) as mock_stripe:
            eng = _engine(SubscriptionTier.PRO, stripe_item=None)
            eng.meter_intent("u1", fdia_score=0.80)
            mock_stripe.assert_not_called()

    def test_stripe_failure_non_fatal(self):
        with patch(
            "rct_control_plane.payment_engine._stripe_create_usage_record",
            side_effect=StripeEventError("network timeout"),
        ):
            eng = _engine(SubscriptionTier.PRO, stripe_item="si_test")
            # Should NOT raise — billing continues without Stripe confirmation
            r = eng.meter_intent("u1", fdia_score=0.80)
            self.assertIsNone(r.stripe_event_id)

    def test_stripe_create_usage_record_raises_when_stripe_missing(self):
        """_stripe_create_usage_record should raise StripeEventError when stripe not installed."""
        import sys
        # Temporarily hide the stripe module
        original = sys.modules.get("stripe", None)
        sys.modules["stripe"] = None  # type: ignore
        try:
            with self.assertRaises((StripeEventError, ImportError, TypeError)):
                _stripe_create_usage_record("si_test", 1, "key-1")
        finally:
            if original is None:
                sys.modules.pop("stripe", None)
            else:
                sys.modules["stripe"] = original


# ============================================================
# 6. Usage Query
# ============================================================

class TestUsageQuery(unittest.TestCase):
    def test_get_usage_zero_initially(self):
        eng = _engine(SubscriptionTier.PRO)
        self.assertEqual(eng.get_usage("new-user"), 0)

    def test_get_usage_increments(self):
        eng = _engine(SubscriptionTier.PRO)
        eng.meter_intent("u1", fdia_score=0.80)
        eng.meter_intent("u1", fdia_score=0.80)
        self.assertEqual(eng.get_usage("u1"), 2)

    def test_get_records_returns_user_records(self):
        eng = _engine(SubscriptionTier.PRO)
        eng.meter_intent("u1", fdia_score=0.80)
        eng.meter_intent("u2", fdia_score=0.80)
        records = eng.get_records("u1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].user_id, "u1")

    def test_get_tier_policy_returns_correct_policy(self):
        eng = _engine()
        policy = eng.get_tier_policy(SubscriptionTier.PRO)
        self.assertIsInstance(policy, TierPolicy)
        self.assertEqual(policy.tier, SubscriptionTier.PRO)


# ============================================================
# 7. Multi-tier routing
# ============================================================

class TestMultiTierRouting(unittest.TestCase):
    def test_different_users_different_tiers(self):
        tier_map = {
            "alice": SubscriptionTier.ENTERPRISE,
            "bob": SubscriptionTier.PRO,
            "charlie": SubscriptionTier.COMMUNITY,
        }
        eng = PaymentEngine(get_tier=lambda uid: tier_map[uid])
        eng.meter_intent("charlie", fdia_score=0.0)
        eng.meter_intent("bob", fdia_score=0.60)
        eng.meter_intent("alice", fdia_score=0.85)
        self.assertEqual(eng.get_usage("charlie"), 1)
        self.assertEqual(eng.get_usage("bob"), 1)
        self.assertEqual(eng.get_usage("alice"), 1)

    def test_fdia_gate_independent_per_tier(self):
        tier_map = {
            "pro_user": SubscriptionTier.PRO,
            "ent_user": SubscriptionTier.ENTERPRISE,
        }
        eng = PaymentEngine(get_tier=lambda uid: tier_map[uid])
        # FDIA 0.65 passes PRO (≥0.50) but fails ENTERPRISE (≥0.70)
        eng.meter_intent("pro_user", fdia_score=0.65)
        with self.assertRaises(FDIAGateError):
            eng.meter_intent("ent_user", fdia_score=0.65)


if __name__ == "__main__":
    unittest.main()
