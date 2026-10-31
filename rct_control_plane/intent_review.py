"""Explicit review bindings for opt-in typed intent contracts.

The authenticated service supplies current bindings independently of the user
confirmation. This module authenticates neither identities nor source truth.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.typed_intent import IntentProposal, parse_intent


class ReviewBinding(PlanItem):
    actor: str = Field(min_length=1, max_length=200)
    workspace_root: str = Field(min_length=1, max_length=4096)
    policy_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    catalog_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class IntentReview(PlanItem):
    schema_version: Literal[1]
    binding: ReviewBinding
    proposal: IntentProposal


class IntentConfirmation(PlanItem):
    contract_id: str
    version: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def validate_review(value: dict, goal: str, criteria: list, actor: str, workspace: str) -> dict:
    if type(value.get('schema_version')) is not int:
        raise ValueError('review schema version must be an integer')
    intent = parse_intent(goal, json.dumps(value.get("proposal"), allow_nan=False))
    parsed = IntentReview.model_validate(value)
    if intent.proposal.unknowns:
        raise ValueError('resolve typed intent questions before attaching review')
    ids = {item.id for item in [*intent.proposal.material_criteria, *intent.proposal.constraints]}
    if ids != {item['id'] for item in criteria}:
        raise ValueError('review obligations must match contract criteria')
    if parsed.binding.actor != actor or parsed.binding.workspace_root != workspace:
        raise ValueError('review actor/workspace binding mismatch')
    return parsed.model_dump(mode='json')


def check_confirmation(contract: dict, actor: str, current_binding: dict | None,
                       confirmation: dict | None) -> None:
    review = validate_review(contract['plan']['intent_review'], contract['goal'],
                             contract['plan']['criteria'], actor, contract['plan']['workspace'])
    current = ReviewBinding.model_validate(current_binding)
    confirmed = IntentConfirmation.model_validate(confirmation)
    if current.model_dump() != review['binding']:
        raise ValueError('review authorization policy or catalog changed')
    if (confirmed.contract_id != contract['id'] or confirmed.version != contract['version']
            or confirmed.plan_sha256 != contract['plan_sha256']):
        raise ValueError('confirmation must bind the current contract/version/plan')
