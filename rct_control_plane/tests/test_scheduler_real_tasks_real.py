"""
Round 50: the daemon's default tasks do real work. The earlier defaults returned
fixed strings ("verified 207,000 invariants... Zero violations") and reported
SUCCESS without running anything. Now: audit_chain_verify recomputes the chain,
and audit_chain_anchor publishes the signed head to a tier-A3 witness on a
schedule (off until the host configures it). Real SQLite, real Ed25519, a real
HTTP witness stand-in on an ephemeral port that checks the signature.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from rct_control_plane import audit_chain
from rct_control_plane.autonomous_scheduler import (
    ANCHOR_KEY_ID_ENV, ANCHOR_URL_ENV, AutonomousScheduler, anchor_configured,
)
from rct_control_plane.persistence import ControlPlanePersistence


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def kernel(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "k.db"))
    for i in range(3):
        persistence.append_audit(entity_type="t", entity_id=str(i), action="a", actor="x", changes={"i": i})
    return _Kernel(persistence)


@pytest.fixture
def signing_key(tmp_path, monkeypatch):
    path = tmp_path / "keys" / "audit.pem"
    public_hex = audit_chain.generate_signing_key(str(path))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(path))
    return public_hex


@pytest.fixture
def witness(signing_key):
    """Stand-in for the fdia Worker's /v1/audit/anchor: verifies the Ed25519
    signature over the v1 anchor message and refuses a rollback."""
    received = []
    verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signing_key))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            msg = audit_chain.anchor_message(body["key_id"], body["entries"], body["head"], body["signed_at"])
            try:
                verifier.verify(bytes.fromhex(body["signature"]), msg.encode())
                ok = not received or body["entries"] >= received[-1]["entries"]
            except Exception:
                ok = False
            if ok:
                received.append(body)
            self.send_response(201 if ok else 409)
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"url": f"http://127.0.0.1:{server.server_address[1]}", "received": received}
    server.shutdown()
    server.server_close()


def _clear_anchor_env(monkeypatch):
    for name in (ANCHOR_URL_ENV, ANCHOR_KEY_ID_ENV):
        monkeypatch.delenv(name, raising=False)


def test_no_fake_default_tasks_remain(kernel, monkeypatch):
    _clear_anchor_env(monkeypatch)
    names = {t["name"] for t in AutonomousScheduler(kernel=kernel).list_tasks()}
    assert {"audit_chain_verify", "audit_chain_anchor", "reminder_poller"} <= names
    assert not names & {"daily_ai_news_digest", "nightly_stress_benchmark", "exchange_integrity_audit"}


def test_verify_task_reports_a_real_chain(kernel):
    result = asyncio.run(AutonomousScheduler(kernel=kernel).trigger_task_async("task_audit_chain_verify"))
    assert result["status"] == "SUCCESS" and "3 chained rows" in result["output"]


def test_verify_task_fails_honestly_on_a_broken_chain(kernel):
    with kernel._persistence._connect() as conn:
        conn.execute("UPDATE audit_trail SET action = 'forged' WHERE entity_id = '1'")  # test DB only
    result = asyncio.run(AutonomousScheduler(kernel=kernel).trigger_task_async("task_audit_chain_verify"))
    assert result["status"] == "FAILED" and "broken" in result["error"]


def test_anchor_task_is_off_until_the_host_is_configured(kernel, monkeypatch):
    _clear_anchor_env(monkeypatch)
    scheduler = AutonomousScheduler(kernel=kernel)
    assert not anchor_configured()
    assert scheduler.tasks["task_audit_chain_anchor"].is_enabled is False
    result = asyncio.run(scheduler.trigger_task_async("task_audit_chain_anchor"))
    assert "not configured" in result["output"]


def test_anchor_task_publishes_a_verifiable_head(kernel, monkeypatch, witness):
    monkeypatch.setenv(ANCHOR_URL_ENV, witness["url"])
    monkeypatch.setenv(ANCHOR_KEY_ID_ENV, "delentia-os-test")
    scheduler = AutonomousScheduler(kernel=kernel)
    assert scheduler.tasks["task_audit_chain_anchor"].is_enabled is True
    result = asyncio.run(scheduler.trigger_task_async("task_audit_chain_anchor"))
    assert result["status"] == "SUCCESS", result
    with kernel._persistence._connect() as conn:
        head = audit_chain.chain_head(conn)
    assert witness["received"][-1]["entries"] == head["seq"] and witness["received"][-1]["head"] == head["row_hash"]


def test_anchor_task_reports_a_refused_anchor(kernel, monkeypatch, witness):
    monkeypatch.setenv(ANCHOR_URL_ENV, witness["url"])
    monkeypatch.setenv(ANCHOR_KEY_ID_ENV, "delentia-os-test")
    witness["received"].append({"entries": 10_000})  # the witness already saw a longer chain
    result = asyncio.run(AutonomousScheduler(kernel=kernel).trigger_task_async("task_audit_chain_anchor"))
    assert result["status"] == "FAILED" and "409" in result["error"]
