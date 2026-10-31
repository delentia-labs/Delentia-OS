"""Actual SQLite contract claim refuses stale or incomplete bound evidence."""
from datetime import datetime, timedelta, timezone

import pytest

from rct_control_plane.evidence_assessment import observe
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop


def requirement(age=0, value='100'):
    now = datetime.now(timezone.utc) - timedelta(seconds=age)
    return {'schema_version': 1, 'policy': {'id': 'fresh-quote', 'required_claim_ids': ['total']},
            'observations': [observe('read1', 'quote.json', b'100', now).model_dump(mode='json')],
            'claims': [{'id': 'total', 'observation_id': 'read1', 'subject': 'quote', 'key': 'THB',
                        'value': value, 'claimed_at': now.isoformat()}], 'max_age_seconds': 60}


def test_current_evidence_is_plan_bound_and_checked_before_running(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'gate')._persistence, 'gate')
    req = requirement()
    c = store.create('Compare quote', [{'kind': 'json_object'}], tmp_path, evidence_requirement=req)
    req['claims'][0]['value'] = 'changed by caller'
    assert store.get(c['id'])['plan']['evidence_requirement']['claims'][0]['value'] == '100'
    running = store.claim(c['id'], c['version'])
    assert running['state'] == 'running'
    assert running['evidence_decision']['satisfies_declared_policy']
    assert running['evidence_decision']['grants_execution'] is False


@pytest.mark.parametrize('change', ['stale', 'missing', 'conflict', 'unknown_date'])
def test_bad_evidence_never_claims_running(tmp_path, change):
    store = IntentContractStore(_loop(tmp_path, 'gate')._persistence, 'gate')
    req = requirement(age=120 if change == 'stale' else 0)
    if change == 'missing': req['claims'] = []
    if change == 'unknown_date': req['claims'][0].pop('claimed_at')
    if change == 'conflict': req['claims'].append({**req['claims'][0], 'id': 'other', 'value': '101'})
    c = store.create('Compare quote', [{'kind': 'json_object'}], tmp_path, evidence_requirement=req)
    with pytest.raises(IntentContractError, match='evidence requirement not satisfied'):
        store.claim(c['id'], c['version'])
    assert store.get(c['id'])['state'] == 'plan_ready'
    assert store.get(c['id'])['version'] == c['version']


def test_bound_evidence_tampering_is_detected_by_plan_digest(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'gate')._persistence, 'gate')
    c = store.create('Compare quote', [{'kind': 'json_object'}], tmp_path, evidence_requirement=requirement())
    # Exercise the stored plan digest check without recomputing it.
    with store.db._connect() as conn:
        import json
        row = conn.execute('SELECT payload FROM intent_contracts WHERE id=?', (c['id'],)).fetchone()
        from rct_control_plane import audit_text
        data = audit_text.reveal('gate', json.loads(row[0])['data'])
        data['plan']['evidence_requirement']['max_age_seconds'] = 999
        conn.execute('UPDATE intent_contracts SET payload=? WHERE id=?', (store._encode(data), c['id']))
    with pytest.raises(IntentContractError, match='plan digest mismatch'):
        store.get(c['id'])


def test_claim_reassesses_age_instead_of_reusing_creation_result(tmp_path, monkeypatch):
    from rct_control_plane import evidence_requirement as gate
    store = IntentContractStore(_loop(tmp_path, 'gate')._persistence, 'gate')
    c = store.create('Compare quote', [{'kind': 'json_object'}], tmp_path, evidence_requirement=requirement())
    original = gate.check_requirement
    monkeypatch.setattr(gate, 'check_requirement', lambda value, now: original(value, now + timedelta(seconds=120)))
    with pytest.raises(IntentContractError, match='stale'):
        store.claim(c['id'], c['version'])
    assert store.get(c['id'])['state'] == 'plan_ready'


def test_replanning_preserves_bound_requirement_and_clears_old_decision(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'gate')._persistence, 'gate')
    c = store.create('Compare quote', [{'kind': 'json_object'}], tmp_path, evidence_requirement=requirement())
    running = store.claim(c['id'], c['version'])
    waiting = store.transition(running, 'waiting_for_clarification')
    revised = store.claim(c['id'], waiting['version'], response='Use explicit JSON')
    assert revised['plan']['evidence_requirement'] == c['plan']['evidence_requirement']
    assert 'evidence_decision' not in revised
