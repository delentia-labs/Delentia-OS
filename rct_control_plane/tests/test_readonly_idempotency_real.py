"""HTTP retries, concurrent workers and durable keyed contract creation."""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from rct_control_plane.intent_contract import IntentContractStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop
from rct_control_plane.tests.test_readonly_service_real import (
    confirm, post, service as _service, status,
)

service = _service
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='budget execution requires POSIX no-follow')


def test_lost_create_response_recovers_same_plan(service):
    client, body, _, _ = service
    body['request_id'] = 'retry-1'
    first = post(client, body).json()['contract']
    second = post(client, body).json()['contract']
    assert first == second and not second['verified'] and not second['receipts']


@pytest.mark.parametrize('field,value', [('budget', '2 THB'), ('executor_version', 'v2')])
def test_request_id_cannot_change_input(service, field, value):
    client, body, _, _ = service
    body['request_id'] = 'same-key'
    original = post(client, body).json()['contract']
    body[field] = value
    response = post(client, body)
    assert response.status_code == (409 if field == 'budget' else 422)
    assert status(client, original).json()['contract'] == original


def test_concurrent_creates_persist_one_contract(service, tmp_path):
    client, body, _, _ = service
    body['request_id'] = 'concurrent'
    # Construct per-actor fixture schemas once before concurrent HTTP workers.
    _loop(tmp_path, 'alice')
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post(client, body), range(4)))
    assert all(r.status_code == 200 for r in responses), [(r.status_code, r.json().get('error')) for r in responses]
    assert len({r.json()['contract']['id'] for r in responses}) == 1
    store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
    with store.db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM intent_request_keys').fetchone()[0] == 1


def test_same_key_is_scoped_to_actor(service):
    client, body, _, _ = service
    body['request_id'] = 'same-key'
    alice = post(client, body).json()['contract']
    body['evidence']['relative_path'] = 'bob.json'
    bob = post(client, body, 'bob').json()['contract']
    assert alice['id'] != bob['id'] and bob['actor'] == 'bob'


def test_retry_after_execution_returns_saved_result_without_replay(service):
    client, body, _, _ = service
    body['request_id'] = 'complete-once'
    plan = post(client, body).json()['contract']
    finished = confirm(client, plan).json()['contract']
    assert finished['verified']
    repeated = post(client, body).json()['contract']
    assert repeated == finished
    assert confirm(client, repeated).status_code == 409


def test_failed_key_insert_rolls_back_plan_too(service, tmp_path):
    client, body, _, _ = service
    body['request_id'] = 'rollback'
    store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
    with store.db._connect() as conn:
        conn.execute("CREATE TRIGGER fail_key BEFORE INSERT ON intent_request_keys BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    assert post(client, body).status_code == 503
    with store.db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 0
        conn.execute('DROP TRIGGER fail_key')
    assert post(client, body).status_code == 200


def test_restart_lookup_does_not_reset_claimed_contract(service, tmp_path):
    client, body, _, _ = service
    body['request_id'] = 'restart'
    plan = post(client, body).json()['contract']
    store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
    store.claim(plan['id'], plan['version'])
    repeated = post(client, body).json()['contract']
    assert repeated['id'] == plan['id'] and repeated['state'] == 'running'
    assert not repeated['verified'] and confirm(client, repeated).status_code == 409


@pytest.mark.parametrize('key', ['', 'x' * 129, 'ไทย', '../key', True, 7])
def test_invalid_identifiers_fail_validation(service, key):
    client, body, _, _ = service
    body['request_id'] = key
    assert post(client, body).status_code == 422


def test_without_key_retains_create_new_plan_behavior(service):
    client, body, _, _ = service
    assert post(client, body).json()['contract']['id'] != post(client, body).json()['contract']['id']


def test_same_key_new_policy_cannot_reuse_old_authority(service, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from rct_control_plane.api_auth import ApiTokenMiddleware
    from rct_control_plane.readonly_service import ReadOnlyBoundary, install_route, load_policy
    client, body, _, _ = service
    body['request_id'] = 'policy-bound'
    original = post(client, body).json()['contract']
    path = tmp_path / 'policy.json'
    policy_data = json.loads(path.read_text())
    policy_data['policy_version'] = 2
    path.write_text(json.dumps(policy_data))
    policy = load_policy()
    app = FastAPI()
    install_route(app, policy, lambda actor: _loop(tmp_path, actor))
    app.add_middleware(ApiTokenMiddleware)
    app.add_middleware(ReadOnlyBoundary, policy=policy)
    restarted = TestClient(app)
    assert post(restarted, body).status_code == 409
    assert status(restarted, original).status_code == 403


def test_cold_worker_busy_response_can_retry_same_key(service):
    client, body, _, _ = service
    body['request_id'] = 'cold-workers'
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post(client, body), range(4)))
    # Fixture constructs a persistence/skill library per worker. A cold schema
    # lock may yield 503; a busy retry must still converge on one contract.
    assert all(r.status_code in {200, 503} for r in responses)
    final = post(client, body)
    assert final.status_code == 200
    ids = {r.json()['contract']['id'] for r in responses if r.status_code == 200}
    ids.add(final.json()['contract']['id'])
    assert len(ids) == 1


@pytest.mark.parametrize('boundary', ['before_insert', 'after_commit'])
def test_killed_create_recovers_without_orphan_or_duplicate(service, tmp_path, boundary):
    import multiprocessing
    import time
    client, body, _, _ = service
    body['request_id'] = 'kill-create'
    marker = tmp_path / 'reached'
    def worker():
        def pause():
            marker.write_text('ready')
            time.sleep(30)
        if boundary == 'before_insert':
            original = IntentContractStore._encode
            def encode(store, data):
                value = original(store, data)
                pause()
                return value
            IntentContractStore._encode = encode
        else:
            original_create = IntentContractStore.create
            def create(store, *args, **kwargs):
                result = original_create(store, *args, **kwargs)
                pause()  # transaction committed, before sending the HTTP reply
                return result
            IntentContractStore.create = create
        post(client, body)
    process = multiprocessing.get_context('fork').Process(target=worker)
    process.start()
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline and process.is_alive():
            time.sleep(0.02)
        assert marker.exists(), process.exitcode
        process.kill()
        process.join(5)
        recovered = post(client, body)
        assert recovered.status_code == 200, recovered.text
        assert not recovered.json()['contract']['verified']
        store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
        with store.db._connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 1
            assert conn.execute('SELECT COUNT(*) FROM intent_request_keys').fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type='intent_contract'").fetchone()[0] == 1
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
