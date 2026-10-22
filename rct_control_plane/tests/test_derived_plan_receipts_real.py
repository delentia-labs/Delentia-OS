"""Real SQLite receipts, bounded derivation and pre-execution visibility."""
import asyncio
import copy
import json

import pytest

from rct_control_plane import autonomous_loop
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore, plan_digest
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel
from rct_control_plane.tests.test_rct_plan_context_real import context, finish


def store_at(tmp_path):
    return IntentContractStore(_loop(tmp_path, 'derive')._persistence, 'derive')


def test_goal_and_predicate_change_rebuild_prerequisites_with_provenance(tmp_path):
    store = store_at(tmp_path)
    a = store.create('ตอบภาษาไทยเรื่องน้ำ', [{'kind': 'language', 'value': 'th'}], tmp_path,
                     {'derive_from_criteria': True})
    b = store.create('คืน JSON', [{'kind': 'json_object'}], tmp_path, {'derive_from_criteria': True})
    assert a['plan']['planning_origin'] == b['plan']['planning_origin'] == 'criterion_derived'
    assert a['plan']['components'] != b['plan']['components']
    assert a['plan']['facts'][0]['text'] == 'ตอบภาษาไทยเรื่องน้ำ'
    assert a['plan']['facts'][1]['source'] == 'acceptance_criteria:C1'
    chain = a['plan']['backward_chain']['necessary_conditions'][0]
    assert [c['id'] for c in chain['prerequisites']] == ['prepare_C1', 'check_C1']
    assert chain['components'][0]['depends_on'] == ['prepare_C1']
    assert a['plan']['derivation']['semantic_completeness'] is False
    assert a['plan_sha256'] != b['plan_sha256']


def test_derived_revision_retains_original_and_protected_bytes(tmp_path):
    (tmp_path / 'source.md').write_text('original')
    store = store_at(tmp_path)
    criteria = [{'kind': 'file_unchanged', 'value': 'source.md'}, {'kind': 'language', 'value': 'th'}]
    c = store.create('รักษาไฟล์ ตอบไทย', criteria, tmp_path, {'derive_from_criteria': True})
    c = store.transition(store.claim(c['id'], c['version']), 'waiting_for_clarification')
    (tmp_path / 'source.md').write_text('externally changed')
    ready = store.claim(c['id'], c['version'], response='ยืนยันแก้เฉพาะรูปแบบ', revised_goal='รักษาไฟล์ คืน JSON',
                        criteria=[criteria[0], {'kind': 'json_object'}])
    assert ready['plan']['planning_origin'] == 'criterion_derived'
    assert ready['original_goal'] == 'รักษาไฟล์ ตอบไทย'
    assert ready['plan']['protected_sha256'] == c['plan']['protected_sha256']
    assert ready['planning_context']['facts'][0]['text'] == ready['goal']
    assert ready['plan_sha256'] == plan_digest(ready['plan'])
    assert store.get(c['id']) == ready


