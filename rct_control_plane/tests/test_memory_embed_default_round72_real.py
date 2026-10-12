"""
Round 72: what `delentia serve` does about recall by meaning when nothing is configured. DELENTIA_MEMORY_EMBED=auto is the served default: it is on only when the local Ollama has an embedding model, and it
chooses bge-m3 (reads Thai) before nomic-embed-text; a model named by DELENTIA_MEMORY_EMBED_MODEL is always obeyed. Tested against a real loopback server that answers /api/tags like Ollama.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest

from rct_control_plane import memory_embeddings as me


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


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in (me.ENV, me.MODEL_ENV, me.URL_ENV):
        monkeypatch.delenv(name, raising=False)
    me.reset_auto_probe()
    yield
    me.reset_auto_probe()


def _serve(monkeypatch, names):
    server = Tags(names)
    monkeypatch.setenv(me.URL_ENV, server.url)
    monkeypatch.setenv(me.ENV, "auto")
    me.reset_auto_probe()
    return server


@pytest.mark.parametrize("installed,expected,on", [
    (["bge-m3:latest", "nomic-embed-text:latest", "qwen2.5:7b"], "bge-m3", True),
    (["nomic-embed-text:latest", "qwen2.5:7b"], "nomic-embed-text", True),
    (["qwen2.5:7b", "llama3.2:3b"], "nomic-embed-text", False),
    ([], "nomic-embed-text", False),
])
def test_auto_takes_the_best_embedding_model_the_local_ollama_has(monkeypatch, installed, expected, on):
    server = _serve(monkeypatch, installed)
    try:
        assert me.enabled() is on and me.model() == expected
    finally:
        server.stop()


def test_a_model_named_by_the_owner_is_always_obeyed_even_when_a_better_one_is_installed(monkeypatch):
    server = _serve(monkeypatch, ["bge-m3:latest", "nomic-embed-text:latest"])
    monkeypatch.setenv(me.MODEL_ENV, "nomic-embed-text")
    try:
        assert me.enabled() is True and me.model() == "nomic-embed-text"
        monkeypatch.setenv(me.MODEL_ENV, "mxbai-embed-large")
        me.reset_auto_probe()
        assert me.enabled() is False and me.model() == "mxbai-embed-large"                    # named but not installed: off, never a silent switch to another model
    finally:
        server.stop()


def test_without_auto_the_default_model_is_unchanged(monkeypatch):
    monkeypatch.setenv(me.ENV, "ollama")
    assert me.model() == "nomic-embed-text" and me.enabled() is True
    monkeypatch.delenv(me.ENV)
    assert me.enabled() is False and me.model() == "nomic-embed-text"


def test_the_choice_is_probed_once_and_remembered(monkeypatch):
    server = _serve(monkeypatch, ["bge-m3:latest"])
    calls = []
    original = me._installed_models
    monkeypatch.setattr(me, "_installed_models", lambda url: calls.append(url) or original(url))
    try:
        for _ in range(5):
            assert me.model() == "bge-m3" and me.enabled()
        assert len(calls) == 1
    finally:
        server.stop()


def test_an_address_that_is_not_this_machine_is_not_probed(monkeypatch):
    monkeypatch.setenv(me.ENV, "auto")
    monkeypatch.setenv(me.URL_ENV, "http://203.0.113.9:11434")
    me.reset_auto_probe()
    calls = []
    monkeypatch.setattr(me, "_installed_models", lambda url: calls.append(url) or ["bge-m3"])
    assert me.enabled() is False and calls == []


def test_serve_sets_auto_unless_the_owner_chose_something_else():
    import click.testing
    from rct_control_plane.cli import cli
    seen = {}
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DELENTIA_MEMORY_EMBED", None)
        with mock.patch("uvicorn.run", lambda *a, **k: seen.update(embed=os.environ.get("DELENTIA_MEMORY_EMBED"))):
            click.testing.CliRunner().invoke(cli, ["serve", "--port", "8123"])
        assert seen["embed"] == "auto"
        os.environ["DELENTIA_MEMORY_EMBED"] = "off"
        with mock.patch("uvicorn.run", lambda *a, **k: seen.update(embed=os.environ.get("DELENTIA_MEMORY_EMBED"))):
            click.testing.CliRunner().invoke(cli, ["serve", "--port", "8123"])
        assert seen["embed"] == "off"
        os.environ.pop("DELENTIA_DAEMON_ENABLED", None)
