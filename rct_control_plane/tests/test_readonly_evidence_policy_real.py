"""Real HTTP evidence gate: operator configuration, actor/file/digest binding."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rct_control_plane import mcp_server
from rct_control_plane.api_auth import ApiTokenMiddleware
from rct_control_plane.readonly_service import ROUTE, ReadOnlyBoundary, install_route, load_policy
from rct_control_plane.tests import test_readonly_service_real as base
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel

service = base.service


def configured(service, tmp_path, age=0):
    _, body, _, root = service
    now = datetime.now(timezone.utc) - timedelta(seconds=age)
    req = {'schema_version': 1, 'policy': {'id': 'fresh', 'required_claim_ids': ['c1']},
           'max_age_seconds': 60,
           'observations': [{'id': 'o1', 'locator': 'alice.json', 'sha256': body['evidence']['sha256'], 'observed_at': now.isoformat()}],
           'claims': [{'id': 'c1', 'observation_id': 'o1', 'subject': 'quote', 'key': 'THB', 'value': '0.10', 'claimed_at': now.isoformat()}]}
    path = tmp_path / 'policy.json'
    policy_data = json.loads(path.read_text(encoding='utf-8'))
    policy_data['evidence_requirements'] = {'alice': {'alice.json': req}}
    path.write_text(json.dumps(policy_data), encoding='utf-8')
    policy = load_policy()
    app = FastAPI()
    install_route(app, policy, lambda actor: _loop(tmp_path, actor, kernel=_FakeKernel(), mcp=mcp_server.mcp))
    app.add_middleware(ApiTokenMiddleware)
    app.add_middleware(ReadOnlyBoundary, policy=policy)
    return TestClient(app), body, path


def confirm(client, c, actor='alice'):
    return client.post(ROUTE + '/' + c['id'] + '/confirm', headers={'Authorization': f'Bearer {actor}-token'},
                       json={'schema_version': '1', 'version': c['version'], 'plan_sha256': c['plan_sha256']})


@pytest.mark.parametrize('age,expected', [(0, 200), (120, 409)])
def test_http_gate_controls_confirmation(service, tmp_path, age, expected):
    client, body, _ = configured(service, tmp_path, age)
    planned = base.post(client, body)
    assert planned.status_code == 200
    c = planned.json()['contract']
    assert c['plan']['evidence_requirement']['schema_version'] == 1
    assert c['evidence_decision'] is None
    assert c['acquisition_links'] == []
    result = confirm(client, c)
    assert result.status_code == expected, result.text
    status = client.get(ROUTE + '/' + c['id'], headers={'Authorization': 'Bearer alice-token'}).json()['contract']
    if age:
        assert status['state'] == 'plan_ready' and not status['receipts'] and status['version'] == c['version']
    else:
        assert status['verified'] and status['evidence_decision']['satisfies_declared_policy']
        assert status['evidence_decision']['grants_execution'] is False
        link = status['acquisition_links'][0]
        receipt = next(r for r in status['receipts'] if r['component_id'] == 'inspect_sources')
        assert link == {'observation_id': 'o1', 'receipt_sha256': receipt['receipt_sha256'],
                        'tool_result_sha256': receipt['output']['tool_result_sha256'],
                        'source_sha256': body['evidence']['sha256'], 'source_locator': 'alice.json'}


def test_caller_cannot_replace_requirement_or_read_other_actor(service, tmp_path):
    client, body, _ = configured(service, tmp_path)
    assert base.post(client, {**body, 'evidence_requirement': {}}).status_code == 422
    c = base.post(client, body).json()['contract']
    assert confirm(client, c, 'bob').status_code == 404
    assert confirm(client, {**c, 'version': c['version'] + 1}).status_code == 409


def test_source_digest_and_changed_operator_policy_are_rejected(service, tmp_path):
    client, body, path = configured(service, tmp_path)
    changed = {**body, 'evidence': {**body['evidence'], 'sha256': '0' * 64}}
    assert base.post(client, changed).status_code == 409
    c = base.post(client, body).json()['contract']
    data = json.loads(path.read_text(encoding='utf-8'))
    data['evidence_requirements']['alice']['alice.json']['max_age_seconds'] = 999
    path.write_text(json.dumps(data), encoding='utf-8')
    assert confirm(client, c).status_code == 409


def test_operator_cannot_bind_another_actors_file(service, tmp_path):
    _, _, path = configured(service, tmp_path)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['evidence_requirements']['bob'] = data['evidence_requirements']['alice']
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='authorized actor files'):
        load_policy(os.environ['DELENTIA_READONLY_POLICY'])
