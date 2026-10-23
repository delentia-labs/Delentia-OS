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

    def factory(actor):
        calls.append(actor)
        return _loop(tmp_path, actor, kernel=_FakeKernel(), mcp=mcp_server.mcp)

    install_route(app, policy, factory)
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
    result = response.json()['contract']
    assert result['state'] == 'plan_ready'
    assert not result['verified']
    assert result['plan']['semantic_planning']['executor'] == 'verified_budget_v1'
    assert not result['receipts']
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
    result = post(client, body).json()['contract']
    assert result['state'] == 'plan_ready'
    assert not result['verified']
    assert not result['receipts']


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


def confirm(client, contract, actor='alice', **changes):
    payload = {'schema_version': '1', 'version': contract['version'], 'plan_sha256': contract['plan_sha256']}
    payload.update(changes)
    return client.post(ROUTE + '/' + contract['id'] + '/confirm', json=payload,
                       headers={'Authorization': 'Bearer ' + actor + '-token'})


def status(client, contract, actor='alice'):
    return client.get(ROUTE + '/' + contract['id'], headers={'Authorization': 'Bearer ' + actor + '-token'})


def test_http_plan_confirm_receipts_and_status(service, monkeypatch):
    from rct_control_plane import autonomous_loop
    async def forbidden(*args, **kwargs):
        pytest.fail('bounded service must never call model generation')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    client, body, _, root = service
    plan = post(client, body).json()['contract']
    assert not plan['receipts'] and not plan['verified']
    assert 'workspace' not in plan['plan']
    response = confirm(client, plan)
    assert response.status_code == 200, response.text
    done = response.json()['contract']
    assert done['verified'] and done['state'] == 'criteria_satisfied'
    assert done['execution_status'] == 'complete'
    assert done['report']['remaining'] == '0.20'
    assert len(done['receipts']) == 5
    assert status(client, plan).json()['contract'] == done
    assert confirm(client, plan).status_code == 409
    assert confirm(client, done).status_code == 409
    assert (root / 'alice.json').read_bytes() == (root / 'bob.json').read_bytes()


@pytest.mark.parametrize('change', ['version', 'digest', 'actor', 'extra', 'bool_version'])
def test_confirmation_rejects_before_source_read(service, monkeypatch, change):
    from rct_control_plane import verified_budget
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    def forbidden(*args, **kwargs):
        pytest.fail('denied confirmation must not read evidence')
    monkeypatch.setattr(verified_budget, 'current_bytes', forbidden)
    kwargs = {'version': {'version': 99}, 'digest': {'plan_sha256': '0' * 64},
              'actor': {'actor': 'bob'}, 'extra': {'goal': 'write'}, 'bool_version': {'version': True}}[change]
    response = confirm(client, plan, **kwargs)
    assert response.status_code == {'version': 409, 'digest': 409, 'actor': 404, 'extra': 422, 'bool_version': 422}[change]
    assert not status(client, plan).json()['contract']['receipts']


def test_generic_contract_cannot_be_imported(service, tmp_path):
    from rct_control_plane.intent_contract import IntentContractStore
    client, body, _, root = service
    loop = _loop(tmp_path, 'alice')
    generic = IntentContractStore(loop._persistence, 'alice').create('Compare quote with budget',
        [{'kind': 'json_object'}], root, {'semantic_plan': {'budget': body['budget'], 'quote_evidence': body['evidence']}})
    assert status(client, generic).status_code == 403
    assert confirm(client, generic).status_code == 403


def test_policy_revocation_is_immediate(service, tmp_path):
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    path = tmp_path / 'policy.json'
    policy = json.loads(path.read_text())
    policy['actor_files']['alice'] = ['bob.json']
    path.write_text(json.dumps(policy))
    assert confirm(client, plan).status_code == 409
    assert status(client, plan).status_code == 409
    assert post(client, body).status_code == 409


def test_changed_evidence_does_not_verify(service):
    client, body, _, root = service
    plan = post(client, body).json()['contract']
    (root / 'alice.json').write_text('{}')
    result = confirm(client, plan).json()['contract']
    assert not result['verified'] and result['execution_status'] == 'incomplete'
    assert result['state'] == 'waiting_for_clarification'
    assert confirm(client, result).status_code == 409


def test_restart_after_claim_refuses_replay(service, tmp_path):
    from rct_control_plane.intent_contract import IntentContractStore
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    loop = _loop(tmp_path, 'alice')
    store = IntentContractStore(loop._persistence, 'alice')
    claimed = store.claim(plan['id'], plan['version'])
    # Every HTTP operation opens a fresh loop/store on the persisted database.
    observed = status(client, plan).json()['contract']
    assert observed['state'] == 'running' and not observed['verified']
    assert confirm(client, claimed).status_code == 409


def test_two_confirmations_only_one_claim(service):
    from concurrent.futures import ThreadPoolExecutor
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(client, plan), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    done = status(client, plan).json()['contract']
    assert done['verified'] and len(done['receipts']) == 5


def test_receipt_encoding_preserves_nanoseconds_for_javascript(service):
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    done = confirm(client, plan).json()['contract']
    for receipt in done['receipts']:
        assert isinstance(receipt['recorded_ns'], str)
        assert int(receipt['recorded_ns']) > 2 ** 53
        raw = receipt['hashed_payload_json'].encode('utf-8')
        assert hashlib.sha256(raw).hexdigest() == receipt['receipt_sha256']
        assert str(json.loads(raw)['recorded_ns']) == receipt['recorded_ns']


