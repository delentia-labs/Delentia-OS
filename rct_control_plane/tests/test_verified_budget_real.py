"""Governed real reads/SQLite with zero generation calls; no vendor-truth claim."""
import asyncio
import copy
import hashlib
import json
import os

import pytest

from rct_control_plane import autonomous_loop, mcp_server
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel
from rct_control_plane.verified_budget import BudgetPipeline, current_bytes, validate_receipts

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Verified quote execution needs POSIX descriptor-relative no-follow reads')


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path/'workspace';root.mkdir()
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    async def forbidden(*args, **kwargs):
        pytest.fail('Verified quote executor must not call the generation provider')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    return root


def setup(tmp_path, root, total='12500', budget='15000 THB', raw=None, currency='THB', final=True, extra_criteria=None):
    value = {'schema_version': 1, 'total': total, 'currency': currency, 'total_is_final': final}
    raw = json.dumps(value, separators=(',', ':')).encode() if raw is None else raw
    (root/'quote.json').write_bytes(raw)
    context = {'semantic_plan': {'budget': budget, 'quote_evidence': {'relative_path': 'quote.json', 'sha256': hashlib.sha256(raw).hexdigest()}}}
    criteria = [{'kind': 'json_object'}] + (extra_criteria or [])
    loop = _loop(tmp_path, 'verified', kernel=_FakeKernel(), mcp=mcp_server.mcp)
    return loop, context, criteria


@pytest.mark.parametrize('total,budget,within,remaining', [('12500','15000 THB',True,'2500.00'),
    ('15000','15000 THB',True,'0.00'), ('15000.01','15000 THB',False,'-0.01'),
    ('0.10','0.30 THB',True,'0.20'), ('0','1 THB',True,'1.00')])
def test_exact_arithmetic_full_dag_and_durable_receipts_without_model(tmp_path, world, total, budget, within, remaining):
    loop, context, criteria = setup(tmp_path, world, total, budget)
    before = (world/'quote.json').read_bytes();visible = []
    result = asyncio.run(loop.run('เทียบราคากับงบ', acceptance_criteria=criteria, planning_context=context, on_plan=visible.append))
    assert visible and result['executor'] == 'verified_budget_v1'
    assert result['semantic_verification']['satisfied'] and result['acceptance_verification']['satisfied']
    answer = json.loads(result['final_answer'])
    assert answer['within_budget'] is within and answer['remaining'] == remaining
    c = result['intent_contract']
    assert c['execution_status'] == 'complete' and c['state'] == 'criteria_satisfied'
    assert [r['component_id'] for r in c['execution_receipts']] == ['inspect_sources','compare_budget','compose_answer','prepare_C1','check_C1']
    assert [s['tool_name'] for s in result['steps'] if s.get('tool_name')] == ['delentia_read_repo_file']
    store = IntentContractStore(loop._persistence, 'verified')
    assert store.get(c['id']) == c
    validate_receipts(c['plan'], c['id'], 'verified', c['execution_receipts'])
    assert (world/'quote.json').read_bytes() == before


@pytest.mark.parametrize('raw', [b'not json', b'[]', b'{"schema_version":true,"total":"1","currency":"THB","total_is_final":true}',
    b'{"schema_version":1,"total":1,"currency":"THB","total_is_final":true}',
    b'{"schema_version":1,"total":"-1","currency":"THB","total_is_final":true}',
    b'{"schema_version":1,"total":"1","total":"2","currency":"THB","total_is_final":true}',
    b'{"schema_version":1,"total":NaN,"currency":"THB","total_is_final":true}',
    b'{"schema_version":1,"total":"1","currency":"THB","total_is_final":1}',
    b'{"schema_version":1,"total":"1","currency":"THB","total_is_final":true,"tax":7}',
    b' ' * 20001])
def test_invalid_or_truncated_quote_cannot_satisfy_json_only_criterion(tmp_path, world, raw):
    loop, context, criteria = setup(tmp_path, world, raw=raw)
    result = asyncio.run(loop.run('Compare with my budget', acceptance_criteria=criteria, planning_context=context, on_plan=lambda c: None))
    assert result['stopped_reason'] == 'waiting_for_clarification'
    assert not result['semantic_verification']['satisfied'] and not result['acceptance_verification']['satisfied']
    assert result['intent_contract']['execution_status'] == 'incomplete'
    assert not any(r['component_id'] == 'compare_budget' for r in result['intent_contract']['execution_receipts'])


