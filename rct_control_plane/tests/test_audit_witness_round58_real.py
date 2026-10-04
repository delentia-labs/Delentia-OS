"""
Round 58: tamper-evidence with independent witnesses (audit_witness.py) and the standalone proof verifier (scripts/verify_audit_bundle.py).
Real SQLite audit chain with real Ed25519 signatures, a REAL git repository with a real bare "remote", a real HTTP witness speaking the Worker's protocol, and an attacker who
rewrites the log. The verifier is run as a separate Python process that imports nothing from this repository.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import shutil
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import audit_chain, audit_witness as aw
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence

ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER = ROOT / "scripts" / "verify_audit_bundle.py"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


class WorkerWitness:
    """The fdia Worker's anchor protocol: POST /v1/audit/anchor stores; refuses a rollback or a fork and remembers the refusal; GET /v1/audit/anchor/<key_id> lists."""

    def __init__(self):
        self.anchors, self.conflicts, self.refused = [], [], 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, payload):
                raw = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                last = outer.anchors[-1] if outer.anchors else None
                if last and (body["entries"] < last["entries"] or (body["entries"] == last["entries"] and body["head"] != last["head"])):
                    outer.refused += 1
                    outer.conflicts.append(body)
                    return self._send(409, {"error": "rollback or fork"})
                if not last or body["entries"] > last["entries"]:
                    outer.anchors.append({**body, "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                self._send(201, {"stored": True})

            def do_GET(self):  # noqa: N802
                self._send(200, {"anchors": outer.anchors, "conflicts": outer.conflicts})

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}"

    def stop(self):
        self.http.shutdown()


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def world(tmp_path, monkeypatch):
    for name in (aw.WITNESSES_ENV, aw.URL_ENV, aw.KEY_ID_ENV, aw.INTERVAL_ENV, audit_chain.PUBKEY_ENV):
        monkeypatch.delenv(name, raising=False)
    key = tmp_path / "audit.pem"
    public = audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "chain.db"))
    worker = WorkerWitness()
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(bare))
    config = [{"type": "http", "name": "worker", "url": worker.url, "key_id": "host-1"},
              {"type": "git", "name": "git-mirror", "path": str(tmp_path / "anchors"), "remote": "origin", "branch": "main", "key_id": "host-1"}]
    (tmp_path / "anchors").mkdir()
    git("init", "-q", "-b", "main", cwd=str(tmp_path / "anchors"))
    git("remote", "add", "origin", str(bare), cwd=str(tmp_path / "anchors"))
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps(config))
    yield persistence, worker, bare, tmp_path, public
    worker.stop()


def add_rows(persistence, n, label="event"):
    for i in range(n):
        persistence.append_audit(entity_type="governed_loop_episode_start", entity_id=f"{label}-{i}", action="episode_start", actor="alice", changes={"goal": f"{label} {i}"})


def conn_of(persistence):
    return persistence._connect()


# ------------------------------------------------------------------ configuration

def test_the_witness_list_is_validated_not_half_applied(monkeypatch):
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{"type": "http", "url": "http://evil.example", "key_id": "k"}]))
    with pytest.raises(aw.WitnessError, match="https"):
        aw.specs_from_env()
    for bad in ("[]", '[{"type": "ftp", "key_id": "k"}]', '[{"type": "git", "key_id": "k"}]', '[{"type": "git", "path": "/x"}]',
                json.dumps([{"type": "git", "path": "/a", "key_id": "k", "name": "n"}, {"type": "git", "path": "/b", "key_id": "k", "name": "n"}])):
        monkeypatch.setenv(aw.WITNESSES_ENV, bad)
        with pytest.raises(aw.WitnessError):
            aw.specs_from_env()
    monkeypatch.setenv(aw.WITNESSES_ENV, "not json")
    with pytest.raises(ValueError):
        aw.specs_from_env()


def test_the_older_single_witness_settings_still_work(monkeypatch):
    monkeypatch.delenv(aw.WITNESSES_ENV, raising=False)
    monkeypatch.setenv(aw.URL_ENV, "https://witness.example.org")
    monkeypatch.setenv(aw.KEY_ID_ENV, "delentia-os-1")
    specs = aw.specs_from_env()
    assert [(s.type, s.name, s.key_id) for s in specs] == [("http", "worker", "delentia-os-1")]
    monkeypatch.delenv(aw.URL_ENV)
    assert aw.specs_from_env() == []


# ------------------------------------------------------------------ publishing and the state of protection

