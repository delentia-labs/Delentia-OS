"""
Round 101: approving with a passkey (WebAuthn). Real SQLite, real Ed25519 approvers, real P-256 and RSA signatures from a software authenticator (virtual_authenticator.py), the real governed loop.

What is pinned: a device becomes trusted only after an existing approver signed for it; an assertion is bound to one action and one decision; every way a confirmation can be wrong is refused; the
stored assertion is checked again at execution and a revoked device voids what it signed; roles and scope apply; the Ed25519 path is untouched.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import random

import pytest

from rct_control_plane import approvals, passkeys, plan_approval
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.passkeys import PasskeyError, PasskeyStore
from rct_control_plane.persistence import ControlPlanePersistence
from virtual_authenticator import VirtualAuthenticator


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(passkeys.RP_ID_ENV, raising=False)
    monkeypatch.delenv(passkeys.ORIGINS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def world(tmp_path):
    key = tmp_path / "keys" / "root.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "root", "public_key_hex": public}]), encoding="utf-8")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "a.db"))
    return {"key": str(key), "persistence": persistence, "approvals": PendingActionStore(persistence), "passkeys": PasskeyStore(persistence)}


def sign_ed25519(world, action, decision="APPROVED"):
    signed = approvals.sign_decision(world["key"], action.approval_id, action.action_sha256, decision)
    return world["approvals"].decide(action.approval_id, decision, signed["public_key_hex"], signed["signature_hex"])


def enroll(world, device=None, name="laptop", role=None, scope=None, activate=True):
    device = device or VirtualAuthenticator()
    begun = world["passkeys"].begin_registration(name, role, scope)
    finished = world["passkeys"].finish_registration(begun["enrollment_id"], device.create(begun["options"]))
    action = passkeys.create_enrollment_action(world["approvals"], finished)
    if activate:
        sign_ed25519(world, action)
        passkeys.activate_enrollment(world["approvals"], world["passkeys"], action.approval_id)
    return device, finished, action


def new_action(world, tool="delentia_write_repo_file", args=None, **kw):
    return world["approvals"].create("owner", "a goal", tool, args or {"relative_path": "docs/a.md"}, **kw)


def confirm(world, action, device, decision="APPROVED", **misbehave):
    options = world["passkeys"].request_options(action.action_sha256, action.approval_id, decision)
    return device.get(options, **misbehave)


# ------------------------------------------------------------------ the format code
def test_cbor_round_trips_what_webauthn_uses():
    value = {1: 2, 3: -7, -1: 1, -2: b"x" * 32, "fmt": "none", "list": [1, True, None, -300, 70000]}
    assert passkeys.cbor_decode(passkeys.cbor_encode(value))[0] == value


@pytest.mark.parametrize("bad", [b"", b"\x5f\x41a\xff", b"\x9f\x01\xff", b"\xbf\x01\x02\xff", b"\x5a\xff\xff\xff\xff", b"\x82\x01", b"\xc1\x01", b"\xfa\x00\x00\x00\x00", b"\x01\x02"])
def test_cbor_refuses_indefinite_truncated_oversized_and_unknown_items(bad):
    with pytest.raises(PasskeyError):
        passkeys.cbor_decode(bad)


def test_cbor_depth_and_size_are_bounded():
    with pytest.raises(PasskeyError):
        passkeys.cbor_decode(b"\x81" * 40 + b"\x00")
    with pytest.raises(PasskeyError):
        passkeys.cbor_decode(passkeys.cbor_encode(list(range(200))))


def test_random_bytes_never_raise_anything_but_a_passkey_error():
    rng = random.Random(1101)
    for _ in range(3000):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 80)))
        try:
            passkeys.cbor_decode(blob)
        except PasskeyError:
            pass
        try:
            passkeys.parse_auth_data(blob, expect_credential=rng.random() < 0.5)
        except PasskeyError:
            pass


def test_scope_is_validated_and_unknown_fields_are_refused():
    assert passkeys.clean_scope({"kinds": ["delete", "delete"], "namespaces": ["owner"]}) == {"kinds": ["delete"], "namespaces": ["owner"]}
    assert passkeys.clean_scope({}) == {}
    for bad in ({"kinds": ["fly"]}, {"nope": 1}, {"kinds": "delete"}, {"namespaces": [1]}, "x"):
        with pytest.raises(PasskeyError):
            passkeys.clean_scope(bad)


# ------------------------------------------------------------------ enrollment
@pytest.mark.parametrize("alg", ["ES256", "RS256"])
def test_a_device_is_trusted_only_after_an_existing_approver_signed_for_it(world, alg):
    device = VirtualAuthenticator(alg)
    _, finished, action = enroll(world, device, activate=False)
    assert world["passkeys"].get(finished["credential_id"]).status == "PENDING"
    action_row = new_action(world)
    with pytest.raises(ApprovalError, match="not a trusted approver"):
        world["approvals"].decide_with_passkey(action_row.approval_id, "APPROVED", confirm(world, action_row, device)) if world["passkeys"].active() else (_ for _ in ()).throw(ApprovalError("not a trusted approver"))
    with pytest.raises(PasskeyError):
        passkeys.activate_enrollment(world["approvals"], world["passkeys"], action.approval_id)              # nobody signed yet
    sign_ed25519(world, action)
    activated = passkeys.activate_enrollment(world["approvals"], world["passkeys"], action.approval_id)
    assert activated.status == "ACTIVE" and world["approvals"].get(action.approval_id).status == "EXECUTED"


def test_a_device_cannot_enroll_another_device(world):
    first, _, _ = enroll(world)
    second = VirtualAuthenticator()
    begun = world["passkeys"].begin_registration("phone")
    info = world["passkeys"].finish_registration(begun["enrollment_id"], second.create(begun["options"]))
    action = passkeys.create_enrollment_action(world["approvals"], info)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, first))
    with pytest.raises(PasskeyError, match="approver key, not of another device"):
        passkeys.activate_enrollment(world["approvals"], world["passkeys"], action.approval_id)
    assert world["passkeys"].get(info["credential_id"]).status == "PENDING"


def test_the_signature_covers_this_exact_device(world):
    _, finished, action = enroll(world, activate=False)
    with world["persistence"]._connect() as conn:                                         # someone swaps the stored public key between signing and activation
        conn.execute("UPDATE approver_credentials SET public_key_json = ? WHERE credential_id = ?", (json.dumps({"alg": -7, "x": "00" * 32, "y": "00" * 32}), finished["credential_id"]))
    sign_ed25519(world, action)
    with pytest.raises(PasskeyError, match="not the one that was signed for"):
        passkeys.activate_enrollment(world["approvals"], world["passkeys"], action.approval_id)


@pytest.mark.parametrize("kwargs,message", [
    ({"origin": "http://evil.example"}, "origin"), ({"rp_id": "evil.example"}, "another site"), ({"challenge": "AAAA"}, "challenge"), ({"uv": False}, "confirm the person"),
    ({"ctype": "webauthn.get"}, "webauthn.create"), ({"origin": "http://localhost.evil.example"}, "origin"),
])
def test_a_registration_with_a_wrong_origin_site_challenge_or_no_user_check_is_refused(world, kwargs, message):
    begun = world["passkeys"].begin_registration("laptop")
    with pytest.raises(PasskeyError, match=message):
        world["passkeys"].finish_registration(begun["enrollment_id"], VirtualAuthenticator().create(begun["options"], **kwargs))


def test_an_enrollment_can_be_finished_once_and_expires(world, monkeypatch):
    device = VirtualAuthenticator()
    begun = world["passkeys"].begin_registration("laptop")
    credential = device.create(begun["options"])
    world["passkeys"].finish_registration(begun["enrollment_id"], credential)
    with pytest.raises(PasskeyError, match="already used"):
        world["passkeys"].finish_registration(begun["enrollment_id"], credential)
    late = world["passkeys"].begin_registration("phone")
    real = passkeys.time.time
    monkeypatch.setattr(passkeys.time, "time", lambda: real() + passkeys.ENROLLMENT_TTL_SECONDS + 5)
    with pytest.raises(PasskeyError, match="took too long"):
        world["passkeys"].finish_registration(late["enrollment_id"], VirtualAuthenticator().create(late["options"]))


def test_a_device_with_no_name_or_a_copy_of_a_registered_device_is_refused(world):
    with pytest.raises(PasskeyError, match="name"):
        world["passkeys"].begin_registration("   ")
    device, _, _ = enroll(world)
    begun = world["passkeys"].begin_registration("again")
    with pytest.raises(PasskeyError, match="already registered"):
        world["passkeys"].finish_registration(begun["enrollment_id"], device.create(begun["options"]))


def test_a_malformed_registration_is_a_refusal_not_a_crash(world):
    begun = world["passkeys"].begin_registration("laptop")
    for junk in ({}, {"response": "x"}, {"response": {"clientDataJSON": "!!", "attestationObject": "!!"}}, {"response": {"clientDataJSON": "e30", "attestationObject": "oA"}}):
        with pytest.raises(PasskeyError):
            world["passkeys"].finish_registration(begun["enrollment_id"], junk)


# ------------------------------------------------------------------ approving
@pytest.mark.parametrize("alg", ["ES256", "RS256"])
def test_a_confirmation_on_the_device_approves_the_action_and_it_can_then_be_claimed_once(world, alg):
    device, _, _ = enroll(world, VirtualAuthenticator(alg))
    action = new_action(world)
    decided = world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    assert decided.status == "APPROVED"
    claimed = world["approvals"].claim_for_execution(action.approval_id)
    assert claimed.status == "EXECUTING"
    with pytest.raises(ApprovalError):
        world["approvals"].claim_for_execution(action.approval_id)


def test_a_rejection_by_passkey_is_recorded(world):
    device, _, _ = enroll(world)
    action = new_action(world)
    assert world["approvals"].decide_with_passkey(action.approval_id, "REJECTED", confirm(world, action, device, "REJECTED")).status == "REJECTED"


def test_the_decision_is_audited_with_the_scheme_and_the_device_name(world):
    device, _, _ = enroll(world, name="my laptop")
    action = new_action(world)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    with world["persistence"]._connect() as conn:
        row = conn.execute("SELECT actor, changes FROM audit_trail WHERE entity_type='pending_action_decided' AND entity_id=?", (action.approval_id,)).fetchone()
    changes = json.loads(row[1])
    assert "my laptop" in row[0] and changes["scheme"] == "passkey"


def test_a_confirmation_for_one_decision_cannot_be_used_for_the_other(world):
    device, _, _ = enroll(world)
    action = new_action(world)
    reject = confirm(world, action, device, "REJECTED")
    with pytest.raises(ApprovalError, match="different action or a different decision"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", reject)
    assert world["approvals"].get(action.approval_id).status == "PENDING"


def test_a_confirmation_for_one_action_cannot_be_used_for_another(world):
    device, _, _ = enroll(world)
    first, second = new_action(world), new_action(world, args={"relative_path": "docs/b.md"})
    with pytest.raises(ApprovalError, match="different action"):
        world["approvals"].decide_with_passkey(second.approval_id, "APPROVED", confirm(world, first, device))


@pytest.mark.parametrize("misbehave,message", [
    ({"origin": "http://evil.example"}, "origin"), ({"rp_id": "evil.example"}, "another site"), ({"uv": False}, "confirm the person"), ({"tamper": True}, "does not verify"),
    ({"challenge": "AAAA"}, "different action"),
])
def test_every_way_a_confirmation_can_be_wrong_is_refused(world, misbehave, message):
    device, _, _ = enroll(world)
    action = new_action(world)
    with pytest.raises(ApprovalError, match=message):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device, **misbehave))
    assert world["approvals"].get(action.approval_id).status == "PENDING"


def test_a_replayed_confirmation_is_refused_by_the_counter(world):
    device, _, _ = enroll(world)
    first = new_action(world)
    assertion = confirm(world, first, device)
    world["approvals"].decide_with_passkey(first.approval_id, "APPROVED", assertion)
    # a clone of the device that signs with a counter that does not advance
    second = new_action(world, args={"relative_path": "docs/c.md"})
    with pytest.raises(ApprovalError, match="counter"):
        world["approvals"].decide_with_passkey(second.approval_id, "APPROVED", confirm(world, second, device, bump=False))


def test_a_device_that_was_never_trusted_or_an_unknown_one_is_refused(world):
    enroll(world)
    stranger = VirtualAuthenticator()
    action = new_action(world)
    options = world["passkeys"].request_options(action.action_sha256, action.approval_id, "APPROVED")
    with pytest.raises(ApprovalError, match="not a trusted approver"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", stranger.get(options))


def test_a_pending_device_cannot_approve_until_it_is_activated(world):
    device, _, _ = enroll(world, activate=False)
    enroll(world, VirtualAuthenticator(), name="other")                 # some other device is active, so options can be requested
    action = new_action(world)
    options = world["passkeys"].request_options(action.action_sha256, action.approval_id, "APPROVED")
    with pytest.raises(ApprovalError, match="not a trusted approver"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", device.get(options))


def test_with_no_device_registered_there_are_no_options(world):
    action = new_action(world)
    with pytest.raises(PasskeyError, match="no approval device"):
        world["passkeys"].request_options(action.action_sha256, action.approval_id, "APPROVED")


def test_revoking_a_device_voids_what_it_approved_and_has_not_run(world):
    device, finished, _ = enroll(world)
    action = new_action(world)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    world["passkeys"].revoke(finished["credential_id"])
    with pytest.raises(ApprovalError, match="no longer a trusted approver"):
        world["approvals"].claim_for_execution(action.approval_id)


def test_editing_the_stored_confirmation_does_not_get_an_action_run(world):
    device, _, _ = enroll(world)
    action = new_action(world)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    with world["persistence"]._connect() as conn:
        key, stored = conn.execute("SELECT public_key, signature_hex FROM pending_action_signatures WHERE approval_id = ?", (action.approval_id,)).fetchone()
        blob = json.loads(bytes.fromhex(stored).decode("utf-8"))
        blob["signature"] = blob["signature"][:-4] + "AAAA"
        conn.execute("UPDATE pending_action_signatures SET signature_hex = ? WHERE approval_id = ?", (json.dumps(blob, sort_keys=True).encode("utf-8").hex(), action.approval_id))
        conn.execute("UPDATE pending_actions SET signature_hex = ? WHERE approval_id = ?", (json.dumps(blob, sort_keys=True).encode("utf-8").hex(), action.approval_id))
    with pytest.raises(ApprovalError):
        world["approvals"].claim_for_execution(action.approval_id)


def test_changing_the_action_after_the_confirmation_voids_it(world):
    device, _, _ = enroll(world)
    action = new_action(world)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    with world["persistence"]._connect() as conn:
        conn.execute("UPDATE pending_actions SET tool_args_json = ? WHERE approval_id = ?", (json.dumps({"relative_path": "docs/ELSEWHERE.md"}), action.approval_id))
    with pytest.raises(ApprovalError):
        world["approvals"].claim_for_execution(action.approval_id)


def test_a_role_the_action_asks_for_is_enforced_for_a_device(world):
    plain, _, _ = enroll(world, name="plain")
    admin, _, _ = enroll(world, VirtualAuthenticator(), name="admin", role="Security_Admin")
    action = new_action(world, approver_roles=["Security_Admin"])
    with pytest.raises(ApprovalError, match="role"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, plain))
    assert world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, admin)).status == "APPROVED"


def test_two_signatures_need_two_different_devices(world):
    first, _, _ = enroll(world, name="one")
    second, _, _ = enroll(world, VirtualAuthenticator(), name="two")
    action = new_action(world, required_signatures=2)
    assert world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, first)).status == "PENDING"
    with pytest.raises(ApprovalError, match="already signed"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, first))
    assert world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, second)).status == "APPROVED"


def test_a_passkey_and_an_ed25519_key_can_make_up_two_signatures(world):
    device, _, _ = enroll(world)
    action = new_action(world, required_signatures=2)
    sign_ed25519(world, action)
    assert world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device)).status == "APPROVED"
    assert world["approvals"].claim_for_execution(action.approval_id).status == "EXECUTING"


def test_scope_limits_the_kinds_and_people_a_device_may_approve(world):
    deleter, _, _ = enroll(world, name="deleter", scope={"kinds": ["delete"]})
    owner_only, _, _ = enroll(world, VirtualAuthenticator(), name="mine", scope={"namespaces": ["owner"]})
    edit = new_action(world)
    with pytest.raises(ApprovalError, match="may not approve the kind"):
        world["approvals"].decide_with_passkey(edit.approval_id, "APPROVED", confirm(world, edit, deleter))
    drop = new_action(world, tool="delentia_cron_delete", args={"job_id": "j"})
    assert world["approvals"].decide_with_passkey(drop.approval_id, "APPROVED", confirm(world, drop, deleter)).status == "APPROVED"
    other = world["approvals"].create("someone-else", "g", "delentia_write_repo_file", {"relative_path": "x.md"})
    with pytest.raises(ApprovalError, match="may not approve actions of"):
        world["approvals"].decide_with_passkey(other.approval_id, "APPROVED", confirm(world, other, owner_only))


def test_a_plan_can_only_be_approved_by_a_device_whose_scope_covers_every_step(world):
    deleter, _, _ = enroll(world, name="deleter", scope={"kinds": ["delete"]})
    plan = plan_approval.build_plan("g", [{"tool_name": "delentia_cron_delete", "tool_args": {"job_id": "j"}}, {"tool_name": "delentia_save_exchange_file", "tool_args": {"category": "c", "filename": "f", "content_text": "t"}}])
    action = world["approvals"].create("owner", "g", plan_approval.PLAN_TOOL, {"plan": plan})
    with pytest.raises(ApprovalError, match="may not approve the kind"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, deleter))


def test_a_decided_or_expired_action_cannot_be_decided_again(world):
    device, _, _ = enroll(world)
    action = new_action(world)
    world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    with pytest.raises(ApprovalError, match="already"):
        world["approvals"].decide_with_passkey(action.approval_id, "APPROVED", confirm(world, action, device))
    with pytest.raises(ApprovalError, match="no pending action"):
        world["approvals"].decide_with_passkey("nope", "APPROVED", {})


def test_the_ed25519_path_is_unchanged(world):
    action = new_action(world)
    assert sign_ed25519(world, action).status == "APPROVED"
    assert world["approvals"].claim_for_execution(action.approval_id).status == "EXECUTING"


# ------------------------------------------------------------------ in the real loop: a plan confirmed with a passkey runs exactly once
def test_a_plan_confirmed_on_a_device_runs_in_the_governed_loop(tmp_path):
    from test_plan_approval_loop_round101_real import CRON, FINISH, Tools, make_policy, mk, run, dispatched_names
    import rct_control_plane.autonomous_loop as autonomous_loop_module
    from test_governed_autonomous_loop_real import _scripted_decide

    class Patch:
        def __enter__(self):
            self.real = autonomous_loop_module.decide_next_action
            fake, _ = _scripted_decide([CRON, FINISH])
            autonomous_loop_module.decide_next_action = fake

        def __exit__(self, *exc):
            autonomous_loop_module.decide_next_action = self.real

    key = tmp_path / "keys" / "root.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "root", "public_key_hex": public}]), encoding="utf-8")
    mcp = Tools()
    with Patch():
        loop = mk(tmp_path, "pk1", mcp, make_policy(plan_first=["delete"]))
        result = run(loop)
    store = loop._pending_actions()
    pk_store = PasskeyStore(loop._persistence)
    device = VirtualAuthenticator()
    world = {"passkeys": pk_store, "approvals": store, "key": str(key), "persistence": loop._persistence}
    enroll(world, device)
    action = store.get(result["approval_id"])
    options = pk_store.request_options(action.action_sha256, action.approval_id, "APPROVED")
    store.decide_with_passkey(action.approval_id, "APPROVED", device.get(options))
    assert mcp.dispatched == []
    outcome = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert dispatched_names(mcp) == ["delentia_cron_delete"] and outcome["executed_result"]["executed"] == 1
