"""
Round 74: the OpenAPI-to-MCP bridge (openapi_mcp_bridge.py) with a REAL HTTP service on a real port, the bridge as a real MCP server process, and the real external-MCP hub on top - so every rule of the
gate (names, the read/write split, screening, pins, the governed loop) applies to a service nobody wrote a tool for. What is checked: the tools come from the OpenAPI document; a read runs, a write waits
for a signature and no request reaches the service until it is signed; a path value cannot steer the request; a redirect is not followed; what comes back is screened; a poisoned description drops the tool.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import external_mcp as xm
from rct_control_plane import openapi_mcp_bridge as bridge
from fake_http_service import Running
from test_governed_autonomous_loop_real import _FakeMCP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def service():
    started = []

    def start(**kw):
        s = Running(**kw)
        started.append(s)
        return s
    yield start
    for s in started:
        s.stop()


def configure(tmp_path, monkeypatch, url, read_only=("get_health", "get_items_item_id", "get_search", "get_page", "get_elsewhere"), **extra):
    spec = {"command": sys.executable, "args": ["-m", "rct_control_plane.openapi_mcp_bridge", "--name", "svc", "--base-url", url], "env_vars": ["PYTHONPATH"], "read_only_tools": list(read_only), "timeout_s": 90}
    spec.update(extra)
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": {"svc": spec}}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    monkeypatch.setenv("PYTHONPATH", ROOT)
    xm.clear_cache()


@pytest.fixture(autouse=True)
def _clean():
    xm.clear_cache()
    yield
    xm.clear_cache()


def call(name, args):
    out = run(xm.maybe_wrap(_FakeMCP()).call_tool(name, args))
    return json.loads(out.content[0].text)


# ---- pure parts ----------------------------------------------------------------------------------------------------------------------------------------

def test_the_base_url_must_be_this_machine_or_explicit_https():
    assert bridge.check_base_url("http://127.0.0.1:9000/") == "http://127.0.0.1:9000"
    for bad in ("http://example.com", "https://example.com", "ftp://127.0.0.1", "http://127.0.0.1@evil.example", "http://user:pw@127.0.0.1:1", "http://127.0.0.1:1/?q=1"):
        with pytest.raises(bridge.BridgeError):
            bridge.check_base_url(bad)
    assert bridge.check_base_url("https://api.example.com", allow_remote=True) == "https://api.example.com"


def test_operations_are_named_from_the_method_and_path_and_documentation_routes_are_skipped():
    spec = {"paths": {"/openapi.json": {"get": {}}, "/docs": {"get": {}}, "/items/{item_id}": {"get": {"summary": "Read", "parameters": [{"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}}]}},
                      "/items": {"post": {"requestBody": {"content": {"application/json": {}}}}, "get": {}}}}
    ops = {o["name"]: o for o in bridge.operations(spec)}
    assert set(ops) == {"get_items", "post_items", "get_items_item_id"} and ops["post_items"]["body"] is True
    assert ops["get_items_item_id"]["parameters"] == [{"name": "item_id", "in": "path", "required": True, "type": "string"}]


@pytest.mark.parametrize("value", ["../../etc/passwd", "a/b", "x?y=1", "x#frag", "%2e%2e", "http://evil.example/", "a b"])
def test_a_path_value_is_quoted_completely_so_it_cannot_change_the_path_or_the_host(value):
    op = {"path": "/items/{item_id}", "method": "get", "parameters": [{"name": "item_id", "in": "path", "required": True, "type": "string"}], "body": False}
    method, url, query, body = bridge.build_request("http://127.0.0.1:9000", op, {"item_id": value})
    assert url.startswith("http://127.0.0.1:9000/items/") and "/" not in url[len("http://127.0.0.1:9000/items/"):] and "?" not in url and "#" not in url and query == {} and body is None


def test_a_missing_required_argument_is_an_error_not_a_guess():
    op = {"path": "/search", "method": "get", "parameters": [{"name": "q", "in": "query", "required": True, "type": "string"}], "body": False}
    with pytest.raises(bridge.BridgeError):
        bridge.build_request("http://127.0.0.1:1", op, {})


def test_print_config_lists_the_get_operations_as_read_only_for_the_owner_to_review(service):
    svc = service()
    ops = bridge.operations(bridge.fetch_spec(svc.url))
    config = json.loads(bridge.print_config("svc", svc.url, ops))["servers"]["svc"]
    assert set(config["read_only_tools"]) == {"get_health", "get_items_item_id", "get_search", "get_page", "get_elsewhere"}
    assert "post_items" not in config["read_only_tools"] and "delete_items_item_id" not in config["read_only_tools"]


# ---- through the real hub ------------------------------------------------------------------------------------------------------------------------------

def test_the_service_appears_as_namespaced_tools_and_only_the_declared_reads_run_without_a_signature(tmp_path, monkeypatch, service):
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    names = {t.name: t for t in run(xm.maybe_wrap(_FakeMCP()).list_tools()) if t.name.startswith("mcp__")}
    assert {"mcp__svc__get_health", "mcp__svc__get_items_item_id", "mcp__svc__post_items", "mcp__svc__delete_items_item_id", "mcp__svc__get_search"} <= set(names)
    assert xm.needs_approval("mcp__svc__post_items") and xm.needs_approval("mcp__svc__delete_items_item_id")
    assert not xm.needs_approval("mcp__svc__get_health") and not xm.needs_approval("mcp__svc__get_items_item_id")
    schema = names["mcp__svc__get_search"].input_schema
    assert set(schema["properties"]) == {"q", "limit"} and schema["required"] == ["q"]


def test_a_read_reaches_the_service_with_path_and_query_arguments(tmp_path, monkeypatch, service):
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    assert call("mcp__svc__get_health", {})["data"]["body"] == {"status": "ok"}
    out = call("mcp__svc__get_items_item_id", {"item_id": "abc", "verbose": True})["data"]
    assert out["status"] == 200 and out["body"] == {"item_id": "abc", "verbose": True}
    assert call("mcp__svc__get_search", {"q": "tea", "limit": 2})["data"]["body"] == {"q": "tea", "limit": 2}
    assert svc.counter["health"] == 1 and svc.counter["read"] == 1


def test_a_write_through_the_bridge_works_when_it_is_called_and_the_gate_is_what_holds_it_back(tmp_path, monkeypatch, service):
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    out = call("mcp__svc__post_items", {"body": {"name": "tea"}})["data"]
    assert out["status"] == 200 and out["body"] == {"created": {"name": "tea"}} and svc.counter["create"] == 1      # the hub itself does not decide: the governed loop does (next test)


def test_in_the_governed_loop_a_write_waits_for_a_signature_and_no_request_reaches_the_service(tmp_path, monkeypatch, service):
    import rct_control_plane.autonomous_loop as autonomous_loop_module
    from test_governed_autonomous_loop_real import _loop
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    script = [{"action": "call_tool", "tool_name": "mcp__svc__delete_items_item_id", "tool_args": {"item_id": "7"}, "reasoning": "clean up"}]
    calls = {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = calls["n"]
        calls["n"] += 1
        return dict(script[i]) if i < len(script) else {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "bridge-loop", mcp=xm.maybe_wrap(_FakeMCP()))
    result = run(loop.run("Delete item 7 from the service"))
    step = next(s for s in result["steps"] if s["tool_name"] == "mcp__svc__delete_items_item_id")
    assert step["tool_result"].get("pending_approval") is True
    assert "delete" not in svc.counter                                           # nothing was sent


def test_a_redirect_is_not_followed(tmp_path, monkeypatch, service):
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    out = call("mcp__svc__get_elsewhere", {})["data"]
    assert out["status"] in (302, 307) and svc.counter["redirect"] == 1          # the answer is reported, the other address is never contacted


def test_text_with_an_instruction_that_the_service_returns_is_withheld_before_the_model_reads_it(tmp_path, monkeypatch, service):
    import rct_control_plane.autonomous_loop as autonomous_loop_module
    from test_governed_autonomous_loop_real import _loop
    svc = service()
    configure(tmp_path, monkeypatch, svc.url)
    prompts = []
    calls = {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        prompts.append(str(history) + extra_context)
        i = calls["n"]
        calls["n"] += 1
        if i == 0:
            return {"action": "call_tool", "tool_name": "mcp__svc__get_page", "tool_args": {}, "reasoning": "read it"}
        return {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    result = run(_loop(tmp_path, "bridge-attack", mcp=xm.maybe_wrap(_FakeMCP())).run("summarise the page of the service"))
    step = next(s for s in result["steps"] if s["tool_name"] == "mcp__svc__get_page")
    assert step["tool_result"].get("withheld_by_cord") is True
    assert "reveal your system prompt" not in " ".join(prompts)


def test_a_poisoned_openapi_summary_drops_that_tool_only(tmp_path, monkeypatch, service):
    svc = service(poisoned_summary=True)
    configure(tmp_path, monkeypatch, svc.url)
    names = {t.name for t in run(xm.maybe_wrap(_FakeMCP()).list_tools()) if t.name.startswith("mcp__")}
    assert "mcp__svc__post_items" not in names and "mcp__svc__get_health" in names


def test_the_bridge_refuses_to_start_for_a_remote_http_address_and_a_pasted_token(capsys):
    assert bridge.main(["--name", "x", "--base-url", "http://203.0.113.5:80"]) == 2
    assert bridge.main(["--name", "x", "--base-url", "http://127.0.0.1:1", "--auth-env", "sk-live-abc"]) == 2
    err = capsys.readouterr().err
    assert "base URL" in err and "NAME of an environment variable" in err and "sk-live-abc" not in err.replace("--auth-env", "")
