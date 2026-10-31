"""Pure R1 evidence assessment. No I/O, source authentication or truth certification.

Freshness concerns a source's claimed date. Conflicts mean different literal
values for the same caller-defined subject/key, not semantic contradiction.
This opt-in building block does not change existing contract acceptance.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from rct_control_plane.rct_plan import PlanItem


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value


class Observation(PlanItem):
    id: str = Field(min_length=1, max_length=80)
    locator: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> Observation:
        aware(self.observed_at)
        return self


class SourceClaim(PlanItem):
    id: str = Field(min_length=1, max_length=80)
    observation_id: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    claimed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time(self) -> SourceClaim:
        if self.claimed_at is not None:
            aware(self.claimed_at)
        return self


class ClaimAssessment(PlanItem):
    claim_id: str
    observation_id: str
    freshness: Literal["unknown", "current", "stale", "future"]
    conflicting_claim_ids: list[str]
    truth_verified: Literal[False] = False


class EvidenceAssessment(PlanItem):
    schema_version: Literal[1] = 1
    claims: list[ClaimAssessment]
    needs_review: bool
    scope: Literal["claimed_date_and_literal_disagreement"] = "claimed_date_and_literal_disagreement"


def observe(observation_id: str, locator: str, content: bytes, observed_at: datetime) -> Observation:
    """Hash exactly the bytes supplied by the acquisition caller."""
    if not isinstance(content, bytes):
        raise ValueError("observation content must be bytes")
    return Observation(id=observation_id, locator=locator,
                       sha256=hashlib.sha256(content).hexdigest(), observed_at=observed_at)


def assess_evidence(observations: list[Observation], claims: list[SourceClaim], *,
                    now: datetime, max_age_seconds: int) -> EvidenceAssessment:
    aware(now)
    if type(max_age_seconds) is not int or not 0 <= max_age_seconds <= 315360000:
        raise ValueError("max_age_seconds must be an integer in 0..315360000")
    if len(observations) > 256 or len(claims) > 256:
        raise ValueError("evidence inventory exceeds 256 items")
    by_id = {o.id: o for o in observations}
    if len(by_id) != len(observations) or len({c.id for c in claims}) != len(claims):
        raise ValueError("duplicate evidence identity")
    if any(o.observed_at > now for o in observations):
        raise ValueError("observation time is later than evaluation time")
    results = []
    for claim in claims:
        if claim.observation_id not in by_id:
            raise ValueError("claim has no linked observation")
        observed = by_id[claim.observation_id]
        date = claim.claimed_at
        if date is None:
            freshness = "unknown"
        elif date > observed.observed_at:
            freshness = "future"
        elif now - date > timedelta(seconds=max_age_seconds):
            freshness = "stale"
        else:
            freshness = "current"
        conflicts = sorted(c.id for c in claims if c.id != claim.id
                           and (c.subject, c.key) == (claim.subject, claim.key) and c.value != claim.value)
        results.append(ClaimAssessment(claim_id=claim.id, observation_id=claim.observation_id,
                                      freshness=freshness, conflicting_claim_ids=conflicts))
    # Even a current, nonconflicting claim is not certified true or authoritative.
    return EvidenceAssessment(claims=results, needs_review=not results or any(
        c.freshness != "current" or c.conflicting_claim_ids for c in results))
