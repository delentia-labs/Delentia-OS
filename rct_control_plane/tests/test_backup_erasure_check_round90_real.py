"""
Round 90: `delentia backup erasure-check`. Round 87's whole-job test found that a backup made BEFORE an erasure still holds the person's words in readable tables. The check lists the backups that
predate an erasure recorded in the live audit chain, so a person can rotate or destroy them. Real SQLite, real backups, a real signed erasure; nothing is mocked.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import time

import pytest
from click.testing import CliRunner

from rct_control_plane import approvals, backup
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
from rct_control_plane.cli import cli
from rct_control_plane.data_home import agentic_db_path
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "no-approvers.json"))
    pem = tmp_path / "outside" / "approver.pem"
    public = approvals.generate_approver_key(str(pem))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    p = ControlPlanePersistence(db_path=agentic_db_path())
    p.save_memory("a", "alice", "fact", "alice keeps the key under the flower pot", {}, 0.8)
    p.save_memory("b", "bob", "fact", "bob likes tea", {}, 0.5)
    return p, str(pem), tmp_path


def erase_alice(p, pem):
    log = me.MemoryEventLog(p)
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    return er.erase_person(p, "alice", "asked to be forgotten", sig["public_key"], sig["signature"])


def test_a_backup_made_before_the_erasure_is_listed_and_one_made_after_is_not(world):
    p, pem, tmp = world
    before = tmp / "before.zip"
    backup.create_backup(str(before))
    time.sleep(1.1)
    assert erase_alice(p, pem)["erased"]
    time.sleep(1.1)
    after = tmp / "after.zip"
    backup.create_backup(str(after))
    junk = tmp / "junk.zip"
    junk.write_bytes(b"not a zip")
    result = backup.erasure_check([str(tmp)], p)
    by_name = {r["backup"].split(os.sep)[-1].split("/")[-1]: r for r in result["report"]}
    assert result["erasures_recorded"] == 1 and result["backups_holding_erased_people"] == 1
    assert by_name["before.zip"]["status"] == "holds_erased_people" and by_name["before.zip"]["namespaces"] == ["alice"] and "rotate or destroy" in by_name["before.zip"]["advice"]
    assert by_name["after.zip"]["status"] == "ok"
    assert by_name["junk.zip"]["status"] == "not_a_valid_backup"          # reported, never silently skipped
    assert before.exists()                                                # nothing is deleted (Zero-Delete)


def test_with_no_erasure_every_valid_backup_is_ok(world):
    p, pem, tmp = world
    backup.create_backup(str(tmp / "one.zip"))
    result = backup.erasure_check([str(tmp / "one.zip")], p)
    assert result["erasures_recorded"] == 0 and result["backups_holding_erased_people"] == 0 and result["report"][0]["status"] == "ok"


def test_the_command_exits_with_1_when_a_backup_holds_an_erased_person(world):
    p, pem, tmp = world
    backup.create_backup(str(tmp / "old.zip"))
    time.sleep(1.1)
    erase_alice(p, pem)
    out = CliRunner().invoke(cli, ["backup", "erasure-check", str(tmp / "old.zip"), "--db", agentic_db_path()])
    assert out.exit_code == 1 and "HOLDS ERASED PEOPLE" in out.output and "alice" in out.output
    clean = CliRunner().invoke(cli, ["backup", "erasure-check", str(tmp / "old.zip"), "--db", str(tmp / "empty.db")])
    assert clean.exit_code == 0 and "[ok]" in clean.output