def test_one_signed_head_reaches_both_witnesses_and_the_git_one_is_really_pushed(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 5)
    with conn_of(persistence) as conn:
        results = aw.anchor_all(conn)
    assert [(r["witness"], r["ok"]) for r in results] == [("worker", True), ("git-mirror", True)]
    assert worker.anchors[-1]["entries"] == 5 and aw.verify_anchor_signature(worker.anchors[-1], public)
    pushed = git("show", "main:anchors/host-1.jsonl", cwd=str(bare))                      # read from the REMOTE, not from the host's working copy
    line = json.loads(pushed.strip().splitlines()[-1])
    assert line["entries"] == 5 and line["head"] == worker.anchors[-1]["head"] and aw.verify_anchor_signature(line, public)
    assert "anchor host-1 entries=5" in git("log", "-1", "--format=%s", cwd=str(bare))


def test_anchoring_the_same_head_twice_is_quiet_and_a_growing_chain_adds_a_line(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 3)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
        again = aw.anchor_all(conn)
        assert all(r["ok"] for r in again) and again[1]["detail"] == "already anchored"
    add_rows(persistence, 4, "more")
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    assert [json.loads(l)["entries"] for l in git("show", "main:anchors/host-1.jsonl", cwd=str(bare)).strip().splitlines()] == [3, 7]


def test_one_dead_witness_does_not_stop_the_other_and_is_not_hidden(world):
    persistence, worker, bare, tmp_path, public = world
    worker.stop()
    add_rows(persistence, 2)
    with conn_of(persistence) as conn:
        results = aw.anchor_all(conn)
        status = aw.status(conn)
    assert [r["ok"] for r in results] == [False, True] and "unreachable" in results[0]["detail"]
    by = {w["name"]: w for w in status["witnesses"]}
    assert by["worker"]["fresh"] is False and by["worker"]["last_attempt_ok"] is False and by["git-mirror"]["fresh"] is True
    assert status["fresh_witnesses"] == 1 and status["tamper_evident_against_host_compromise"] is True and "add a second" in status["plain"]


def test_status_says_plainly_when_nothing_protects_the_log(world, monkeypatch):
    persistence, *_ = world
    monkeypatch.delenv(aw.WITNESSES_ENV)
    add_rows(persistence, 4)
    with conn_of(persistence) as conn:
        status = aw.status(conn)
    assert status["configured"] == 0 and status["tamper_evident_against_host_compromise"] is False and status["rows_not_yet_anchored"] == 4
    assert "would not be noticed" in status["plain"]


def test_the_unanchored_window_is_the_number_of_rows_after_the_newest_anchor(world):
    persistence, *_ = world
    add_rows(persistence, 5)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "late")
    with conn_of(persistence) as conn:
        status = aw.status(conn)
    assert status["rows_not_yet_anchored"] == 3 and status["head_seq"] == 8 and "the 3 row(s) newer" in status["plain"]


def test_an_anchor_goes_stale_when_the_interval_passes_without_one(world, monkeypatch):
    persistence, *_ = world
    monkeypatch.setenv(aw.INTERVAL_ENV, "60")
    add_rows(persistence, 2)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn, now=1000.0)
        assert aw.status(conn, now=1100.0)["fresh_witnesses"] == 2          # within 2 x 60 + 60
        stale = aw.status(conn, now=1000.0 + 500)
    assert stale["fresh_witnesses"] == 0 and stale["tamper_evident_against_host_compromise"] is False and "no witness has received the head recently" in stale["plain"]


# ------------------------------------------------------------------ the attacker

