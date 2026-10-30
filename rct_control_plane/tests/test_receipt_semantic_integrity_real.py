"""Well-hashed receipts must still match typed source/compute/verdict data."""
import asyncio
import copy
import json
import os

import pytest

from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.tests import test_verified_budget_real as budget_tests
from rct_control_plane.verified_budget import BudgetPipeline, digest, validate_receipts

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Verified budget acquisition requires POSIX no-follow descriptors')
world = budget_tests.world


def completed(tmp_path, world):
    loop, context, criteria = budget_tests.setup(tmp_path, world, raw=None)
    prepared = asyncio.run(loop.run('Compare within budget', acceptance_criteria=criteria, planning_context=context))
    assert prepared['stopped_reason'] == 'plan_ready' and not prepared['steps']
    visible = prepared['intent_contract']
    result = asyncio.run(loop.continue_intent(visible['id'], visible['version']))
    assert result['stopped_reason'] == 'llm_finished', {k: result.get(k) for k in ('stopped_reason', 'clarification_question', 'plan_approval')}
    return result['intent_contract']


def rehash(receipts):
    previous = '0' * 64
    for receipt in receipts:
        receipt['previous_sha256'] = previous
        receipt['output_sha256'] = digest(receipt['output'])
        receipt['receipt_sha256'] = digest({k: v for k, v in receipt.items() if k != 'receipt_sha256'})
        previous = receipt['receipt_sha256']


@pytest.mark.parametrize('mutation', ['false_verdict', 'other_criterion', 'truthy_verdict', 'wrong_total',
    'wrong_remainder', 'wrong_composed_report', 'wrong_prepared_report', 'different_source_path', 'different_source_hash', 'invalid_tool_hash', 'wrong_type'])
def test_rehashed_inconsistent_receipts_are_rejected(tmp_path, world, mutation):
    contract = completed(tmp_path, world)
    receipts = copy.deepcopy(contract['execution_receipts'])
    by_id = {r['component_id']: r['output'] for r in receipts}
    if mutation == 'false_verdict': by_id['check_C1']['satisfied'] = False
    elif mutation == 'other_criterion': by_id['check_C1']['criterion_id'] = 'C999'
    elif mutation == 'truthy_verdict': by_id['check_C1']['satisfied'] = 1
    elif mutation == 'wrong_total': by_id['compare_budget']['quote_total'] = '0.00'
    elif mutation == 'wrong_remainder': by_id['compare_budget']['remaining'] = '999999.00'
    elif mutation == 'wrong_composed_report': by_id['compose_answer']['within_budget'] = False
    elif mutation == 'wrong_prepared_report': by_id['prepare_C1']['budget_limit'] = '1.00'
    elif mutation == 'different_source_path': by_id['inspect_sources']['relative_path'] = 'other.json'
    elif mutation == 'different_source_hash': by_id['inspect_sources']['sha256'] = '0' * 64
    elif mutation == 'invalid_tool_hash': by_id['inspect_sources']['tool_result_sha256'] = 'not-a-hash'
    else: by_id['compare_budget']['quote_total'] = 12500
    rehash(receipts)  # Hash/chain validation alone would accept these changes.
    with pytest.raises(IntentContractError, match='semantic or type mismatch'):
        validate_receipts(contract['plan'], contract['id'], 'verified', receipts)


def test_historical_receipts_do_not_reexecute_file_predicates(tmp_path, world):
    loop, context, criteria = budget_tests.setup(tmp_path, world, extra_criteria=[{'kind': 'file_unchanged', 'value': 'quote.json'}])
    prepared = asyncio.run(loop.run('Compare within budget', acceptance_criteria=criteria, planning_context=context))
    assert prepared['stopped_reason'] == 'plan_ready' and not prepared['steps']
    visible = prepared['intent_contract']
    result = asyncio.run(loop.continue_intent(visible['id'], visible['version']))
    contract = result['intent_contract']
    (world / 'quote.json').write_text('later document', encoding='utf-8')
    # Valid historical observation remains inspectable after the source changes.
    validate_receipts(contract['plan'], contract['id'], 'verified', contract['execution_receipts'])
    assert IntentContractStore(loop._persistence, 'verified').get(contract['id'])['execution_status'] == 'complete'


def test_partial_observation_is_inspectable_without_claiming_completion(tmp_path, world):
    contract = completed(tmp_path, world)
    validate_receipts(contract['plan'], contract['id'], 'verified', contract['execution_receipts'][:1])


