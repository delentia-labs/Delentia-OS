"""
Round 62: external MCP over HTTP with OAuth (client-credentials), and MCP resources/prompts as read-only third-party text.

A real MCP server (tests/fake_mcp_oauth_server.py) runs in its own OS process on loopback: it issues tokens at /token and answers 401 to anything without a currently valid bearer. The client is the real
MCP SDK through external_mcp. What is checked: the configuration refuses a pasted secret, the token is fetched and used, reused until it expires and fetched again after, a wrong secret fails
plainly, resources and prompts come back as screened text and never need a signature, and a server that did not ask for resources gets no such tools.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import socket
import subprocess
import time

import pytest

from rct_control_plane import external_mcp as xm

SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_oauth_server.py")


def run(coro):
    return asyncio.run(coro)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def oauth_server(tmp_path, monkeypatch):
    port = free_port()
    log = tmp_path / "server.log"
    monkeypatch.setenv("FAKE_LOG", str(log))
    proc = subprocess.Popen([sys.executable, SERVER, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "FAKE_LOG": str(log)})
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("the fake OAuth server did not start")
    yield port, log
    proc.kill()
    proc.wait(timeout=10)


def lines(log):
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def write_config(tmp_path, monkeypatch, port, **extra):
    spec = {"url": f"http://127.0.0.1:{port}/mcp", "timeout_s": 30, "read_only_tools": ["whoami"],
            "oauth": {"token_url": f"http://127.0.0.1:{port}/token", "client_id_env": "FAKE_CLIENT_ID", "client_secret_env": "FAKE_CLIENT_SECRET", "scope": "read"}}
    spec.update(extra)
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": {"docs": spec}}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    monkeypatch.setenv("FAKE_CLIENT_ID", "svc-reader")
    monkeypatch.setenv("FAKE_CLIENT_SECRET", "s3cret-value")
    monkeypatch.delenv(xm.PERSISTENT_ENV, raising=False)
    xm.clear_cache()
    xm.clear_tokens()


@pytest.fixture(autouse=True)
def clean():
    xm.clear_cache()
    xm.clear_tokens()
    yield
    xm.shutdown_pool()
    xm.clear_cache()
    xm.clear_tokens()


class TestConfig:
    @pytest.mark.parametrize("oauth,why", [
        ({"token_url": "https://x.example/token", "client_id_env": "abc", "client_secret_env": "X_SECRET"}, "NAME of an environment variable"),
        ({"token_url": "https://x.example/token", "client_id_env": "X_ID", "client_secret_env": "hunter2"}, "NAME of an environment variable"),
        ({"token_url": "http://x.example/token", "client_id_env": "X_ID", "client_secret_env": "X_SECRET"}, "must be https"),
        ({"token_url": "https://x.example/token", "client_id_env": "X_ID", "client_secret_env": "X_SECRET", "client_secret": "literal"}, "takes token_url"),
    ])
    def test_a_pasted_secret_or_an_insecure_endpoint_is_refused(self, tmp_path, monkeypatch, oauth, why):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"servers": {"docs": {"url": "https://x.example/mcp", "oauth": oauth}}}), encoding="utf-8")
        monkeypatch.setenv(xm.CONFIG_ENV, str(path))
        with pytest.raises(xm.ExternalMCPError, match=why):
            xm.load_servers()

    def test_oauth_needs_a_remote_url(self, tmp_path, monkeypatch):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"servers": {"docs": {"command": "python", "oauth": {"token_url": "https://x.example/t", "client_id_env": "X_ID", "client_secret_env": "X_SECRET"}}}}), encoding="utf-8")
        monkeypatch.setenv(xm.CONFIG_ENV, str(path))
        with pytest.raises(xm.ExternalMCPError, match="remote url"):
            xm.load_servers()


class TestOAuth:
    def test_the_token_is_fetched_used_and_reused(self, oauth_server, tmp_path, monkeypatch):
        port, log = oauth_server
        write_config(tmp_path, monkeypatch, port)

        async def go():
            first = await xm.call_external_tool("mcp__docs__whoami", {})
            second = await xm.call_external_tool("mcp__docs__whoami", {})
            return first, second
        first, second = run(go())
        assert first["data"] == {"client": "svc-reader"} and second["data"] == {"client": "svc-reader"}
        issued = [x for x in lines(log) if x.startswith("token-issued")]
        assert len(issued) == 1 and "scope=read" in issued[0]                       # one token for several sessions

    def test_without_a_token_the_server_says_401_so_the_header_really_is_what_lets_it_in(self, oauth_server, tmp_path, monkeypatch):
        port, log = oauth_server
        write_config(tmp_path, monkeypatch, port)
        spec = xm.load_servers()["docs"]
        spec.oauth = {}                                                              # as if the owner had forgotten the oauth block
        xm.clear_cache()

        async def go():
            return await xm.call_external_tool("mcp__docs__whoami", {})
        monkeypatch.setattr(xm, "load_servers", lambda path=None: {"docs": spec})
        out = run(go())
        assert "error" in out and "rejected" in lines(log)

    def test_a_wrong_secret_fails_plainly_and_nothing_is_cached(self, oauth_server, tmp_path, monkeypatch):
        port, log = oauth_server
        write_config(tmp_path, monkeypatch, port)
        monkeypatch.setenv("FAKE_CLIENT_SECRET", "not-the-secret")
        out = run(xm.call_external_tool("mcp__docs__whoami", {}))
        assert "error" in out and "token endpoint answered HTTP 401" in json.dumps(out) and "not-the-secret" not in json.dumps(out)
        assert xm._TOKENS == {} and "token-refused" in lines(log)

    def test_missing_variables_are_named_not_guessed(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port)
        monkeypatch.delenv("FAKE_CLIENT_SECRET")
        out = run(xm.call_external_tool("mcp__docs__whoami", {}))
        assert "FAKE_CLIENT_SECRET" in out["error"]

    def test_an_expired_token_is_fetched_again(self, oauth_server, tmp_path, monkeypatch):
        port, log = oauth_server
        write_config(tmp_path, monkeypatch, port)
        run(xm.call_external_tool("mcp__docs__whoami", {}))
        name, (_, token) = next(iter(xm._TOKENS.items()))
        xm._TOKENS[name] = (time.time() - 1, token)                                 # it ran out
        out = run(xm.call_external_tool("mcp__docs__whoami", {}))
        assert out["data"] == {"client": "svc-reader"} and len([x for x in lines(log) if x.startswith("token-issued")]) == 2

    def test_the_secret_never_appears_in_a_result_or_an_error(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port)
        assert "s3cret-value" not in json.dumps(run(xm.call_external_tool("mcp__docs__whoami", {})))


class TestResourcesAndPrompts:
    def test_resources_are_listed_and_read_as_text(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port, resources=True)

        async def go():
            listed = await xm.call_external_tool("mcp__docs__list_resources", {})
            plain = await xm.call_external_tool("mcp__docs__read_resource", {"uri": "docs://plain"})
            return listed, plain
        listed, plain = run(go())
        assert {r["uri"] for r in listed["data"]} == {"docs://handbook", "docs://plain"}
        assert "canary release is at 10:00" in plain["text"] and plain["uri"] == "docs://plain"

    def test_a_resource_that_tries_to_instruct_the_model_is_flagged(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port, resources=True)
        out = run(xm.call_external_tool("mcp__docs__read_resource", {"uri": "docs://handbook"}))
        assert "deploys happen on Thursdays" in out["text"] and "_cord_warning" in out

    def test_a_prompt_template_comes_back_as_text_to_read(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port, prompts=True)

        async def go():
            return await xm.call_external_tool("mcp__docs__list_prompts", {}), await xm.call_external_tool("mcp__docs__get_prompt", {"name": "summarise", "arguments": {"topic": "the outage"}})
        listed, got = run(go())
        assert [p["name"] for p in listed["data"]] == ["summarise"]
        assert "Summarise the outage in three bullet points" in got["text"] and "not an instruction" in got["note"]

    def test_a_server_that_did_not_ask_for_resources_gets_no_such_tools(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port)
        servers = xm.load_servers()
        tools, _ = run(xm.list_server_tools(servers["docs"]))
        assert "list_resources" not in {t["name"] for t in tools}
        out = run(xm.call_external_tool("mcp__docs__read_resource", {"uri": "docs://plain"}))
        assert "error" in out

    def test_they_never_wait_for_a_signature_but_are_not_taint_exempt(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port, resources=True, prompts=True)
        for name in ("list_resources", "read_resource", "list_prompts", "get_prompt"):
            assert xm.needs_approval(f"mcp__docs__{name}") is False and xm.taint_exempt(f"mcp__docs__{name}") is False
        assert xm.needs_approval("mcp__docs__some_other_tool") is True

    def test_they_appear_in_the_menu_without_the_signature_warning(self, oauth_server, tmp_path, monkeypatch):
        port, _ = oauth_server
        write_config(tmp_path, monkeypatch, port, resources=True, prompts=True)

        class Base:
            async def list_tools(self):
                return []
        listed = run(xm.ExternalToolHub(Base()).list_tools())
        by_name = {t.name: t.description for t in listed}
        assert "mcp__docs__read_resource" in by_name and "Waits for a human signature" not in by_name["mcp__docs__read_resource"]
        assert "mcp__docs__whoami" in by_name
