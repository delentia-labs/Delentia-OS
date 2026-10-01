"""
Round 50, audit tier A2 for the agent runtime: an out-of-process notary holds
the signing key; the governed loop can only append records to it over
loopback, and a tool call the notary cannot record does not run.

Real HTTP server (ThreadingHTTPServer on an ephemeral port), real Ed25519,
real SQLite; the model is scripted and MCP is faked, as in the other
governed-loop tests.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import socket
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, notary
from rct_control_plane.approvals import ApprovalError
from rct_control_plane.notary import NotaryClient, NotaryStore, NotaryUnavailable, sha256_hex, verify_log
from rct_control_plane.sandbox import classify_command_risk
from test_governed_autonomous_loop_real import _FakeMCP, _loop

TOKEN = "test-notary-token"


@pytest.fixture
def notary_server(tmp_path):
    key = Ed25519PrivateKey.generate()
    store = NotaryStore(str(tmp_path / "notary" / "notary.db"), key, "notary-test")
    server = notary.make_server(store, port=0, token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield {"url": url, "store": store, "pubkey": notary.public_hex(key), "key": key}
    server.shutdown()
    server.server_close()


def _client(server):
    return NotaryClient(server["url"], TOKEN)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _script(monkeypatch, decisions):
    calls = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = calls["n"]
        calls["n"] += 1
        if i < len(decisions):
            return dict(decisions[i])
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)


RECALL = {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "release notes"},
          "reasoning": "look it up"}
DENIED = {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
          "tool_args": {"command": "format c:"}, "reasoning": "r"}
WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file",
         "tool_args": {"relative_path": "docs/notes.md", "content_text": "hello"}, "reasoning": "r"}


# ------------------------------------------------------------- the log

class TestNotaryLog:
    def test_entries_are_chained_signed_and_verifiable(self, tmp_path):
        key = Ed25519PrivateKey.generate()
        db = str(tmp_path / "n.db")
        store = NotaryStore(db, key, "k1")
        r1 = store.append({"kind": "a"})
        r2 = store.append({"kind": "b"})
        assert (r1["seq"], r2["seq"]) == (1, 2)
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT prev_hash FROM notary_log WHERE seq = 2").fetchone()[0] == r1["hash"]
        report = verify_log(db, notary.public_hex(key))
        assert report.ok and report.entries == 2 and report.head_hash == r2["hash"]

    def test_edited_entry_is_detected(self, tmp_path):
        key = Ed25519PrivateKey.generate()
        db = str(tmp_path / "n.db")
        store = NotaryStore(db, key, "k1")
        for kind in ("a", "b", "c"):
            store.append({"kind": kind})
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE notary_log SET record = ? WHERE seq = 2", (json.dumps({"kind": "forged"}),))
        report = verify_log(db, notary.public_hex(key))
        assert not report.ok and report.first_bad_seq == 2 and "modified" in report.reason

    def test_removed_entry_is_detected(self, tmp_path):
        key = Ed25519PrivateKey.generate()
        db = str(tmp_path / "n.db")
        store = NotaryStore(db, key, "k1")
        for kind in ("a", "b", "c"):
            store.append({"kind": kind})
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM notary_log WHERE seq = 2")  # test DB in tmp_path only
        report = verify_log(db, notary.public_hex(key))
        assert not report.ok and report.first_bad_seq == 3 and "gap" in report.reason

    def test_rewritten_history_without_the_key_fails_signature_check(self, tmp_path):
        """Whoever rewrites the log and recomputes the hashes still cannot
        sign with the notary's key."""
        key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        db = str(tmp_path / "n.db")
        NotaryStore(db, key, "k1").append({"kind": "a"})
        forger = NotaryStore(db, other, "k1")
        forger.append({"kind": "forged"})
        report = verify_log(db, notary.public_hex(key))
        assert not report.ok and report.first_bad_seq == 2 and "signature" in report.reason

    def test_large_records_are_refused(self, tmp_path):
        store = NotaryStore(str(tmp_path / "n.db"), Ed25519PrivateKey.generate(), "k1")
        with pytest.raises(ValueError, match="hashes, not content"):
            store.append({"kind": "a", "blob": "x" * (notary.MAX_RECORD_BYTES + 1)})

    def test_key_inside_the_repository_is_refused(self):
        inside = Path(notary.__file__).resolve().parent / "no-such-notary.pem"
        with pytest.raises(ValueError, match="inside the repository"):
            notary.load_key(str(inside))

    def test_anchor_matches_the_a3_protocol_and_check_detects_rewrites(self, tmp_path):
        from rct_control_plane.audit_chain import anchor_message
        key = Ed25519PrivateKey.generate()
        db = str(tmp_path / "n.db")
        store = NotaryStore(db, key, "k1")
        store.append({"kind": "a"})
        head = store.append({"kind": "b"})
        body = notary.sign_anchor(db, "delentia-notary-1", key, signed_at="2026-09-29T00:00:00.000Z")
        assert body["entries"] == 2 and body["head"] == head["hash"]
        key.public_key().verify(bytes.fromhex(body["signature"]),
                                anchor_message("delentia-notary-1", 2, head["hash"], body["signed_at"]).encode())
        witness = {"anchors": [{"entries": 2, "head": head["hash"], "received_at": "t"}]}
        assert notary.check_anchors(db, witness)["ok"]
        witness_bad = {"anchors": [{"entries": 2, "head": "0" * 64, "received_at": "t"}]}
        assert not notary.check_anchors(db, witness_bad)["ok"]
        witness_trunc = {"anchors": [{"entries": 9, "head": head["hash"], "received_at": "t"}]}
        assert "truncated" in notary.check_anchors(db, witness_trunc)["problems"][0]