def test_transition_returns_own_receipt_even_when_next_claim_commits_during_audit(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    c = store.create('เทียบงบ', [{'kind': 'language', 'value': 'th'}], tmp_path, context())
    original_audit = store.db.append_audit
    other = []
    def racing_audit(**kwargs):
        original_audit(**kwargs)
        if kwargs['action'] == 'plan_ready':
            current = store.get(c['id'])
            other.append(store.claim(current['id'], current['version']))
    monkeypatch.setattr(store.db, 'append_audit', racing_audit)
    own = store.claim(c['id'], c['version'], answers={'budget': '15,000 บาท'})
    assert own['state'] == 'plan_ready' and own['version'] == 2
    assert other[0]['state'] == 'running' and other[0]['version'] == 3
    assert store.get(c['id']) == other[0]
    with pytest.raises(IntentContractError):
        store.claim(own['id'], own['version'])


def test_creation_receipt_cannot_inherit_later_running_claim(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    original_audit = store.db.append_audit
    def racing_audit(**kwargs):
        original_audit(**kwargs)
        if kwargs['action'] == 'plan_ready':
            store.claim(kwargs['entity_id'], 1)
    monkeypatch.setattr(store.db, 'append_audit', racing_audit)
    own = store.create('JSON', [{'kind': 'json_object'}], tmp_path)
    assert own['state'] == 'plan_ready' and own['version'] == 1
    assert store.get(own['id'])['state'] == 'running'


def test_plan_digest_detects_payload_drift_and_not_a_signature(tmp_path):
    store = store_at(tmp_path)
    c = store.create('ไทย', [{'kind': 'language', 'value': 'th'}], tmp_path, {'derive_from_criteria': True})
    changed = copy.deepcopy(c['plan']);changed['goal'] = 'changed'
    assert plan_digest(changed) != c['plan_sha256']
    assert plan_digest(dict(reversed(list(c['plan'].items())))) == c['plan_sha256']
    payload = {k: v for k, v in c.items() if k not in {'state', 'version', 'id'}}
    payload['plan'] = changed
    with store.db._connect() as conn:
        conn.execute('UPDATE intent_contracts SET payload=? WHERE id=?', (store._encode(payload), c['id']))
    with pytest.raises(IntentContractError, match='digest mismatch'):
        store.get(c['id'])


@pytest.mark.parametrize('planning_request', [{'derive_from_criteria': 1}, {'derive_from_criteria': 'true'},
                                     {'derive_from_criteria': True, 'approval': True}])
def test_derivation_request_is_strict_and_grants_no_authority(tmp_path, planning_request):
    with pytest.raises(IntentContractError):
        store_at(tmp_path).create('ไทย', [{'kind': 'language', 'value': 'th'}], tmp_path, planning_request)


def test_derived_plan_visible_before_any_model_then_existing_verifier_runs(tmp_path, monkeypatch):
    calls = []
    async def decide(*args, **kwargs):
        calls.append(1)
        return finish('คำตอบภาษาไทยเรื่องน้ำ')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    loop = _loop(tmp_path, 'derive', kernel=_FakeKernel())
    ready = asyncio.run(loop.run('ตอบไทยเรื่องน้ำ', acceptance_criteria=[{'kind': 'language', 'value': 'th'}],
                                planning_context={'derive_from_criteria': True}))
    assert ready['stopped_reason'] == 'plan_ready' and calls == []
    c = ready['intent_contract']
    result = asyncio.run(loop.continue_intent(c['id'], c['version']))
    assert result['acceptance_verification']['satisfied'] and calls == [1]


def test_cli_derive_flag_and_conflicting_options(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    from rct_control_plane import mcp_server
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, '_kernel', APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    async def decide(*args, **kwargs):
        return finish('คำตอบภาษาไทย')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    criteria = tmp_path / 'criteria.json';criteria.write_text(json.dumps([{'kind': 'language', 'value': 'th'}]))
    runner = CliRunner()
    ok = runner.invoke(cli, ['agent', 'ตอบไทย', '--criteria-file', str(criteria), '--derive-plan'])
    assert ok.exit_code == 0, ok.output
    assert 'criterion_derived' in ok.output and 'semantic_completeness' in ok.output
    assert runner.invoke(cli, ['agent', 'ไทย', '--derive-plan']).exit_code != 0
    assert runner.invoke(cli, ['agent', 'ไทย', '--derive-plan', '--criteria-file', str(criteria),
                               '--planning-context-file', str(criteria)]).exit_code != 0


def test_http_derived_plan_waits_before_execution_and_rejects_replay(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    from rct_control_plane import mcp_server
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, '_kernel', APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, 'mcp', _FakeMCP())
    calls = []
    async def decide(*args, **kwargs):
        calls.append(1)
        return finish('คำตอบภาษาไทย')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', decide)
    with TestClient(create_app()) as client:
        response = client.post('/v1/agent/run', json={'goal': 'ตอบไทย', 'namespace': 'owner',
            'acceptance_criteria': [{'kind': 'language', 'value': 'th'}],
            'planning_context': {'derive_from_criteria': True}})
        assert response.status_code == 200
        c = response.json()['intent_contract']
        assert c['state'] == 'plan_ready' and c['plan']['planning_origin'] == 'criterion_derived' and not calls
        url = f"/v1/agent/intent-contracts/{c['id']}/continue"
        payload = {'namespace': 'owner', 'version': c['version']}
        assert client.post(url, json=payload).json()['acceptance_verification']['satisfied']
        assert client.post(url, json=payload).status_code == 409
        assert calls == [1]


def test_maximum_criteria_derives_a_valid_bounded_graph(tmp_path):
    criteria = [{'kind': 'contains', 'value': f'ข้อ {i}'} for i in range(20)]
    c = store_at(tmp_path).create('รายการภาษาไทย', criteria, tmp_path, {'derive_from_criteria': True})
    assert len(c['plan']['components']) == 40
    assert len(c['plan']['facts']) == 21