def test_errors_have_version_and_do_not_echo_payload(service):
    client, body, _, _ = service
    assert client.post(ROUTE, json=body).json() == {'schema_version': '1', 'error': 'unauthenticated'}
    body['private_unknown_field'] = 'must-not-echo'
    response = post(client, body)
    assert response.status_code == 422
    assert response.json() == {'schema_version': '1', 'error': 'invalid_request'}
    assert client.post('/mcp', json={}).json() == {'schema_version': '1', 'error': 'forbidden'}


@pytest.mark.parametrize('message', ['database is locked', 'database or disk is full'])
def test_persistence_failure_never_reports_success(service, monkeypatch, message):
    import sqlite3
    from rct_control_plane.intent_contract import IntentContractStore
    client, body, _, _ = service
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError(message)
    monkeypatch.setattr(IntentContractStore, 'create', fail)
    response = post(client, body)
    assert response.status_code == 503
    assert response.json() == {'schema_version': '1', 'error': 'unavailable'}


def test_policy_unavailable_fails_closed(service, tmp_path):
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    (tmp_path / 'policy.json').unlink()
    assert confirm(client, plan).status_code == 503
    assert status(client, plan).status_code == 503


def test_token_revocation_blocks_existing_contract(service, tmp_path):
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    path = tmp_path / 'tokens.json'
    entries = json.loads(path.read_text())
    entries['users'][0]['disabled'] = True
    path.write_text(json.dumps(entries))
    assert confirm(client, plan).status_code == 401
    assert status(client, plan).status_code == 401


@pytest.mark.skipif(__import__('os').name != 'posix', reason='real process kill requires POSIX')
@pytest.mark.parametrize('boundary', ['before_read', 'after_read', 'after_receipt', 'after_completion'])
def test_killed_worker_status_and_no_automatic_replay(service, tmp_path, boundary):
    import asyncio
    import multiprocessing
    from rct_control_plane import verified_budget
    from rct_control_plane.intent_contract import IntentContractStore
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    context = multiprocessing.get_context('fork')
    reached = context.Event()
    import time

    def worker():
        original_read = verified_budget.current_bytes
        original_transition = IntentContractStore.transition

        def pause():
            reached.set()
            time.sleep(30)

        def read(*args, **kwargs):
            if boundary == 'before_read':
                pause()
            value = original_read(*args, **kwargs)
            if boundary == 'after_read':
                pause()
            return value

        def transition(store, data, state):
            value = original_transition(store, data, state)
            if ((boundary == 'after_receipt' and state == 'running' and value.get('execution_receipts'))
                    or (boundary == 'after_completion' and state == 'criteria_satisfied')):
                pause()
            return value

        verified_budget.current_bytes = read
        IntentContractStore.transition = transition
        loop = _loop(tmp_path, 'alice', kernel=_FakeKernel(), mcp=mcp_server.mcp)
        asyncio.run(loop.continue_intent(plan['id'], plan['version']))

    process = context.Process(target=worker)
    process.start()
    try:
        assert reached.wait(15), f'worker failed to reach {boundary}: exit={process.exitcode}'
        process.kill()
        process.join(5)
        assert not process.is_alive() and process.exitcode != 0
        observed = status(client, plan).json()['contract']
        assert observed['verified'] is (boundary == 'after_completion')
        assert confirm(client, observed).status_code == 409
        if boundary == 'after_completion':
            assert len(observed['receipts']) == 5
        else:
            assert observed['state'] == 'running'
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)


def test_unsupported_platform_has_explicit_api_error(service, monkeypatch):
    from rct_control_plane import verified_budget
    client, body, calls, _ = service
    plan = post(client, body).json()['contract']
    calls.clear()
    monkeypatch.setattr(verified_budget, 'supports_verified_reads', lambda: False)
    for response in (post(client, body), confirm(client, plan)):
        assert response.status_code == 501
        assert response.json() == {'schema_version': '1', 'error': 'unsupported_platform'}
    assert not calls
    # Reading already persisted status does not need source acquisition.
    assert status(client, plan).status_code == 200


def test_desk_receipt_and_verdict_snapshot_matches_persisted_execution(service, tmp_path):
    import copy
    from rct_control_plane.desk_agent_stream import contract_snapshot_events
    from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
    client, body, _, _ = service
    plan = post(client, body).json()['contract']
    assert confirm(client, plan).status_code == 200
    store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
    raw = store.get(plan['id'])
    events = contract_snapshot_events(raw, 'alice')
    assert [e['type'] for e in events] == ['plan'] + ['receipt'] * 5 + ['verdict']
    assert events[-1]['data']['satisfied']
    assert events[-1]['data']['method'] == 'document_bytes_and_same_currency_arithmetic'
    assert contract_snapshot_events(raw, 'alice') == events
    assert all(isinstance(e['data']['recorded_ns'], str) for e in events if e['type'] == 'receipt')
    missing = copy.deepcopy(raw)
    missing['execution_receipts'].pop()
    assert not contract_snapshot_events(missing, 'alice')[-1]['data']['satisfied']
    with pytest.raises(IntentContractError):
        contract_snapshot_events(raw, 'bob')
