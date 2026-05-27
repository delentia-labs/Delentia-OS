"""
Payment Engine — Agentic Metered Billing

Three subscription tiers for RCT OS API access:

    Community  — free tier, limited to 50 intents/day, FDIA ≥ 0.0 (no gate)
    Pro        — $49/month,  limited to 500 intents/day, FDIA ≥ 0.50
    Enterprise — $299/month, unlimited intents, FDIA ≥ 0.70

Usage Flow:
    1. ``PaymentEngine.meter_intent(user_id, fdia_score)``
       → validate tier gate, write billing record, return ``BillingRecord``
    2. Caller may call ``PaymentEngine.get_usage(user_id)`` to read daily usage.
    3. Stripe calls are made via ``_stripe_create_usage_record()`` (patched in tests).

PAYMENT_ENGINE_VERSION = "1.0"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

PAYMENT_ENGINE_VERSION = "1.0"


# ============================================================
# Subscription Tiers
# ============================================================

class SubscriptionTier(str, Enum):
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class TierPolicy:
    tier: SubscriptionTier
    monthly_price_usd: float    # 0 for Community
    daily_intent_limit: int     # 0 = unlimited
    min_fdia: float             # minimum FDIA score to gate execution


TIER_POLICIES: Dict[SubscriptionTier, TierPolicy] = {
    SubscriptionTier.COMMUNITY: TierPolicy(
        tier=SubscriptionTier.COMMUNITY,
        monthly_price_usd=0.0,
        daily_intent_limit=50,
        min_fdia=0.0,
    ),
    SubscriptionTier.PRO: TierPolicy(
        tier=SubscriptionTier.PRO,
        monthly_price_usd=49.0,
        daily_intent_limit=500,
        min_fdia=0.50,
    ),
    SubscriptionTier.ENTERPRISE: TierPolicy(
        tier=SubscriptionTier.ENTERPRISE,
        monthly_price_usd=299.0,
        daily_intent_limit=0,       # unlimited
        min_fdia=0.70,
    ),
}


# ============================================================
# Billing Record
# ============================================================

@dataclass
class BillingRecord:
    record_id: str
    user_id: str
    tier: SubscriptionTier
    fdia_score: float
    date: str                   # ISO-8601 date
    daily_usage: int            # after this record
    stripe_event_id: Optional[str]
    billed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    approved: bool = True

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "tier": self.tier.value,
            "fdia_score": round(self.fdia_score, 6),
            "date": self.date,
            "daily_usage": self.daily_usage,
            "stripe_event_id": self.stripe_event_id,
            "billed_at": self.billed_at,
            "approved": self.approved,
        }


# ============================================================
# Errors
# ============================================================

class BillingError(Exception):
    """Base class for billing errors."""


class FDIAGateError(BillingError):
    """FDIA score too low for the user's tier."""

    def __init__(self, user_id: str, tier: SubscriptionTier, fdia: float, min_fdia: float):
        self.user_id = user_id
        self.tier = tier
        self.fdia = fdia
        self.min_fdia = min_fdia
        super().__init__(
            f"user={user_id} tier={tier.value}: FDIA {fdia:.3f} < minimum {min_fdia:.3f}"
        )


class DailyLimitExceededError(BillingError):
    """Daily intent limit exceeded for the user's tier."""

    def __init__(self, user_id: str, tier: SubscriptionTier, used: int, limit: int):
        self.user_id = user_id
        self.tier = tier
        self.used = used
        self.limit = limit
        super().__init__(
            f"user={user_id} tier={tier.value}: daily limit {limit} exceeded (used {used})"
        )


class StripeEventError(BillingError):
    """Failed to create a Stripe usage record (non-fatal in metered billing)."""


# ============================================================
# Stripe stub (patched in tests)
# ============================================================

def _stripe_create_usage_record(
    subscription_item_id: str,
    quantity: int,
    idempotency_key: str,
) -> str:
    """
    Create a Stripe usage record for a metered subscription item.

    Returns the Stripe event ID.

    This function makes a real HTTP call via the ``stripe`` Python SDK.
    It is intentionally NOT imported at module level — tests patch it directly
    via ``unittest.mock.patch("rct_control_plane.payment_engine._stripe_create_usage_record")``.
    """
    try:
        import stripe  # type: ignore  # noqa: F401  (optional dep)
        record = stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            {"quantity": quantity, "action": "increment"},
            idempotency_key=idempotency_key,
        )
        return record.id
    except Exception as exc:
        raise StripeEventError(str(exc)) from exc


