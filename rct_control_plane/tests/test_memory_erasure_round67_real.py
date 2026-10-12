"""
Round 67: per-person erasure by destroying a key (memory_erasure.py). Real SQLite, real AES-GCM, real Ed25519 approver keys, the real audit chain. Nothing is mocked.

What is pinned: the log's text is ciphertext in the database; the chain keeps verifying after the key is gone; erasure needs a trusted approver's signature over this person at this head;
the report says what was NOT erased; another person is untouched; the table copy is scrubbed; the anchors still match.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sqlite3

import pytest

from rct_control_plane import approvals
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
from rct_control_plane.persistence import ControlPlanePersistence

SECRET = "my landlord Somchai lives at 12 Sukhumvit Soi 4 and his phone is 081-234-5678"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv(me.ENABLE_ENV, raising=False)
    monkeypatch.delenv(er.SEAL_ENV, raising=False)
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.setenv(me.CHECKPOINT_ENV, "5")
    monkeypatch.setenv(me.ANCHOR_ENV, "10")
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "no-approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    p = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    return p, me.MemoryEventLog(p), tmp_path


def approver(tmp_path, monkeypatch, name="approver.pem"):
    pem = tmp_path / "outside" / name
    public = approvals.generate_approver_key(str(pem))
    return str(pem), public


def trust(monkeypatch, *publics):
    monkeypatch.setenv(approvals.APPROVERS_ENV, ",".join(publics))


def stored_text(db):
    conn = sqlite3.connect(db)
    blobs = [r[0] for r in conn.execute("SELECT payload FROM memory_events")] + [bytes(r[0]).decode("latin-1") for r in conn.execute("SELECT state_zstd FROM memory_checkpoints")]
    conn.close()
    return " ".join(blobs)


def fill(p):
    p.save_memory("a", "alice", "fact", SECRET, {}, 0.8)
    for i in range(12):
        p.save_memory(f"x{i}", "alice", "fact", f"alice note {i}", {}, 0.5)
    p.save_memory("b", "bob", "fact", "bob keeps his budget at 15000", {}, 0.5)
    p.revoke_memory("a", "alice", "reason mentions Somchai too")


def test_the_log_holds_ciphertext_not_the_text(world):
    p, log, tmp = world
    fill(p)
    raw = stored_text(str(tmp / "m.db"))
    assert "Somchai" not in raw and "Sukhumvit" not in raw and "081-234" not in raw
    assert log.fold("alice", include_revoked=True)["a"]["content"] == SECRET        # the holder of the key reads it back
    assert log.verify()["ok"] and log.consistent_with_table("alice")["ok"]


def test_sealing_can_be_switched_off(world, monkeypatch):
    p, log, tmp = world
    monkeypatch.setenv(er.SEAL_ENV, "off")
    p.save_memory("a", "alice", "fact", SECRET, {}, 0.5)
    assert "Somchai" in stored_text(str(tmp / "m.db"))
    assert er.inventory(p, "alice")["plaintext_events"] == 1


def test_erasure_needs_a_trusted_approver_and_the_exact_head(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    with pytest.raises(er.ErasureError, match="no approver key"):
        er.erase_person(p, "alice", "requested by the person", "ab" * 32, "cd" * 64)
    pem, public = approver(tmp, monkeypatch)
    other_pem, _ = approver(tmp, monkeypatch, "other.pem")
    trust(monkeypatch, public)
    stranger = er.sign_erase(other_pem, "alice", log.head()["hash"])
    with pytest.raises(er.ErasureError, match="not a trusted approver"):
        er.erase_person(p, "alice", "x", stranger["public_key"], stranger["signature"])
    stale = er.sign_erase(pem, "alice", log.head()["hash"])
    p.save_memory("late", "alice", "fact", "written after the signature", {}, 0.5)             # the head moved
    with pytest.raises(er.ErasureError, match="does not match this request"):
        er.erase_person(p, "alice", "x", stale["public_key"], stale["signature"])
    wrong_person = er.sign_erase(pem, "bob", log.head()["hash"])
    with pytest.raises(er.ErasureError, match="does not match this request"):
        er.erase_person(p, "alice", "x", wrong_person["public_key"], wrong_person["signature"])
    good = er.sign_erase(pem, "alice", log.head()["hash"])
    with pytest.raises(er.ErasureError, match="reason"):
        er.erase_person(p, "alice", "  ", good["public_key"], good["signature"])
    assert er.get_key("alice") is not None                                                    # no refusal destroyed anything


def test_erasing_a_person_destroys_their_text_and_leaves_the_chain_intact(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    events_before = log.stats("alice")["events"]
    old_fp = er.fingerprint(er.get_key("alice"))
    bob_before = log.fold("bob")
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    report = er.erase_person(p, "alice", "the person asked to be forgotten", sig["public_key"], sig["signature"])
    assert report["erased"] and report["key_destroyed"] and report["table_rows_scrubbed"] == 13
    new_key = er.get_key("alice")                                                             # the checkpoint written with the erase event may create a fresh key; it is never the old one
    assert new_key is None or er.fingerprint(new_key) != old_fp
    after = log.fold("alice", include_revoked=True)
    assert len(after) == 13 and all(m["content"] == "[erased]" and m.get("erased") for m in after.values())
    assert log.stats("alice")["events"] == events_before + 1                                  # the history is still there, plus the erase event
    assert log.verify()["ok"] and log.verify_anchors()["ok"] and log.consistent_with_table("alice")["ok"]
    assert log.fold("bob") == bob_before                                                      # another person is untouched
    assert er.get_key("bob") is not None
    conn = sqlite3.connect(str(tmp / "m.db"))
    assert {r[0] for r in conn.execute("SELECT content FROM memories WHERE namespace = 'alice'")} == {"[erased]"}
    assert conn.execute("SELECT content FROM memories WHERE namespace = 'bob'").fetchone()[0].startswith("bob keeps")
    audit = conn.execute("SELECT changes FROM audit_trail WHERE action = 'memory_erased'").fetchone()
    assert audit and "the person asked" in audit[0] and "Somchai" not in audit[0]
    from rct_control_plane import audit_chain
    assert audit_chain.verify_audit_chain(conn).ok


def test_the_report_says_what_was_not_erased(world, monkeypatch):
    p, log, tmp = world
    monkeypatch.setenv(er.SEAL_ENV, "off")
    p.save_memory("old", "alice", "fact", "written before sealing existed", {}, 0.5)          # a plaintext event: its hash fixes its text, it cannot be sealed later
    monkeypatch.delenv(er.SEAL_ENV)
    p.save_memory("new", "alice", "fact", "written after", {}, 0.5)
    with p._connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sessions_demo (id INTEGER PRIMARY KEY, namespace TEXT, goal TEXT)")
        conn.execute("INSERT INTO sessions_demo (namespace, goal) VALUES ('alice', 'a past request')")
        conn.execute("CREATE TABLE IF NOT EXISTS odd_table (id INTEGER PRIMARY KEY, namespace TEXT, body TEXT)")        # a column this module does not know carries the person's words
        conn.execute("INSERT INTO odd_table (namespace, body) VALUES ('alice', 'something the person wrote')")
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    report = er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    assert report["not_erased"]["plaintext_events_in_the_chain"] == 1
    assert {"table": "odd_table", "rows": 1} in report["not_erased"]["other_tables"]                         # an unknown column is listed, never silently skipped
    assert {"table": "sessions_demo", "rows": 1, "columns": ["goal"]} in report["other_tables_scrubbed"]      # a known one is overwritten
    assert "backups" in report["not_erased"]["note"]


def test_a_returning_person_starts_again_with_a_new_key(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    old_fp = er.fingerprint(er.get_key("alice"))
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    p.save_memory("again", "alice", "fact", "a new beginning", {}, 0.5)
    assert er.fingerprint(er.get_key("alice")) != old_fp
    state = log.fold("alice", include_revoked=True)
    assert state["again"]["content"] == "a new beginning" and state["a"]["content"] == "[erased]"
    assert log.verify()["ok"]


def test_checkpoints_are_sealed_and_unreadable_after_erasure(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    assert log.stats("alice")["checkpoints"] >= 1
    assert "Somchai" not in stored_text(str(tmp / "m.db"))
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    assert log.verify()["ok"]                                                                 # the checkpoint hash covers the ciphertext
    assert all(m["content"] == "[erased]" for m in log.fold("alice", include_revoked=True).values())


def test_the_archive_of_a_sealed_person_verifies_with_the_key_and_by_hash_without_it(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    log.export_archive("alice", str(tmp / "alice.zst"))
    assert me.verify_archive(str(tmp / "alice.zst"))["ok"]
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    after = me.verify_archive(str(tmp / "alice.zst"))
    assert after["ok"] and after["replay_checked"] is False and after["sealed_events"] > 0       # without the key only the hashes can be checked, and it says so


def test_the_key_file_is_named_by_a_hash_of_the_person(world):
    p, log, tmp = world
    p.save_memory("a", "alice", "fact", "x", {}, 0.5)
    files = list((tmp / "keys").iterdir())
    assert len(files) == 1 and "alice" not in files[0].name and len(files[0].read_text().strip()) == 64
    if os.name != "nt":
        assert oct(files[0].stat().st_mode & 0o777) == "0o600"


def test_the_command_line_flow_request_sign_erase(world, monkeypatch):
    import json
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    p, log, tmp = world
    fill(p)
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    db = str(tmp / "m.db")
    run = CliRunner()
    req = run.invoke(cli, ["memory", "erase-request", "alice", "--db", db])
    assert req.exit_code == 0, req.output
    asked = json.loads(req.output[req.output.index("{"):])
    assert asked["inventory"]["sealed_events"] > 0 and asked["head_hash"] == log.head()["hash"]
    sig = json.loads(run.invoke(cli, ["memory", "erase-sign", "alice", asked["head_hash"], "--approver-key", pem]).output)
    refused = run.invoke(cli, ["memory", "erase", "alice", "--reason", "asked", "--public-key", sig["public_key"], "--signature", sig["signature"], "--confirm", "bob", "--db", db])
    assert refused.exit_code == 1 and er.get_key("alice") is not None
    done = run.invoke(cli, ["memory", "erase", "alice", "--reason", "asked", "--public-key", sig["public_key"], "--signature", sig["signature"], "--confirm", "alice", "--db", db])
    assert done.exit_code == 0, done.output
    assert json.loads(done.output[done.output.index("{"):])["erased"] is True
    assert all(m["content"] == "[erased]" for m in log.fold("alice", include_revoked=True).values())


def test_after_an_erase_the_text_is_gone_from_every_byte_of_the_database_file(world, monkeypatch):
    p, log, tmp = world
    fill(p)
    for _ in range(3):
        p.touch_memory("a")
    pem, public = approver(tmp, monkeypatch)
    trust(monkeypatch, public)
    needle = b"Somchai"
    with p._connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert needle in (tmp / "m.db").read_bytes()                       # before: the readable copy in the table
    sig = er.sign_erase(pem, "alice", log.head()["hash"])
    report = er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    assert report["vacuumed"] is True
    leftovers = [f.name for f in tmp.rglob("*") if f.is_file() and needle in f.read_bytes()]
    assert leftovers == [], leftovers


def test_host_check_h23_reports_the_log_sealing_and_where_the_keys_are(world, monkeypatch, tmp_path):
    from rct_control_plane import host_check
    only = lambda: host_check.check_memory_log()[0]                                      # noqa: E731
    assert only().status == "PASS"
    monkeypatch.setenv(er.SEAL_ENV, "off")
    assert only().status == "WARN" and "not sealed" in only().detail
    monkeypatch.delenv(er.SEAL_ENV)
    monkeypatch.setenv(me.ENABLE_ENV, "off")
    assert only().status == "WARN" and "log is off" in only().detail
    monkeypatch.delenv(me.ENABLE_ENV)
    inside = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "keys-in-repo")
    monkeypatch.setenv(er.KEYS_ENV, inside)
    assert only().status == "FAIL" and "inside the repository" in only().detail
