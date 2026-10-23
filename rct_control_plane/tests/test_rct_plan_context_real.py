"""Declared RCT plans: graph validity, initial wait, durable answers, real reads."""
import asyncio
import copy

import pytest

from rct_control_plane import autonomous_loop, mcp_server
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.rct_plan import validate_context
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel


def context(critical=True):
    return {'schema_version': 1, 'facts': [{'id': 'quote', 'text': 'ราคา 12,500 บาท', 'source': 'user-provided synthetic quote'}],
            'unknowns': [{'id': 'budget', 'question': 'งบสูงสุดกี่บาท?', 'critical': critical}],
            'assumptions': ['ราคาทั้งหมดใช้สกุลเงินบาท'],
            'components': [{'id': 'decide', 'action': 'compare', 'description': 'เทียบราคากับงบที่ยืนยัน',
                            'input_facts': ['quote'], 'requires': ['budget'], 'outputs': ['คำตอบภาษาไทยพร้อมเหตุผล'],
                            'criteria': ['C1']}]}


def finish(text):
    return {'action': 'finish', 'reasoning': 'scripted', 'final_answer': text, 'tool_name': None, 'tool_args': {}}


def test_critical_input_wait_survives_restart_and_cannot_be_bypassed(tmp_path, monkeypatch):
    seen = []
    async def no_model(*args, **kwargs):
        seen.append(kwargs.get('extra_context', ''))
        return finish('ราคานี้อยู่ในงบที่ยืนยัน')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', no_model)
    loop = _loop(tmp_path, 'initial', kernel=_FakeKernel())
    criteria = [{'kind': 'language', 'value': 'th'}]
    result = asyncio.run(loop.run('เทียบใบเสนอราคากับงบ', acceptance_criteria=criteria, planning_context=context(), on_plan=lambda c: None))
    c = result['intent_contract']
    assert result['stopped_reason'] == 'waiting_for_input' and seen == [] and result['steps'] == []
    assert 'งบสูงสุด' in result['clarification_question']
    fresh = _loop(tmp_path, 'initial', kernel=_FakeKernel())
    for answers in [None, {}, {'budget': ''}, {'budget': '15000', 'fake': 'anything'}]:
        with pytest.raises(IntentContractError):
            asyncio.run(fresh.continue_intent(c['id'], c['version'], answers=answers))
    ready = asyncio.run(fresh.continue_intent(c['id'], c['version'], answers={'budget': '15,000 บาท'}))
    assert ready['stopped_reason'] == 'plan_ready' and seen == []
    c2 = ready['intent_contract']
    assert c2['original_goal'] == c['original_goal'] and c2['revisions'][0]['user_answers']['budget'] == '15,000 บาท'
    assert c2['plan']['unknowns'][0]['answer'] == '15,000 บาท'
    assert c2['plan']['backward_chain']['necessary_conditions'][0]['components'][0]['requires'] == ['budget']
    done = asyncio.run(fresh.continue_intent(c2['id'], c2['version']))
    assert done['intent_contract']['state'] == 'criteria_satisfied' and '15,000 บาท' in seen[0]
    with pytest.raises(IntentContractError):
        asyncio.run(fresh.continue_intent(c['id'], c['version'], answers={'budget': 'replay'}))


def test_noncritical_unknown_is_visible_but_does_not_block_preparation(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'optional')._persistence, 'owner')
    c = store.create('สรุปราคา ไม่ต้องตัดสินงบ', [{'kind': 'language', 'value': 'th'}], tmp_path, context(False))
    assert c['state'] == 'plan_ready' and c['plan']['unknowns'][0]['answer'] is None
    assert c['plan']['facts'][0]['source'] == 'user-provided synthetic quote'


@pytest.mark.parametrize('fault', ['cycle', 'dangling', 'duplicate', 'uncovered', 'authority'])
def test_graph_refusals(fault):
    value = context()
    component = value['components'][0]
    if fault == 'cycle':component['depends_on'] = ['decide']
    elif fault == 'dangling':component['input_facts'] = ['invented']
    elif fault == 'duplicate':value['facts'].append(copy.deepcopy(value['facts'][0]))
    elif fault == 'uncovered':component['criteria'] = []
    else:component['approval'] = 'already authorized'
    with pytest.raises(IntentContractError):validate_context(value, {'C1'})