def rewrite_history(persistence, upto_seq):
    """What someone with the host's root can do: change an old row and recompute every hash after it (and, having the key on the host, sign it all again)."""
    with sqlite3.connect(str(persistence.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT c.seq, c.audit_id, t.entity_type, t.entity_id, t.action, t.actor, t.changes, t.created_at FROM audit_chain c JOIN audit_trail t ON t.id = c.audit_id ORDER BY c.seq").fetchall()
        signer = audit_chain.load_signing_key()
        prev = audit_chain.GENESIS_HASH
        for r in rows:
            changes = '{"goal": "nothing happened here"}' if r["seq"] == 2 else r["changes"]
            if r["seq"] == 2:
                conn.execute("UPDATE audit_trail SET changes = ? WHERE id = ?", (changes, r["audit_id"]))
            h = audit_chain.row_hash(prev, r["audit_id"], r["entity_type"], r["entity_id"], r["action"], r["actor"], changes, r["created_at"])
            conn.execute("UPDATE audit_chain SET prev_hash = ?, row_hash = ?, signature_hex = ? WHERE seq = ?", (prev, h, signer.sign(bytes.fromhex(h)).hex(), r["seq"]))
            prev = h


def test_a_rewrite_of_the_whole_log_with_every_hash_and_signature_redone_passes_the_hosts_own_check_but_not_the_witnesses(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 6)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    rewrite_history(persistence, 6)
    with conn_of(persistence) as conn:
        own = audit_chain.verify_audit_chain(conn, public_key_hex=public)
        report = aw.check_witnesses(conn)
    assert own.ok is True                                                               # the host cannot tell: this is exactly why a witness is needed
    assert [r["ok"] for r in report] == [False, False] and all(any("rewritten" in p for p in r["problems"]) for r in report)


def test_truncating_the_newest_rows_is_caught_by_the_witnesses_not_by_the_chain(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 6)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    with sqlite3.connect(str(persistence.db_path)) as conn:
        conn.execute("DELETE FROM audit_chain WHERE seq > 3")
        conn.execute("DELETE FROM audit_trail WHERE id > (SELECT MAX(audit_id) FROM audit_chain)")
    with conn_of(persistence) as conn:
        assert audit_chain.verify_audit_chain(conn, public_key_hex=public).ok is True
        report = aw.check_witnesses(conn)
    assert all(not r["ok"] and any("truncated" in p for p in r["problems"]) for r in report)


def test_a_witness_refuses_to_go_backwards_and_the_git_one_says_why(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 6)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    with sqlite3.connect(str(persistence.db_path)) as conn:
        conn.execute("DELETE FROM audit_chain WHERE seq > 3")
        conn.execute("DELETE FROM audit_trail WHERE id > (SELECT MAX(audit_id) FROM audit_chain)")
    with conn_of(persistence) as conn:
        results = aw.anchor_all(conn)                                                   # the attacker (or an honest restore from backup) tries to anchor the shorter chain
    assert [r["ok"] for r in results] == [False, False] and worker.refused == 1
    assert "rollback refused" in results[1]["detail"] and "was already anchored" in results[1]["detail"]


def test_a_forged_anchor_at_a_witness_is_noticed_by_its_signature(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 3)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    forged = dict(worker.anchors[-1], entries=99, head="f" * 64, signature="00" * 64)
    worker.anchors.append(forged)                                                       # somebody with access to the witness writes an entry the host never signed
    with conn_of(persistence) as conn:
        report = aw.check_witnesses(conn)
    http = next(r for r in report if r["witness"] == "worker")
    assert not http["ok"] and any("do not verify with this host's public key" in p for p in http["problems"])


def test_a_force_push_that_rewrites_the_git_witness_history_shows_as_a_conflict_or_a_mismatch(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 4)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    clone = tmp_path / "attacker"
    git("clone", "-q", str(bare), str(clone))
    path = clone / "anchors" / "host-1.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    row["head"] = "a" * 64                                                              # an attacker with push rights replaces the anchored head
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    git("-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qam", "rewrite", cwd=str(clone))
    git("push", "-q", "--force", "origin", "main", cwd=str(clone))
    with conn_of(persistence) as conn:
        report = aw.check_witnesses(conn)
    assert not next(r for r in report if r["witness"] == "git-mirror")["ok"] and next(r for r in report if r["witness"] == "worker")["ok"]       # the other witness still agrees with the chain


def test_an_unreachable_witness_is_a_failed_check_not_a_pass(world):
    persistence, worker, bare, tmp_path, public = world
    add_rows(persistence, 2)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
    worker.stop()
    with conn_of(persistence) as conn:
        report = aw.check_witnesses(conn)
    assert next(r for r in report if r["witness"] == "worker") == {"witness": "worker", "reachable": False, "ok": False, "checked": 0, "problems": [report[0]["problems"][0]]}


# ------------------------------------------------------------------ the proof bundle and the standalone verifier

def verify_bundle(path, *args):
    done = subprocess.run([sys.executable, str(VERIFIER), str(path), "--json", *args], capture_output=True, text=True, cwd=str(path.parent))
    return done.returncode, json.loads(done.stdout)


def test_the_verifier_is_standalone_and_accepts_an_untouched_bundle(world, tmp_path):
    persistence, worker, bare, _, public = world
    add_rows(persistence, 8)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
        bundle = aw.export_proof(conn, witnesses=[{"name": "worker", **json.loads(json.dumps({"anchors": worker.anchors}))}])
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert "rct_control_plane" not in VERIFIER.read_text(encoding="utf-8").replace("Delentia code", "")
    code, report = verify_bundle(path, "--pubkey", public)
    assert code == 0 and report["ok"] and report["rows_checked"] == 8 and report["rows_signed"] == 8 and report["anchors_checked"] == 1 and report["key_source"] == "argument"


def test_the_verifier_catches_an_edited_row_a_dropped_row_a_swapped_key_and_a_forged_anchor(world, tmp_path):
    persistence, worker, bare, _, public = world
    add_rows(persistence, 6)
    with conn_of(persistence) as conn:
        aw.anchor_all(conn)
        good = aw.export_proof(conn, witnesses=[{"name": "worker", "anchors": worker.anchors}])

    def check(mutate, *args):
        bundle = json.loads(json.dumps(good))
        mutate(bundle)
        p = tmp_path / "b.json"
        p.write_text(json.dumps(bundle), encoding="utf-8")
        return verify_bundle(p, *args)

    code, report = check(lambda b: b["rows"][2].__setitem__("changes", '{"goal": "edited"}'), "--pubkey", public)
    assert code == 1 and any("row 3: its recorded content does not hash" in p for p in report["problems"])
    code, report = check(lambda b: b["rows"].pop(3), "--pubkey", public)
    assert code == 1 and any("not the row after" in p or "prev_hash does not match" in p for p in report["problems"])
    code, report = check(lambda b: b["rows"][1].__setitem__("signature_hex", "00" * 64), "--pubkey", public)
    assert code == 1 and any("signature does not verify" in p for p in report["problems"])
    other = audit_chain.generate_signing_key(str(tmp_path / "other.pem"))
    code, report = check(lambda b: None, "--pubkey", other)
    assert code == 1 and any("different signer key" in p for p in report["problems"])
    code, report = check(lambda b: b["witnesses"][0]["anchors"][0].__setitem__("head", "e" * 64), "--pubkey", public)
    assert code == 1 and any("anchor at worker" in p for p in report["problems"])


def test_a_bundle_cannot_vouch_for_its_own_key_and_the_verifier_says_so(world, tmp_path):
    persistence, worker, bare, _, public = world
    add_rows(persistence, 3)
    with conn_of(persistence) as conn:
        path = tmp_path / "b.json"
        path.write_text(json.dumps(aw.export_proof(conn)), encoding="utf-8")
    code, report = verify_bundle(path)
    assert code == 0 and report["key_source"] == "bundle" and any("INSIDE the bundle" in n for n in report["notes"])


def test_a_hashes_only_bundle_checks_links_and_signatures_and_says_content_was_not_bound(world, tmp_path):
    persistence, worker, bare, _, public = world
    add_rows(persistence, 4)
    with conn_of(persistence) as conn:
        bundle = aw.export_proof(conn, include_content=False)
    assert "changes" not in bundle["rows"][0] and "entity_id" not in bundle["rows"][0]                     # nothing about what happened leaves the host
    path = tmp_path / "b.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, report = verify_bundle(path, "--pubkey", public)
    assert code == 0 and any("content was not included" in n for n in report["notes"])


def test_a_partial_bundle_is_accepted_for_what_it_covers_and_says_where_it_stops_and_starts(world, tmp_path):
    persistence, worker, bare, _, public = world
    add_rows(persistence, 10)
    with conn_of(persistence) as conn:
        bundle = aw.export_proof(conn, from_seq=4, to_seq=7)
    path = tmp_path / "b.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, report = verify_bundle(path, "--pubkey", public)
    assert code == 0 and report["rows_checked"] == 4
    assert any("starts at row 4" in n for n in report["notes"]) and any("stops before the chain's head" in n for n in report["notes"])


def test_a_garbage_file_is_refused_with_an_exit_code(tmp_path):
    path = tmp_path / "x.json"
    path.write_text("not json", encoding="utf-8")
    assert subprocess.run([sys.executable, str(VERIFIER), str(path)], capture_output=True, text=True).returncode == 2
    path.write_text(json.dumps({"format": "something else"}), encoding="utf-8")
    assert verify_bundle(path)[0] == 1


# ------------------------------------------------------------------ the CLI, the daemon task and the Desk

def test_the_cli_anchors_checks_reports_and_exports(world, tmp_path, monkeypatch):
    persistence, worker, bare, _, public = world
    monkeypatch.setenv("RCT_AGENTIC_DB_PATH", str(tmp_path / "cli-agentic.db"))      # the CLI's own store: not the one earlier tests in a full run have already written to
    from rct_control_plane.data_home import agentic_db_path
    cli_persistence = ControlPlanePersistence(db_path=agentic_db_path())
    add_rows(cli_persistence, 5)
    runner = CliRunner()
    anchored = runner.invoke(cli, ["audit-chain", "anchor-all"])
    assert anchored.exit_code == 0 and "ok   worker" in anchored.output and "ok   git-mirror" in anchored.output
    checked = runner.invoke(cli, ["audit-chain", "check-witnesses"])
    assert checked.exit_code == 0 and json.loads(checked.output)[0]["ok"] is True
    status = json.loads(runner.invoke(cli, ["audit-chain", "witness-status"]).output)
    assert status["fresh_witnesses"] == 2 and status["rows_not_yet_anchored"] == 0
    out = tmp_path / "proof.json"
    exported = runner.invoke(cli, ["audit-chain", "export-proof", "--out", str(out)])
    assert exported.exit_code == 0 and "2 witness(es) consulted" in exported.output
    code, report = verify_bundle(out, "--pubkey", public)
    assert code == 0, report


def test_the_cli_fails_loudly_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv(aw.WITNESSES_ENV, raising=False)
    runner = CliRunner()
    assert runner.invoke(cli, ["audit-chain", "anchor-all"]).exit_code == 1
    assert runner.invoke(cli, ["audit-chain", "check-witnesses"]).exit_code == 1


def test_the_daemon_task_anchors_every_witness_and_is_on_only_with_a_witness_and_a_key(world, monkeypatch):
    from rct_control_plane.autonomous_scheduler import AutonomousScheduler, anchor_configured
    persistence, worker, bare, tmp_path, public = world
    assert anchor_configured() is True
    scheduler = AutonomousScheduler(kernel=type("K", (), {"_persistence": persistence})())
    assert scheduler.tasks["task_audit_chain_anchor"].is_enabled is True
    add_rows(persistence, 3)
    result = asyncio_run(scheduler.trigger_task_async("task_audit_chain_anchor"))
    assert result["status"] == "SUCCESS" and "anchored at 2 of 2 witness(es)" in result["output"] and worker.anchors[-1]["entries"] == 3
    monkeypatch.delenv(audit_chain.SIGNING_KEY_ENV)
    assert anchor_configured() is False
    monkeypatch.setenv(aw.WITNESSES_ENV, "not json")
    assert anchor_configured() is False


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def test_every_witness_failing_makes_the_daemon_task_fail_visibly(world):
    from rct_control_plane.autonomous_scheduler import AutonomousScheduler
    persistence, worker, bare, tmp_path, public = world
    worker.stop()
    shutil.rmtree(tmp_path / "remote.git")
    add_rows(persistence, 2)
    scheduler = AutonomousScheduler(kernel=type("K", (), {"_persistence": persistence})())
    result = asyncio_run(scheduler.trigger_task_async("task_audit_chain_anchor"))
    assert result["status"] == "FAILED" and "no witness received the head" in result["error"]


def test_the_desk_reports_protection_in_numbers_checks_every_witness_and_turns_a3_on_only_for_a_fresh_one(world, monkeypatch):
    persistence, worker, bare, tmp_path, public = world
    monkeypatch.setattr(desk_api, "_kernel", lambda: type("K", (), {"_persistence": persistence})())
    add_rows(persistence, 4)
    with TestClient(create_app()) as client:
        a3 = lambda: next(c for c in client.get("/v1/desk/governance").json()["controls"] if c["id"] == "audit_anchor")   # noqa: E731
        assert a3()["on"] is False and "no witness has received the head recently" in a3()["detail"]
        with conn_of(persistence) as conn:
            aw.anchor_all(conn)
        assert a3()["on"] is True and "2 independent witness(es)" in a3()["detail"]
        second = next(c for c in client.get("/v1/desk/governance").json()["controls"] if c["id"] == "audit_second_witness")
        assert second["on"] is True
        status = client.get("/v1/desk/governance/audit/witnesses").json()
        assert status["fresh_witnesses"] == 2 and status["rows_not_yet_anchored"] == 0
        checked = client.post("/v1/desk/governance/audit/check-witnesses").json()
        assert checked["ok"] is True and [w["witness"] for w in checked["witnesses"]] == ["worker", "git-mirror"]
        rewrite_history(persistence, 4)
        bad = client.post("/v1/desk/governance/audit/check-witnesses").json()
        assert bad["ok"] is False and all(not w["ok"] for w in bad["witnesses"])
        monkeypatch.delenv(aw.WITNESSES_ENV)
        assert client.post("/v1/desk/governance/audit/check-witnesses").status_code == 409
        monkeypatch.setenv(aw.WITNESSES_ENV, "not json")
        broken = client.post("/v1/desk/governance/audit/check-witnesses")
        assert broken.status_code == 409 and "unusable" in broken.json()["detail"]
