"""
Round 109: getting a local model from inside the Desk (local_models.py and its /v1/desk routes), against a REAL HTTP server that speaks Ollama's protocol (/api/tags and the streamed /api/pull),
started in this process on a free loopback port. What is pinned:

  * the catalog says only what its source says: every entry is a valid Ollama tag with a size, only the model this project measured carries measurements, no entry says "best";
  * the fit rule is the stated estimate and gives the expected answers at 4, 8, 16 and 32 GB, and nothing is claimed when the memory is unknown;
  * Ollama's state is told apart (not installed / installed but not running / running with models) and starting it never installs anything;
  * a download shows real progress, is refused for a model outside the catalog, for a full disk, for a stopped Ollama and for a second download at once, and can be cancelled;
  * the Desk routes are owner-only, a download needs `confirm: true`, and it leaves an audit row naming the model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import api_tokens, local_models
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence


class FakeOllama:
    """A real server on a loopback port: /api/tags lists models, /api/pull streams progress lines like Ollama's."""

    def __init__(self):
        self.models = ["qwen3:8b"]
        self.delay = 0.0
        self.fail_with = None
        self.pulls = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/api/tags":
                    body = json.dumps({"models": [{"name": m} for m in outer.models]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                outer.pulls.append(payload.get("name"))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                lines = [{"status": "pulling manifest"}]
                if outer.fail_with:
                    lines.append({"error": outer.fail_with})
                else:
                    lines += [{"status": "pulling abc", "total": 1000, "completed": c} for c in (0, 250, 500, 1000)] + [{"status": "success"}]
                try:
                    for line in lines:
                        self.wfile.write((json.dumps(line) + "\n").encode())
                        self.wfile.flush()
                        time.sleep(outer.delay)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", fake.url)
    monkeypatch.setattr(local_models, "PULLS", local_models.PullManager())
    yield fake
    fake.stop()


def test_the_catalog_is_valid_and_claims_only_what_its_source_says():
    tags = [m.tag for m in local_models.CATALOG]
    assert len(tags) == len(set(tags))
    for m in local_models.CATALOG:
        assert local_models.MODEL_NAME.match(m.tag) and m.size_gb > 0 and m.tools
        assert "best" not in (m.note_en + m.label).lower() and "recommended" not in m.note_en.lower()     # nothing here ranks quality
        if m.vendor_claim:
            assert "maker" in m.note_en.lower() or "its own page" in m.note_en.lower() or "own page" in m.note_en.lower()     # a claim of the maker says whose claim it is
    measured = [m.tag for m in local_models.CATALOG if m.measured_en]
    assert measured == ["qwen3:8b"]                                                       # the only model this project measured; the others say nothing about results
    assert all(m.note_th and (not m.measured_en or m.measured_th) for m in local_models.CATALOG)


@pytest.mark.parametrize("ram,fits_tags,not_fit", [
    (4.0, [], ["qwen3:1.7b", "qwen3:8b"]),
    (8.0, ["qwen3:1.7b", "qwen3:4b", "bonsai-2:4b", "lfm3:1.7b"], ["qwen3:8b", "qwen3:14b"]),
    (16.0, ["qwen3:8b", "bonsai-2:9b"], ["qwen3:14b"]),
    (32.0, ["qwen3:14b"], [])])
def test_the_fit_rule_gives_the_stated_answers(ram, fits_tags, not_fit):
    rows = {r["tag"]: r for r in local_models.recommend(ram)["models"]}
    assert all(rows[t]["fits"] is True for t in fits_tags) and all(rows[t]["fits"] is False for t in not_fit)


def test_try_first_prefers_the_measured_model_when_it_fits_and_says_nothing_when_the_memory_is_unknown():
    assert local_models.recommend(16.0)["try_first"] == "qwen3:8b"
    assert local_models.recommend(8.0)["try_first"] == "qwen3:4b"                       # nothing measured fits: the largest light one, not a vendor-claim one
    assert local_models.recommend(4.0)["try_first"] is None
    unknown = local_models.recommend(None)
    assert unknown["try_first"] is None and all(r["fits"] is None for r in unknown["models"])
    assert local_models.recommend(16.0)["rule"]["kind"] == "estimate, not measured"


def test_the_hardware_facts_are_real_numbers_on_this_computer():
    facts = local_models.hardware_facts()
    assert isinstance(facts["cpu_threads"], int) and facts["cpu_threads"] >= 1
    assert facts["ram_gb"] is None or facts["ram_gb"] >= 1.0


def test_ollama_states_are_told_apart(ollama, monkeypatch):
    monkeypatch.setattr(local_models, "find_ollama", lambda: "/somewhere/ollama")
    running = local_models.ollama_status()
    assert running["state"] == "running" and running["models"] == ["qwen3:8b"]
    ollama.stop()
    assert local_models.ollama_status()["state"] == "installed_not_running"
    monkeypatch.setattr(local_models, "find_ollama", lambda: None)
    nothing = local_models.ollama_status()
    assert nothing["state"] == "not_installed" and nothing["download_url"] == "https://ollama.com/download"


def test_starting_ollama_never_installs_and_reports_each_case(ollama, monkeypatch):
    assert local_models.start_ollama()["started"] is False and "already running" in local_models.start_ollama()["message"]
    ollama.stop()
    monkeypatch.setattr(local_models, "find_ollama", lambda: None)
    assert "not installed" in local_models.start_ollama()["message"]
    monkeypatch.setattr(local_models, "find_ollama", lambda: "/somewhere/ollama")
    started = []

    def fake_popen(argv, **kwargs):
        started.append(argv)
        restarted = FakeOllama()
        monkeypatch.setenv("DELENTIA_OLLAMA_URL", restarted.url)

    result = local_models.start_ollama(wait_seconds=5, popen=fake_popen)
    assert started == [["/somewhere/ollama", "serve"]] and result["started"] is True and result["running"] is True


def test_a_download_shows_real_progress_and_ends_done(ollama):
    manager = local_models.PullManager()
    manager.start("qwen3:4b", free_bytes=50 * 1024 ** 3)
    manager.wait(20)
    state = manager.state()
    assert state["status"] == "done" and state["percent"] == 100.0 and ollama.pulls == ["qwen3:4b"]


def test_progress_is_visible_while_it_runs_and_it_can_be_cancelled(ollama):
    ollama.delay = 0.3
    manager = local_models.PullManager()
    manager.start("qwen3:4b", free_bytes=50 * 1024 ** 3)
    deadline = time.time() + 10
    while time.time() < deadline and manager.state()["completed"] == 0:
        time.sleep(0.05)
    mid = manager.state()
    assert mid["status"] == "downloading" and mid["total"] == 1000
    with pytest.raises(local_models.PullError, match="already running"):
        manager.start("qwen3:8b", free_bytes=50 * 1024 ** 3)
    manager.cancel()
    manager.wait(20)
    assert manager.state()["status"] == "cancelled"


@pytest.mark.parametrize("name", ["", "llama3.2:3b", "qwen3:8b; rm -rf /", "../../etc:passwd", "qwen3", "QWEN3:8B", "x" * 200 + ":8b"])
def test_only_a_catalog_model_can_be_downloaded(ollama, name):
    manager = local_models.PullManager()
    with pytest.raises(local_models.PullError, match="not in Delentia's list"):
        manager.start(name, free_bytes=50 * 1024 ** 3)
    assert ollama.pulls == []


def test_a_full_disk_and_a_stopped_ollama_are_refused_before_anything_is_sent(ollama):
    manager = local_models.PullManager()
    with pytest.raises(local_models.PullError, match="free disk space"):
        manager.start("qwen3:8b", free_bytes=2 * 1024 ** 3)
    ollama.stop()
    with pytest.raises(local_models.PullError, match="not running"):
        manager.start("qwen3:4b", free_bytes=50 * 1024 ** 3)
    assert ollama.pulls == []


def test_an_error_from_ollama_becomes_a_failed_download_with_its_words(ollama):
    ollama.fail_with = "pull model manifest: file does not exist"
    manager = local_models.PullManager()
    manager.start("qwen3:4b", free_bytes=50 * 1024 ** 3)
    manager.wait(20)
    state = manager.state()
    assert state["status"] == "failed" and "does not exist" in state["message"]


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch, ollama):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.delenv("DELENTIA_API_TOKENS_FILE", raising=False)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    monkeypatch.setattr(local_models, "find_ollama", lambda: "/somewhere/ollama")
    with TestClient(create_app()) as client:
        yield client, persistence


def test_the_desk_view_puts_memory_ollama_and_the_recommendation_together(desk):
    client, _ = desk
    view = client.get("/v1/desk/local-models").json()
    assert view["ollama"]["state"] == "running" and view["ollama"]["models"] == ["qwen3:8b"]
    assert view["recommendation"]["catalog_date"] == "2026-11-03" and view["pull"]["status"] == "idle"
    row = next(r for r in view["recommendation"]["models"] if r["tag"] == "qwen3:8b")
    assert row["installed"] is True and row["measured_here"] is True


def test_a_download_through_the_desk_needs_confirmation_and_is_audited(desk, ollama, monkeypatch):
    client, persistence = desk
    monkeypatch.setattr(local_models.shutil, "disk_usage", lambda _p: type("U", (), {"free": 50 * 1024 ** 3})())
    assert client.post("/v1/desk/ollama/pull", json={"name": "qwen3:4b"}).status_code == 400
    assert client.post("/v1/desk/ollama/pull", json={"name": "not-in-the-list:1b", "confirm": True}).status_code == 400
    answer = client.post("/v1/desk/ollama/pull", json={"name": "qwen3:4b", "confirm": True})
    assert answer.status_code == 200 and answer.json()["name"] == "qwen3:4b"
    local_models.PULLS.wait(20)
    assert client.get("/v1/desk/ollama/pull").json()["status"] == "done"
    with sqlite3.connect(persistence.db_path) as conn:
        rows = conn.execute("SELECT action, entity_id FROM audit_trail WHERE entity_type='local_model'").fetchall()
    assert rows == [("download_started", "qwen3:4b")]


@pytest.mark.parametrize("name", ["LOCAL_MODELS_EN.md", "LOCAL_MODELS_TH.md"])
def test_the_guides_list_every_catalog_model_with_its_size_and_estimate_and_say_what_was_measured(name):
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "docs" / "demo" / name).read_text(encoding="utf-8")
    for m in local_models.CATALOG:
        line = next((ln for ln in text.splitlines() if f"`{m.tag}`" in ln and ln.startswith("|")), None)
        assert line, (name, m.tag)
        assert f"{m.size_gb} GB" in line and f"{local_models.estimated_memory_gb(m)} GB" in line, (name, m.tag, line)
    assert ("2026-11-03" in text or "3 พ.ย. 2026" in text) and local_models.CATALOG_DATE == "2026-11-03"
    assert text.count("**") >= 4 and "best" not in text.replace("not ranked", "").lower().replace("none is called \"best\"", "")


def test_a_person_with_their_own_token_cannot_start_ollama_or_download_anything(tmp_path, monkeypatch, ollama):
    path = tmp_path / "tokens.json"
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(path))
    alice = api_tokens.create("alice", path)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        headers = {"Authorization": f"Bearer {alice}"}
        assert client.get("/v1/desk/local-models", headers=headers).status_code == 403
        assert client.post("/v1/desk/ollama/start", headers=headers).status_code == 403
        assert client.post("/v1/desk/ollama/pull", json={"name": "qwen3:4b", "confirm": True}, headers=headers).status_code == 403
        assert client.post("/v1/desk/ollama/pull/cancel", headers=headers).status_code == 403
    assert ollama.pulls == []