def test_report_and_answer_cannot_drift_together_from_completed_arithmetic(tmp_path, world):
    loop, context, criteria = budget_tests.setup(tmp_path, world)
    store = IntentContractStore(loop._persistence, 'verified')
    contract = store.claim(store.create('Compare within budget', criteria, world, context)['id'], 1)
    pipeline = BudgetPipeline(contract, 'verified')
    raw = (world / 'quote.json').read_text(encoding='utf-8')
    pipeline.observe('delentia_read_repo_file', {'relative_path': 'quote.json'},
                     {'content_text': raw, 'path': 'quote.json', 'truncated': False})
    assert pipeline.error is None
    pipeline.report['quote_total'] = '0.00'
    differences = pipeline.finish(json.dumps(pipeline.report), [])
    assert differences and 'completed computation' in differences[0]['observed']
    assert [r['component_id'] for r in pipeline.receipts] == ['inspect_sources', 'compare_budget']


@pytest.mark.parametrize('mutation', ['wrong_report', 'missing_report', 'incomplete_receipts', 'missing_receipts'])
def test_contract_lookup_cannot_present_inconsistent_stored_report_as_complete(tmp_path, world, mutation):
    contract = completed(tmp_path, world)
    from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop
    store = IntentContractStore(_loop(tmp_path, 'verified')._persistence, 'verified')
    if mutation == 'wrong_report': contract['execution_report']['remaining'] = '999999.00'
    elif mutation == 'missing_report': contract.pop('execution_report')
    elif mutation == 'missing_receipts': contract.pop('execution_receipts')
    else: contract['execution_receipts'] = contract['execution_receipts'][:1]
    store.transition(contract, 'criteria_satisfied')
    with pytest.raises(IntentContractError, match='invalid stored execution receipts'):
        store.get(contract['id'])


@pytest.mark.parametrize('kind,value', [('contains', 'missing business condition'), ('language', 'th')])
def test_historical_pure_verdict_must_match_recorded_report(tmp_path, world, kind, value):
    from rct_control_plane.intent_contract import plan_digest
    contract = completed(tmp_path, world)
    plan = copy.deepcopy(contract['plan'])
    receipts = copy.deepcopy(contract['execution_receipts'])
    # A coherent local hash chain is not proof of criterion satisfaction.
    # Keep the typed graph and report intact, but bind an unsatisfied criterion.
    plan['criteria'][0]['kind'] = kind
    plan['criteria'][0]['value'] = value
    for receipt in receipts:
        receipt['plan_sha256'] = plan_digest(plan)
    rehash(receipts)
    with pytest.raises(IntentContractError, match='semantic or type mismatch'):
        validate_receipts(plan, contract['id'], 'verified', receipts)


def test_changed_budget_after_clarification_invalidates_history_and_stale_versions(tmp_path, world):
    loop, context, criteria = budget_tests.setup(
        tmp_path, world, budget=None,
        extra_criteria=[{'kind': 'contains', 'value': 'missing business condition'}],
    )
    waiting = asyncio.run(loop.run('เทียบราคากับงบ', acceptance_criteria=criteria, planning_context=context))['intent_contract']
    ready = asyncio.run(loop.continue_intent(waiting['id'], waiting['version'], answers={'budget': '15000 THB'}))['intent_contract']
    failed = asyncio.run(loop.continue_intent(ready['id'], ready['version']))['intent_contract']
    assert failed['state'] == 'waiting_for_clarification'
    assert failed['execution_report']['within_budget'] is True
    old_receipts = copy.deepcopy(failed['execution_receipts'])
    store = IntentContractStore(loop._persistence, 'verified')
    replanned = store.claim(failed['id'], failed['version'], response='ตรวจ JSON แล้วถามงบใหม่', criteria=[{'kind': 'json_object'}])
    assert replanned['state'] == 'waiting_for_input'
    assert all(key not in replanned for key in ('execution_receipts', 'execution_report', 'execution_status'))
    with pytest.raises(IntentContractError):
        store.claim(waiting['id'], waiting['version'], answers={'budget': '15000 THB'})
    changed = store.claim(replanned['id'], replanned['version'], answers={'budget': '10000 THB'})
    assert changed['state'] == 'plan_ready'
    assert all(key not in changed for key in ('execution_receipts', 'execution_report', 'execution_status'))
    with pytest.raises(IntentContractError):
        validate_receipts(changed['plan'], changed['id'], 'verified', old_receipts)
    with pytest.raises(IntentContractError):
        store.claim(replanned['id'], replanned['version'], answers={'budget': '15000 THB'})
    final = asyncio.run(loop.continue_intent(changed['id'], changed['version']))['intent_contract']
    assert final['state'] == 'criteria_satisfied'
    assert final['execution_report']['within_budget'] is False
    assert final['execution_report']['remaining'] == '-2500.00'
    assert final['execution_report']['budget_limit'] == '10000.00'
    assert final['execution_receipts'][0]['run_version'] > old_receipts[0]['run_version']
