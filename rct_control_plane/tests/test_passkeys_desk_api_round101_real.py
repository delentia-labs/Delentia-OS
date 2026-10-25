"""
Round 101: the Desk's routes for approval devices (passkeys). Real FastAPI app, real SQLite, real Ed25519 approver, a software authenticator that answers like Windows Hello would.

Pinned: the whole path over HTTP (add a device -> an approver signs once -> activate -> approve a waiting action with the device); the wrong action, the wrong decision and a revoked device
are refused; a person's token cannot reach any of these routes.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import approvals, passkeys
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence
from virtual_authenticator import VirtualAuthenticator


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.delenv(passkeys.RP_ID_ENV, raising=False)
    monkeypatch.delenv(passkeys.ORIGINS_ENV, raising=False)
    key = tmp_path / "keys" / "root.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "root", "public_key_hex": public}]), encoding="utf-8")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        yield client, persistence, str(key)


def add_device(client, persistence, key, device=None, name="laptop", role=None):
    device = device or VirtualAuthenticator()
    begun = client.post("/v1/desk/passkeys/register/begin", json={"name": name, "role": role}).json()
    finished = client.post("/v1/desk/passkeys/register/finish", json={"enrollment_id": begun["enrollment_id"], "credential": device.create(begun["options"])})
    assert finished.status_code == 200, finished.text
    approval_id = finished.json()["approval_id"]
    store = PendingActionStore(persistence)
    action = store.get(approval_id)
    signed = approvals.sign_decision(key, approval_id, action.action_sha256, "APPROVED")
    store.decide(approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
    activated = client.post("/v1/desk/passkeys/register/activate", json={"approval_id": approval_id})
    assert activated.status_code == 200, activated.text
    return device, activated.json()


def waiting_action(persistence, **kw):
    return PendingActionStore(persistence).create("owner", "a goal", "delentia_write_repo_file", {"relative_path": "docs/a.md"}, **kw)


def test_a_device_is_added_signed_for_once_and_then_approves_a_waiting_action(desk):
    client, persistence, key = desk
    listed = client.get("/v1/desk/passkeys").json()
    assert listed["devices"] == [] and listed["rp_id"] == "localhost"
    device, summary = add_device(client, persistence, key)
    assert summary["status"] == "ACTIVE" and client.get("/v1/desk/passkeys").json()["devices"][0]["name"] == "laptop"
    action = waiting_action(persistence)
    options = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"}).json()
    decided = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/decide", json={"decision": "APPROVED", "assertion": device.get(options["options"])})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"


def test_a_new_device_cannot_approve_before_an_approver_signed_for_it(desk):
    client, persistence, key = desk
    device = VirtualAuthenticator()
    begun = client.post("/v1/desk/passkeys/register/begin", json={"name": "phone"}).json()
    finished = client.post("/v1/desk/passkeys/register/finish", json={"enrollment_id": begun["enrollment_id"], "credential": device.create(begun["options"])}).json()
    activated = client.post("/v1/desk/passkeys/register/activate", json={"approval_id": finished["approval_id"]})
    assert activated.status_code == 400
    action = waiting_action(persistence)
    options = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"})
    assert options.status_code == 400                                   # no active device at all


def test_the_confirmation_belongs_to_one_action_and_one_decision(desk):
    client, persistence, key = desk
    device, _ = add_device(client, persistence, key)
    first, second = waiting_action(persistence), PendingActionStore(persistence).create("owner", "another goal", "delentia_write_repo_file", {"relative_path": "docs/b.md"})
    options = client.post(f"/v1/desk/approvals/{first.approval_id}/passkey/options", json={"decision": "APPROVED"}).json()
    assertion = device.get(options["options"])
    assert client.post(f"/v1/desk/approvals/{second.approval_id}/passkey/decide", json={"decision": "APPROVED", "assertion": assertion}).status_code == 400
    assert client.post(f"/v1/desk/approvals/{first.approval_id}/passkey/decide", json={"decision": "REJECTED", "assertion": assertion}).status_code == 400
    assert PendingActionStore(persistence).get(first.approval_id).status == "PENDING"


def test_a_revoked_device_can_no_longer_approve(desk):
    client, persistence, key = desk
    device, summary = add_device(client, persistence, key)
    assert client.post(f"/v1/desk/passkeys/{summary['id']}/revoke").json()["status"] == "REVOKED"
    action = waiting_action(persistence)
    assert client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"}).status_code == 400
    assert client.post("/v1/desk/passkeys/nope/revoke").status_code == 404


def test_every_step_leaves_an_audit_row(desk):
    client, persistence, key = desk
    add_device(client, persistence, key)
    with persistence._connect() as conn:
        actions = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'passkey'").fetchall()]
    assert "enrollment_requested" in actions and "activated" in actions


def test_a_person_token_cannot_reach_the_device_routes():
    from rct_control_plane import api_auth
    for method, path in (("GET", "/v1/desk/passkeys"), ("POST", "/v1/desk/passkeys/register/begin"), ("POST", "/v1/desk/passkeys/abc/revoke"),
                         ("POST", "/v1/desk/approvals/x/passkey/options"), ("POST", "/v1/desk/approvals/x/passkey/decide")):
        assert not api_auth.person_route_allowed(method, path), path


def test_the_signature_ledger_names_the_device_and_checks_its_signature(desk):
    client, persistence, key = desk
    from rct_control_plane import governance_view
    device, summary = add_device(client, persistence, key, name="my laptop", role="owner")
    action = waiting_action(persistence)
    options = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"}).json()
    client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/decide", json={"decision": "APPROVED", "assertion": device.get(options["options"])})
    ledger = governance_view.signature_ledger(persistence)
    row = next(a for a in ledger["approvals"] if a["approval_id"] == action.approval_id)
    signer = row["signers"][0]
    assert signer["scheme"] == "passkey" and signer["name"] == "my laptop" and signer["verifies_now"] and signer["key_still_trusted"]
    client.post(f"/v1/desk/passkeys/{summary['id']}/revoke")
    again = next(a for a in governance_view.signature_ledger(persistence)["approvals"] if a["approval_id"] == action.approval_id)["signers"][0]
    assert again["verifies_now"] and not again["key_still_trusted"]          # the old record is genuine; the device is no longer trusted
    assert governance_view.fingerprint(summary["signer"]) != ""


def test_the_cli_says_what_enrolling_a_device_means(desk):
    client, persistence, key = desk
    from rct_control_plane import cli
    begun = client.post("/v1/desk/passkeys/register/begin", json={"name": "phone"}).json()
    finished = client.post("/v1/desk/passkeys/register/finish", json={"enrollment_id": begun["enrollment_id"], "credential": VirtualAuthenticator().create(begun["options"])}).json()
    text = cli._describe_action(PendingActionStore(persistence).get(finished["approval_id"]))
    assert "phone" in text and "ONLY if you just added" in text


def test_a_short_prefix_never_revokes_a_device_by_accident(desk):
    client, persistence, key = desk
    device, summary = add_device(client, persistence, key)
    assert client.post(f"/v1/desk/passkeys/{summary['id'][:6]}/revoke").status_code == 404
    assert client.get("/v1/desk/passkeys").json()["devices"][0]["status"] == "ACTIVE"
    assert client.post(f"/v1/desk/passkeys/{summary['id']}/revoke").json()["status"] == "REVOKED"