# ------------------------------------------------------------- HTTP

class TestNotaryHttp:
    def test_append_needs_the_token(self, notary_server):
        r = httpx.post(f"{notary_server['url']}/append", json={"kind": "x"})
        assert r.status_code == 401
        r = httpx.post(f"{notary_server['url']}/append", json={"kind": "x"},
                       headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 201 and r.json()["seq"] == 1

    def test_bad_records_are_rejected(self, notary_server):
        h = {"Authorization": f"Bearer {TOKEN}"}
        assert httpx.post(f"{notary_server['url']}/append", json={"no_kind": 1}, headers=h).status_code == 400
        assert httpx.post(f"{notary_server['url']}/append", content=b"{not json", headers=h).status_code == 400
        big = {"kind": "x", "blob": "y" * (notary.MAX_RECORD_BYTES + 10)}
        assert httpx.post(f"{notary_server['url']}/append", json=big, headers=h).status_code == 413

    def test_no_endpoint_rewrites_or_reads_the_key(self, notary_server):
        h = {"Authorization": f"Bearer {TOKEN}"}
        for method, path in (("PUT", "/append"), ("DELETE", "/append"), ("GET", "/key"), ("POST", "/rewrite")):
            assert httpx.request(method, f"{notary_server['url']}{path}", headers=h).status_code in (404, 501)
        health = httpx.get(f"{notary_server['url']}/health").json()
        assert health == {"status": "ok", "key_id": "notary-test"}

    def test_only_loopback_binds_are_allowed(self, tmp_path):
        store = NotaryStore(str(tmp_path / "n.db"), Ed25519PrivateKey.generate(), "k1")
        with pytest.raises(ValueError, match="loopback"):
            notary.make_server(store, host="0.0.0.0", port=0)

    def test_client_raises_when_unreachable(self):
        client = NotaryClient(f"http://127.0.0.1:{_free_port()}", timeout=1.0)
        with pytest.raises(NotaryUnavailable, match="unreachable"):
            asyncio.run(client.append({"kind": "x"}))


# ------------------------------------------------------------- the loop

def _receipts_in_local_audit(loop):
    with loop._persistence._connect() as conn:
        rows = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'notary_receipt' "
                            "ORDER BY id").fetchall()
    return [(a, json.loads(c) if isinstance(c, str) else c) for a, c in rows]


