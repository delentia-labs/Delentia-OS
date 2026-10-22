"""Development regression cases, NOT a held-out semantic accuracy benchmark."""
import asyncio
import json

import pytest

from rct_control_plane import autonomous_loop
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore, plan_digest
from rct_control_plane.semantic_plan import compile_request, validate_budget
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel
from rct_control_plane.tests.test_rct_plan_context_real import finish


FACT = {'id': 'quote', 'text': 'ราคา 12,500 บาท / Quote total 12,500 THB', 'source': 'user-provided synthetic quote'}
CRITERIA = [{'kind': 'language', 'value': 'th'}]


def request(budget=None, facts=None):
    return {'semantic_plan': {'facts': [FACT] if facts is None else facts, 'budget': budget}}


@pytest.mark.parametrize('goal,task', [
    ('สรุปใบเสนอราคานี้', 'summary'), ('ช่วยสรุปข้อมูลที่ส่งให้', 'summary'),
    ('Summarize this quotation', 'summary'), ('Summarise this evidence', 'summary'), ('Give a summary', 'summary'),
    ('เทียบใบเสนอราคากับงบ', 'budget_compare'), ('เปรียบเทียบราคากับงบสูงสุด', 'budget_compare'),
    ('ราคานี้อยู่ในงบไหม', 'budget_compare'), ('Compare this quotation with my budget', 'budget_compare'),
    ('Can I afford this quote?', 'budget_compare'), ('Is this within budget?', 'budget_compare')])
def test_bilingual_development_goals_infer_task_and_dependencies(tmp_path, goal, task):
    store = IntentContractStore(_loop(tmp_path, 'semantic')._persistence, 'semantic')
    c = store.create(goal, CRITERIA, tmp_path, request())
    plan = c['plan']
    assert plan['semantic_planning']['task'] == task
    assert plan['planning_origin'] == 'bounded_semantic_rules'
    ids = {component['id'] for component in plan['components']}
    assert ('compare_budget' in ids) == (task == 'budget_compare')
    assert c['state'] == ('waiting_for_input' if task == 'budget_compare' else 'plan_ready')
    chain = {component['id'] for component in plan['backward_chain']['necessary_conditions'][0]['prerequisites']}
    assert chain == ids
    assert plan['semantic_planning']['sources'][0]['status'] == 'user_reported'
    assert plan['semantic_planning']['classification']['status'] == 'rule_inferred'
    assert c['plan_sha256'] == plan_digest(plan)


@pytest.mark.parametrize('goal', ['write a production service', 'แปลข้อความนี้', 'Compare quotes',
    'Do not compare this with my budget', 'ห้ามเทียบราคากับงบ', 'Summarize and compare with my budget'])
def test_unsupported_negated_and_ambiguous_goals_refuse_before_model(goal):
    with pytest.raises(IntentContractError, match='unsupported or ambiguous'):
        compile_request(goal, [{'id': 'C1', 'kind': 'language', 'value': 'th'}], request())


@pytest.mark.parametrize('value', ['yes', 'looks good', '15000', '0 THB', '-1 THB', 'NaN THB',
                                  '15,00 บาท', 'THB 100 USD', '1e5 THB', '$100', '1000000000000001 THB'])
def test_budget_answer_needs_amount_and_currency(value):
    with pytest.raises(IntentContractError):
        validate_budget(value)


@pytest.mark.parametrize('value', ['15,000 บาท', '15000 THB', 'THB 15000', '99.50 USD', '1 EUR'])
def test_budget_formats(value):
    validate_budget(value)


def test_same_facts_different_goals_produce_different_task_components(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'same-facts')._persistence, 'same-facts')
    a = store.create('สรุปราคา', CRITERIA, tmp_path, request())
    b = store.create('เทียบราคากับงบ', CRITERIA, tmp_path, request())
    assert [f for f in a['plan']['facts'] if f['id'].startswith('source_')] == [f for f in b['plan']['facts'] if f['id'].startswith('source_')]
    assert a['plan']['components'] != b['plan']['components']
    assert a['state'] == 'plan_ready' and b['state'] == 'waiting_for_input'


def test_inferred_wait_restart_exact_answers_and_provenance(tmp_path, monkeypatch):
    calls = []
    async def decide(*args, **kwargs):
        calls.append(kwargs.get('extra_context', ''))
        return finish('ราคาอยู่ในงบที่ยืนยัน 15,000 บาท')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    loop = _loop(tmp_path, 'semantic-wait', kernel=_FakeKernel())
    result = asyncio.run(loop.run('เทียบราคากับงบ', acceptance_criteria=CRITERIA, planning_context=request()))
    c = result['intent_contract']
    assert result['stopped_reason'] == 'waiting_for_input' and calls == []
    fresh = _loop(tmp_path, 'semantic-wait', kernel=_FakeKernel())
    for value in ['yes', '15000', '0 THB']:
        with pytest.raises(IntentContractError):
            asyncio.run(fresh.continue_intent(c['id'], c['version'], answers={'budget': value}))
    ready = asyncio.run(fresh.continue_intent(c['id'], c['version'], answers={'budget': '15,000 บาท'}))
    assert ready['stopped_reason'] == 'plan_ready' and not calls
    c2 = ready['intent_contract']
    assert c2['plan']['planning_origin'] == 'bounded_semantic_rules'
    assert c2['revisions'][0]['provenance'] == 'confirmed_user_input'
    done = asyncio.run(fresh.continue_intent(c2['id'], c2['version']))
    assert done['acceptance_verification']['satisfied'] and len(calls) == 1
    assert '15,000 บาท' in calls[0]


