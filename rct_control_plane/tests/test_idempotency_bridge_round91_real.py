"""
Round 91: the idempotency key reaches a real service through the real external-MCP hub and the real OpenAPI bridge process: as MCP request meta to a tool that can change something, as the
HTTP header `Idempotency-Key` on POST/PUT/PATCH/DELETE, and never on a read.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import external_mcp as xm, idempotency, openapi_mcp_bridge as bridge
from fake_http_service import Running
from test_governed_autonomous_loop_real import _FakeMCP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KEY = idempotency.key_for("episode-root", "mcp__svc__post_items", idempotency.args_sha({"body": {"name": "tea"}}), 0)


@pytest.fixture
def svc(tmp_path, monkeypatch):
    s = Running()
    spec = {"command": sys.executable, "args": ["-m", "rct_control_plane.openapi_mcp_bridge", "--name", "svc", "--base-url", s.url], "env_vars": ["PYTHONPATH"],
            "read_only_tools": ["get_health", "get_items_item_id", "get_search"], "timeout_s": 90}
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": {"svc": spec}}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    monkeypatch.setenv("PYTHONPATH", ROOT)
    xm.clear_cache()
    yield s
    xm.clear_cache()
    idempotency.current_key.set(None)
    s.stop()


def call(name, args):
    out = asyncio.run(xm.maybe_wrap(_FakeMCP()).call_tool(name, args))
    return json.loads(out.content[0].text)


def test_a_write_carries_the_key_as_a_header(svc):
    idempotency.current_key.set(KEY)
    assert call("mcp__svc__post_items", {"body": {"name": "tea"}})["data"]["status"] == 200
    assert svc.counter["create_idem"] == [KEY]
    assert call("mcp__svc__delete_items_item_id", {"item_id": "7"})["data"]["status"] == 200
    assert svc.counter["delete_idem"] == [KEY]


def test_a_read_never_carries_a_key_even_when_one_is_set(svc):
    idempotency.current_key.set(KEY)
    assert call("mcp__svc__get_items_item_id", {"item_id": "abc"})["data"]["status"] == 200
    assert svc.counter["read_idem"] == [None]


def test_without_a_key_nothing_is_sent(svc):
    idempotency.current_key.set(None)
    call("mcp__svc__post_items", {"body": {"name": "tea"}})
    assert svc.counter["create_idem"] == [None]


def test_the_tools_input_schema_does_not_show_the_hidden_context_parameter(svc):
    tools = {t.name: t for t in asyncio.run(xm.maybe_wrap(_FakeMCP()).list_tools()) if t.name.startswith("mcp__svc__")}
    assert "mcp_ctx" not in json.dumps(tools["mcp__svc__post_items"].input_schema) and set(tools["mcp__svc__get_search"].input_schema["properties"]) == {"q", "limit"}


@pytest.mark.parametrize("value", ["", "not-a-key", "dl-" + "G" * 32, "dl-abc", "dl-" + "0" * 200, 12345, None, {"a": 1}])
def test_a_malformed_key_in_the_meta_is_ignored_not_forwarded(value):
    class Ctx:
        class request_context:                                                              # noqa: N801
            meta = {idempotency.META_KEY: value}
    assert bridge.idempotency_key_from(Ctx) is None


def test_a_well_formed_key_is_forwarded():
    class Ctx:
        class request_context:                                                              # noqa: N801
            meta = {idempotency.META_KEY: KEY}
    assert bridge.idempotency_key_from(Ctx) == KEY
    assert bridge.idempotency_key_from(None) is None
