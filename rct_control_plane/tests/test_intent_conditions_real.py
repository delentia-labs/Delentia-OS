"""Structural oracles; these do not evaluate model understanding."""
import copy
import json

import pytest

from rct_control_plane.component_execution import CriterionVerification, Handler
from rct_control_plane.intent_conditions import (
    CriterionCapability, NecessaryCondition, validate_conditioned_program,
)
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.typed_intent import parse_intent


class Empty(PlanItem):
    pass


class Text(PlanItem):
    text: str


class Input(PlanItem):
    source: Text


def fixture():
    intent = parse_intent('Compare documents', json.dumps({
        'schema_version': 1, 'material_criteria': [{'id': 'compare',
        'statement': 'Compare documents', 'polarity': 'required',
        'source_quotes': ['Compare documents']}]}))
    registry = {
        'read': Handler(Empty, Text, 'observation', None),
        'transform': Handler(Input, Text, 'compute', lambda x: {'text': x.source.text}),
        'verify': Handler(Input, CriterionVerification, 'verify', lambda _: {}),
        'empty_verify': Handler(Empty, CriterionVerification, 'verify', lambda _: {}),
    }
    program = {'schema_version': 1, 'nodes': [
        {'id': 'read', 'handler': 'read', 'phase': 'observation'},
        {'id': 'transform', 'handler': 'transform', 'phase': 'compute',
         'depends_on': ['read'], 'inputs': {'source': 'read'}},
        {'id': 'verify', 'handler': 'verify', 'phase': 'verify', 'criteria': ['compare'],
         'depends_on': ['transform'], 'inputs': {'source': 'transform'}},
    ]}
    capabilities = {'compare': CriterionCapability(frozenset({'verify', 'empty_verify'}),
                     (NecessaryCondition('document', frozenset({'read'})),))}
    return intent, program, registry, capabilities


def test_transitive_typed_input_satisfies_condition_without_dispatch():
    intent, program, registry, capabilities = fixture()
    before = copy.deepcopy(program)
    result = validate_conditioned_program(intent, program, registry, {}, capabilities)
    assert len(result.nodes) == 3 and program == before
    assert intent.grants_execution is False


def test_complete_dag_with_ordering_only_evidence_is_rejected():
    intent, program, registry, capabilities = fixture()
    program['nodes'][-1].update(handler='empty_verify', inputs={})
    with pytest.raises(ValueError, match='not consumed'):
        validate_conditioned_program(intent, program, registry, {}, capabilities)


def test_literal_substitution_cannot_replace_required_observation():
    intent, program, registry, capabilities = fixture()
    program['nodes'][1].update(inputs={}, parameters={'source': {'text': 'invented'}})
    with pytest.raises(ValueError, match='not consumed'):
        validate_conditioned_program(intent, program, registry, {}, capabilities)


@pytest.mark.parametrize('case', ['missing', 'extra', 'verifier', 'unknown_verifier',
                                 'producer', 'empty_producer', 'duplicate', 'empty_id'])
def test_invalid_application_catalog_is_rejected(case):
    intent, program, registry, capabilities = fixture()
    condition = NecessaryCondition('document', frozenset({'read'}))
    if case == 'missing': capabilities = {}
    elif case == 'extra': capabilities['extra'] = capabilities['compare']
    elif case == 'verifier': capabilities['compare'] = CriterionCapability(frozenset({'empty_verify'}), (condition,))
    elif case == 'unknown_verifier': capabilities['compare'] = CriterionCapability(frozenset({'absent'}), (condition,))
    else:
        conditions = {
            'producer': (NecessaryCondition('document', frozenset({'absent'})),),
            'empty_producer': (NecessaryCondition('document', frozenset()),),
            'duplicate': (condition, condition),
            'empty_id': (NecessaryCondition(' ', frozenset({'read'})),),
        }[case]
        capabilities['compare'] = CriterionCapability(frozenset({'verify'}), conditions)
    with pytest.raises(ValueError):
        validate_conditioned_program(intent, program, registry, {}, capabilities)


def test_all_conditions_required_and_input_order_irrelevant():
    intent, program, registry, capabilities = fixture()
    capabilities['compare'] = CriterionCapability(frozenset({'verify'}), (
        NecessaryCondition('document', frozenset({'read'})),
        NecessaryCondition('transformed', frozenset({'transform'})),
    ))
    program['nodes'].reverse()
    assert validate_conditioned_program(intent, program, registry, {}, capabilities)
    verifier = program['nodes'][0]
    verifier.update(depends_on=['read'], inputs={'source': 'read'})
    with pytest.raises(ValueError, match='transformed'):
        validate_conditioned_program(intent, program, registry, {}, capabilities)
