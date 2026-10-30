"""Bounded HTTP background jobs over real auth/SQLite/MCP, no model calls."""
import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.readonly_service import ROUTE, readonly_lifespan
from rct_control_plane.tests.test_readonly_service_real import service as _service, post

base_service = _service
pytestmark = pytest.mark.timeout(20)


@pytest.fixture
def background(base_service):
    client, body, calls, root = base_service
    client.app.router.lifespan_context = readonly_lifespan
    with TestClient(client.app) as active:
        yield active, body, calls, root


def headers(actor='alice'):
    return {'Authorization': 'Bearer ' + actor + '-token'}


def submit(client, plan, actor='alice', **changes):
    body = {'schema_version': '1', 'version': plan['version'], 'plan_sha256': plan['plan_sha256']}
    body.update(changes)
    return client.post(ROUTE + '/' + plan['id'] + '/jobs', json=body, headers=headers(actor))


def get(client, job_id, actor='alice'):
    return client.get(ROUTE + '/jobs/' + job_id, headers=headers(actor))


def wait(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = get(client, job_id)
        assert response.status_code == 200, response.text
        result = response.json()
        if result['status'] not in {'queued', 'running'}:
            return result
        time.sleep(0.05)
    pytest.fail('bound job did not settle')


def pause(client):
    assert get(client, 'job-' + '0' * 12).status_code == 404
    service = client.app.state.readonly_job_services['alice']
    started = threading.Event()
    async def install():
        gate = asyncio.Event()
        original = service.jobs._runner
        async def slow(*args):
            started.set()
            await gate.wait()
            return await original(*args)
        service.jobs._runner = slow
        return gate
    gate = client.portal.call(install)
    return service, started, gate


def test_plan_to_background_receipts_and_idempotent_retry(background, monkeypatch):
    from rct_control_plane import autonomous_loop
    async def forbidden(*args, **kwargs):
        pytest.fail('bounded executor must not call a model')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    client, body, _, root = background
    plan = post(client, body).json()['contract']
    response = submit(client, plan)
    assert response.status_code == 202, response.text
    job_id = response.json()['job_id']
    done = wait(client, job_id)
    assert done['status'] == 'done' and done['task_outcome'] == 'verified' and done['verified']
    assert done['contract']['report']['remaining'] == '0.20'
    assert len(done['contract']['receipts']) == 5
    repeated = submit(client, plan)
    assert repeated.status_code == 202 and repeated.json()['job_id'] == job_id
    assert repeated.json() == done
    assert (root / 'alice.json').read_bytes() == (root / 'bob.json').read_bytes()
    assert client.post('/v1/agent/jobs', json={'goal': 'write'}).status_code == 403


@pytest.mark.parametrize('change', ['version', 'digest', 'actor', 'extra'])
def test_unauthorized_confirmation_never_admits_job(background, change):
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    args = {'version': {'version': 99}, 'digest': {'plan_sha256': '0' * 64},
            'actor': {'actor': 'bob'}, 'extra': {'goal': 'write a file'}}[change]
    response = submit(client, plan, **args)
    assert response.status_code == {'version': 409, 'digest': 409, 'actor': 404, 'extra': 422}[change]
    current = client.get(ROUTE + '/' + plan['id'], headers=headers()).json()['contract']
    assert current == plan


def test_cancel_does_not_report_complete_and_cannot_replay(background):
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    service, started, gate = pause(client)
    response = submit(client, plan)
    job_id = response.json()['job_id']
    assert started.wait(5)
    assert get(client, job_id, 'bob').status_code == 404
    assert client.delete(ROUTE + '/jobs/' + job_id, headers=headers('bob')).status_code == 404
    response = client.delete(ROUTE + '/jobs/' + job_id, headers=headers())
    assert response.status_code == 200
    settled = wait(client, job_id)
    assert settled['status'] == 'cancelled' and not settled['verified']
    assert settled['contract']['state'] == 'interrupted' and not settled['contract']['receipts']
    repeated = submit(client, plan)
    assert repeated.json()['job_id'] == job_id and not repeated.json()['verified']


def test_lease_loss_reconciles_without_dispatch(background):
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    service, started, gate = pause(client)
    job_id = submit(client, plan).json()['job_id']
    assert started.wait(5)
    service.jobs._ownership.clock = lambda: time.time() + 3600
    observed = get(client, job_id).json()
    assert observed['status'] == 'interrupted' and not observed['verified']
    assert observed['contract']['state'] == 'interrupted'
    client.portal.call(gate.set)


def test_job_audit_failure_rolls_back_contract_claim_and_admission(background, tmp_path):
    from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    db = _loop(tmp_path, 'alice')._persistence
    with db._connect() as conn:
        conn.execute("CREATE TRIGGER fail_submit BEFORE INSERT ON audit_trail WHEN NEW.entity_type='agent_job' AND NEW.action='submitted' BEGIN SELECT RAISE(ABORT, 'injected admission audit failure'); END")
    assert submit(client, plan).status_code == 503
    assert client.get(ROUTE + '/' + plan['id'], headers=headers()).json()['contract'] == plan
    with db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM agent_jobs').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM readonly_budget_jobs').fetchone()[0] == 0
        conn.execute('DROP TRIGGER fail_submit')
    assert submit(client, plan).status_code == 202


