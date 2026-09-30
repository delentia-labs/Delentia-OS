"""
Round 50: the audit hash chain on PostgreSQL (parity with the SQLite chain).

Runs against a real PostgreSQL when DELENTIA_TEST_PG_DSN is set (CI starts a
postgres service for this); skipped otherwise. Every test works in its own
fresh schema, so nothing is ever dropped or truncated.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import threading
import uuid

import pytest

DSN = os.getenv("DELENTIA_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set DELENTIA_TEST_PG_DSN to run the PostgreSQL audit chain tests")


@pytest.fixture
def pg(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    monkeypatch.delenv("DELENTIA_AUDIT_SIGNING_KEY", raising=False)
    schema = f"audit_test_{uuid.uuid4().hex[:12]}"
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
    from rct_control_plane.persistence_pg import PostgresPersistence
    return PostgresPersistence(dsn=f"{DSN} options='-csearch_path={schema}'")


def _write(p, n, start=0):
    for i in range(start, start + n):
        p.append_audit(entity_type="test", entity_id=f"e{i}", action="write", actor="tester",
                       changes={"i": i, "z": "last", "a": "first", "thai": "ทดสอบ"})


def _exec(p, sql, params=()):
    with p._connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)


def test_an_untouched_chain_verifies_and_has_a_head(pg):
    _write(pg, 5)
    report = pg.verify_audit_chain()
    assert report.ok and report.chained_rows == 5 and report.signed_rows == 0
    assert pg.chain_head() == {"seq": report.head_seq, "row_hash": report.head_hash}


def test_editing_a_row_is_detected(pg):
    _write(pg, 4)
    _exec(pg, "UPDATE audit_trail SET changes = %s::jsonb WHERE entity_id = 'e2'", ('{"i": 999}',))
    report = pg.verify_audit_chain()
    assert not report.ok and "was modified" in report.reason


def test_removing_a_link_is_detected(pg):
    _write(pg, 4)
    _exec(pg, "DELETE FROM audit_chain WHERE seq = (SELECT MIN(seq) + 1 FROM audit_chain)")
    report = pg.verify_audit_chain()
    assert not report.ok and "broken link" in report.reason


def test_a_row_written_around_the_chain_is_detected(pg):
    _write(pg, 2)
    _exec(pg, "INSERT INTO audit_trail (entity_type, entity_id, action, actor, changes, created_at) "
              "VALUES ('test', 'sneaky', 'write', 'x', '{}'::jsonb, now())")
    report = pg.verify_audit_chain()
    assert not report.ok and "without going through the chain" in report.reason


def test_signed_rows_verify_only_against_the_right_key(pg, tmp_path, monkeypatch):
    from rct_control_plane import audit_chain
    key_path = tmp_path / "keys" / "audit.pem"
    public_hex = audit_chain.generate_signing_key(str(key_path))
    monkeypatch.setenv("DELENTIA_AUDIT_SIGNING_KEY", str(key_path))
    _write(pg, 3)
    assert pg.verify_audit_chain(public_hex).signed_rows == 3
    assert pg.verify_audit_chain(public_hex).ok
    other = audit_chain.generate_signing_key(str(tmp_path / "keys" / "other.pem"))
    report = pg.verify_audit_chain(other)
    assert not report.ok and "unexpected key" in report.reason


def test_concurrent_writers_cannot_fork_the_chain(pg):
    errors = []

    def worker(k):
        try:
            _write(pg, 10, start=k * 100)
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    report = pg.verify_audit_chain()
    assert report.ok and report.chained_rows == 40


def test_the_same_head_format_can_be_anchored(pg):
    _write(pg, 3)
    head = pg.chain_head()
    assert head["seq"] >= 3 and len(head["row_hash"]) == 64
