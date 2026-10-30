"""Criterion verdicts, pre-read validation and execution snapshot integrity."""
import copy

import pytest
from pydantic import Field

from rct_control_plane.component_execution import (
    ComponentScheduler, CriterionVerification, Handler, VerificationRejected,
)
from rct_control_plane.rct_plan import PlanItem


class Empty(PlanItem):
    pass


class Number(PlanItem):
    value: int


class ReadNumber(PlanItem):
    source: Number


class Rule(PlanItem):
    threshold: int = Field(gt=0)


class RuleInput(PlanItem):
    rule: Rule


class Constrained(PlanItem):
    source: Number
    limit: int = Field(gt=0)


def criterion_program():
    return {'schema_version': 1, 'nodes': [
        {'id': 'source', 'handler': 'read', 'phase': 'observation'},
        {'id': 'check', 'handler': 'check', 'phase': 'verify', 'depends_on': ['source'],
         'inputs': {'source': 'source'}, 'criteria': ['C1']},
        {'id': 'after', 'handler': 'after', 'phase': 'verify', 'depends_on': ['check'],
         'inputs': {'source': 'check'}},
    ]}


class AfterInput(PlanItem):
    source: CriterionVerification


def criterion_engine(verdict, receipts, after=None):
    registry = {
        'read': Handler(Empty, Number, 'observation', None),
        'check': Handler(ReadNumber, CriterionVerification, 'verify', lambda i: verdict),
        'after': Handler(AfterInput, Number, 'verify', after or (lambda i: {'value': 1})),
    }
    return ComponentScheduler(criterion_program(), registry, ['C1'], {}, lambda k, v: receipts.append((k, v)))


@pytest.mark.parametrize('verdict', [
    {'criterion_id': 'C1', 'satisfied': False},
    {'criterion_id': 'C2', 'satisfied': True},
    {'criterion_id': 'C2', 'satisfied': False},
])
def test_negative_or_misbound_verdict_cannot_publish_completion_or_release_dependents(verdict):
    receipts, effects = [], []
    scheduler = criterion_engine(verdict, receipts, lambda i: effects.append('ran') or {'value': 1})
    scheduler.observe('source', {'value': 2})
    with pytest.raises(VerificationRejected) as error:
        scheduler.drain('verify')
    assert error.value.criterion_id == 'C1'
    assert error.value.expected == {'criterion_id': 'C1', 'satisfied': True}
    assert error.value.observed == verdict
    assert [key for key, _ in receipts] == ['source'] and not effects
    with pytest.raises(ValueError):
        scheduler.require_complete()
    with pytest.raises(ValueError, match='reconciliation'):
        scheduler.drain('verify')


@pytest.mark.parametrize('value', ['true', 1, None, 'false'])
def test_truthy_untyped_verdict_is_not_verification(value):
    receipts = []
    scheduler = criterion_engine({'criterion_id': 'C1', 'satisfied': value}, receipts)
    scheduler.observe('source', {'value': 2})
    with pytest.raises(ValueError):
        scheduler.drain('verify')
    assert [key for key, _ in receipts] == ['source']


def test_bound_positive_verdict_persists_before_dependent_runs():
    receipts, seen = [], []
    def after(inputs):
        seen.append(copy.deepcopy(receipts))
        return {'value': 1}
    scheduler = criterion_engine({'criterion_id': 'C1', 'satisfied': True}, receipts, after)
    scheduler.observe('source', {'value': 2})
    assert scheduler.drain('verify') == 2
    scheduler.require_complete()
    assert [key for key, _ in seen[0]] == ['source', 'check']


@pytest.mark.parametrize('kind', ['no_typed_verdict', 'multiple_criteria', 'missing_implementation', 'generated_observation'])
def test_invalid_verifier_registration_is_refused_before_any_observation(kind):
    nodes = [{'id': 'check', 'handler': 'verify', 'phase': 'verify', 'criteria': ['C1']}]
    handler = Handler(Empty, CriterionVerification, 'verify', lambda i: {'criterion_id': 'C1', 'satisfied': True})
    criteria = ['C1']
    if kind == 'no_typed_verdict':
        handler = Handler(Empty, Number, 'verify', lambda i: {'value': 1})
    elif kind == 'multiple_criteria':
        nodes[0]['criteria'] = criteria = ['C1', 'C2']
    elif kind == 'missing_implementation':
        handler = Handler(Empty, CriterionVerification, 'verify', None)
    else:
        nodes = [{'id': 'source', 'handler': 'verify', 'phase': 'observation'}]
        handler = Handler(Empty, Number, 'observation', lambda i: {'value': 1})
        criteria = []
    with pytest.raises(ValueError):
        ComponentScheduler({'schema_version': 1, 'nodes': nodes}, {'verify': handler}, criteria, {}, lambda *a: pytest.fail('no receipt'))


