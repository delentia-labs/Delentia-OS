"""Opt-in server-owned typed review through actual HTTP/auth/SQLite/MCP."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rct_control_plane import api_tokens, mcp_server
from rct_control_plane.api_auth import ApiTokenMiddleware
from rct_control_plane.readonly_service import ReadOnlyBoundary, install_route, load_policy
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeKernel, _loop


@pytest.fixture
def reviewed_service(tmp_path, monkeypatch):
    from rct_control_plane.verified_budget import supports_verified_reads
    if not supports_verified_reads():
        pytest.skip('The read-only budget service reads its evidence with POSIX no-follow descriptors (verified_budget.supports_verified_reads), which this platform lacks')
    root = tmp_path / 'workspace'
    root.mkdir()
    raw = b'{"schema_version":1,"total":"0.10","currency":"THB","total_is_final":true}'
    (root / 'alice.json').write_bytes(raw)
    (root / 'bob.json').write_bytes(raw)
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    tokens = tmp_path / 'tokens.json'
    tokens.write_text(json.dumps({'users': [{'name': a, 'token_sha256': api_tokens.hash_token(a + '-token')} for a in ('alice', 'bob')]}), encoding='utf-8')
    monkeypatch.setenv('DELENTIA_API_TOKENS_FILE', str(tokens))
    monkeypatch.delenv('DELENTIA_API_TOKEN', raising=False)
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps({'schema_version': '1', 'workspace_id': 'local', 'workspace_root': str(root),
        'actor_files': {'alice': ['alice.json'], 'bob': ['bob.json']}, 'intent_review_required': True}), encoding='utf-8')
    monkeypatch.setenv('DELENTIA_READONLY_POLICY', str(path))
    policy = load_policy()
    app = FastAPI()
    calls = []

    def factory(actor):
        calls.append(actor)
        return _loop(tmp_path, actor, kernel=_FakeKernel(), mcp=mcp_server.mcp)

    install_route(app, policy, factory)
    app.add_middleware(ApiTokenMiddleware)
    app.add_middleware(ReadOnlyBoundary, policy=policy)
    body = {'schema_version': '1', 'executor_version': 'verified_budget_v1', 'workspace_id': 'local',
            'budget': '0.30 THB', 'evidence': {'relative_path': 'alice.json', 'sha256': hashlib.sha256(raw).hexdigest()}}
    return TestClient(app), body, calls, root


from rct_control_plane.tests.test_readonly_service_real import post, confirm, status


def test_reviewed_http_lifecycle_has_receipts_and_redacts_host_path(reviewed_service):
    client, body, _, root = reviewed_service
    response = post(client, body)
    assert response.status_code == 200, response.text
    planned = response.json()['contract']
    review = planned['plan']['intent_review']
    assert review['binding']['actor'] == 'alice'
    assert 'workspace_root' not in review['binding']
    assert str(root) not in response.text
    assert not planned['receipts'] and not planned['verified']
    done = confirm(client, planned)
    assert done.status_code == 200, done.text
    result = done.json()['contract']
    assert result['verified'] and result['receipts']
    assert status(client, result).json()['contract']['verified']
    assert confirm(client, planned).status_code == 409


@pytest.mark.parametrize('change', ['actor', 'version', 'digest', 'caller_binding', 'bool_version'])
def test_invalid_confirmation_never_executes(reviewed_service, change):
    client, body, _, _ = reviewed_service
    planned = post(client, body).json()['contract']
    kwargs = {'actor': 'bob'} if change == 'actor' else {
        'version': {'version': 99}, 'digest': {'plan_sha256': 'f'*64},
        'caller_binding': {'review_binding': {'actor': 'alice'}}, 'bool_version': {'version': True},
    }[change]
    result = confirm(client, planned, **kwargs)
    assert result.status_code in (404, 409, 422), result.text
    current = status(client, planned).json()['contract']
    assert current['version'] == planned['version'] and not current['receipts']


def test_catalog_change_refuses_confirmation_without_claim(reviewed_service, monkeypatch):
    from rct_control_plane import readonly_service
    client, body, _, _ = reviewed_service
    planned = post(client, body).json()['contract']
    monkeypatch.setattr(readonly_service, 'budget_review_catalog', lambda: {'review_protocol': 2})
    assert confirm(client, planned).status_code == 409
    assert status(client, planned).json()['contract']['state'] == 'plan_ready'


@pytest.mark.parametrize('change', ['policy', 'token'])
def test_revocation_prevents_confirm_before_backend(reviewed_service, monkeypatch, change):
    import os
    client, body, calls, _ = reviewed_service
    planned = post(client, body).json()['contract']
    before = len(calls)
    key = 'DELENTIA_READONLY_POLICY' if change == 'policy' else 'DELENTIA_API_TOKENS_FILE'
    path = Path(os.environ[key])
    value = json.loads(path.read_text(encoding='utf-8'))
    if change == 'policy': value['actor_files'].pop('alice')
    else: value['users'] = [u for u in value['users'] if u['name'] != 'alice']
    path.write_text(json.dumps(value), encoding='utf-8')
    assert confirm(client, planned).status_code in (401, 403, 409)
    assert len(calls) == before


def test_request_cannot_inject_proposal_or_catalog(reviewed_service):
    client, body, calls, _ = reviewed_service
    for field in ('intent_review', 'proposal', 'catalog_sha256'):
        response = post(client, {**body, field: {}})
        assert response.status_code == 422
    assert calls == []