def test_same_reported_facts_support_different_explicit_goal_plans(tmp_path):
    from rct_control_plane.intent_contract import build_plan, validate_criteria
    thai = context(False)
    structured = copy.deepcopy(thai)
    structured['components'][0].update(action='transform_answer', description='จัดข้อมูลราคาเป็น JSON', outputs=['JSON object'])
    a = build_plan('ตอบภาษาไทย', validate_criteria([{'kind': 'language', 'value': 'th'}]), tmp_path, thai)
    b = build_plan('คืนข้อมูล JSON', validate_criteria([{'kind': 'json_object'}]), tmp_path, structured)
    assert a['facts'] == b['facts'] and a['components'] != b['components']
    assert a['planning_origin'] == b['planning_origin'] == 'user_declared'


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_contract_expands_omitted_thai_passage_through_real_mcp(tmp_path, monkeypatch, newline):
    root = tmp_path / 'workspace';root.mkdir()
    target = 'ราคาจริง 12,345 บาท น้ำ กำลัง'
    text = '\n'.join(f'line {i}: unrelated build detail ' + ('abc ' * 20) for i in range(400))
    text = text.replace('line 200:', target + '\nline 200:')
    (root / 'source.md').write_text(text, encoding='utf-8', newline=newline)
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    loop = _loop(tmp_path, 'expand-owner', kernel=_FakeKernel(), mcp=mcp_server.mcp)
    monkeypatch.setattr(mcp_server._kernel, '_persistence', loop._persistence)
    async def decide(goal, history, available_tools, llm_provider=None, **kwargs):
        if not history:
            return {'action': 'call_tool', 'tool_name': 'delentia_read_repo_file', 'tool_args': {'relative_path': 'source.md'}, 'reasoning': 'read'}
        if len(history) == 1:
            output = history[0].tool_result
            assert output['delta_compressed'] and target not in output['content']
            assert any(t['name'] == 'delentia_expand_tool_output' for t in available_tools)
            return {'action': 'call_tool', 'tool_name': 'delentia_expand_tool_output', 'tool_args': {'original_id': output['original_id'], 'query': 'ราคาจริง'}, 'reasoning': 'recover omitted evidence'}
        assert target in history[-1].tool_result['content']
        return finish(target)
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    result = asyncio.run(loop.run('Read source.md and answer in Thai', acceptance_criteria=[{'kind': 'contains', 'value': target}], on_plan=lambda c: None))
    assert result['intent_contract']['state'] == 'criteria_satisfied', result
    assert [s['tool_name'] for s in result['steps'][:2]] == ['delentia_read_repo_file', 'delentia_expand_tool_output']
    assert (root / 'source.md').read_text(encoding='utf-8') == text


@pytest.mark.parametrize('same_namespace', [True, False])
def test_stored_output_requires_current_episode_and_namespace(tmp_path, monkeypatch, same_namespace):
    from rct_control_plane.tool_output_store import ToolOutputStore
    loop = _loop(tmp_path, 'scope', kernel=_FakeKernel())
    store = ToolOutputStore(loop._persistence)
    original = store.save('scope' if same_namespace else 'other', 'read', 'private text')
    # Even with a leaked ID, the other namespace fails; a previous episode in
    # the same namespace also fails. Never dispatch to the raw owner MCP tool.
    loop._episode_compressions = [] if same_namespace else [{'original_id': original}]
    gate = asyncio.run(loop._pre_dispatch_gate('read', 'delentia_expand_tool_output', {'original_id': original}))
    assert gate['tool_result']['blocked'] and not loop._mcp.dispatched


