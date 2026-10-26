"""
Round 101 (UX audit): the "can I use this yet?" checks. Real HTTP (a tiny server standing in for Ollama), real SQLite, a real approver key.
Every state a new person can meet is a case, and no answer carries a secret.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import approvals, readiness
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence


class _Ollama(BaseHTTPRequestHandler):
    models = ["qwen2.5:7b"]

    def do_GET(self):                                           # noqa: N802
        body = json.dumps({"models": [{"name": n} for n in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                                  # noqa: D401
        pass


@pytest.fixture
def ollama():
    server = HTTPServer(("127.0.0.1", 0), _Ollama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", "qwen2.5:7b")


def _facts(**kw):
    base = {"provider": "ollama", "model": "qwen2.5:7b", "ollama_models": ["qwen2.5:7b"], "approver_keys": 1, "approver_devices": 0, "episodes": 3}
    base.update(kw)
    return base


def _check(report, name):
    return next(c for c in report["checks"] if c["id"] == name)


def test_everything_in_place_is_ready_and_done():
    report = readiness.evaluate(_facts())
    assert report["ready"] and report["all_done"]


def test_a_local_model_server_that_is_off_is_named():
    check = _check(readiness.evaluate(_facts(ollama_models=None)), "model")
    assert check["state"] == "server_down" and not check["ok"]


def test_a_model_that_is_not_downloaded_is_named_with_what_is_installed():
    check = _check(readiness.evaluate(_facts(ollama_models=["llama3.2:3b"])), "model")
    assert check["state"] == "model_missing" and check["installed"] == ["llama3.2:3b"]


def test_a_tag_suffix_is_not_a_missing_model():
    assert _check(readiness.evaluate(_facts(model="bge-m3", ollama_models=["bge-m3:latest"])), "model")["ok"]


def test_a_hosted_model_without_a_key_is_named_and_with_a_key_is_ready():
    hosted = dict(provider="openrouter", model="x/y", ollama_models=None, needs_key=True)
    assert _check(readiness.evaluate(_facts(**hosted, key_present=False)), "model")["state"] == "no_key"
    assert _check(readiness.evaluate(_facts(**hosted, key_present=True)), "model")["ok"]


def test_nobody_who_can_approve_means_not_ready_and_one_key_or_one_device_is_enough():
    assert not readiness.evaluate(_facts(approver_keys=0))["ready"]
    assert readiness.evaluate(_facts(approver_keys=0, approver_devices=1))["ready"]
    assert readiness.evaluate(_facts(approver_keys=1, approver_devices=0))["ready"]


def test_a_first_request_is_a_nudge_not_a_blocker():
    report = readiness.evaluate(_facts(episodes=0))
    assert report["ready"] and not report["all_done"] and not _check(report, "first_request")["essential"]


def test_gather_reads_a_real_local_server_and_a_real_approver_key(ollama, tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", ollama)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "r.db"))
    first = readiness.report(persistence)
    assert _check(first, "model")["ok"] and not _check(first, "approver")["ok"] and not first["ready"]
    key = tmp_path / "k.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "me", "public_key_hex": public}]), encoding="utf-8")
    assert readiness.report(persistence)["ready"]
    _Ollama.models = ["other:1b"]
    try:
        assert _check(readiness.report(persistence), "model")["state"] == "model_missing"
    finally:
        _Ollama.models = ["qwen2.5:7b"]


def test_an_unreachable_server_answers_quickly_instead_of_hanging(tmp_path, monkeypatch):
    import time
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", "http://127.0.0.1:9")            # nothing listens on the discard port
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "r.db"))
    started = time.monotonic()
    report = readiness.report(persistence)
    assert _check(report, "model")["state"] == "server_down" and time.monotonic() - started < 5


def test_the_route_returns_the_checks_and_no_secret(tmp_path, monkeypatch, ollama):
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", ollama)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-this-must-never-appear-in-an-answer")

    class _Kernel:
        _persistence = ControlPlanePersistence(db_path=str(tmp_path / "d.db"))

    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel())
    with TestClient(create_app()) as client:
        answer = client.get("/v1/desk/readiness")
    assert answer.status_code == 200 and {c["id"] for c in answer.json()["checks"]} == {"model", "approver", "first_request"}
    assert "sk-or-this-must-never-appear" not in answer.text


def test_a_person_token_cannot_read_the_readiness_route():
    from rct_control_plane import api_auth
    assert not api_auth.person_route_allowed("GET", "/v1/desk/readiness")