@pytest.mark.parametrize('change', ['currency','scope','hash'])
def test_unresolved_currency_scope_and_hash_wait(tmp_path, world, change):
    loop, context, criteria = setup(tmp_path, world, currency='USD' if change=='currency' else 'THB', final=change!='scope')
    if change == 'hash':context['semantic_plan']['quote_evidence']['sha256'] = '0'*64
    result = asyncio.run(loop.run('Compare with my budget', acceptance_criteria=criteria, planning_context=context, on_plan=lambda c: None))
    assert result['stopped_reason'] == 'waiting_for_clarification' and not result['semantic_verification']['satisfied']


def test_input_wait_and_api_style_visible_plan_before_actual_read(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world, budget=None)
    waiting = asyncio.run(loop.run('เทียบราคากับงบ', acceptance_criteria=criteria, planning_context=context))
    c = waiting['intent_contract']
    assert waiting['stopped_reason']=='waiting_for_input' and not waiting['steps'] and 'execution_receipts' not in c
    ready = asyncio.run(loop.continue_intent(c['id'], c['version'], answers={'budget':'15,000 บาท'}))
    assert ready['stopped_reason']=='plan_ready' and not ready['steps']
    c = ready['intent_contract']
    finished = asyncio.run(loop.continue_intent(c['id'], c['version']))
    assert finished['semantic_verification']['satisfied']


def test_source_change_after_observation_refuses_acceptance_and_retains_partial_receipts(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world)
    def change(step):
        if step.tool_name:
            (world/'quote.json').write_text('{"changed":true}')
    result = asyncio.run(loop.run('Compare with my budget', acceptance_criteria=criteria, planning_context=context, on_plan=lambda c: None, on_step=change))
    assert result['stopped_reason']=='waiting_for_clarification'
    assert not result['semantic_verification']['satisfied']
    assert [r['component_id'] for r in result['intent_contract']['execution_receipts']] == ['inspect_sources','compare_budget']


def test_interrupt_after_read_has_durable_partial_state_and_no_automatic_restart(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world)
    shown = []
    def interrupt(step):
        if step.tool_name:raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(loop.run('Compare with my budget', acceptance_criteria=criteria, planning_context=context, on_plan=shown.append, on_step=interrupt))
    store = IntentContractStore(loop._persistence, 'verified')
    c = store.get(shown[0]['id'])
    assert c['state']=='running' and c['execution_status']=='partial'
    assert len(c['execution_receipts'])==2
    with pytest.raises(IntentContractError):store.claim(c['id'],c['version'])


def test_dependencies_answer_tamper_and_receipt_binding(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world)
    store = IntentContractStore(loop._persistence, 'verified')
    c = store.create('Compare with my budget',criteria,world,context)
    c = store.claim(c['id'],c['version'])
    pipeline = BudgetPipeline(c,'verified')
    with pytest.raises(ValueError):pipeline.complete('compare_budget',{})
    assert pipeline.finish('{}',[])[0]['kind']=='verified_budget'
    result = {'path':'quote.json','content_text':(world/'quote.json').read_text(),'truncated':False}
    pipeline.observe('delentia_read_repo_file',{'relative_path':'quote.json'},result)
    forged = {**pipeline.report,'within_budget':1}
    assert pipeline.finish(json.dumps(forged),[])
    bad = copy.deepcopy(pipeline.receipts);bad[0]['output_sha256']='0'*64
    with pytest.raises(IntentContractError):validate_receipts(c['plan'],c['id'],'verified',bad)
    with pytest.raises(IntentContractError):validate_receipts(c['plan'],c['id'],'other',pipeline.receipts)
    with pytest.raises(IntentContractError):validate_receipts(c['plan'],c['id'],'verified',list(reversed(pipeline.receipts)))


