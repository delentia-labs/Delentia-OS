"""
Round 91: the RFC 3161 witness (audit_witness_tsa.py).

A REAL time-stamping authority is built here from the `openssl` command (a throw-away CA, a TSA certificate with the timeStamping usage, `openssl ts -reply`) and served over
real HTTP, so the token the host receives is a real CMS signature and `openssl ts -verify` is the real verifier. The attacks are real too: a rewritten chain, a truncated chain,
a token filed under the wrong head, a token from an authority the host does not trust, an authority that answers for another digest. An opt-in test talks to a public
authority (DELENTIA_REAL_SERVICES=1).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import base64
import json
import random
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rct_control_plane import audit_chain, audit_witness as aw, audit_witness_tsa as tsa
from rct_control_plane.persistence import ControlPlanePersistence

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")

TS_CONF = """
oid_section = new_oids
[ new_oids ]
tsa_policy1 = 1.2.3.4.1
[ tsa ]
default_tsa = tsa_config1
[ tsa_config1 ]
dir = .
serial = ./tsaserial
crypto_device = builtin
signer_cert = ./tsa.crt
certs = ./ca.crt
signer_key = ./tsa.key
signer_digest = sha256
default_policy = tsa_policy1
other_policies = tsa_policy1
digests = sha256
accuracy = secs:1
ordering = yes
tsa_name = yes
ess_cert_id_chain = no
ess_cert_id_alg = sha256
"""


def run(*args, cwd, data=None):
    done = subprocess.run(["openssl", *args], cwd=cwd, capture_output=True, timeout=60, input=data)
    assert done.returncode == 0, done.stderr.decode(errors="replace")[-400:]
    return done.stdout


def make_authority(folder: Path, name: str = "TestTSA") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    cwd = str(folder)
    (folder / "ts.cnf").write_text(TS_CONF, encoding="utf-8")
    (folder / "ext.cnf").write_text("extendedKeyUsage=critical,timeStamping\n", encoding="utf-8")
    (folder / "tsaserial").write_text("01\n", encoding="utf-8")
    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt", "-subj", f"/CN={name}-CA", "-days", "3", cwd=cwd)
    run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "tsa.key", "-out", "tsa.csr", "-subj", f"/CN={name}", cwd=cwd)
    run("x509", "-req", "-in", "tsa.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-out", "tsa.crt", "-days", "3", "-extfile", "ext.cnf", cwd=cwd)
    return folder


class Authority:
    """An HTTP time-stamping authority whose answers come from `openssl ts -reply`. `mode` lets a test make it lie."""

    def __init__(self, folder: Path, mode: str = "honest"):
        self.folder, self.mode, self.calls, self.canned = folder, mode, 0, None
        self.lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                query = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                with outer.lock:
                    outer.calls += 1
                    if outer.mode == "stale" and outer.canned is not None:
                        reply = outer.canned
                    else:
                        (outer.folder / "q.tsq").write_bytes(query)
                        run("ts", "-reply", "-queryfile", "q.tsq", "-config", "ts.cnf", "-out", "r.tsr", cwd=str(outer.folder))
                        reply = (outer.folder / "r.tsr").read_bytes()
                        outer.canned = outer.canned or reply
                self.send_response(200)
                self.send_header("Content-Type", "application/timestamp-reply")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}"

    def stop(self):
        self.http.shutdown()


@pytest.fixture
def world(tmp_path, monkeypatch):
    for name in (aw.WITNESSES_ENV, aw.URL_ENV, aw.KEY_ID_ENV, aw.INTERVAL_ENV, audit_chain.PUBKEY_ENV):
        monkeypatch.delenv(name, raising=False)
    key = tmp_path / "audit.pem"
    audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "chain.db"))
    folder = make_authority(tmp_path / "authority")
    authority = Authority(folder)
    spec = aw.WitnessSpec(type="rfc3161", name="tsa", key_id="host-1", url=authority.url, path=str(tmp_path / "tokens"), ca_file=str(folder / "ca.crt"))
    yield persistence, authority, spec, tmp_path
    authority.stop()


def add_rows(persistence, n, label="event"):
    for i in range(n):
        persistence.append_audit(entity_type="governed_loop_episode_start", entity_id=f"{label}-{i}", action="episode_start", actor="alice", changes={"goal": f"{label} {i}"})


# ------------------------------------------------------------------ the wire format

def test_the_request_we_build_is_a_valid_rfc3161_query(tmp_path):
    digest = bytes(range(32))
    raw = tsa.timestamp_query(digest, 0x1234567890ABCDEF)
    (tmp_path / "q.tsq").write_bytes(raw)
    text = run("ts", "-query", "-in", "q.tsq", "-text", cwd=str(tmp_path)).decode()
    assert "Hash Algorithm: sha256" in text and "Certificate required: yes" in text
    assert "00 01 02 03 04 05 06 07" in text.replace("-", " ")
    assert "Nonce: 0x1234567890ABCDEF" in text
    with pytest.raises(ValueError):
        tsa.timestamp_query(b"short", 1)


def test_a_real_token_is_read_correctly(world):
    persistence, authority, spec, tmp_path = world
    digest = bytes(range(32))
    (tmp_path / "q.tsq").write_bytes(tsa.timestamp_query(digest, 99))
    (authority.folder / "q.tsq").write_bytes((tmp_path / "q.tsq").read_bytes())
    reply = run("ts", "-reply", "-queryfile", "q.tsq", "-config", "ts.cnf", cwd=str(authority.folder))
    parsed = tsa.parse_timestamp_response(reply)
    assert parsed["granted"] and parsed["digest"] == digest.hex() and parsed["nonce"] == 99
    assert parsed["gen_time"].endswith("Z") and len(parsed["gen_time"]) >= 15


def test_malformed_responses_raise_only_value_or_index_errors(world):
    persistence, authority, spec, tmp_path = world
    digest = bytes(32)
    (authority.folder / "q.tsq").write_bytes(tsa.timestamp_query(digest, 5))
    good = run("ts", "-reply", "-queryfile", "q.tsq", "-config", "ts.cnf", cwd=str(authority.folder))
    rng = random.Random(91)
    for _ in range(300):
        data = bytearray(good)
        for _ in range(rng.randint(1, 6)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        cut = bytes(data[: rng.randrange(1, len(data))]) if rng.random() < 0.4 else bytes(data)
        try:
            tsa.parse_timestamp_response(cut)
        except (ValueError, IndexError):
            pass
    with pytest.raises(ValueError):
        tsa.parse_timestamp_response(b"\x30" * 300_000)
    with pytest.raises((ValueError, IndexError)):
        tsa.parse_timestamp_response(b"")


# ------------------------------------------------------------------ the witness

def test_a_head_is_time_stamped_and_the_signature_is_really_verified(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 4)
    results = aw.anchor_all(persistence._connect(), [spec])
    assert results[0]["ok"] and results[0]["entries"] == 4 and "time-stamped" in results[0]["detail"]
    held = aw.make(spec).fetch()
    assert [a["entries"] for a in held["anchors"]] == [4] and held["conflicts"] == [] and held["unchecked_signatures"] == 0
    report = aw.check_witnesses(persistence._connect(), [spec])[0]
    assert report["reachable"] and report["ok"] and report["highest_anchored"] == 4 and "unchecked_signatures" not in report
    status = aw.status(persistence._connect(), [spec])
    assert status["fresh_witnesses"] == 1 and status["tamper_evident_against_host_compromise"] and status["rows_not_yet_anchored"] == 0


def test_only_a_hash_leaves_the_host(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 3, label="the-secret-goal-text")
    aw.anchor_all(persistence._connect(), [spec])
    sent = (authority.folder / "q.tsq").read_bytes()
    assert b"the-secret-goal-text" not in sent and len(sent) < 80
    stored = (tmp_path / "tokens" / "host-1" / "3.json").read_text(encoding="utf-8")
    assert "the-secret-goal-text" not in stored


def test_a_rewritten_chain_no_longer_matches_what_the_authority_stamped(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 5)
    aw.anchor_all(persistence._connect(), [spec])
    conn = persistence._connect()
    # an attacker who holds the host's signing key rewrites row 3 and re-chains everything after it: the chain verifies by itself, but row 5 now hashes to something else
    conn.execute("UPDATE audit_trail SET changes = ? WHERE id = (SELECT audit_id FROM audit_chain WHERE seq = 3)", (json.dumps({"goal": "forged"}),))
    for seq in (3, 4, 5):
        conn.execute("UPDATE audit_chain SET row_hash = ? WHERE seq = ?", (f"{seq:x}" * 64, seq))
    conn.commit()
    report = aw.check_witnesses(conn, [spec])[0]
    assert not report["ok"] and any("rewritten" in p for p in report["problems"])


def test_a_truncated_chain_is_caught(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 6)
    aw.anchor_all(persistence._connect(), [spec])
    conn = persistence._connect()
    conn.execute("DELETE FROM audit_chain WHERE seq > 4")
    conn.commit()
    report = aw.check_witnesses(conn, [spec])[0]
    assert not report["ok"] and any("truncated" in p for p in report["problems"])


def test_a_token_filed_under_a_different_head_is_a_conflict(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 3)
    aw.anchor_all(persistence._connect(), [spec])
    f = tmp_path / "tokens" / "host-1" / "3.json"
    record = json.loads(f.read_text(encoding="utf-8"))
    record["head"] = "0" * 64                                   # someone edits the record next to the token
    f.write_text(json.dumps(record), encoding="utf-8")
    held = aw.make(spec).fetch()
    assert held["anchors"] == [] and "does not cover" in held["conflicts"][0]["reason"]
    report = aw.check_witnesses(persistence._connect(), [spec])[0]
    assert not report["ok"] and any("does not cover" in p for p in report["problems"])


def test_a_token_from_an_authority_the_host_does_not_trust_is_refused(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 2)
    aw.anchor_all(persistence._connect(), [spec])
    other = make_authority(tmp_path / "other_authority", name="OtherTSA")
    untrusting = aw.WitnessSpec(type="rfc3161", name="tsa", key_id="host-1", url=authority.url, path=spec.path, ca_file=str(other / "ca.crt"))
    held = aw.make(untrusting).fetch()
    assert held["anchors"] == [] and "no valid signature" in held["conflicts"][0]["reason"]


def test_without_openssl_the_token_is_read_but_reported_as_unchecked(world, monkeypatch):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 2)
    aw.anchor_all(persistence._connect(), [spec])
    monkeypatch.setattr(tsa.shutil, "which", lambda name: None)
    held = aw.make(spec).fetch()
    assert [a["entries"] for a in held["anchors"]] == [2] and held["unchecked_signatures"] == 1
    report = aw.check_witnesses(persistence._connect(), [spec])[0]
    assert report["ok"] and report["unchecked_signatures"] == 1


def test_rollback_and_fork_are_refused_and_a_repeat_is_idempotent(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 3)
    conn = persistence._connect()
    assert aw.anchor_all(conn, [spec])[0]["ok"]
    again = aw.anchor_all(conn, [spec])[0]
    assert again["ok"] and "already" in again["detail"] and authority.calls == 1
    add_rows(persistence, 2, label="later")
    assert aw.anchor_all(conn, [spec])[0]["ok"]
    body = audit_chain.sign_anchor(conn, "host-1")
    stale = dict(body, entries=2, head=conn.execute("SELECT row_hash FROM audit_chain WHERE seq = 2").fetchone()[0])
    with pytest.raises(aw.WitnessError, match="rollback refused"):
        aw.make(spec).publish(stale)
    fork = dict(body, entries=5, head="a" * 64)
    with pytest.raises(aw.WitnessError, match="fork refused"):
        aw.make(spec).publish(fork)


def test_an_authority_that_answers_for_another_digest_is_refused(world):
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 2)
    conn = persistence._connect()
    assert aw.anchor_all(conn, [spec])[0]["ok"]                 # primes the authority's canned reply
    authority.mode = "stale"                                    # from now on it replays that old token
    add_rows(persistence, 2, label="newer")
    result = aw.anchor_all(conn, [spec])[0]
    assert not result["ok"] and "different digest" in result["detail"]
    assert not (tmp_path / "tokens" / "host-1" / "4.json").exists()


def test_an_unreachable_authority_never_stops_the_other_witnesses(world, tmp_path):
    persistence, authority, spec, _ = world
    add_rows(persistence, 2)
    dead = aw.WitnessSpec(type="rfc3161", name="dead", key_id="host-1", url="http://127.0.0.1:9/", path=str(tmp_path / "dead"))
    results = aw.anchor_all(persistence._connect(), [dead, spec])
    assert [r["ok"] for r in results] == [False, True] and "unreachable" in results[0]["detail"]


def test_configuration_is_validated(monkeypatch, tmp_path):
    good = {"type": "rfc3161", "url": "http://timestamp.digicert.com", "path": str(tmp_path), "key_id": "k", "name": "tsa"}
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([good]))
    assert aw.specs_from_env()[0].type == "rfc3161"
    for bad in ({**good, "url": "ftp://x"}, {**good, "url": "http://user:pw@timestamp.example"}, {**good, "url": ""}, {k: v for k, v in good.items() if k != "path"}):
        monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([bad]))
        with pytest.raises(aw.WitnessError):
            aw.specs_from_env()


def test_the_token_file_is_a_standalone_proof(world):
    """A third party needs only the token, the digest and a CA file: no Delentia code, no database."""
    persistence, authority, spec, tmp_path = world
    add_rows(persistence, 3)
    aw.anchor_all(persistence._connect(), [spec])
    record = json.loads((tmp_path / "tokens" / "host-1" / "3.json").read_text(encoding="utf-8"))
    (tmp_path / "proof.tsr").write_bytes(base64.b64decode(record["tsr_b64"]))
    run("ts", "-verify", "-in", "proof.tsr", "-digest", record["digest"], "-CAfile", str(authority.folder / "ca.crt"), cwd=str(tmp_path))   # run() fails the test on a bad exit code
    wrong = subprocess.run(["openssl", "ts", "-verify", "-in", "proof.tsr", "-digest", "0" * 64, "-CAfile", str(authority.folder / "ca.crt")], cwd=str(tmp_path), capture_output=True)
    assert wrong.returncode != 0


@pytest.mark.skipif(os.environ.get("DELENTIA_REAL_SERVICES") != "1", reason="talks to public time-stamping authorities: set DELENTIA_REAL_SERVICES=1")
@pytest.mark.parametrize("url", ["http://timestamp.digicert.com", "http://timestamp.sectigo.com"])
def test_a_public_authority_time_stamps_and_the_default_ca_bundle_verifies_it(tmp_path, monkeypatch, url):
    for name in (aw.WITNESSES_ENV, aw.URL_ENV, aw.KEY_ID_ENV):
        monkeypatch.delenv(name, raising=False)
    key = tmp_path / "audit.pem"
    audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "chain.db"))
    add_rows(persistence, 2)
    spec = aw.WitnessSpec(type="rfc3161", name="public", key_id="host-1", url=url, path=str(tmp_path / "tokens"))
    assert aw.anchor_all(persistence._connect(), [spec])[0]["ok"]
    held = aw.make(spec).fetch()
    assert held["conflicts"] == [] and held["unchecked_signatures"] == 0 and held["anchors"][0]["received_at"].startswith("20")


# ------------------------------------------------------------------ the notary time-stamps its own log (the token lives where the agent's account cannot delete it)

@pytest.fixture
def notary_world(tmp_path):
    from rct_control_plane import notary
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    db = str(tmp_path / "notary" / "notary.db")
    store = notary.NotaryStore(db, key, "notary-test")
    for i in range(4):
        store.append({"kind": "tool_call", "n": i})
    authority = Authority(make_authority(tmp_path / "notary_authority"))
    yield notary, key, db, store, authority, tmp_path
    authority.stop()


def test_the_notary_time_stamps_its_head_and_the_cli_checks_the_tokens(notary_world):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    notary, key, db, store, authority, tmp_path = notary_world
    out = notary.timestamp_once(db, "host-notary-1", key, authority.url, str(tmp_path / "ts"), None, str(authority.folder / "ca.crt"))
    assert out["timestamped"] is True and out["entries"] == 4
    again = notary.timestamp_once(db, "host-notary-1", key, authority.url, str(tmp_path / "ts"), 4, str(authority.folder / "ca.crt"))
    assert again["timestamped"] is False and "unchanged" in again["reason"] and authority.calls == 1
    ok = CliRunner().invoke(cli, ["notary", "check-timestamps", "--dir", str(tmp_path / "ts"), "--key-id", "host-notary-1", "--db", db, "--ca", str(authority.folder / "ca.crt")])
    assert ok.exit_code == 0 and '"ok": true' in ok.output and '"tokens": 1' in ok.output


def test_a_rewritten_notary_log_fails_the_timestamp_check_and_a_truncated_one_too(notary_world):
    import sqlite3
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    notary, key, db, store, authority, tmp_path = notary_world
    notary.timestamp_once(db, "host-notary-1", key, authority.url, str(tmp_path / "ts"), None, str(authority.folder / "ca.crt"))
    args = ["notary", "check-timestamps", "--dir", str(tmp_path / "ts"), "--key-id", "host-notary-1", "--db", db, "--ca", str(authority.folder / "ca.crt")]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE notary_log SET hash = ? WHERE seq = 4", ("e" * 64,))
    rewritten = CliRunner().invoke(cli, args)
    assert rewritten.exit_code == 1 and "rewritten" in rewritten.output
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM notary_log WHERE seq > 2")
    truncated = CliRunner().invoke(cli, args)
    assert truncated.exit_code == 1 and "truncated" in truncated.output


def test_the_loop_time_stamps_only_when_the_head_moved_and_survives_a_dead_authority(notary_world):
    import threading
    import time
    notary, key, db, store, authority, tmp_path = notary_world
    results, seen = [], threading.Event()

    def on_result(r):
        results.append(r)
        seen.set()
    stop = notary.start_anchor_loop(db, "host-notary-1", key, None, 0.4, on_result=on_result, timestamp_url=authority.url, timestamp_dir=str(tmp_path / "ts"), timestamp_ca=str(authority.folder / "ca.crt"))
    try:
        assert seen.wait(20)
        time.sleep(1.3)
        store.append({"kind": "tool_call", "n": 99})
        time.sleep(1.3)
    finally:
        stop.set()
    stamped = [r for r in results if r.get("timestamped")]
    assert [r["entries"] for r in stamped] == [4, 5], results
    assert authority.calls == 2
    dead = notary.timestamp_once(db, "host-notary-1", key, "http://127.0.0.1:9/", str(tmp_path / "ts2"), None, "")
    assert dead["timestamped"] is False and "unreachable" in dead["reason"]


def test_serve_options_must_come_as_a_pair():
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    bad = CliRunner().invoke(cli, ["notary", "serve", "--timestamp-url", "http://timestamp.digicert.com", "--anchor-key-id", "k"])
    assert bad.exit_code == 1 and "go together" in bad.output
