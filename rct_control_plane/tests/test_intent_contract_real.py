"""Contract acceptance, restart, isolation and ordering using real SQLite/tools."""
import asyncio
import json
from pathlib import Path

import pytest
from rct_control_plane.verified_budget import supports_verified_reads

from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane import autonomous_loop, mcp_server
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop, _FakeKernel


def finish(answer):
    return {"action": "finish", "reasoning": "scripted", "final_answer": answer, "tool_name": None, "tool_args": {}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "source.md").write_text("original", encoding='utf-8')
    monkeypatch.setattr(mcp_server, "REPO_ROOT", root)
    return root


def script(monkeypatch, decisions, observed=None):
    seq = iter(decisions)
    async def decide(*args, **kwargs):
        if observed is not None:
            assert observed, "model called before the plan was shown"
        return next(seq)
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)


def test_prepare_has_no_model_or_tool_effects_and_invalid_criteria_fail(tmp_path, world, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("preparation must not call a model")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", forbidden)
    loop = _loop(tmp_path, "prepare", kernel=_FakeKernel())
    result = asyncio.run(loop.run("Answer in Thai", acceptance_criteria=[{"kind": "language", "value": "th"}]))
    assert result["stopped_reason"] == "plan_ready" and result["steps"] == []
    contract = result["intent_contract"]
    assert contract["plan"]["backward_chain"]["necessary_conditions"][0]["criterion_id"] == "C1"
    with pytest.raises(IntentContractError):
        asyncio.run(loop.run("test", acceptance_criteria=[{"kind": "invented"}]))


def test_mismatch_persists_waits_for_a_real_answer_and_replans(tmp_path, world, monkeypatch):
    shown = []
    script(monkeypatch, [finish("An English answer"), finish("คำตอบภาษาไทย")], shown)
    loop = _loop(tmp_path, "clarify", kernel=_FakeKernel())
    result = asyncio.run(loop.run("Give a Thai answer", acceptance_criteria=[{"kind": "language", "value": "th"}], on_plan=shown.append))
    assert result["stopped_reason"] == "waiting_for_clarification"
    assert result["intent_verification"]["aligned_with_intent"] is False
    assert result["acceptance_verification"]["satisfied"] is False
    assert not result["skill_extracted"] and not result["partial_completion"]["finished"]
    assert result["growth"]["delta"] == 0
    c = result["intent_contract"]
    # Reopen the real DB after discarding the first loop, as a restarted caller.
    fresh = _loop(tmp_path, "clarify", kernel=_FakeKernel())
    with pytest.raises(IntentContractError, match="nonempty"):
        asyncio.run(fresh.continue_intent(c["id"], c["version"]))
    store = IntentContractStore(fresh._persistence, "clarify")
    assert store.get(c["id"])["state"] == "waiting_for_clarification"
    done = asyncio.run(fresh.continue_intent(c["id"], c["version"], "Keep Thai", revised_goal="Answer briefly in Thai", on_plan=shown.append))
    after = done["intent_contract"]
    assert after["state"] == "criteria_satisfied"
    assert done["acceptance_verification"]["satisfied"] is True
    assert after["original_goal"] == "Give a Thai answer" and after["goal"] == "Answer briefly in Thai"
    assert after["revisions"][0]["user_response"] == "Keep Thai" and len(shown) == 2
    with pytest.raises(IntentContractError):
        asyncio.run(fresh.continue_intent(c["id"], c["version"], "replay"))


@pytest.mark.skipif(not supports_verified_reads(), reason='Protected files need POSIX no-follow reading (verified_budget.supports_verified_reads), which this platform lacks')
def test_protected_write_is_refused_before_dispatch(tmp_path, world, monkeypatch):
    script(monkeypatch, [{"action": "call_tool", "tool_name": "delentia_write_repo_file",
                          "tool_args": {"relative_path": "source.md", "content": "changed"}, "reasoning": "write"}])
    loop = _loop(tmp_path, "protected", kernel=_FakeKernel())
    result = asyncio.run(loop.run("Read source.md without changing it", acceptance_criteria=[{"kind": "file_unchanged", "value": "source.md"}], on_plan=lambda c: None))
    assert result["stopped_reason"] == "waiting_for_clarification"
    assert (world / "source.md").read_text(encoding='utf-8') == "original"
    assert not loop._mcp.dispatched


def test_contract_namespace_cas_and_sealed_storage(tmp_path, world):
    db = ControlPlanePersistence(db_path=str(tmp_path / "contracts.db"))
    owner = IntentContractStore(db, "alice")
    c = owner.create("private unique goal", [{"kind": "contains", "value": "4"}], world)
    with pytest.raises(IntentContractError, match="not found"):
        IntentContractStore(db, "bob").get(c["id"])
    owner.claim(c["id"], c["version"])
    with pytest.raises(IntentContractError):
        owner.claim(c["id"], c["version"])
    with db._connect() as conn:
        assert "private unique goal" not in conn.execute("SELECT payload FROM intent_contracts").fetchone()[0]


def test_correct_short_answer_uses_explicit_predicate(tmp_path, world, monkeypatch):
    script(monkeypatch, [finish("4")])
    result = asyncio.run(_loop(tmp_path, "short", kernel=_FakeKernel()).run(
        "What is 2+2?", acceptance_criteria=[{"kind": "contains", "value": "4"}], on_plan=lambda c: None))
    assert result["intent_contract"]["state"] == "criteria_satisfied"
    assert result["stopped_reason"] == "llm_finished"
    assert not result["skill_extracted"]


@pytest.mark.parametrize("relative", ["../outside.md", "/etc/passwd", "missing.md"])
def test_protected_file_must_exist_inside_the_workspace(tmp_path, world, relative):
    store = IntentContractStore(ControlPlanePersistence(db_path=str(tmp_path / "p.db")), "alice")
    with pytest.raises(IntentContractError):
        store.create("read", [{"kind": "file_unchanged", "value": relative}], world)


def test_http_plan_roundtrip_revised_plan_is_visible_before_resume(tmp_path, world, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, "_kernel", APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, "mcp", _FakeMCP())
    decisions = []
    async def decide(*args, **kwargs):
        decisions.append(1)
        return finish("English" if len(decisions) == 1 else "ภาษาไทย")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    with TestClient(create_app()) as client:
        response = client.post("/v1/agent/run", json={"goal": "Answer in Thai", "namespace": "api-owner",
                                                       "acceptance_criteria": [{"kind": "language", "value": "th"}]})
        assert response.status_code == 200, response.text
        c = response.json()["intent_contract"]
        assert not decisions and c["state"] == "plan_ready"
        url = f"/v1/agent/intent-contracts/{c['id']}"
        assert client.get(url, params={"namespace": "someone-else"}).status_code == 404
        result = client.post(url + "/continue", json={"namespace": "api-owner", "version": c["version"]}).json()
        assert result["stopped_reason"] == "waiting_for_clarification" and len(decisions) == 1
        c = result["intent_contract"]
        assert client.post(url + "/continue", json={"namespace": "api-owner", "version": c["version"]}).status_code == 409
        result = client.post(url + "/continue", json={"namespace": "api-owner", "version": c["version"], "response": "Keep Thai"}).json()
        assert result["stopped_reason"] == "plan_ready" and len(decisions) == 1
        c = result["intent_contract"]
        result = client.post(url + "/continue", json={"namespace": "api-owner", "version": c["version"]}).json()
        assert result["intent_contract"]["state"] == "criteria_satisfied" and len(decisions) == 2


def test_cli_prints_plan_before_model_then_exposes_waiting_question(tmp_path, world, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    monkeypatch.setattr(mcp_server, "_kernel", APIKernel(tmp_path))
    monkeypatch.setattr(mcp_server, "mcp", _FakeMCP())
    async def decide(*args, **kwargs):
        print("MODEL-CALLED")
        return finish("English")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    criteria = tmp_path / "criteria.json"
    criteria.write_text(json.dumps([{"kind": "language", "value": "th"}]), encoding='utf-8')
    result = CliRunner().invoke(cli, ["agent", "Answer in Thai", "--namespace", "cli-owner", "--criteria-file", str(criteria)])
    assert result.exit_code == 1, result.output
    assert result.output.index("Plan before execution") < result.output.index("MODEL-CALLED")
    assert "waiting_for_clarification" in result.output and "Which requirement" in result.output


def test_unsafe_previous_effect_cannot_be_replayed_on_clarification(tmp_path, world):
    store = IntentContractStore(ControlPlanePersistence(db_path=str(tmp_path / "unsafe.db")), "owner")
    c = store.create("answer", [{"kind": "contains", "value": "good"}], world)
    c = store.claim(c["id"], c["version"])
    c["safe_to_resume"] = False
    c = store.transition(c, "waiting_for_clarification")
    with pytest.raises(IntentContractError, match="reconciliation"):
        store.claim(c["id"], c["version"], "Try again")


def test_cli_continue_after_restart_and_invalid_criteria_report_errors(tmp_path, world, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    from rct_control_plane.tests.test_api_agent_run_real import _FakeKernel as APIKernel, _FakeMCP
    kernel = APIKernel(tmp_path)
    monkeypatch.setattr(mcp_server, "_kernel", kernel)
    monkeypatch.setattr(mcp_server, "mcp", _FakeMCP())
    store = IntentContractStore(kernel._persistence, "cli-owner")
    c = store.create("Answer four", [{"kind": "contains", "value": "4"}], world)
    script(monkeypatch, [finish("4")])
    runner = CliRunner()
    result = runner.invoke(cli, ["intent-contract", "continue", c["id"], "--namespace", "cli-owner", "--version", str(c["version"])])
    assert result.exit_code == 0, result.output
    assert "Plan before execution" in result.output and "criteria_satisfied" in result.output
    bad = tmp_path / "bad.json"
    bad.write_text('[{"kind": []}]', encoding='utf-8')
    result = runner.invoke(cli, ["agent", "test", "--criteria-file", str(bad)])
    assert result.exit_code != 0 and "unsupported criterion" in result.output


def test_erased_or_corrupted_contract_fails_closed(tmp_path, world):
    db = ControlPlanePersistence(db_path=str(tmp_path / "erased.db"))
    store = IntentContractStore(db, "owner")
    c = store.create("goal", [{"kind": "contains", "value": "answer"}], world)
    with db._connect() as conn:
        conn.execute("UPDATE intent_contracts SET payload='[erased]' WHERE id=?", (c["id"],))
    with pytest.raises(IntentContractError, match="erased or unavailable"):
        store.get(c["id"])


def test_unknown_external_effect_cannot_be_replayed(tmp_path, world, monkeypatch):
    from rct_control_plane import external_mcp
    loop = _loop(tmp_path, "external-effect", kernel=_FakeKernel())
    contract = asyncio.run(loop.run("Answer good", acceptance_criteria=[{"kind": "contains", "value": "good"}]))["intent_contract"]
    store = IntentContractStore(loop._persistence, "external-effect")
    loop._active_contract = store.claim(contract["id"], contract["version"])
    loop._contract_store = store
    monkeypatch.setattr(external_mcp, "needs_approval", lambda name: name == "mcp__unknown__send")
    async def decide(*args, **kwargs):
        return finish("wrong")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    # Supply the completed external-effect step at the end hook without
    # sending anything to a real external service.
    original_end = loop._on_episode_end
    async def with_external_result(result):
        result["steps"].append({"iteration": 0, "tool_name": "mcp__unknown__send", "tool_args": {}, "tool_result": {"error": "outcome unknown"}})
        return await original_end(result)
    monkeypatch.setattr(loop, "_on_episode_end", with_external_result)
    result = asyncio.run(loop.run("Answer good", intent_contract=loop._active_contract))
    assert not result["intent_contract"]["safe_to_resume"]
    c = result["intent_contract"]
    with pytest.raises(IntentContractError, match="reconciliation"):
        asyncio.run(loop.continue_intent(c["id"], c["version"], "again"))


def test_answer_contract_cannot_drop_criteria_through_pending_effect_approval(tmp_path, world, monkeypatch):
    script(monkeypatch, [{"action": "call_tool", "tool_name": "delentia_write_repo_file",
                          "tool_args": {"relative_path": "new.md", "content_text": "effect"}, "reasoning": "write"}])
    loop = _loop(tmp_path, "read-only-contract", kernel=_FakeKernel())
    result = asyncio.run(loop.run("Answer good", acceptance_criteria=[{"kind": "contains", "value": "good"}], on_plan=lambda c: None))
    assert result["stopped_reason"] == "waiting_for_clarification"
    assert result["intent_contract"]["differences"][0]["kind"] == "unsupported_effect"
    assert not loop._mcp.dispatched and "approval_id" not in result


def test_preparing_a_contract_cannot_hash_a_secret_file(tmp_path, world):
    (world / ".env").write_text("not-a-real-key", encoding='utf-8')
    store = IntentContractStore(ControlPlanePersistence(db_path=str(tmp_path / "secret.db")), "owner")
    with pytest.raises(IntentContractError, match="workspace read policy"):
        store.create("read", [{"kind": "file_unchanged", "value": ".env"}], world)


def test_competing_continuations_claim_only_once(tmp_path, world):
    from concurrent.futures import ThreadPoolExecutor
    db = ControlPlanePersistence(db_path=str(tmp_path / "race.db"))
    store = IntentContractStore(db, "owner")
    c = store.create("answer", [{"kind": "contains", "value": "ok"}], world)
    def claim(_):
        try:
            return store.claim(c["id"], c["version"])["state"]
        except IntentContractError:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == ["refused", "running"]


def test_unicode_contains_accepts_canonical_equivalence_without_changing_thai(world):
    from rct_control_plane.intent_contract import compare, build_plan, validate_criteria
    plan = build_plan('ตอบภาษาไทย', validate_criteria([{'kind': 'contains', 'value': 'café น้ำ กำลัง'}]), world)
    assert compare(plan, 'cafe\u0301 น้ำ กำลัง') == []
    assert compare(plan, 'cafe น้ำ กาลัง')


def test_schema_export_legacy_compatibility_and_future_schema_fail_closed(tmp_path, world):
    store = IntentContractStore(ControlPlanePersistence(db_path=str(tmp_path / 'schema.db')), 'owner')
    c = store.create('ข้อมูลภาษาไทย', [{'kind': 'contains', 'value': 'น้ำ'}], world)
    exported = store.export(c['id'])
    assert exported['contract']['schema_version'] == 1
    assert exported['contains_personal_text'] and exported['executable'] is False
    assert 'ข้อมูลภาษาไทย' in json.dumps(exported, ensure_ascii=False)
    with pytest.raises(IntentContractError):
        IntentContractStore(store.db, 'other').export(c['id'])
    data = {k: v for k, v in c.items() if k not in {'id', 'state', 'version', 'schema_version'}}
    with store.db._connect() as conn:
        conn.execute('UPDATE intent_contracts SET payload=? WHERE id=?', (store._encode(data), c['id']))
    assert store.get(c['id'])['schema_version'] == 1
    data['schema_version'] = 999
    with store.db._connect() as conn:
        conn.execute('UPDATE intent_contracts SET payload=? WHERE id=?', (store._encode(data), c['id']))
    with pytest.raises(IntentContractError, match='schema version'):
        store.claim(c['id'], c['version'])


@pytest.mark.parametrize('sealed', [True, False])
def test_signed_erasure_scrubs_contract_projection_without_affecting_other_owner(tmp_path, world, monkeypatch, sealed):
    from rct_control_plane import approvals, memory_erasure as er, memory_eventlog, audit_chain
    monkeypatch.setenv('DELENTIA_MEMORY_SEAL', '1' if sealed else '0')
    monkeypatch.setenv('DELENTIA_AUDIT_TEXT', 'sealed' if sealed else 'plain')
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / 'keys'))
    db = ControlPlanePersistence(db_path=str(tmp_path / 'erase-contract.db'))
    store = IntentContractStore(db, 'alice')
    alice = store.create('ALICE-PRIVATE-น้ำ-ข้อมูล', [{'kind': 'contains', 'value': 'น้ำ'}], world)
    bob_store = IntentContractStore(db, 'bob')
    bob = bob_store.create('BOB-PRIVATE-ข้อมูล', [{'kind': 'contains', 'value': 'ข้อมูล'}], world)
    key = tmp_path / 'outside' / 'approver.pem'
    public = approvals.generate_approver_key(str(key))
    monkeypatch.setenv('DELENTIA_APPROVER_PUBKEYS', public)
    head = memory_eventlog.MemoryEventLog(db).head()['hash']
    signature = er.sign_erase(str(key), 'alice', head)
    before = bob_store.get(bob['id'])
    er.erase_person(db, 'alice', 'owner requested erasure', signature['public_key'], signature['signature'])
    with pytest.raises(IntentContractError, match='erased'):
        store.get(alice['id'])
    with pytest.raises(IntentContractError):
        store.claim(alice['id'], alice['version'])
    assert bob_store.get(bob['id']) == before
    with db._connect() as conn:
        row = conn.execute('SELECT payload,state FROM intent_contracts WHERE id=?', (alice['id'],)).fetchone()
    assert tuple(row) == ('{}', 'erased')
    assert 'ALICE-PRIVATE'.encode() not in Path(db.db_path).read_bytes()
    assert not any(x['table'] == 'intent_contracts' for x in er.inventory(db, 'alice')['other_tables_with_this_person'])
    with db._connect() as conn:
        assert audit_chain.verify_audit_chain(conn).ok


def test_backup_restore_requires_namespace_key_and_preserves_waiting(tmp_path, world, monkeypatch):
    from rct_control_plane import backup, memory_erasure as er
    home = tmp_path / 'backup-home'
    home.mkdir()
    monkeypatch.setenv('DELENTIA_HOME', str(home))
    monkeypatch.setenv(er.KEYS_ENV, str(home / 'memory_keys'))
    db = ControlPlanePersistence(db_path=str(home / 'agentic.db'))
    store = IntentContractStore(db, 'alice')
    c = store.create('ข้อมูลสำหรับ backup', [{'kind': 'language', 'value': 'th'}], world)
    c = store.transition(store.claim(c['id'], c['version']), 'waiting_for_clarification')
    plain_zip, keyed_zip = tmp_path / 'no-keys.zip', tmp_path / 'with-keys.zip'
    backup.create_backup(str(plain_zip))
    backup.create_backup(str(keyed_zip), include_keys=True)
    restored = tmp_path / 'restore-no-keys'
    backup.restore_backup(str(plain_zip), str(restored))
    monkeypatch.setenv(er.KEYS_ENV, str(restored / 'home' / 'memory_keys'))
    restored_store = IntentContractStore(ControlPlanePersistence(db_path=str(restored / 'home' / 'agentic.db')), 'alice')
    with pytest.raises(IntentContractError, match='erased or unavailable'):
        restored_store.get(c['id'])
    keyed = tmp_path / 'restore-with-keys'
    backup.restore_backup(str(keyed_zip), str(keyed))
    monkeypatch.setenv(er.KEYS_ENV, str(keyed / 'home' / 'memory_keys'))
    recovered = IntentContractStore(ControlPlanePersistence(db_path=str(keyed / 'home' / 'agentic.db')), 'alice').get(c['id'])
    assert recovered['state'] == 'waiting_for_clarification'
    assert recovered['original_goal'] == c['original_goal'] and recovered['version'] == c['version']