def test_revised_criteria_clear_old_receipts_before_new_claim(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world, extra_criteria=[{'kind':'contains','value':'missing literal'}])
    result = asyncio.run(loop.run('Compare with my budget',acceptance_criteria=criteria,planning_context=context,on_plan=lambda c: None))
    c=result['intent_contract'];assert c['state']=='waiting_for_clarification' and c['execution_receipts']
    store=IntentContractStore(loop._persistence,'verified')
    ready=store.claim(c['id'],c['version'],response='Remove literal criterion',criteria=[{'kind':'json_object'}])
    assert ready['state']=='plan_ready' and 'execution_receipts' not in ready
    assert store.get(ready['id'])==ready


@pytest.mark.parametrize('relative',['../outside.json','/tmp/outside.json','.env','a/../quote.json'])
def test_binding_paths_refuse_before_execution(tmp_path, world, relative):
    loop, context, criteria=setup(tmp_path,world)
    context['semantic_plan']['quote_evidence']['relative_path']=relative
    with pytest.raises(IntentContractError):
        asyncio.run(loop.run('Compare with my budget',acceptance_criteria=criteria,planning_context=context))


def test_freshness_reader_refuses_symlinks_and_fifo(tmp_path, world):
    (world/'target.json').write_text('{}');(world/'link.json').symlink_to(world/'target.json')
    with pytest.raises(OSError):current_bytes(world,'link.json')
    import os
    os.mkfifo(world/'pipe')
    with pytest.raises(ValueError):current_bytes(world,'pipe')


def test_governance_refusal_is_not_bypassed_by_deterministic_driver(tmp_path, world, monkeypatch):
    loop, context, criteria=setup(tmp_path,world)
    calls=[]
    async def deny(goal, tool, args):
        calls.append(tool)
        return loop._gate_refusal(tool,0.0,'Owner test policy refuses this read')
    monkeypatch.setattr(loop,'_notarised_pre_dispatch',deny)
    result=asyncio.run(loop.run('Compare with my budget',acceptance_criteria=criteria,planning_context=context,on_plan=lambda c: None))
    assert calls==['delentia_read_repo_file']
    assert result['stopped_reason']=='fdia_blocked' and not result['acceptance_verification']['satisfied']
    assert result['intent_contract']['execution_receipts']==[]


def test_http_contract_round_trip_zero_generation_actual_read(tmp_path, world, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel
    _, context, criteria=setup(tmp_path,world)
    monkeypatch.setattr(mcp_server,'_kernel',APIKernel(tmp_path))
    with TestClient(create_app()) as client:
        ready=client.post('/v1/agent/run',json={'goal':'เทียบราคากับงบ','namespace':'owner','acceptance_criteria':criteria,'planning_context':context})
        assert ready.status_code==200
        c=ready.json()['intent_contract'];assert c['state']=='plan_ready' and 'execution_receipts' not in c
        url=f"/v1/agent/intent-contracts/{c['id']}/continue"
        result=client.post(url,json={'namespace':'owner','version':c['version']})
        assert result.status_code==200,result.text
        assert result.json()['semantic_verification']['satisfied']
        assert result.json()['cost']['calls']==0
        assert client.post(url,json={'namespace':'owner','version':c['version']}).status_code==409
        assert client.get(f"/v1/agent/intent-contracts/{c['id']}?namespace=other").status_code==404


def test_arithmetic_is_independent_of_ambient_decimal_context(tmp_path, world):
    from decimal import localcontext
    loop, context, criteria=setup(tmp_path,world,total='12500.10')
    with localcontext() as ambient:
        ambient.prec=2
        result=asyncio.run(loop.run('Compare with my budget',acceptance_criteria=criteria,planning_context=context,on_plan=lambda c: None))
        assert ambient.prec==2
    assert result['semantic_verification']['satisfied']
    assert json.loads(result['final_answer'])['remaining']=='2499.90'


def test_unsupported_filesystem_capability_refuses_before_claim(tmp_path, world, monkeypatch):
    from rct_control_plane import verified_budget
    loop, context, criteria=setup(tmp_path,world)
    monkeypatch.setattr(verified_budget,'supports_verified_reads',lambda:False)
    with pytest.raises(IntentContractError,match='POSIX'):
        asyncio.run(loop.run('Compare with my budget',acceptance_criteria=criteria,planning_context=context))
