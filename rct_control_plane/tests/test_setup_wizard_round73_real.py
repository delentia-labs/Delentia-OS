"""
Round 73: `delentia setup` (setup_wizard.py) with a real loopback server that answers /api/tags like Ollama, real key generation, a real temporary home folder and the real CLI.
What must hold: nothing is written outside the home folder; a second run changes nothing; the approver key is not created unless asked and is refused inside the repository; --dry-run writes nothing.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from rct_control_plane import memory_embeddings as me
from rct_control_plane import setup_wizard as sw
from rct_control_plane.cli import cli


class Tags:
    def __init__(self, names):
        outer = self
        self.names = names

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps({"models": [{"name": n} for n in outer.names]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}"

    def stop(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def machine(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    servers = []

    def start(names):
        server = Tags(names)
        servers.append(server)
        monkeypatch.setenv(me.URL_ENV, server.url)
        me.reset_auto_probe()
        return server
    yield start, tmp_path / "home"
    for server in servers:
        server.stop()


def _tree(path):
    return sorted(str(p.relative_to(path)) for p in path.rglob("*")) if path.exists() else []


def test_a_fresh_machine_with_a_local_model_gets_a_model_and_an_audit_key_but_no_approver_key(machine):
    start, home = machine
    start(["qwen2.5:7b", "bge-m3:latest"])
    facts = sw.inspect_machine(home)
    steps = {s.id: s for s in sw.make_plan(facts)}
    assert steps["model"].action == "do" and steps["model"].payload == {"provider": "ollama", "model": "qwen2.5:7b"}
    assert steps["audit_key"].action == "do" and steps["approver_key"].action == "needs-you" and "ANOTHER device" in steps["approver_key"].detail
    assert "bge-m3" in steps["embedding"].detail
    sw.apply_plan(list(steps.values()), home)
    assert (home / "model.json").exists() and (home / "keys" / "audit-signer.pem").exists()
    assert not (home / "approvers.json").exists() and not (home / "keys" / "approver-trial.pem").exists()
    model = json.loads((home / "model.json").read_text(encoding="utf-8"))
    assert "ollama" in json.dumps(model) and "qwen2.5:7b" in json.dumps(model)


def test_the_better_measured_local_model_is_preferred_when_both_are_installed(machine):
    start, home = machine
    start(["qwen2.5:7b", "qwen3:8b"])
    steps = {s.id: s for s in sw.make_plan(sw.inspect_machine(home))}
    assert steps["model"].payload == {"provider": "ollama", "model": "qwen3:8b"}


def test_a_second_run_changes_nothing(machine):
    start, home = machine
    start(["qwen2.5:7b"])
    sw.apply_plan(sw.make_plan(sw.inspect_machine(home), approver_here=True), home)
    before = {p: (home / p).read_bytes() for p in _tree(home) if (home / p).is_file()}
    again = sw.make_plan(sw.inspect_machine(home), approver_here=True)
    assert all(s.action in ("skip", "info") for s in again), [(s.id, s.action) for s in again]
    sw.apply_plan(again, home)
    assert {p: (home / p).read_bytes() for p in _tree(home) if (home / p).is_file()} == before


def test_the_approver_key_on_this_machine_needs_the_flag_and_is_listed_for_a_trial_only(machine):
    start, home = machine
    start(["qwen2.5:7b"])
    steps = sw.apply_plan(sw.make_plan(sw.inspect_machine(home), approver_here=True), home)
    done = {s.id: s for s in steps}["approver_key"]
    assert done.done and "trial" in done.result
    entries = json.loads((home / "approvers.json").read_text(encoding="utf-8"))
    assert len(entries) == 1 and "same machine" in entries[0]["name"] and len(entries[0]["public_key_hex"]) == 64


def test_no_model_anywhere_is_said_plainly_and_nothing_is_invented(machine):
    start, home = machine
    start(["llama3.2:3b"])                                             # installed but not a preferred brain
    steps = {s.id: s for s in sw.make_plan(sw.inspect_machine(home))}
    assert steps["model"].action == "needs-you" and "ollama pull" in steps["model"].detail
    sw.apply_plan(list(steps.values()), home)
    assert not (home / "model.json").exists()


def test_an_openrouter_key_in_the_environment_selects_openrouter_and_is_never_written(machine, monkeypatch):
    start, home = machine
    start([])
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-value-that-must-not-be-saved")
    steps = sw.apply_plan(sw.make_plan(sw.inspect_machine(home)), home)
    assert {s.id: s for s in steps}["model"].payload["provider"] == "openrouter"
    written = "".join((home / p).read_text(encoding="utf-8", errors="ignore") for p in _tree(home) if (home / p).is_file() and not p.endswith(".pem"))
    assert "sk-or-test-value" not in written


def test_dry_run_writes_nothing_and_the_cli_does_nothing_without_a_yes(machine):
    start, home = machine
    start(["qwen2.5:7b"])
    dry = CliRunner().invoke(cli, ["setup", "--home", str(home), "--dry-run"])
    assert dry.exit_code == 0 and "would do" in dry.output and _tree(home) == []
    declined = CliRunner().invoke(cli, ["setup", "--home", str(home)], input="n\n")
    assert declined.exit_code == 0 and "Nothing was changed" in declined.output and _tree(home) == []
    accepted = CliRunner().invoke(cli, ["setup", "--home", str(home), "--yes", "--approver-key-here"])
    assert accepted.exit_code == 0 and (home / "model.json").exists() and (home / "approvers.json").exists()
    assert "DELENTIA_APPROVERS_FILE" in accepted.output                  # a home that is not ~/.delentia says how to point the server at it


def test_a_home_inside_the_repository_cannot_hold_keys(machine):
    start, _ = machine
    start(["qwen2.5:7b"])
    inside = os.path.join(os.path.dirname(__file__), "..", "..", "workspace_output", "setup_inside_repo")
    steps = sw.apply_plan(sw.make_plan(sw.inspect_machine(sw.delentia_home(inside)), approver_here=True), sw.delentia_home(inside))
    results = {s.id: s.result for s in steps}
    assert results["audit_key"].startswith("FAILED") and results["approver_key"].startswith("FAILED")        # both refuse a path inside the repository
    assert not os.path.exists(os.path.join(inside, "keys", "audit-signer.pem"))