class TestGovernedLoopWithNotary:
    def test_every_tool_call_is_notarised_before_and_after_it_runs(self, tmp_path, monkeypatch, notary_server):
        _script(monkeypatch, [RECALL])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "notarised", mcp=mcp, notary=_client(notary_server))
        result = asyncio.run(loop.run("find the release notes"))

        assert result["stopped_reason"] == "llm_finished"
        # Round 52: the notary records the arguments that actually ran, including the pinned namespace
        ran_args = mcp.dispatched[0][1]
        assert mcp.dispatched == [("delentia_recall", ran_args)] and ran_args["query"] == RECALL["tool_args"]["query"] and "namespace" in ran_args
        records = notary.records_for_episode(notary_server["store"].db_path, "notarised")
        assert [r["kind"] for r in records] == ["episode_start", "tool_call", "tool_result", "episode_end"]
        call, res = records[1], records[2]
        assert call["gate_decision"] == "allowed" and call["arguments_sha256"] == sha256_hex(ran_args)
        assert res["result_sha256"] == sha256_hex({"ok": True})
        assert records[3]["stopped_reason"] == "llm_finished"
        assert "release notes" not in json.dumps(records)  # hashes only, never content
        assert len({r["episode_id"] for r in records}) == 1

        assert result["notary"]["receipts"] == 4 and result["notary"]["gaps"] == []
        assert verify_log(notary_server["store"].db_path, notary_server["pubkey"]).ok

        local = _receipts_in_local_audit(loop)
        assert [a for a, _ in local] == ["episode_start", "tool_call", "tool_result", "episode_end"]
        with sqlite3.connect(notary_server["store"].db_path) as conn:
            notary_hashes = dict(conn.execute("SELECT seq, hash FROM notary_log").fetchall())
        for _, changes in local:
            assert notary_hashes[changes["receipt"]["seq"]] == changes["receipt"]["hash"]

    def test_notary_down_means_the_tool_does_not_run(self, tmp_path, monkeypatch):
        _script(monkeypatch, [RECALL])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "down", mcp=mcp,
                     notary=NotaryClient(f"http://127.0.0.1:{_free_port()}", timeout=1.0))
        result = asyncio.run(loop.run("find the release notes"))

        assert mcp.dispatched == []
        assert result["stopped_reason"] == "notary_unavailable"
        assert result["steps"][-1]["tool_result"]["notary_unavailable"] is True
        kinds = [g["kind"] for g in result["notary"]["gaps"]]
        assert kinds == ["episode_start", "tool_call", "episode_end"]
        with loop._persistence._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'notary_gap'").fetchone()[0] == 3

    def test_blocked_calls_are_notarised_with_the_fdia_decision(self, tmp_path, monkeypatch, notary_server):
        _script(monkeypatch, [DENIED])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "blocked", mcp=mcp, notary=_client(notary_server))
        result = asyncio.run(loop.run("clean the disk"))

        assert result["stopped_reason"] == "fdia_blocked" and mcp.dispatched == []
        call = [r for r in notary.records_for_episode(notary_server["store"].db_path, "blocked")
                if r["kind"] == "tool_call"][0]
        assert call["gate_decision"] == "fdia_blocked"
        assert call["fdia"]["A"] == 0.0 and call["fdia"]["F"] == 0.0

    def test_without_a_notary_nothing_changes(self, tmp_path, monkeypatch):
        monkeypatch.delenv(notary.NOTARY_URL_ENV, raising=False)
        _script(monkeypatch, [RECALL])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "plain", mcp=mcp)
        result = asyncio.run(loop.run("find the release notes"))
        assert result["stopped_reason"] == "llm_finished" and len(mcp.dispatched) == 1
        assert result["notary"] == {"enabled": False}

    def test_notary_url_env_is_picked_up_by_every_governed_loop(self, tmp_path, monkeypatch, notary_server):
        monkeypatch.setenv(notary.NOTARY_URL_ENV, notary_server["url"])
        monkeypatch.setenv(notary.NOTARY_TOKEN_ENV, TOKEN)
        _script(monkeypatch, [RECALL])
        loop = _loop(tmp_path, "env", mcp=_FakeMCP())
        result = asyncio.run(loop.run("find the release notes"))
        assert result["notary"]["enabled"] and result["notary"]["receipts"] == 4


