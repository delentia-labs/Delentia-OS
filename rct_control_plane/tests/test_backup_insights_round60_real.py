"""
Round 60 (D8): backup/restore of the runtime's state, and the insights report.

Real SQLite databases (one of them with a hash-chained audit trail that must still verify after a restore), real zip files, and a home directory built in a temp folder.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import sqlite3
import time
import zipfile

import pytest
from click.testing import CliRunner

from rct_control_plane import audit_chain, backup, envelope, insights
from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.session_search import SessionLog


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, user = tmp_path / "datahome", tmp_path / "userhome"
    (user / ".delentia" / "keys").mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("DELENTIA_HOME", str(home))
    monkeypatch.setenv("HOME", str(user))
    monkeypatch.setenv("USERPROFILE", str(user))
    persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
    for i in range(5):
        persistence.append_audit(entity_type="episode", entity_id=f"e{i}", action="x", actor="alice", changes={"n": i})
    (user / ".delentia" / "model.json").write_text('{"provider": "ollama"}', encoding="utf-8")
    (user / ".delentia" / "approvers.json").write_text('{"keys": {"abcd": "owner"}}', encoding="utf-8")
    (user / ".delentia" / "api_tokens.json").write_text('{"tokens": {"hash": "alice"}}', encoding="utf-8")
    (user / ".delentia" / "keys" / "audit.pem").write_text("-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----", encoding="utf-8")
    (home / "notes.txt").write_text("not state we back up", encoding="utf-8")
    return tmp_path, home, user, persistence


class TestBackup:
    def test_a_backup_holds_the_databases_and_the_configuration_but_not_the_secrets(self, world):
        tmp, home, user, _ = world
        done = backup.create_backup(str(tmp / "b.zip"))
        names = set(zipfile.ZipFile(done["path"]).namelist())
        assert "home/agentic.db" in names and "user/model.json" in names and "user/approvers.json" in names and "manifest.json" in names
        assert not any("pem" in n or "api_tokens" in n or "notes.txt" in n for n in names)
        assert done["includes_keys"] is False and "left out on purpose" in done["keys_note"]

    def test_include_keys_adds_the_private_key_and_says_so_in_the_manifest(self, world):
        tmp, *_ = world
        backup.create_backup(str(tmp / "k.zip"), include_keys=True)
        z = zipfile.ZipFile(tmp / "k.zip")
        assert any(n.endswith("audit.pem") for n in z.namelist()) and json.loads(z.read("manifest.json"))["includes_keys"] is True

    def test_a_backup_is_never_overwritten(self, world):
        tmp, *_ = world
        backup.create_backup(str(tmp / "b.zip"))
        with pytest.raises(backup.BackupError, match="never overwritten"):
            backup.create_backup(str(tmp / "b.zip"))

    def test_nothing_to_back_up_is_said_plainly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "empty"))
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "nohome"))
        with pytest.raises(backup.BackupError, match="nothing to back up"):
            backup.create_backup(str(tmp_path / "b.zip"))

    def test_a_database_that_is_being_written_to_is_copied_consistently(self, world):
        tmp, home, _, persistence = world
        done = backup.create_backup(str(tmp / "live.zip"))                    # the writer connection is still open
        persistence.append_audit(entity_type="episode", entity_id="late", action="x", actor="alice", changes={})
        restored = tmp / "r"
        backup.restore_backup(done["path"], str(restored))
        with sqlite3.connect(str(restored / "home" / "agentic.db")) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0] == 5          # what existed when the backup was taken, not the later row


class TestRestore:
    def test_the_audit_chain_still_verifies_after_a_restore(self, world):
        tmp, *_ = world
        done = backup.create_backup(str(tmp / "b.zip"))
        restored = tmp / "r"
        result = backup.restore_backup(done["path"], str(restored))
        assert result["restored"] == done["files"] and result["moved_aside"] == 0
        with sqlite3.connect(str(restored / "home" / "agentic.db")) as conn:
            report = audit_chain.verify_audit_chain(conn)
        assert report.ok and report.chained_rows == 5
        assert (restored / "user" / "model.json").read_text(encoding="utf-8") == '{"provider": "ollama"}'

    def test_restore_refuses_to_overwrite_and_with_force_moves_the_old_file_aside(self, world):
        tmp, *_ = world
        done = backup.create_backup(str(tmp / "b.zip"))
        restored = tmp / "r"
        backup.restore_backup(done["path"], str(restored))
        with pytest.raises(backup.BackupError, match="already exist"):
            backup.restore_backup(done["path"], str(restored))
        (restored / "user" / "model.json").write_text("changed by hand", encoding="utf-8")
        result = backup.restore_backup(done["path"], str(restored), force=True)
        assert result["moved_aside"] >= 1
        aside = list((restored / "user").glob("model.json.before-restore-*"))
        assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == "changed by hand"          # nothing was deleted
        assert (restored / "user" / "model.json").read_text(encoding="utf-8") == '{"provider": "ollama"}'

    def test_a_changed_byte_fails_the_whole_restore_before_anything_is_written(self, world):
        tmp, *_ = world
        done = backup.create_backup(str(tmp / "b.zip"))
        tampered = tmp / "t.zip"
        with zipfile.ZipFile(done["path"]) as src, zipfile.ZipFile(tampered, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "user/approvers.json":
                    data = data.replace(b"owner", b"mallory")
                dst.writestr(item.filename, data)
        target = tmp / "r"
        with pytest.raises(backup.BackupError, match="does not match"):
            backup.restore_backup(str(tampered), str(target))
        assert not target.exists()

    def test_a_file_the_manifest_does_not_list_is_refused(self, world):
        tmp, *_ = world
        done = backup.create_backup(str(tmp / "b.zip"))
        with zipfile.ZipFile(done["path"], "a") as z:
            z.writestr("home/evil.db", b"x")
        with pytest.raises(backup.BackupError, match="does not list"):
            backup.verify_backup(done["path"])

    @pytest.mark.parametrize("evil", ["../escape.txt", "/etc/passwd", "home/../../escape.txt", "C:/Windows/x", "other/x.json", "home"])
    def test_names_that_try_to_leave_the_target_are_refused(self, tmp_path, evil):
        path = tmp_path / "evil.zip"
        data = b"x"
        import hashlib
        manifest = {"format": backup.FORMAT, "created_at": time.time(), "includes_keys": False,
                    "files": [{"name": evil, "kind": "config", "bytes": 1, "sha256": hashlib.sha256(data).hexdigest()}]}
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(evil, data)
            z.writestr("manifest.json", json.dumps(manifest))
        target = tmp_path / "t"
        with pytest.raises(backup.BackupError):
            backup.restore_backup(str(path), str(target))
        assert not (tmp_path / "escape.txt").exists() and not target.exists()

    def test_not_a_backup_and_not_a_zip(self, tmp_path):
        (tmp_path / "plain.txt").write_text("hello", encoding="utf-8")
        with pytest.raises(backup.BackupError, match="cannot open"):
            backup.verify_backup(str(tmp_path / "plain.txt"))
        with zipfile.ZipFile(tmp_path / "other.zip", "w") as z:
            z.writestr("a.txt", "x")
        with pytest.raises(backup.BackupError, match="not a Delentia backup"):
            backup.verify_backup(str(tmp_path / "other.zip"))

    def test_the_cli_round_trip(self, world):
        tmp, *_ = world
        runner = CliRunner()
        created = runner.invoke(cli, ["backup", "create", "--out", str(tmp / "c.zip")])
        assert created.exit_code == 0 and "left out on purpose" in created.output
        assert "valid:" in runner.invoke(cli, ["backup", "verify", str(tmp / "c.zip")]).output
        restored = runner.invoke(cli, ["backup", "restore", str(tmp / "c.zip"), "--to", str(tmp / "rr")])
        assert restored.exit_code == 0 and "restored" in restored.output
        again = runner.invoke(cli, ["backup", "restore", str(tmp / "c.zip"), "--to", str(tmp / "rr")])
        assert again.exit_code == 1 and "already exist" in again.output


class TestInsights:
    def test_the_report_adds_up(self, tmp_path):
        p = ControlPlanePersistence(db_path=str(tmp_path / "i.db"))
        now = time.time()
        envelope.record(p, "alice", "e1", 0.01, 1000, "llm_finished", now=now - 100)
        envelope.record(p, "alice", "e2", 0.02, 2000, "pending_approval", now=now - 50)
        envelope.record(p, "bob", "e3", None, 500, "llm_finished", now=now - 10)
        envelope.record(p, "bob", "e4", 0.0, 0, "paused", now=now - 5)
        envelope.record(p, "carol", "old", 9.0, 9999, "llm_finished", now=now - 30 * 86400)
        log = SessionLog(p)
        log.record("alice", "read a page", "ok", tainted=True)
        log.record("bob", "plain", "ok")
        from rct_control_plane.approvals import PendingActionStore
        store = PendingActionStore(p)
        store.create("alice", "g", "delentia_write_repo_file", {})
        store.create("bob", "g", "delentia_remember", {})
        report = insights.report(p, days=7, now=now)
        assert report["episodes"] == 4 and report["tokens"] == 3500 and report["cost_usd"] == pytest.approx(0.03) and report["episodes_with_unknown_cost"] == 1
        assert report["stop_reasons"] == {"llm_finished": 2, "pending_approval": 1, "paused": 1}
        assert report["tainted_episodes"] == {"tainted": 1, "of": 2} and report["signatures"]["asked"] == 2 and report["signatures"]["still_waiting"] == 2
        assert [u["namespace"] for u in report["top_users"]][:2] in (["alice", "bob"], ["bob", "alice"]) and "carol" not in json.dumps(report["top_users"])
        text = insights.render(report)
        assert "4 episodes" in text and "paused 1" in text and "1 of 2" in text

    def test_an_empty_store_is_a_valid_report_and_the_cli_prints_it(self, tmp_path):
        out = CliRunner().invoke(cli, ["insights", "--days", "3", "--db", str(tmp_path / "e.db")])
        assert out.exit_code == 0 and "0 episodes" in out.output and "Signatures: 0 asked" in out.output
