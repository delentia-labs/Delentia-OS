"""Adapter/coverage protocol tests with scripted replies, not model capability."""
import asyncio
import copy
import json

import pytest
from pydantic import ValidationError

from rct_control_plane.typed_intent import parse_intent, propose_intent, validate_intent_program
from rct_control_plane.llm_provider import LLMProvider
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.component_execution import Handler, CriterionVerification

GOAL = 'สรุปรายงาน และห้ามส่งอีเมล'
DATA = {'schema_version': 1, 'material_criteria': [{'id': 'summary', 'statement': 'สรุปรายงาน', 'polarity': 'required', 'source_quotes': ['สรุปรายงาน']}],
        'constraints': [{'id': 'no_email', 'statement': 'ห้ามส่งอีเมล', 'polarity': 'prohibited', 'source_quotes': ['ห้ามส่งอีเมล']}], 'unknowns': []}


class Fake(LLMProvider):
    def __init__(self, reply): self.reply, self.calls = reply, []
    async def complete(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.reply


def test_adapter_preserves_thai_negation_and_requests_review():
    provider = Fake(json.dumps(DATA, ensure_ascii=False))
    result = asyncio.run(propose_intent(GOAL, provider))
    assert result.status == 'needs_review' and not result.grants_execution
    assert result.proposal.constraints[0].polarity == 'prohibited'
    assert len(provider.calls) == 1
    assert json.loads(provider.calls[0][0])['user_goal'] == GOAL
    assert provider.calls[0][1]['json_mode'] is True


@pytest.mark.parametrize('mutation', ['quote', 'duplicate', 'version', 'tool', 'polarity'])
def test_malformed_or_ungrounded_proposals_are_rejected(mutation):
    data = copy.deepcopy(DATA)
    if mutation == 'quote': data['material_criteria'][0]['source_quotes'] = ['invented source']
    if mutation == 'duplicate': data['constraints'][0]['id'] = 'summary'
    if mutation == 'version': data['schema_version'] = 2
    if mutation == 'tool': data['tool'] = 'write_file'
    if mutation == 'polarity': data['constraints'][0]['polarity'] = 'ignore'
    with pytest.raises((ValueError, ValidationError)):
        parse_intent(GOAL, json.dumps(data))


def test_invalid_goal_never_dispatches_and_bad_output_is_not_retried():
    provider = Fake('not JSON')
    with pytest.raises(ValueError): asyncio.run(propose_intent('', provider))
    assert not provider.calls
    with pytest.raises(ValueError): asyncio.run(propose_intent(GOAL, provider))
    assert len(provider.calls) == 1


class Empty(PlanItem):
    pass


def program(ids):
    return {'schema_version': 1, 'nodes': [{'id': key, 'handler': 'verify', 'phase': 'verify', 'criteria': [key]} for key in ids]}


def registry():
    return {'verify': Handler(Empty, CriterionVerification, 'verify', lambda _: {})}


def test_complete_graph_missing_prohibition_is_not_complete_intent_coverage():
    intent = parse_intent(GOAL, json.dumps(DATA))
    with pytest.raises(ValueError, match='each criterion'):
        validate_intent_program(intent, program(['summary']), registry(), {})
    parsed = validate_intent_program(intent, program(['summary', 'no_email']), registry(), {})
    assert len(parsed.nodes) == 2


def test_critical_unknown_requires_bound_answer_before_program_validation():
    data = copy.deepcopy(DATA)
    data['unknowns'] = [{'id': 'source', 'question': 'รายงานฉบับใด?', 'critical': True, 'source_quotes': ['รายงาน']}]
    intent = parse_intent(GOAL, json.dumps(data))
    assert intent.status == 'needs_clarification'
    with pytest.raises(ValueError, match='unresolved'):
        validate_intent_program(intent, program(['summary', 'no_email']), registry(), {})
    assert validate_intent_program(intent, program(['summary', 'no_email']), registry(), {'source': 'report.txt'})


def test_english_multi_intent_uses_same_schema():
    goal = 'Summarize the report and compare the totals. Do not email.'
    data = {'schema_version': 1, 'material_criteria': [
        {'id': 'summary', 'statement': 'Summary', 'polarity': 'required', 'source_quotes': ['Summarize the report']},
        {'id': 'compare', 'statement': 'Comparison', 'polarity': 'required', 'source_quotes': ['compare the totals']}],
        'constraints': [{'id': 'no_email', 'statement': 'No email', 'polarity': 'prohibited', 'source_quotes': ['Do not email']}], 'unknowns': []}
    intent = parse_intent(goal, json.dumps(data))
    assert len(intent.proposal.material_criteria) == 2
    with pytest.raises(ValueError):
        validate_intent_program(intent, program(['summary', 'no_email']), registry(), {})
