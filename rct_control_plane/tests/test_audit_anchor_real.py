"""
Round 50, audit tier A3: `delentia audit-chain anchor` publishes the signed
chain head to an outside witness (the fdia Worker's /v1/audit/anchor, see
delentia-mcp/ecosystem/packages/shared/src/audit-anchor.ts); `check-anchors`
proves the local chain still matches every head anchored there.

Real SQLite chain, real Ed25519; the witness HTTP calls are faked with the
exact response shape the Worker returns.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest
from click.testing import CliRunner
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rct_control_plane import audit_chain
from rct_control_plane.persistence import ControlPlanePersistence


def _db(tmp_path, rows=3):
    p = ControlPlanePersistence(db_path=str(tmp_path / "audit.db"))
    for i in range(rows):
        p.append_audit(entity_type="test", entity_id=f"e{i}", action="write", actor="tester", changes={"i": i})
    return p


def _verify(anchor, public_key):
    msg = audit_chain.anchor_message(anchor["key_id"], anchor["entries"], anchor["head"], anchor["signed_at"])
    public_key.verify(bytes.fromhex(anchor["signature"]), msg.encode("utf-8"))  # raises if invalid


def test_the_message_format_matches_the_witness_protocol():
    assert audit_chain.anchor_message("k1", 7, "ab" * 32, "2026-09-29T00:00:00.000Z") == \
        f"delentia-audit-anchor:v1|k1|7|{'ab' * 32}|2026-09-29T00:00:00.000Z"


def test_the_anchor_is_the_signed_chain_head(tmp_path):
    p = _db(tmp_path, rows=4)
    key = Ed25519PrivateKey.generate()
    with p._connect() as conn:
        anchor = audit_chain.sign_anchor(conn, "host-1", private_key=key)
        head = audit_chain.chain_head(conn)
    assert (anchor["entries"], anchor["head"]) == (head["seq"], head["row_hash"])
    assert anchor["signed_at"].endswith("Z")
    assert len(anchor["signature"]) == 128
    _verify(anchor, key.public_key())


def test_it_uses_the_configured_audit_key_and_refuses_without_one(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.delenv(audit_chain.SIGNING_KEY_ENV, raising=False)
    with p._connect() as conn, pytest.raises(ValueError, match="no signing key"):
        audit_chain.sign_anchor(conn, "host-1")

    key_path = tmp_path / "keys" / "audit.pem"
    public_hex = audit_chain.generate_signing_key(str(key_path))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key_path))
    with p._connect() as conn:
        anchor = audit_chain.sign_anchor(conn, "host-1")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    _verify(anchor, Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)))


def test_an_empty_chain_has_nothing_to_anchor(tmp_path):
    p = ControlPlanePersistence(db_path=str(tmp_path / "empty.db"))
    with p._connect() as conn, pytest.raises(ValueError, match="empty"):
        audit_chain.sign_anchor(conn, "host-1", private_key=Ed25519PrivateKey.generate())


def _witness(*anchors, conflicts=()):
    return {"key_id": "host-1", "count": len(anchors), "conflicts": list(conflicts),
            "anchors": [dict(a, received_at="2026-09-29T00:00:00Z") for a in anchors]}


def test_a_matching_chain_passes_and_a_rewritten_or_truncated_one_fails(tmp_path):
    p = _db(tmp_path, rows=5)
    key = Ed25519PrivateKey.generate()
    with p._connect() as conn:
        a3 = dict(audit_chain.sign_anchor(conn, "host-1", private_key=key), entries=3,
                  head=conn.execute("SELECT row_hash FROM audit_chain WHERE seq = 3").fetchone()[0])
        a5 = audit_chain.sign_anchor(conn, "host-1", private_key=key)
        assert audit_chain.check_anchors(conn, _witness(a3, a5)) == {"ok": True, "checked": 2, "problems": []}

        # Someone with write access rewrites row 3's hash (and would rebuild the rest).
        conn.execute("UPDATE audit_chain SET row_hash = ? WHERE seq = 3", ("f" * 64,))
        report = audit_chain.check_anchors(conn, _witness(a3, a5))
        assert report["ok"] is False and "rewritten" in report["problems"][0]

        # Or drops the newest rows.
        conn.execute("DELETE FROM audit_chain WHERE seq >= 4")
        report = audit_chain.check_anchors(conn, _witness(a5))
        assert "truncated" in report["problems"][0]


def test_conflicts_recorded_by_the_witness_fail_the_check(tmp_path):
    p = _db(tmp_path)
    with p._connect() as conn:
        a = audit_chain.sign_anchor(conn, "host-1", private_key=Ed25519PrivateKey.generate())
        report = audit_chain.check_anchors(conn, _witness(a, conflicts=[{"kind": "rollback"}]))
    assert report["ok"] is False and "conflicting" in report["problems"][0]


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_cli_anchor_and_check_against_a_witness(tmp_path, monkeypatch):
    from rct_control_plane.cli import cli
    p = _db(tmp_path)
    key_path = tmp_path / "keys" / "audit.pem"
    audit_chain.generate_signing_key(str(key_path))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key_path))
    stored = []

    def _post(url, json=None, timeout=None):
        assert url == "https://witness.example/v1/audit/anchor"
        stored.append(json)
        return _Resp(201, {"accepted": True, "index": len(stored), "anchor": json})

    def _get(url, params=None, timeout=None):
        assert url == "https://witness.example/v1/audit/anchor/host-1"
        return _Resp(200, _witness(*stored))

    import httpx
    monkeypatch.setattr(httpx, "post", _post)
    monkeypatch.setattr(httpx, "get", _get)
    runner = CliRunner()
    db = str(tmp_path / "audit.db")

    r = runner.invoke(cli, ["audit-chain", "anchor", "--url", "https://witness.example/", "--key-id", "host-1", "--db", db])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["status"] == 201

    r = runner.invoke(cli, ["audit-chain", "check-anchors", "--url", "https://witness.example", "--key-id", "host-1", "--db", db])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["ok"] is True

    with p._connect() as conn:
        conn.execute("UPDATE audit_chain SET row_hash = ? WHERE seq = 3", ("0" * 64,))
    r = runner.invoke(cli, ["audit-chain", "check-anchors", "--url", "https://witness.example", "--key-id", "host-1", "--db", db])
    assert r.exit_code == 1
    assert json.loads(r.output)["ok"] is False
