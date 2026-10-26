"""
Round 101C: the first approval device, added with a one-time code instead of a key command. Real SQLite, real FastAPI, a software authenticator, a real CLI process.

Pinned: the code only exists while nobody can approve; it is shown once and stored hashed; five wrong tries, ten minutes or a second code end it; the agent's shell can not ask for it; with a right code the first device
is an approver at once and every device after it needs a signature as before.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import approvals, first_device, passkeys, sandbox
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.first_device import FirstDeviceError, FirstDeviceStore
from rct_control_plane.persistence import ControlPlanePersistence
from virtual_authenticator import VirtualAuthenticator

ROOT = Path(__file__).resolve().parents[2]


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture(autouse=True)
def fresh_install(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))            # does not exist: nobody can approve
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.delenv(first_device.AGENT_SHELL_ENV, raising=False)
    monkeypatch.delenv(passkeys.RP_ID_ENV, raising=False)
    monkeypatch.delenv(passkeys.ORIGINS_ENV, raising=False)


@pytest.fixture
def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "fd.db"))


@pytest.fixture
def desk(tmp_path, persistence, monkeypatch):
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        yield client, persistence


def add_first_device(client, code, name="laptop", device=None):
    device = device or VirtualAuthenticator()
    begun = client.post("/v1/desk/passkeys/register/begin", json={"name": name}).json()
    body = {"enrollment_id": begun["enrollment_id"], "credential": device.create(begun["options"])}
    if code is not None:
        body["first_device_code"] = code
    return device, client.post("/v1/desk/passkeys/register/finish", json=body)


def test_a_code_is_issued_only_while_nobody_can_approve(persistence, tmp_path):
    store = FirstDeviceStore(persistence)
    issued = store.issue()
    assert len(issued["code"]) == 8 and issued["ttl_seconds"] == 600 and "-" in issued["display"]
    key = tmp_path / "k.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "me", "public_key_hex": public}]), encoding="utf-8")
    with pytest.raises(FirstDeviceError, match="someone can already approve"):
        store.issue()
    with pytest.raises(FirstDeviceError, match="someone can already approve"):
        store.check(issued["code"])                                            # a code issued earlier stops working the moment an approver exists


def test_the_agents_shell_can_not_ask_for_a_code(persistence, monkeypatch):
    store = FirstDeviceStore(persistence)
    with pytest.raises(FirstDeviceError, match="person at the keyboard"):
        store.issue(from_agent_shell=True)
    monkeypatch.setenv(first_device.AGENT_SHELL_ENV, "1")
    with pytest.raises(FirstDeviceError, match="person at the keyboard"):
        store.issue()
    assert sandbox.scrubbed_environment()[first_device.AGENT_SHELL_ENV] == "1"          # every command run for the agent carries the mark
    for command in ("delentia approvals first-device-code", "python -m rct_control_plane.cli approvals first-device-code", "delentia update --apply", "delentia   update   --apply"):
        assert sandbox.classify_command_risk(command) == "denied", command


def test_the_code_is_stored_hashed_and_a_status_never_shows_it(persistence):
    store = FirstDeviceStore(persistence)
    issued = store.issue()
    with persistence._connect() as conn:
        rows = [str(r) for r in conn.execute("SELECT * FROM first_device_codes").fetchall()]
    assert issued["code"] not in " ".join(rows) and issued["display"] not in " ".join(rows)
    status = store.status()
    assert status["code_waiting"] and issued["code"] not in json.dumps(status)


def test_a_right_code_passes_and_is_written_with_dashes_or_lowercase(persistence):
    store = FirstDeviceStore(persistence)
    issued = store.issue()
    store.check(issued["display"].lower())
    store.check(" " + issued["code"] + " ")


def test_five_wrong_tries_cancel_the_code_even_for_the_right_one(persistence):
    store = FirstDeviceStore(persistence)
    issued = store.issue()
    for left in (4, 3, 2, 1):
        with pytest.raises(FirstDeviceError, match=rf"\({left} tries left\)"):
            store.check("WRONG123")
    with pytest.raises(FirstDeviceError, match="cancelled"):
        store.check("WRONG123")
    with pytest.raises(FirstDeviceError, match="no live code"):
        store.check(issued["code"])


def test_a_code_expires_after_ten_minutes_and_a_new_one_replaces_the_old(persistence):
    store = FirstDeviceStore(persistence)
    old = store.issue()
    new = store.issue()
    with pytest.raises(FirstDeviceError, match="not right"):
        store.check(old["code"])
    with persistence._connect() as conn:
        conn.execute("UPDATE first_device_codes SET expires_at = ? WHERE state = 'ACTIVE'", (time.time() - 1,))
    with pytest.raises(FirstDeviceError, match="no live code"):
        store.check(new["code"])


def test_with_no_code_issued_there_is_nothing_to_check(persistence):
    with pytest.raises(FirstDeviceError, match="no live code"):
        FirstDeviceStore(persistence).check("ANYTHING")


def test_the_first_device_becomes_an_approver_at_once_with_the_right_code_and_can_approve(desk):
    client, persistence = desk
    assert client.get("/v1/desk/passkeys").json()["first_device"] == {"open": True, "code_waiting": False, "expires_at": None}
    issued = FirstDeviceStore(persistence).issue()
    assert client.get("/v1/desk/passkeys").json()["first_device"]["code_waiting"] is True
    device, answer = add_first_device(client, issued["display"])
    assert answer.status_code == 200 and answer.json()["activated"] and answer.json()["device"]["status"] == "ACTIVE"
    assert client.get("/v1/desk/passkeys").json()["first_device"]["open"] is False
    action = PendingActionStore(persistence).create("owner", "a goal", "delentia_write_repo_file", {"relative_path": "docs/a.md"})
    options = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"}).json()
    decided = client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/decide", json={"decision": "APPROVED", "assertion": device.get(options["options"])})
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"
    with persistence._connect() as conn:
        actions = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'passkey'").fetchall()]
    assert "first_device_activated" in actions


def test_a_wrong_code_makes_no_device_and_costs_a_try(desk):
    client, persistence = desk
    FirstDeviceStore(persistence).issue()
    _, answer = add_first_device(client, "WRONG123")
    assert answer.status_code == 400 and "not right" in answer.json()["detail"]
    assert client.get("/v1/desk/passkeys").json()["devices"] == []


def test_without_a_code_the_first_device_is_only_pending_and_can_not_approve(desk):
    client, persistence = desk
    device, answer = add_first_device(client, None)
    assert answer.status_code == 200 and "approval_id" in answer.json()
    assert client.get("/v1/desk/passkeys").json()["devices"][0]["status"] == "PENDING"
    action = PendingActionStore(persistence).create("owner", "a goal", "delentia_write_repo_file", {"relative_path": "docs/a.md"})
    assert client.post(f"/v1/desk/approvals/{action.approval_id}/passkey/options", json={"decision": "APPROVED"}).status_code == 400


def test_the_code_is_used_up_and_a_second_device_needs_a_signature_as_before(desk):
    client, persistence = desk
    issued = FirstDeviceStore(persistence).issue()
    add_first_device(client, issued["display"], name="first")
    _, second = add_first_device(client, issued["display"], name="second")
    assert second.status_code == 400 and "someone can already approve" in second.json()["detail"]
    devices = client.get("/v1/desk/passkeys").json()["devices"]
    assert [d["status"] for d in devices] == ["ACTIVE"]


def test_the_command_prints_a_code_for_a_person_and_refuses_for_the_agent(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), "DELENTIA_APPROVERS_FILE": str(tmp_path / "none.json")}
    env.pop(first_device.AGENT_SHELL_ENV, None)
    person = subprocess.run([sys.executable, "-m", "rct_control_plane.cli", "approvals", "first-device-code", "--db", str(tmp_path / "cli.db")],
                            env=env, capture_output=True, text=True, timeout=180, cwd=str(tmp_path))
    assert person.returncode == 0 and "one-time code" in person.stdout and "Desk" in person.stdout
    agent = subprocess.run([sys.executable, "-m", "rct_control_plane.cli", "approvals", "first-device-code", "--db", str(tmp_path / "cli2.db")],
                           env={**env, first_device.AGENT_SHELL_ENV: "1"}, capture_output=True, text=True, timeout=180, cwd=str(tmp_path))
    assert agent.returncode == 1 and "person at the keyboard" in agent.stderr and "one-time code" not in agent.stdout


# ------------------------------------------------------------------ races (Round 101D, gap T6)
def _race(workers, fn):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, range(workers)))


def test_twenty_guesses_at_the_same_moment_get_at_most_five_comparisons_and_the_right_code_is_then_dead(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "race.db"))
    issued = FirstDeviceStore(persistence).issue()

    def guess(i):
        try:
            FirstDeviceStore(persistence).check(f"WRONG{i:03d}")
            return "accepted"
        except FirstDeviceError as exc:
            return "wrong" if "not right" in str(exc) else "closed"

    outcomes = _race(20, guess)
    assert "accepted" not in outcomes and outcomes.count("wrong") <= first_device.MAX_ATTEMPTS, outcomes
    with pytest.raises(FirstDeviceError):
        FirstDeviceStore(persistence).check(issued["code"])                  # the tries are used up, so even the right code is refused now


def test_two_requests_with_the_right_code_at_the_same_moment_make_exactly_one_first_device(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "race2.db"))
    issued = FirstDeviceStore(persistence).issue()

    def use(i):
        store = FirstDeviceStore(persistence)
        try:
            code_id = store.check(issued["display"])
        except FirstDeviceError:
            return False
        return store.consume(code_id)

    outcomes = _race(8, use)
    assert outcomes.count(True) == 1, outcomes


def test_over_http_two_devices_with_the_same_code_at_the_same_moment_leave_one_active_device(desk):
    client, persistence = desk
    issued = FirstDeviceStore(persistence).issue()
    prepared = []
    for name in ("first", "second"):
        device = VirtualAuthenticator()
        begun = client.post("/v1/desk/passkeys/register/begin", json={"name": name}).json()
        prepared.append({"enrollment_id": begun["enrollment_id"], "credential": device.create(begun["options"]), "first_device_code": issued["display"]})
    answers = _race(2, lambda i: client.post("/v1/desk/passkeys/register/finish", json=prepared[i]).status_code)
    assert sorted(answers) == [200, 400], answers
    assert [d["status"] for d in client.get("/v1/desk/passkeys").json()["devices"] if d["status"] == "ACTIVE"] == ["ACTIVE"]


def test_more_requests_than_tries_at_once_never_leave_the_right_code_without_a_winner(tmp_path):
    """Found by CI on Python 3.10: with 8 right-code requests at once only 5 can hold a try; the other 3 used to CANCEL the code, which also cancelled the 5 that held one, so nobody got in. The extra
    requests are refused and nothing else changes: exactly one device is made, every time. A barrier starts all 8 together, 25 rounds, because one round hits the bad ordering only sometimes."""
    import threading
    for round_number in range(25):
        persistence = ControlPlanePersistence(db_path=str(tmp_path / f"many{round_number}.db"))
        issued = FirstDeviceStore(persistence).issue()
        barrier = threading.Barrier(8)

        def use(_i):
            store = FirstDeviceStore(persistence)
            barrier.wait()
            try:
                code_id = store.check(issued["display"])
            except FirstDeviceError:
                return False
            return store.consume(code_id)

        outcomes = _race(8, use)
        assert outcomes.count(True) == 1, (round_number, outcomes)