def test_missing_sources_inferred_and_declared_budget_does_not_fill_source(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'source-wait')._persistence, 'source-wait')
    c = store.create('Compare the quote with my budget', CRITERIA, tmp_path, request('15000 THB', facts=[]))
    assert c['state'] == 'waiting_for_input'
    assert {q['id'] for q in c['plan']['clarification_questions']} == {'source_text'}
    c2 = store.claim(c['id'], c['version'], answers={'source_text': 'Quote total 12500 THB'})
    assert c2['state'] == 'plan_ready'
    assert c2['plan']['semantic_planning']['sources'] == []  # no fabricated observed source


def test_revision_to_budget_task_waits_again_without_model(tmp_path, monkeypatch):
    from rct_control_plane import mcp_server
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', tmp_path)
    async def forbidden(*args, **kwargs):
        pytest.fail('Replanning must not invoke the model')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    loop = _loop(tmp_path, 'revision', kernel=_FakeKernel())
    store = IntentContractStore(loop._persistence, 'revision')
    c = store.create('Summarize the quote', CRITERIA, tmp_path, request())
    c = store.transition(store.claim(c['id'], c['version']), 'waiting_for_clarification')
    result = asyncio.run(loop.continue_intent(c['id'], c['version'], response='Change to budget comparison',
                                            revised_goal='Compare this quote with my budget'))
    assert result['stopped_reason'] == 'waiting_for_input' and not result['steps']
    assert result['intent_contract']['original_goal'] == 'Summarize the quote'
    assert 'งบสูงสุด' in result['clarification_question']


@pytest.mark.parametrize('bad', [{'semantic_plan': {'facts': [FACT], 'approval': True}},
    {'semantic_plan': {'facts': [FACT, FACT]}}, {'semantic_plan': {}, 'authority': True}])
def test_schema_refuses_authority_and_duplicate_sources(tmp_path, bad):
    with pytest.raises(IntentContractError):
        IntentContractStore(_loop(tmp_path, 'bad')._persistence, 'bad').create('Summarize this', CRITERIA, tmp_path, bad)


def test_http_semantic_wait_and_bad_budget_are_not_model_calls(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    from rct_control_plane import mcp_server
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, '_kernel', APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    async def forbidden(*args, **kwargs):
        pytest.fail('No model before budget confirmation')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    with TestClient(create_app()) as client:
        response = client.post('/v1/agent/run', json={'goal': 'เทียบราคากับงบ', 'namespace': 'owner',
            'acceptance_criteria': CRITERIA, 'planning_context': request()})
        assert response.status_code == 200
        c = response.json()['intent_contract'];assert c['state'] == 'waiting_for_input'
        url = f"/v1/agent/intent-contracts/{c['id']}/continue"
        assert client.post(url, json={'namespace': 'owner', 'version': c['version'], 'answers': {'budget': 'yes'}}).status_code == 409
        ready = client.post(url, json={'namespace': 'owner', 'version': c['version'], 'answers': {'budget': '15000 THB'}})
        assert ready.status_code == 200 and ready.json()['stopped_reason'] == 'plan_ready'


def test_cli_request_file_exposes_inferred_question(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    from rct_control_plane import mcp_server
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, '_kernel', APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    criteria_file = tmp_path/'criteria.json';criteria_file.write_text(json.dumps(CRITERIA))
    context_file = tmp_path/'context.json';context_file.write_text(json.dumps(request()))
    result = CliRunner().invoke(cli, ['agent', 'เทียบราคากับงบ', '--criteria-file', str(criteria_file),
        '--planning-context-file', str(context_file)])
    assert result.exit_code == 1 and 'งบสูงสุด' in result.output


def test_maximum_inputs_validate_and_do_not_claim_source_verification(tmp_path):
    facts = [{**FACT, 'id': f'quote_{i}'} for i in range(20)]
    criteria = [{'kind': 'contains', 'value': f'item {i}'} for i in range(20)]
    store = IntentContractStore(_loop(tmp_path, 'max')._persistence, 'max')
    c = store.create('Compare with my budget', criteria, tmp_path, request('15000 THB', facts))
    assert c['state'] == 'plan_ready' and len(c['plan']['components']) == 43
    assert len(c['plan']['facts']) == 41
    assert store.get(c['id']) == c
    assert all(source['status'] == 'user_reported' for source in c['plan']['semantic_planning']['sources'])