@pytest.mark.parametrize('limit', [0, -1, True, '5', None])
def test_static_invalid_input_refused_before_source_read(limit):
    program = {'schema_version': 1, 'nodes': [
        {'id': 'source', 'handler': 'read', 'phase': 'observation'},
        {'id': 'compute', 'handler': 'compute', 'phase': 'compute', 'depends_on': ['source'],
         'inputs': {'source': 'source'}, 'parameters': {'limit': limit}},
    ]}
    registry = {'read': Handler(Empty, Number, 'observation', None),
                'compute': Handler(Constrained, Number, 'compute', lambda i: {'value': i.limit})}
    with pytest.raises(ValueError):
        ComponentScheduler(program, registry, [], {}, lambda *a: pytest.fail('no receipt'))


def test_nested_program_and_inspection_views_cannot_mutate_execution():
    program = {'schema_version': 1, 'nodes': [
        {'id': 'compute', 'handler': 'compute', 'phase': 'compute', 'parameters': {'rule': {'threshold': 5}}, 'requires': ['answer']},
    ]}
    answers = {'answer': 'confirmed'}
    scheduler = ComponentScheduler(program, {'compute': Handler(RuleInput, Number, 'compute', lambda i: {'value': i.rule.threshold})}, [], answers, lambda *a: None)
    program['nodes'][0]['parameters']['rule']['threshold'] = 99
    answers['answer'] = None
    scheduler.program.nodes[0].parameters['rule']['threshold'] = 88
    scheduler.nodes['compute'].parameters['rule']['threshold'] = 77
    scheduler.answers['answer'] = None
    assert scheduler.drain('compute') == 1
    scheduler.outputs['compute']['value'] = 999
    assert scheduler.outputs['compute']['value'] == 5
    scheduler.require_complete()


def test_output_inspection_cannot_replace_observed_values_after_receipt():
    from rct_control_plane.tests.test_component_execution_real import engine
    receipts = []
    scheduler = engine(callback=lambda k, v: receipts.append((k, v)))
    scheduler.observe('a', {'value': 2})
    scheduler.outputs['a']['value'] = 999
    scheduler.observe('b', {'value': 3})
    scheduler.drain('compute')
    assert scheduler.outputs['double']['value'] == 10
    assert receipts[0] == ('a', {'value': 2})


@pytest.mark.parametrize('reenter_at', ['handler', 'callback'])
def test_reentrant_handler_or_callback_does_not_execute_a_node_twice(reenter_at):
    calls, receipts = [], []
    scheduler = None
    def run(inputs):
        calls.append('run')
        if reenter_at == 'handler' and len(calls) == 1:
            assert scheduler.drain('compute') == 0
        return {'value': 1}
    def receipt(key, output):
        receipts.append(key)
        if reenter_at == 'callback' and len(receipts) == 1:
            assert scheduler.drain('compute') == 0
    scheduler = ComponentScheduler({'schema_version': 1, 'nodes': [
        {'id': 'compute', 'handler': 'compute', 'phase': 'compute'}]},
        {'compute': Handler(Empty, Number, 'compute', run)}, [], {}, receipt)
    assert scheduler.drain('compute') == 1
    scheduler.require_complete()
    assert calls == ['run'] and receipts == ['compute']


def test_failed_verification_cannot_be_reset_through_public_status():
    scheduler = criterion_engine({'criterion_id': 'C1', 'satisfied': False}, [])
    scheduler.observe('source', {'value': 2})
    with pytest.raises(VerificationRejected):
        scheduler.drain('verify')
    assert scheduler.failed == 'check'
    with pytest.raises(AttributeError):
        scheduler.failed = None
    with pytest.raises(ValueError):
        scheduler.require_complete()
