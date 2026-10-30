"""HTTP intent clarification/confirm/restart over real SQLite and MCP reads.

The fixture kernel avoids model dependency; this proves protocol sequencing,
not capable-model understanding or native GUI behaviour.
"""
import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import agent_factory, api_tokens, autonomous_loop, mcp_server
from rct_control_plane.api import create_app
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='verified quote acquisition needs POSIX no-follow')


def test_ask_answer_plan_confirm_receipts_and_restart(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    raw = b'{"schema_version":1,"total":"100.10","currency":"THB","total_is_final":true}'
    (root / 'quote.json').write_bytes(raw)
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    monkeypatch.delenv('DELENTIA_READONLY_POLICY', raising=False)
    monkeypatch.delenv('DELENTIA_API_TOKEN', raising=False)
    token_path = tmp_path / 'tokens.json'
    token_path.write_text(json.dumps({'users': [{'name': actor, 'token_sha256': api_tokens.hash_token(actor)} for actor in ('alice', 'bob')]}), encoding='utf-8')
    monkeypatch.setenv('DELENTIA_API_TOKENS_FILE', str(token_path))
    def factory(kernel, namespace, **kwargs):
        return _loop(tmp_path, namespace, mcp=mcp_server.mcp)
    monkeypatch.setattr(agent_factory, 'build_governed_loop', factory)
    monkeypatch.setattr(mcp_server._kernel, '_persistence', _loop(tmp_path, 'alice')._persistence)
    async def forbidden(*args, **kwargs):
        pytest.fail('deterministic workflow must not generate with a model')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    client = TestClient(create_app())
    headers = {'Authorization': 'Bearer alice'}
    response = client.post('/v1/agent/run', headers=headers, json={
        'goal': 'เทียบราคากับงบ', 'namespace': 'bob', 'acceptance_criteria': [{'kind': 'json_object'}],
        'planning_context': {'semantic_plan': {'quote_evidence': {'relative_path': 'quote.json', 'sha256': hashlib.sha256(raw).hexdigest()}}}})
    assert response.status_code == 200, response.text
    waiting = response.json()['intent_contract']
    assert waiting['state'] == 'waiting_for_input'
    assert not waiting.get('execution_receipts')
    path = '/v1/agent/intent-contracts/' + waiting['id']
    assert client.get(path, headers={'Authorization': 'Bearer bob'}).status_code == 404
    ready_response = client.post(path + '/continue', headers=headers,
        json={'version': waiting['version'], 'answers': {'budget': '150 THB'}})
    assert ready_response.status_code == 200, ready_response.text
    ready = ready_response.json()['intent_contract']
    assert ready['state'] == 'plan_ready' and not ready.get('execution_receipts')
    assert client.post(path + '/continue', headers=headers, json={'version': waiting['version']}).status_code == 409
    done_response = client.post(path + '/continue', headers=headers, json={'version': ready['version']})
    assert done_response.status_code == 200, done_response.text
    done = done_response.json()['intent_contract']
    assert done['state'] == 'criteria_satisfied' and done['execution_status'] == 'complete'
    assert len(done['execution_receipts']) == 5
    assert done['execution_report']['remaining'] == '49.90'
    restarted = TestClient(create_app())
    assert restarted.get(path, headers=headers).json() == done
    assert restarted.post(path + '/continue', headers=headers, json={'version': done['version']}).status_code == 409
    assert (root / 'quote.json').read_bytes() == raw