class TestResumeWithNotary:
    @pytest.fixture(autouse=True)
    def _approver(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
        key_path = tmp_path / "keys" / "architect.pem"
        public_hex = approvals.generate_approver_key(str(key_path))
        monkeypatch.setenv(approvals.APPROVERS_ENV, public_hex)
        self.key_path = str(key_path)

    def _approve(self, loop, approval_id):
        store = loop._pending_actions()
        action = store.get(approval_id)
        signed = approvals.sign_decision(self.key_path, action.approval_id, action.action_sha256, "APPROVED")
        store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])

    def test_approved_action_is_notarised_and_runs_once(self, tmp_path, monkeypatch, notary_server):
        _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "resume", mcp=mcp, notary=_client(notary_server))
        paused = asyncio.run(loop.run("write the release notes"))
        self._approve(loop, paused["approval_id"])
        asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))

        assert mcp.dispatched == [("delentia_write_repo_file", WRITE["tool_args"])]
        kinds = [r["kind"] for r in notary.records_for_episode(notary_server["store"].db_path, "resume")]
        assert "approved_action_claim" in kinds and "approved_action_result" in kinds
        assert kinds.index("approved_action_claim") < kinds.index("approved_action_result")

    def test_notary_down_at_resume_keeps_the_approval_for_later(self, tmp_path, monkeypatch, notary_server):
        _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "later", mcp=mcp, notary=_client(notary_server))
        paused = asyncio.run(loop.run("write the release notes"))
        self._approve(loop, paused["approval_id"])

        loop._notary = NotaryClient(f"http://127.0.0.1:{_free_port()}", timeout=1.0)
        with pytest.raises(ApprovalError, match="notary unavailable"):
            asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
        assert mcp.dispatched == []
        assert loop._pending_actions().get(paused["approval_id"]).status == "APPROVED"

        loop._notary = _client(notary_server)
        asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
        assert len(mcp.dispatched) == 1


# ------------------------------------------------------------- sandbox

@pytest.mark.parametrize("command", [
    "type C:\\Users\\me\\.delentia-notary\\notary.pem",
    "sqlite3 notary.db \"UPDATE notary_log SET record='x'\"",
    "echo %DELENTIA_NOTARY_TOKEN%",
])
def test_sandbox_denies_commands_naming_the_notary(command):
    assert classify_command_risk(command) == "denied"


# ------------------------------------------------------------- A3 schedule

def test_anchor_once_publishes_only_when_the_head_moves(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from rct_control_plane.audit_chain import anchor_message
    key = Ed25519PrivateKey.generate()
    db = str(tmp_path / "n.db")
    store = NotaryStore(db, key, "k1")
    received = []

    class Witness(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            msg = anchor_message(body["key_id"], body["entries"], body["head"], body["signed_at"])
            key.public_key().verify(bytes.fromhex(body["signature"]), msg.encode())
            received.append(body)
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Witness)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert notary.anchor_once(db, "delentia-notary-1", key, url)["anchored"] is False  # empty log
        store.append({"kind": "a"})
        first = notary.anchor_once(db, "delentia-notary-1", key, url)
        assert first["anchored"] and first["entries"] == 1
        again = notary.anchor_once(db, "delentia-notary-1", key, url, last_entries=1)
        assert again["anchored"] is False and "unchanged" in again["reason"]
        store.append({"kind": "b"})
        assert notary.anchor_once(db, "delentia-notary-1", key, url, last_entries=1)["entries"] == 2
        assert [r["entries"] for r in received] == [1, 2]
    finally:
        server.shutdown()
        server.server_close()


def test_anchor_once_survives_a_witness_outage(tmp_path):
    key = Ed25519PrivateKey.generate()
    db = str(tmp_path / "n.db")
    NotaryStore(db, key, "k1").append({"kind": "a"})
    result = notary.anchor_once(db, "k", key, f"http://127.0.0.1:{_free_port()}")
    assert result["anchored"] is False and "unreachable" in result["reason"]

