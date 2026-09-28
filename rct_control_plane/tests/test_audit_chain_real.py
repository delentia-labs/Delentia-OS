"""
Round 48 audit tier A1: every audit_trail row is hash-chained (and signed
when DELENTIA_AUDIT_SIGNING_KEY is set), and verify_audit_chain() finds
edits, deletions, reordering, rows inserted around the chain, and bad
signatures. Real SQLite, real Ed25519.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rct_control_plane import audit_chain
from rct_control_plane.persistence import ControlPlanePersistence

REPO_ROOT = Path(audit_chain.__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_ambient_signer(monkeypatch):
    monkeypatch.delenv(audit_chain.SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(audit_chain.PUBKEY_ENV, raising=False)


@pytest.fixture
def db(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "audit.db"))


def _write(db, n=3):
    for i in range(n):
        db.append_audit(entity_type="test_event", entity_id=f"e{i}", action="did", actor="tester",
                        changes={"i": i, "text": "สวัสดี"})


def _verify(db, **kw):
    with db._connect() as conn:
        return audit_chain.verify_audit_chain(conn, **kw)


class TestHashChain:
    def test_every_audit_row_is_chained_and_verifies(self, db):
        _write(db, 5)
        report = _verify(db)
        assert report.ok and report.chained_rows == 5 and report.signed_rows == 0
        with db._connect() as conn:
            head = audit_chain.chain_head(conn)
        assert head == {"seq": report.head_seq, "row_hash": report.head_hash}

    def test_editing_a_row_is_detected(self, db):
        _write(db)
        with db._connect() as conn:
            conn.execute("UPDATE audit_trail SET changes = ? WHERE entity_id = 'e1'", (json.dumps({"i": 99}),))
        report = _verify(db)
        assert not report.ok and "was modified" in report.reason

    def test_deleting_a_row_is_detected(self, db):
        _write(db)
        with db._connect() as conn:
            conn.execute("DELETE FROM audit_trail WHERE entity_id = 'e1'")
        report = _verify(db)
        assert not report.ok and "missing" in report.reason

    def test_removing_a_chain_link_is_detected(self, db):
        _write(db)
        with db._connect() as conn:
            conn.execute("DELETE FROM audit_chain WHERE seq = (SELECT MIN(seq) + 1 FROM audit_chain)")
        report = _verify(db)
        assert not report.ok and "broken link" in report.reason

    def test_row_inserted_around_the_chain_is_detected(self, db):
        _write(db)
        with db._connect() as conn:
            conn.execute("INSERT INTO audit_trail (entity_type, entity_id, action, actor, changes, created_at) "
                         "VALUES ('forged', 'x', 'did', 'intruder', '{}', '2026-01-01T00:00:00+00:00')")
        report = _verify(db)
        assert not report.ok and "without going through the chain" in report.reason

    def test_rows_written_before_the_chain_existed_are_legacy_not_failures(self, tmp_path):
        import sqlite3
        path = tmp_path / "legacy.db"
        ControlPlanePersistence(db_path=str(path))
        with sqlite3.connect(path) as conn:  # simulate pre-Round-48 rows: no chain entries
            conn.execute("DROP TABLE audit_chain")
            conn.execute("INSERT INTO audit_trail (entity_type, entity_id, action, actor, changes, created_at) "
                         "VALUES ('old', 'o', 'did', 'a', '{}', '2026-01-01T00:00:00+00:00')")
        db = ControlPlanePersistence(db_path=str(path))
        _write(db, 2)
        report = _verify(db)
        assert report.ok and report.legacy_unchained_rows == 1 and report.chained_rows == 2


class TestSigning:
    @pytest.fixture
    def signer(self, tmp_path, monkeypatch):
        key = tmp_path / "keys" / "audit.pem"
        public_hex = audit_chain.generate_signing_key(str(key))
        monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
        return public_hex

    def test_rows_are_signed_and_verify_with_the_public_key(self, db, signer):
        _write(db, 3)
        report = _verify(db, public_key_hex=signer)
        assert report.ok and report.signed_rows == 3

    def test_wrong_public_key_fails(self, db, signer, tmp_path):
        _write(db, 1)
        other = audit_chain.generate_signing_key(str(tmp_path / "other.pem"))
        report = _verify(db, public_key_hex=other)
        assert not report.ok and "unexpected key" in report.reason

    def test_recomputed_hash_without_the_key_fails_signature_check(self, db, signer):
        _write(db, 2)
        with db._connect() as conn:
            seq, audit_id = conn.execute("SELECT seq, audit_id FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
            prev = conn.execute("SELECT prev_hash FROM audit_chain WHERE seq = ?", (seq,)).fetchone()[0]
            conn.execute("UPDATE audit_trail SET actor = 'forger' WHERE id = ?", (audit_id,))
            row = conn.execute("SELECT entity_type, entity_id, action, actor, changes, created_at "
                               "FROM audit_trail WHERE id = ?", (audit_id,)).fetchone()
            conn.execute("UPDATE audit_chain SET row_hash = ? WHERE seq = ?",
                         (audit_chain.row_hash(prev, audit_id, *row), seq))
        # Hash-only verification cannot see this rewrite of the newest row...
        assert _verify(db).ok
        # ...but the signature can.
        report = _verify(db, public_key_hex=signer)
        assert not report.ok and "signature does not verify" in report.reason

    def test_unsigned_rows_fail_when_a_signer_is_expected(self, db, tmp_path, monkeypatch):
        _write(db, 1)
        public_hex = audit_chain.generate_signing_key(str(tmp_path / "late.pem"))
        report = _verify(db, public_key_hex=public_hex)
        assert not report.ok and "unsigned" in report.reason

    def test_signing_key_inside_the_repo_is_refused(self):
        with pytest.raises(ValueError, match="inside the repository"):
            audit_chain.generate_signing_key(str(REPO_ROOT / "audit-key-should-not-exist.pem"))
        assert not (REPO_ROOT / "audit-key-should-not-exist.pem").exists()


class TestCli:
    def test_verify_head_and_keygen(self, db, tmp_path):
        from rct_control_plane.cli import cli
        _write(db, 2)
        runner = CliRunner()
        r = runner.invoke(cli, ["audit-chain", "verify", "--db", db.db_path, "-o", "json"])
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["ok"] is True
        r = runner.invoke(cli, ["audit-chain", "head", "--db", db.db_path])
        assert r.exit_code == 0 and json.loads(r.output)["seq"] >= 1
        r = runner.invoke(cli, ["audit-chain", "keygen", "--out", str(tmp_path / "k" / "audit.pem")])
        assert r.exit_code == 0 and "public key" in r.output

    def test_verify_exits_nonzero_on_tampering(self, db):
        from rct_control_plane.cli import cli
        _write(db, 2)
        with db._connect() as conn:
            conn.execute("UPDATE audit_trail SET action = 'other' WHERE entity_id = 'e0'")
        r = CliRunner().invoke(cli, ["audit-chain", "verify", "--db", db.db_path])
        assert r.exit_code == 1 and "was modified" in r.output


class TestEpisodeSignatureIsReverifiable:
    """Before Round 48 the episode audit row kept only `jitna_verified: true`."""

    def _episode_row(self, tmp_path, monkeypatch, name):
        sys.path.insert(0, os.path.dirname(__file__))
        import asyncio
        import rct_control_plane.autonomous_loop as autonomous_loop_module
        from test_governed_autonomous_loop_real import _loop

        async def _finish(goal, history, tools, llm_provider=None, extra_context=""):
            return {"action": "finish", "reasoning": "r", "final_answer": f"Completed the goal: {goal}",
                    "tool_name": None, "tool_args": {}}
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _finish)
        loop = _loop(tmp_path, name)
        asyncio.run(loop.run("summarise the audit log"))
        persistence = loop._persistence
        del loop  # the key object is gone; only the stored record remains
        with persistence._connect() as conn:
            (changes,) = conn.execute(
                "SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_start'").fetchone()
        return json.loads(changes), persistence

    @staticmethod
    def _verifies(row):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(row["jitna_public_key"])).verify(
            bytes.fromhex(row["jitna_signature"]), row["jitna_content_hash"].encode("utf-8"))
        return True

    def test_ephemeral_key_record_verifies_and_says_it_is_ephemeral(self, tmp_path, monkeypatch):
        row, persistence = self._episode_row(tmp_path, monkeypatch, "ephemeral")
        assert row["jitna_key_persistent"] is False
        assert self._verifies(row)
        with persistence._connect() as conn:
            assert audit_chain.verify_audit_chain(conn).ok

    def test_persistent_key_signs_episodes_and_chain(self, tmp_path, monkeypatch):
        key = tmp_path / "keys" / "audit.pem"
        public_hex = audit_chain.generate_signing_key(str(key))
        monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
        row, persistence = self._episode_row(tmp_path, monkeypatch, "persistent")
        assert row["jitna_key_persistent"] is True
        assert row["jitna_public_key"] == public_hex
        assert self._verifies(row)
        with persistence._connect() as conn:
            report = audit_chain.verify_audit_chain(conn, public_key_hex=public_hex)
        assert report.ok and report.signed_rows == report.chained_rows > 0
