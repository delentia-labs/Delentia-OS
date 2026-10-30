"""Contract/key/audit chain commit atomically, with erasure-safe retry keys."""
import hashlib
import sqlite3

import pytest

from rct_control_plane import memory_erasure
from rct_control_plane.audit_chain import verify_audit_chain
from rct_control_plane.intent_contract import IntentContractStore, IntentRequestConflict
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def store(tmp_path):
    return IntentContractStore(ControlPlanePersistence(db_path=str(tmp_path / 'state.db')), 'alice')


def create(store, tmp_path):
    return store.create('คืน JSON', [{'kind': 'json_object'}], tmp_path, request_id='request-1')


def fail_contract_audit(monkeypatch):
    original = ControlPlanePersistence._append_audit
    def append(conn, entity_type, *args, **kwargs):
        if entity_type == 'intent_contract':
            raise sqlite3.OperationalError('injected audit write failure')
        return original(conn, entity_type, *args, **kwargs)
    monkeypatch.setattr(ControlPlanePersistence, '_append_audit', staticmethod(append))


def test_failed_create_audit_rolls_back_contract_and_key(store, tmp_path, monkeypatch):
    fail_contract_audit(monkeypatch)
    with pytest.raises(sqlite3.OperationalError):
        create(store, tmp_path)
    with store.db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM intent_request_keys').fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type='intent_contract'").fetchone()[0] == 0


def test_failed_transition_audit_leaves_version_unclaimed(store, tmp_path, monkeypatch):
    contract = create(store, tmp_path)
    fail_contract_audit(monkeypatch)
    with pytest.raises(sqlite3.OperationalError):
        store.claim(contract['id'], contract['version'])
    assert store.get(contract['id']) == contract


def test_idempotent_retry_does_not_duplicate_audit(store, tmp_path):
    contract = create(store, tmp_path)
    assert create(store, tmp_path) == contract
    claimed = store.claim(contract['id'], contract['version'])
    assert create(store, tmp_path) == claimed
    with store.db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type='intent_contract'").fetchone()[0] == 2
        assert verify_audit_chain(conn).ok


def test_erasure_scrubs_request_fingerprint_and_keeps_replay_tombstone(store, tmp_path):
    contract = create(store, tmp_path)
    with store.db._connect() as conn:
        memory_erasure.scrub_tables(conn, 'alice')
        row = conn.execute('SELECT key_sha256,request_sha256,contract_id FROM intent_request_keys').fetchone()
        assert row[0] == hashlib.sha256(b'request-1').hexdigest()
        assert row[1] == '' and row[2] == contract['id']
    with pytest.raises(IntentRequestConflict):
        create(store, tmp_path)
    assert not any(t['table'] == 'intent_request_keys' for t in memory_erasure.inventory(store.db, 'alice')['other_tables_with_this_person'])


def test_unavailable_prior_contract_cannot_be_recreated(store, tmp_path):
    contract = create(store, tmp_path)
    with store.db._connect() as conn:
        conn.execute("UPDATE intent_contracts SET state='erased',payload='{}' WHERE id=?", (contract['id'],))
    with pytest.raises(IntentRequestConflict):
        create(store, tmp_path)
    with store.db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 1
