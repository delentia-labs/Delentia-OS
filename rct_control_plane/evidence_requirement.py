"""Versioned application-supplied evidence gate for intent contract claims."""
from datetime import datetime
import json
from typing import Literal

from pydantic import Field

from rct_control_plane.evidence_assessment import (
    EvidencePolicy, Observation, SourceClaim, apply_evidence_policy, assess_evidence,
)
from rct_control_plane.rct_plan import PlanItem


class EvidenceRequirement(PlanItem):
    schema_version: Literal[1] = 1
    policy: EvidencePolicy
    observations: list[Observation] = Field(max_length=256)
    claims: list[SourceClaim] = Field(max_length=256)
    max_age_seconds: int = Field(ge=0, le=315360000)


def parse_requirement(value: dict) -> EvidenceRequirement:
    # JSON validation preserves strict wire types while decoding ISO timestamps.
    return EvidenceRequirement.model_validate_json(json.dumps(value, allow_nan=False))


def check_requirement(value: dict, now: datetime):
    requirement = parse_requirement(value)
    assessment = assess_evidence(requirement.observations, requirement.claims,
                                 now=now, max_age_seconds=requirement.max_age_seconds)
    return apply_evidence_policy(requirement.policy, assessment)
