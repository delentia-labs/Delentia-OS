"""
Round 108: CodeQL lists eight `py/stack-trace-exposure` alerts in desk_api.py. They are routes of the owner's Desk that return a typed error message (cron, hooks) or a status dictionary (credentials, governance, witnesses).
What the alert is really about is a TRACEBACK reaching a caller: a file path, a line number, "Traceback (most recent call last)". This test provokes the errors those routes can produce, for real, and checks that
no response carries one. It does not claim that no message is returned: a person who mistyped a schedule is told why, by design.

Real FastAPI app, real stores in a temp home, real (broken) configuration files and environment.
"""
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import approvals, desk_api
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence

LEAKS = [re.compile(p) for p in (r"Traceback \(most recent call last\)", r'File "[^"]+", line \d+', r"\.py:\d+", r"\.py\", line", r"site-packages", r"rct_control_plane[\\/][a-z_]+\.py")]


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    for name in ("DELENTIA_API_TOKEN", approvals.APPROVERS_ENV, "DELENTIA_AUDIT_WITNESSES", "DELENTIA_CREDENTIAL_POOL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        yield client, tmp_path


def _no_trace(response):
    text = response.text
    for pattern in LEAKS:
        assert not pattern.search(text), (pattern.pattern, text[:300])


def test_a_mistyped_schedule_or_a_missing_job_gets_a_message_and_no_traceback(desk):
    client, _ = desk
    calls = [
        client.post("/v1/desk/cron/preview", json={"text": "whenever the moon is blue"}),
        client.post("/v1/desk/cron/jobs", json={"goal": "x", "schedule": "not a schedule"}),
        client.post("/v1/desk/cron/jobs", json={"goal": "x", "schedule": "every day at 09:00", "max_runs": "many"}),          # a ValueError from int()
        client.post("/v1/desk/cron/jobs/no-such-job/enable"),
        client.post("/v1/desk/cron/jobs/no-such-job/run"),
        client.delete("/v1/desk/cron/jobs/no-such-job"),
    ]
    for response in calls:
        assert response.status_code in (400, 404), (response.status_code, response.text[:200])
        _no_trace(response)
        assert isinstance(response.json().get("detail"), str) and response.json()["detail"]


def test_a_refused_hook_gets_a_message_and_no_traceback(desk):
    client, _ = desk
    for body in ({"name": "X", "code": "def pre_tool_call(t, a): return None", "description": "bad name"},
                 {"name": "ok_name", "code": "import os\ndef pre_tool_call(t, a):\n    os.system('x')\n", "description": "forbidden import"},
                 {"name": "ok_name", "code": "def pre_tool_call(t, a: return None", "description": "does not parse"}):
        response = client.post("/v1/desk/hooks/propose", json=body)
        assert response.status_code in (200, 400), response.text[:200]           # a bad NAME is refused with 400; bad code is stored as REJECTED with the reasons
        _no_trace(response)
        if response.status_code == 200:
            assert response.json()["status"] == "REJECTED" and response.json()["verification"]["problems"]


def test_a_broken_credential_pool_file_is_reported_without_its_reason_or_a_traceback(desk, monkeypatch):
    client, tmp = desk
    broken = tmp / "pool.json"
    broken.write_text("{ this is not json ", encoding="utf-8")
    monkeypatch.setenv("DELENTIA_CREDENTIAL_POOL", str(broken))
    response = client.get("/v1/desk/credentials")
    assert response.status_code == 200
    _no_trace(response)
    error = response.json()["error"]
    assert error and "not usable" in error and "Expecting" not in error and "json" not in error.lower().replace("credential_pool.json", "")       # the reason stays on the host


def test_a_broken_witness_configuration_is_reported_as_a_sentence_and_no_traceback(desk, monkeypatch):
    client, _ = desk
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", "[ not json")
    response = client.get("/v1/desk/governance/audit/witnesses")
    assert response.status_code == 200
    _no_trace(response)
    assert "unusable" in response.json()["problem"]


def test_the_governance_overview_with_a_broken_witness_and_pool_still_returns_no_traceback(desk, monkeypatch):
    client, tmp = desk
    broken = tmp / "pool.json"
    broken.write_text("[[[", encoding="utf-8")
    monkeypatch.setenv("DELENTIA_CREDENTIAL_POOL", str(broken))
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", "{")
    response = client.get("/v1/desk/governance")
    assert response.status_code == 200
    _no_trace(response)