def test_http_initial_wait_answers_and_plan_order(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    kernel = APIKernel(tmp_path)
    monkeypatch.setattr(mcp_server, '_kernel', kernel)
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    calls = []
    async def decide(*args, **kwargs):
        calls.append(1)
        return finish('ภาษาไทย')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    with TestClient(create_app()) as client:
        assert client.post('/v1/agent/run', json={'goal': 'test', 'planning_context': context()}).status_code == 400
        result = client.post('/v1/agent/run', json={'goal': 'เทียบราคา', 'namespace': 'owner',
            'acceptance_criteria': [{'kind': 'language', 'value': 'th'}], 'planning_context': context()})
        assert result.status_code == 200
        c = result.json()['intent_contract']
        assert c['state'] == 'waiting_for_input' and not calls
        url = f"/v1/agent/intent-contracts/{c['id']}/continue"
        assert client.post(url, json={'namespace': 'owner', 'version': c['version'], 'response': 'looks good'}).status_code == 409
        ready = client.post(url, json={'namespace': 'owner', 'version': c['version'], 'answers': {'budget': '15000'}})
        assert ready.status_code == 200 and ready.json()['stopped_reason'] == 'plan_ready' and not calls
        c2 = ready.json()['intent_contract']
        done = client.post(url, json={'namespace': 'owner', 'version': c2['version']})
        assert done.status_code == 200 and done.json()['acceptance_verification']['satisfied'] and len(calls) == 1


def test_cli_initial_questions_and_explicit_answers(tmp_path, monkeypatch):
    import json
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    kernel = APIKernel(tmp_path)
    monkeypatch.setattr(mcp_server, '_kernel', kernel)
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    calls = []
    async def decide(*args, **kwargs):
        calls.append(1)
        return finish('ภาษาไทย')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    paths = [tmp_path / n for n in ['criteria.json', 'context.json', 'answers.json']]
    for path, value in zip(paths, [[{'kind': 'language', 'value': 'th'}], context(), {'budget': '15000'}], strict=True):
        path.write_text(json.dumps(value, ensure_ascii=False))
    runner = CliRunner()
    waiting = runner.invoke(cli, ['agent', 'เทียบราคา', '--namespace', 'owner', '--criteria-file', str(paths[0]), '--planning-context-file', str(paths[1])])
    assert waiting.exit_code == 1 and 'งบสูงสุดกี่บาท' in waiting.output and not calls
    with kernel._persistence._connect() as conn:
        contract_id = conn.execute('SELECT id FROM intent_contracts WHERE namespace=?', ('owner',)).fetchone()[0]
    c = IntentContractStore(kernel._persistence, 'owner').get(contract_id)
    done = runner.invoke(cli, ['intent-contract', 'continue', contract_id, '--namespace', 'owner', '--version', str(c['version']), '--answers-file', str(paths[2])])
    assert done.exit_code == 0, done.output
    assert done.output.index('Plan before execution:') < done.output.index('criteria_satisfied') and len(calls) == 1


def test_confirmed_budget_is_evidence_for_verify_but_model_numbers_are_not(tmp_path, monkeypatch):
    root = tmp_path / 'workspace';root.mkdir();(root / 'quote.md').write_text('ราคา 12,500 บาท')
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    loop = _loop(tmp_path, 'budget-owner', kernel=_FakeKernel(), mcp=mcp_server.mcp)
    monkeypatch.setattr(mcp_server._kernel, '_persistence', loop._persistence)
    answer = ['ราคา 12,500 บาท อยู่ในงบ 15,000 บาท']
    async def decide(goal, history, available_tools, llm_provider=None, **kwargs):
        if not history:
            return {'action': 'call_tool', 'tool_name': 'delentia_read_repo_file', 'tool_args': {'relative_path': 'quote.md'}, 'reasoning': 'read'}
        return finish(answer[0])
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    waiting = asyncio.run(loop.run('อ่าน quote.md เทียบราคากับงบ', acceptance_criteria=[{'kind': 'language', 'value': 'th'}], planning_context=context()))
    c = waiting['intent_contract']
    ready = asyncio.run(loop.continue_intent(c['id'], c['version'], answers={'budget': '15,000 บาท'}))['intent_contract']
    done = asyncio.run(loop.continue_intent(ready['id'], ready['version']))
    assert done['intent_verification']['aligned_with_intent'], done['intent_verification']
    assert 'ungrounded_values' not in done['intent_verification']['grounding']['flags']
    # A value invented by the model is never added to the verification context.
    answer[0] = 'ราคา 12,500 บาท อยู่ในงบ 99,999 บาท'
    # Fresh contract uses the same confirmed user input; its answer is unsupported.
    loop2 = _loop(tmp_path, 'budget-other', kernel=_FakeKernel(), mcp=mcp_server.mcp)
    monkeypatch.setattr(mcp_server._kernel, '_persistence', loop2._persistence)
    initial = asyncio.run(loop2.run('อ่าน quote.md เทียบราคากับงบ', acceptance_criteria=[{'kind': 'language', 'value': 'th'}], planning_context=context()))['intent_contract']
    prepared = asyncio.run(loop2.continue_intent(initial['id'], initial['version'], answers={'budget': '15,000 บาท'}))['intent_contract']
    bad = asyncio.run(loop2.continue_intent(prepared['id'], prepared['version']))
    assert not bad['intent_verification']['aligned_with_intent']
    assert 'ungrounded_values' in bad['intent_verification']['grounding']['flags']