def test_policy_change_before_worker_dispatch_blocks_execution(background, tmp_path):
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    service, started, gate = pause(client)
    job_id = submit(client, plan).json()['job_id']
    assert started.wait(5)
    path = tmp_path / 'policy.json'
    original = path.read_text(encoding='utf-8')
    policy = json.loads(original)
    policy['policy_version'] = 99
    path.write_text(json.dumps(policy), encoding='utf-8')
    client.portal.call(gate.set)
    client.portal.call(service.jobs.wait, job_id, 5)
    assert get(client, job_id).status_code == 409
    path.write_text(original, encoding='utf-8')
    observed = get(client, job_id).json()
    assert observed['status'] == 'failed' and not observed['verified']
    assert not observed['contract']['receipts']


@pytest.mark.parametrize('loss', ['policy', 'lease', 'actor'])
def test_revocation_after_source_read_cannot_commit_receipts(background, monkeypatch, tmp_path, loss):
    from rct_control_plane import mcp_server
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    assert get(client, 'job-' + '0' * 12).status_code == 404
    service = client.app.state.readonly_job_services['alice']
    source_read = threading.Event()
    async def make_gate():
        return asyncio.Event()
    gate = client.portal.call(make_gate)
    original = mcp_server.mcp.call_tool
    async def hold_result(name, arguments, *args, **kwargs):
        value = await original(name, arguments, *args, **kwargs)
        if name == 'delentia_read_repo_file':
            source_read.set()
            await gate.wait()
        return value
    monkeypatch.setattr(mcp_server.mcp, 'call_tool', hold_result)
    job_id = submit(client, plan).json()['job_id']
    assert source_read.wait(5)
    policy_path = tmp_path / 'policy.json'
    policy_text = policy_path.read_text(encoding='utf-8')
    if loss == 'policy':
        policy = json.loads(policy_text)
        policy['policy_version'] = 99
        policy_path.write_text(json.dumps(policy), encoding='utf-8')
    elif loss == 'actor':
        from rct_control_plane import api_tokens
        token_path = api_tokens.tokens_path()
        token_text = token_path.read_text(encoding='utf-8')
        assert api_tokens.revoke('alice')
    else:
        service.jobs._ownership.clock = lambda: time.time() + 3600
    client.portal.call(gate.set)
    client.portal.call(service.jobs.wait, job_id, 5)
    policy_path.write_text(policy_text, encoding='utf-8')
    if loss == 'actor':
        assert get(client, job_id).status_code == 401
        token_path.write_text(token_text, encoding='utf-8')
        api_tokens._cache.clear()
    observed = get(client, job_id).json()
    assert not observed['verified'] and not observed['contract']['verified']
    assert observed['contract']['state'] == 'interrupted'
    assert not observed['contract']['receipts']


