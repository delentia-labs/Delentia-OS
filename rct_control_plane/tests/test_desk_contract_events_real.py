"""Contract event snapshots over real persisted plans; no model required."""
import asyncio
import json

import pytest
from rct_control_plane.verified_budget import supports_verified_reads

from rct_control_plane import autonomous_loop, mcp_server
from rct_control_plane.desk_agent_stream import agent_events, contract_snapshot_events
from rct_control_plane.intent_contract import IntentContractStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeKernel, _loop


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    async def forbidden(*args, **kwargs):
        pytest.fail('initial contract stream must not generate')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    def factory(kernel, namespace, **kwargs):
        return _loop(tmp_path, namespace, kernel=_FakeKernel(), mcp=mcp_server.mcp)
    return root, factory


def collect(factory, **kwargs):
    async def run():
        return [e async for e in agent_events('Compare quote with budget', kernel=None,
            namespace='alice', loop_factory=factory, **kwargs)]
    return asyncio.run(run())


def test_unknowns_are_presented_without_answer_or_execution(world):
    _, factory = world
    events = collect(factory, structured=True, acceptance_criteria=[{'kind': 'json_object'}],
                     planning_context={'semantic_plan': {}})
    assert [e['type'] for e in events] == ['start', 'plan', 'waiting_for_input', 'verdict', 'done']
    waiting = events[2]
    assert waiting['data']['reason'] == 'waiting_for_input'
    assert 'budget' in {q['id'] for q in waiting['data']['questions']}
    assert not events[3]['data']['satisfied'] and not events[-1]['data']['completed']
    assert 'workspace' not in events[1]['data']['plan']
    assert not any(e['type'] in {'answer', 'fdia', 'receipt'} for e in events)


@pytest.mark.skipif(not supports_verified_reads(), reason='A quote_evidence plan needs POSIX no-follow reading (verified_budget.supports_verified_reads), which this platform lacks')
def test_complete_inputs_still_require_confirmation(world):
    _, factory = world
    events = collect(factory, structured=True, acceptance_criteria=[{'kind': 'json_object'}],
                     planning_context={'semantic_plan': {'budget': '100 THB', 'quote_evidence': {'relative_path': 'quote.json', 'sha256': '0' * 64}}})
    assert events[2]['data']['reason'] == 'plan_ready'
    assert events[-1]['data']['stopped_reason'] == 'plan_ready'


def test_contract_requires_structured_surface(world):
    _, factory = world
    events = collect(factory, acceptance_criteria=[{'kind': 'json_object'}])
    assert [e['type'] for e in events] == ['error']


def test_planning_context_without_criteria_never_falls_back(world):
    _, factory = world
    events = collect(factory, structured=True, planning_context={'semantic_plan': {}})
    assert events[-1]['type'] == 'error'
    assert not any(e['type'] in {'answer', 'verdict'} for e in events)


def test_snapshot_identity_and_waiting_survive_new_store(world, tmp_path):
    _, factory = world
    events = collect(factory, structured=True, acceptance_criteria=[{'kind': 'json_object'}],
                     planning_context={'semantic_plan': {}})
    plan = events[1]
    store = IntentContractStore(factory(None, 'alice')._persistence, 'alice')
    contract = store.get(plan['contract_id'])
    assert contract_snapshot_events(contract, 'alice') == events[1:-1]
    assert [e['sequence'] for e in events[1:-1]] == [1, 2, 3]
    json.dumps(events, ensure_ascii=False, allow_nan=False)


def test_closing_stream_cancels_outstanding_task():
    from types import SimpleNamespace
    cancelled = []
    class WaitingLoop:
        async def run(self, goal, on_step):
            try:
                await on_step(SimpleNamespace(tool_name='read', tool_result={}, iteration=1))
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
    async def run():
        stream = agent_events('read', kernel=None, structured=True, loop_factory=lambda *a, **kw: WaitingLoop())
        assert (await anext(stream))['type'] == 'start'
        assert (await anext(stream))['type'] == 'step'
        await stream.aclose()
    asyncio.run(run())
    assert cancelled == [True]


def test_websocket_forwards_contract_request_and_pins_actor(world, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane import agent_factory, api_tokens
    from rct_control_plane.api import create_app
    _, factory = world
    monkeypatch.setattr(agent_factory, 'build_governed_loop', factory)
    token_file = tmp_path / 'tokens.json'
    token_file.write_text(json.dumps({'users': [{'name': 'alice', 'token_sha256': api_tokens.hash_token('test-token')}]}), encoding='utf-8')
    monkeypatch.setenv('DELENTIA_API_TOKENS_FILE', str(token_file))
    monkeypatch.delenv('DELENTIA_READONLY_POLICY', raising=False)
    client = TestClient(create_app())
    with client.websocket_connect('/v1/kernel/stream', headers={'Authorization': 'Bearer test-token'}) as socket:
        socket.send_json({'intent': 'Compare quote with budget', 'mode': 'agent', 'structured': True,
                          'namespace': 'bob', 'acceptance_criteria': [{'kind': 'json_object'}],
                          'planning_context': {'semantic_plan': {}}})
        events = []
        while not events or events[-1]['type'] != 'done':
            events.append(socket.receive_json())
        assert events[1]['type'] == 'plan' and events[1]['data']['actor'] == 'alice'
        assert [e['type'] for e in events] == ['start', 'plan', 'waiting_for_input', 'verdict', 'done']
        socket.send_json({'intent': 'Compare quote with budget', 'mode': 'agent', 'acceptance_criteria': None})
        assert socket.receive_json()['type'] == 'error'
