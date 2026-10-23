"""Real auth, HTTP, SQLite, scheduler and source reads; no model generation."""
import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rct_control_plane import api_tokens, mcp_server
from rct_control_plane.api_auth import ApiTokenMiddleware
from rct_control_plane.readonly_service import ROUTE, ReadOnlyBoundary, install_route, load_policy
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeKernel, _loop


@pytest.fixture
def service(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    raw = b'{"schema_version":1,"total":"0.10","currency":"THB","total_is_final":true}'
    (root / 'alice.json').write_bytes(raw)
    (root / 'bob.json').write_bytes(raw)
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    tokens = tmp_path / 'tokens.json'
    tokens.write_text(json.dumps({'users': [{'name': a, 'token_sha256': api_tokens.hash_token(a + '-token')} for a in ('alice', 'bob')]}))
    monkeypatch.setenv('DELENTIA_API_TOKENS_FILE', str(tokens))
    monkeypatch.delenv('DELENTIA_API_TOKEN', raising=False)
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps({'schema_version': '1', 'workspace_id': 'local', 'workspace_root': str(root),
        'actor_files': {'alice': ['alice.json'], 'bob': ['bob.json']}}))
    monkeypatch.setenv('DELENTIA_READONLY_POLICY', str(path))
    policy = load_policy()
    app = FastAPI()
    calls = []

    async def runner(payload, request):
        actor = request.state.delentia_user
        calls.append(actor)
        loop = _loop(tmp_path, actor, kernel=_FakeKernel(), mcp=mcp_server.mcp)
        return await loop.run(payload['goal'], acceptance_criteria=payload['acceptance_criteria'],
                              planning_context=payload['planning_context'])

    install_route(app, policy, runner)
    app.add_middleware(ApiTokenMiddleware)
    app.add_middleware(ReadOnlyBoundary, policy=policy)
    body = {'schema_version': '1', 'executor_version': 'verified_budget_v1', 'workspace_id': 'local',
            'budget': '0.30 THB', 'evidence': {'relative_path': 'alice.json', 'sha256': hashlib.sha256(raw).hexdigest()}}
    return TestClient(app), body, calls, root


def post(client, body, actor='alice'):
    return client.post(ROUTE, json=body, headers={'Authorization': 'Bearer ' + actor + '-token'})


def test_plan_is_presented_before_any_execution(service):
    client, body, calls, root = service
    before = (root / 'alice.json').read_bytes()
    response = post(client, body)
    assert response.status_code == 200, response.text
    result = response.json()['result']
    assert result['stopped_reason'] == 'plan_ready'
    assert not result['steps']
    assert result['intent_contract']['plan']['semantic_planning']['executor'] == 'verified_budget_v1'
    assert not result['intent_contract'].get('execution_receipts')
    assert calls == ['alice'] and (root / 'alice.json').read_bytes() == before


@pytest.mark.parametrize('field,value', [('schema_version', True), ('executor_version', 'v2'),
    ('tool', 'write_file'), ('namespace', 'bob'), ('goal', 'write a file'), ('planning_context', {})])
def test_request_cannot_select_general_execution(service, field, value):
    client, body, calls, _ = service
    body[field] = value
    assert post(client, body).status_code == 422
    assert not calls


@pytest.mark.parametrize('change', ['actor', 'workspace', 'traversal', 'secret', 'unknown'])
def test_unauthorized_read_never_reaches_runner(service, change):
    client, body, calls, _ = service
    actor = 'alice'
    if change == 'actor':
        actor = 'bob'
    elif change == 'workspace':
        body['workspace_id'] = 'other'
    else:
        body['evidence']['relative_path'] = {'traversal': '../alice.json', 'secret': '.env', 'unknown': 'new.json'}[change]
    assert post(client, body, actor).status_code == 403
    assert not calls


@pytest.mark.parametrize('route', ['/v1/agent/run', '/mcp', '/v1/agent/jobs', '/docs', '/v1/agent/intent-contracts/x/continue'])
def test_profile_denies_other_routes(service, route):
    client, body, calls, _ = service
    assert client.post(route, json=body).status_code == 403
    assert not calls


def test_auth_is_mandatory_even_on_loopback(service):
    client, body, calls, _ = service
    assert client.post(ROUTE, json=body).status_code == 401
    assert not calls


def test_symlink_cannot_produce_success(service):
    client, body, _, root = service
    (root / 'alice.json').unlink()
    (root / 'alice.json').symlink_to(root / 'bob.json')
    result = post(client, body).json()['result']
    assert result['stopped_reason'] == 'plan_ready'
    assert not result['steps']
    assert not result['intent_contract'].get('execution_receipts')


@pytest.mark.parametrize('mutation', ['root', 'version', 'shared', 'traversal'])
def test_invalid_operator_policy_prevents_startup(service, monkeypatch, tmp_path, mutation):
    _, _, _, root = service
    policy = {'schema_version': '1', 'workspace_id': 'local', 'workspace_root': str(root),
              'actor_files': {'alice': ['alice.json']}}
    if mutation == 'root':
        policy['workspace_root'] = str(tmp_path)
    elif mutation == 'version':
        policy['schema_version'] = '2'
    elif mutation == 'shared':
        policy['actor_files'] = {'shared': ['alice.json']}
    else:
        policy['actor_files'] = {'alice': ['../alice.json']}
    path = tmp_path / 'bad-policy.json'
    path.write_text(json.dumps(policy))
    monkeypatch.setenv('DELENTIA_READONLY_POLICY', str(path))
    with pytest.raises(ValueError):
        load_policy()


def test_websocket_cannot_bypass_boundary(service):
    from starlette.websockets import WebSocketDisconnect
    client, _, calls, _ = service
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect('/v1/kernel/stream'):
            pytest.fail('stream must be denied')
    assert exc.value.code == 4403
    assert not calls


def test_control_plane_installs_profile(service):
    from rct_control_plane.api import ControlPlaneAPI
    api = ControlPlaneAPI()
    client = TestClient(api.app)
    assert client.post('/v1/agent/run', json={'goal': 'anything'}).status_code == 403
    assert client.post(ROUTE, json={}).status_code == 401
    assert any(route.path == ROUTE for route in api.app.routes)
    from rct_control_plane.readonly_service import readonly_lifespan
    assert api.app.router.lifespan_context is readonly_lifespan
    with TestClient(api.app) as running:
        assert running.post("/v1/agent/jobs", json={}).status_code == 403