def test_two_api_workers_admit_only_one_bound_job(background, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import FastAPI
    from rct_control_plane import mcp_server
    from rct_control_plane.api_auth import ApiTokenMiddleware
    from rct_control_plane.readonly_service import ReadOnlyBoundary, install_route, load_policy
    from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    app = FastAPI(lifespan=readonly_lifespan)
    policy = load_policy()
    install_route(app, policy, lambda actor: _loop(tmp_path, actor, mcp=mcp_server.mcp))
    app.add_middleware(ApiTokenMiddleware)
    app.add_middleware(ReadOnlyBoundary, policy=policy)
    with TestClient(app) as other:
        first_service, first_started, first_gate = pause(client)
        second_service, second_started, second_gate = pause(other)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda c: submit(c, plan), [client, other]))
        assert all(r.status_code == 202 for r in responses), [(r.status_code, r.text) for r in responses]
        assert len({r.json()['job_id'] for r in responses}) == 1
        client.portal.call(first_gate.set)
        other.portal.call(second_gate.set)
        job_id = responses[0].json()['job_id']
        assert wait(client, job_id)['verified']


def test_unsupported_platform_does_not_admit(background, monkeypatch):
    from rct_control_plane import verified_budget
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    monkeypatch.setattr(verified_budget, 'supports_verified_reads', lambda: False)
    assert submit(client, plan).status_code == 501


@pytest.mark.parametrize('enrichment', ['jury', 'pipeline', 'pipeline_without_model'])
def test_model_enabled_host_enrichment_is_rejected_not_bypassed(background, enrichment):
    from types import SimpleNamespace
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    assert get(client, 'job-' + '0' * 12).status_code == 404
    service = client.app.state.readonly_job_services['alice']
    original = service.factory
    def configured(actor):
        loop = original(actor)
        if enrichment == 'jury':
            loop._active_policy = lambda: (SimpleNamespace(jury_by_risk={'LOW': 'jury'}, rules=[]), '')
        else:
            loop._get_pipeline = lambda: SimpleNamespace(options=SimpleNamespace(allow_llm=enrichment == 'pipeline'))
        return loop
    service.factory = configured
    assert submit(client, plan).status_code == 409
    current = client.get(ROUTE + '/' + plan['id'], headers=headers()).json()['contract']
    assert current == plan


def test_real_kernel_budget_job_with_generation_forbidden(background, tmp_path, monkeypatch):
    from rct_control_plane import mcp_server
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
    from rct_control_plane.llm_provider import LLMProvider
    client, body, _, _ = background
    isolated_home = tmp_path / 'real-kernel-home'
    isolated_home.mkdir(mode=0o700)
    monkeypatch.setenv('DELENTIA_HOME', str(isolated_home))
    plan = post(client, body).json()['contract']
    assert get(client, 'job-' + '0' * 12).status_code == 404
    service = client.app.state.readonly_job_services['alice']
    kernel = AlgorithmKernel41()
    class ForbiddenGeneration(LLMProvider):
        model = 'generation-forbidden'
        free_of_charge = True
        async def complete(self, *args, **kwargs):
            pytest.fail('real bounded kernel must not generate')
    def factory(actor):
        return build_governed_loop(kernel, actor, persistence=service.db, mcp_server=mcp_server.mcp,
                                   llm_provider=ForbiddenGeneration())
    service.factory = factory
    response = submit(client, plan)
    assert response.status_code == 202, response.text
    settled = wait(client, response.json()['job_id'])
    assert settled['verified'], settled



def test_contract_receipt_guard_holds_sqlite_write_transaction(background):
    from rct_control_plane.contract_execution_guard import execution_guard
    client, body, _, _ = background
    plan = post(client, body).json()['contract']
    assert get(client, 'job-' + '0' * 12).status_code == 404
    service = client.app.state.readonly_job_services['alice']
    inspections = []
    def checked(conn, contract, state):
        inspections.append(conn.in_transaction)
        assert conn.in_transaction
    token = execution_guard.set(checked)
    try:
        service.store.transition(service.store.get(plan['id']), 'running')
    finally:
        execution_guard.reset(token)
    assert inspections == [True]