# ============================================================
# Usage Store (in-memory; replace with DB in prod)
# ============================================================

class _UsageStore:
    """Thread-unsafe in-memory daily usage counter."""

    def __init__(self) -> None:
        # (user_id, date_str) → count
        self._counts: Dict[Tuple[str, str], int] = {}

    def increment(self, user_id: str, date_str: str) -> int:
        key = (user_id, date_str)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def get(self, user_id: str, date_str: str) -> int:
        return self._counts.get((user_id, date_str), 0)

    def reset(self, user_id: str, date_str: str) -> None:
        self._counts.pop((user_id, date_str), None)

    def clear(self) -> None:
        self._counts.clear()


# ============================================================
# PaymentEngine
# ============================================================

class PaymentEngine:
    """
    Agentic billing engine for RCT OS.

    Args:
        get_tier:   callable ``(user_id: str) → SubscriptionTier``
                    (override in tests with a simple dict lookup)
        stripe_item_id_for: callable ``(user_id: str) → Optional[str]``
                    Returns the Stripe subscription item ID for metered billing,
                    or None to skip Stripe (Community / unregistered).
    """

    def __init__(
        self,
        get_tier: Callable[[str], SubscriptionTier],
        stripe_item_id_for: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self._get_tier = get_tier
        self._stripe_item_id_for = stripe_item_id_for or (lambda uid: None)
        self._store = _UsageStore()
        self._records: List[BillingRecord] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def meter_intent(self, user_id: str, fdia_score: float) -> BillingRecord:
        """
        Gate and bill one intent execution.

        1. Resolve the user's tier.
        2. Check FDIA gate: fdia_score ≥ policy.min_fdia (raises FDIAGateError).
        3. Check daily limit (raises DailyLimitExceededError).
        4. Increment usage counter.
        5. Post Stripe usage record (non-fatal; StripeEventError is caught).
        6. Return a BillingRecord.

        Raises:
            FDIAGateError:            FDIA score below tier minimum.
            DailyLimitExceededError:  Daily intent limit exceeded.
        """
        tier = self._get_tier(user_id)
        policy = TIER_POLICIES[tier]
        today = date.today().isoformat()

        # Gate 1 — FDIA
        if fdia_score < policy.min_fdia:
            raise FDIAGateError(user_id, tier, fdia_score, policy.min_fdia)

        # Gate 2 — daily limit
        if policy.daily_intent_limit > 0:
            current_usage = self._store.get(user_id, today)
            if current_usage >= policy.daily_intent_limit:
                raise DailyLimitExceededError(user_id, tier, current_usage, policy.daily_intent_limit)

        # Increment
        new_usage = self._store.increment(user_id, today)

        # Stripe (non-fatal)
        stripe_event_id: Optional[str] = None
        stripe_item = self._stripe_item_id_for(user_id)
        if stripe_item:
            idempotency_key = f"rct-intent-{user_id}-{today}-{new_usage}"
            try:
                stripe_event_id = _stripe_create_usage_record(
                    stripe_item, 1, idempotency_key
                )
            except StripeEventError:
                pass  # non-fatal — billing can be reconciled later

        record = BillingRecord(
            record_id=str(uuid.uuid4()),
            user_id=user_id,
            tier=tier,
            fdia_score=fdia_score,
            date=today,
            daily_usage=new_usage,
            stripe_event_id=stripe_event_id,
        )
        self._records.append(record)
        return record

    def get_usage(self, user_id: str) -> int:
        """Return today's usage count for a user."""
        return self._store.get(user_id, date.today().isoformat())

    def get_records(self, user_id: str) -> List[BillingRecord]:
        """Return all billing records for a user."""
        return [r for r in self._records if r.user_id == user_id]

    def get_tier_policy(self, tier: SubscriptionTier) -> TierPolicy:
        return TIER_POLICIES[tier]
