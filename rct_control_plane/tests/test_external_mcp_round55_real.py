"""
Round 55: tools from other MCP servers go through the same gate as the built-in ones.

The server under test (tests/fake_mcp_server.py) is a real MCP server in its own OS process speaking the real protocol over
stdio; the client is the real MCP SDK. What is checked: names, the read/write split, screening of what comes back and of tool
descriptions, the pin, credential inheritance, timeouts, a broken config, and the governed loop's behaviour end to end.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import external_mcp as xm
from rct_control_plane.governed_autonomous_loop import is_external_content, is_risky_tool, needs_signature_always
from test_governed_autonomous_loop_real import _FakeMCP, _loop

SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


def run(coro):
    return asyncio.run(coro)


def write_config(tmp_path, monkeypatch, servers):
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": servers}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    xm.clear_cache()
    return path


def notes_server(**extra):
    spec = {"command": "python", "args": [SERVER], "read_only_tools": ["read_note", "fetch_page", "show_env"], "timeout_s": 60}
    spec.update(extra)
    return spec


@pytest.fixture(autouse=True)
def _clean_cache():
    xm.clear_cache()
    yield
    xm.clear_cache()


# ------------------------------------------------------------------ configuration

@pytest.mark.parametrize("bad,why", [
    ({"command": "python", "args": [], "env": {"TOKEN": "abc"}}, "unknown field"),                  # a field that invites a pasted secret
    ({"command": "python", "token": "abc"}, "unknown field"),
    ({"command": "python", "url": "https://x.example/mcp"}, "exactly one"),
    ({}, "exactly one"),
    ({"url": "http://remote.example/mcp"}, "https"),
    ({"command": "python", "env_vars": ["not a name"]}, "NAMES"),
    ({"command": "python", "env_vars": ["sk-live-abc123"]}, "NAMES"),
    ({"url": "https://x.example/mcp", "headers_env": {"Authorization": "Bearer abc"}}, "NAME"),
    ({"command": "python", "tools_sha256": "xyz"}, "64-character"),
    ({"command": "python", "read_only_tools": "read_note"}, "list"),
])
def test_a_configuration_that_invites_a_pasted_secret_or_is_unsafe_is_refused(tmp_path, monkeypatch, bad, why):
    write_config(tmp_path, monkeypatch, {"notes": bad})
    with pytest.raises(xm.ExternalMCPError) as caught:
        xm.load_servers()
    assert why in str(caught.value)
    servers, error = xm.enabled_servers()
    assert servers == {} and error                       # fail closed: nothing from a half-valid file is exposed


@pytest.mark.parametrize("name", ["Notes", "no_underscore", "", "a" * 25, "-lead"])
def test_server_names_cannot_collide_with_the_separator(tmp_path, monkeypatch, name):
    write_config(tmp_path, monkeypatch, {name: {"command": "python"}})
    with pytest.raises(xm.ExternalMCPError):
        xm.load_servers()


def test_loopback_http_is_allowed_remote_http_is_not(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"local": {"url": "http://127.0.0.1:9000/mcp"}, "remote": {"url": "https://mcp.example.com/mcp"}})
    assert set(xm.load_servers()) == {"local", "remote"}


def test_no_file_means_no_servers_and_the_hub_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv(xm.CONFIG_ENV, str(tmp_path / "absent.json"))
    base = _FakeMCP()
    assert xm.maybe_wrap(base) is base


def test_names_are_namespaced_and_split_back():
    assert xm.qualified("notes", "read_note") == "mcp__notes__read_note"
    assert xm.split("mcp__notes__read_note") == ("notes", "read_note")
    assert xm.split("mcp__notes__a__b") == ("notes", "a__b")
    assert xm.split("delentia_recall") is None and xm.split("mcp__only") is None


# ------------------------------------------------------------------ listing and calling (a real server process)

def test_the_menu_has_the_built_in_tools_first_and_external_tools_namespaced_and_marked(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    hub = xm.maybe_wrap(_FakeMCP())
    names = [t.name for t in run(hub.list_tools())]
    assert names[0] == "delentia_recall" or not names[0].startswith("mcp__")
    external = {t.name: t for t in run(hub.list_tools()) if t.name.startswith("mcp__")}
    assert {"mcp__notes__read_note", "mcp__notes__write_note", "mcp__notes__fetch_page"} <= set(external)
    assert "third-party" in external["mcp__notes__read_note"].description
    assert "Waits for a human signature" in external["mcp__notes__write_note"].description
    assert "Waits for a human signature" not in external["mcp__notes__read_note"].description


def test_only_what_the_owner_declared_read_only_runs_without_a_signature(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    assert xm.needs_approval("mcp__notes__write_note") is True      # not declared
    assert xm.needs_approval("mcp__notes__read_note") is False      # declared by the owner
    assert xm.needs_approval("mcp__ghost__anything") is True        # a server that is not configured at all
    assert xm.needs_approval("delentia_recall") is False            # not an external tool
    assert needs_signature_always("mcp__notes__write_note") and not needs_signature_always("mcp__notes__read_note")
    assert is_risky_tool("mcp__notes__read_note") and is_external_content("mcp__notes__read_note")
    assert not is_external_content("delentia_read_repo_file")


def test_a_call_goes_to_the_real_server_and_comes_back_as_json(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    hub = xm.maybe_wrap(_FakeMCP())
    out = json.loads(run(hub.call_tool("mcp__notes__read_note", {"title": "x"})).content[0].text)
    assert out["external_mcp"] == {"server": "notes", "tool": "read_note"} and out["is_error"] is False
    assert out["data"] == {"title": "x", "text": ""}


def test_built_in_tools_still_reach_the_base_server(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    base = _FakeMCP()
    hub = xm.maybe_wrap(base)
    run(hub.call_tool("delentia_recall", {"query": "x"}))
    assert base.dispatched and base.dispatched[0][0] == "delentia_recall"


def test_a_tool_that_fails_reports_an_error_not_an_exception(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    out = json.loads(run(xm.maybe_wrap(_FakeMCP()).call_tool("mcp__notes__broken", {})).content[0].text)
    assert out["is_error"] is True


def test_a_slow_server_costs_one_timeout_not_the_episode(tmp_path, monkeypatch):
    path = write_config(tmp_path, monkeypatch, {"notes": notes_server(timeout_s=60)})
    run(xm.maybe_wrap(_FakeMCP()).list_tools())                      # listed (and cached) with the generous timeout
    path.write_text(json.dumps({"servers": {"notes": notes_server(timeout_s=2)}}), encoding="utf-8")
    out = run(xm.call_external_tool("mcp__notes__slow", {"seconds": 20}))
    assert "did not answer within 2s" in out["error"]


def test_a_tool_that_was_never_listed_cannot_be_reached_by_name(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    out = run(xm.call_external_tool("mcp__notes__not_a_tool", {}))
    assert "not an available tool" in out["error"]
    assert "unknown external tool" in run(xm.call_external_tool("mcp__ghost__x", {}))["error"]


def test_a_dead_server_gives_no_tools_and_a_reason_and_the_menu_still_works(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"dead": {"command": "python", "args": ["-c", "import sys; sys.exit(3)"], "timeout_s": 20}})
    tools = run(xm.maybe_wrap(_FakeMCP()).list_tools())
    assert all(not t.name.startswith("mcp__") for t in tools)
    assert "dead" in xm.LAST_ERRORS and xm.LAST_ERRORS["dead"]


# ------------------------------------------------------------------ credentials, descriptions, pin

def test_a_local_server_does_not_inherit_credentials_only_the_ones_named(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_SECRET_TOKEN", "super-secret-value")
    monkeypatch.setenv("OTHER_SECRET_TOKEN", "another-secret")
    write_config(tmp_path, monkeypatch, {"notes": notes_server(), "named": notes_server(env_vars=["NOTES_SECRET_TOKEN"])})
    hub = xm.maybe_wrap(_FakeMCP())
    seen = lambda tool, var: json.loads(run(hub.call_tool(tool, {"name": var})).content[0].text)["data"]["visible"]
    assert seen("mcp__notes__show_env", "NOTES_SECRET_TOKEN") is False
    assert seen("mcp__named__show_env", "NOTES_SECRET_TOKEN") is True
    assert seen("mcp__named__show_env", "OTHER_SECRET_TOKEN") is False       # only what was named


def test_a_poisoned_tool_description_is_dropped_and_reported_never_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_POISON", "1")
    write_config(tmp_path, monkeypatch, {"notes": notes_server(env_vars=["FAKE_POISON"])})
    tools = run(xm.maybe_wrap(_FakeMCP()).list_tools())
    names = [t.name for t in tools]
    assert "mcp__notes__read_note" in names and "mcp__notes__helper" not in names
    assert "dropped" in xm.LAST_ERRORS["notes"] and "helper" in xm.LAST_ERRORS["notes"]
    assert not any("attacker@example.com" in (t.description or "") for t in tools)
    assert "not an available tool" in run(xm.call_external_tool("mcp__notes__helper", {}))["error"]


def test_a_pinned_tool_list_that_no_longer_matches_is_hidden_until_the_owner_looks(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    seen = xm.inspect_server("notes")
    assert seen["digest"] and {t["name"] for t in seen["tools"]} >= {"read_note", "write_note"}
    write_config(tmp_path, monkeypatch, {"notes": notes_server(tools_sha256=seen["digest"])})
    assert any(t.name == "mcp__notes__read_note" for t in run(xm.maybe_wrap(_FakeMCP()).list_tools()))
    write_config(tmp_path, monkeypatch, {"notes": notes_server(tools_sha256="0" * 64)})
    tools = run(xm.maybe_wrap(_FakeMCP()).list_tools())
    assert not any(t.name.startswith("mcp__") for t in tools) and "changed since they were pinned" in xm.LAST_ERRORS["notes"]


def test_inspect_shows_what_is_there_even_when_a_pin_would_hide_it(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server(tools_sha256="f" * 64)})
    seen = xm.inspect_server("notes")
    assert seen["tools"] and seen["pinned"] is True and seen["pin_matches"] is False


# ------------------------------------------------------------------ a remote server over streamable HTTP (loopback)

@pytest.fixture
def http_server():
    import socket
    import subprocess
    import time
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen([sys.executable, SERVER], env=dict(os.environ, FAKE_HTTP_PORT=str(port)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        yield port
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_a_remote_streamable_http_server_lists_and_answers_through_the_same_path(tmp_path, monkeypatch, http_server):
    """Found by trying it: the MCP SDK wants its own HTTP client package (httpx2); a plain httpx client was refused."""
    write_config(tmp_path, monkeypatch, {"remote": {"url": f"http://127.0.0.1:{http_server}/mcp", "read_only_tools": ["read_note"], "timeout_s": 60}})
    hub = xm.maybe_wrap(_FakeMCP())
    names = [t.name for t in run(hub.list_tools())]
    assert "mcp__remote__read_note" in names and "mcp__remote__write_note" in names
    out = json.loads(run(hub.call_tool("mcp__remote__read_note", {"title": "x"})).content[0].text)
    assert out["data"] == {"title": "x", "text": ""} and out["is_error"] is False
    assert xm.needs_approval("mcp__remote__write_note") and not xm.needs_approval("mcp__remote__read_note")


# ------------------------------------------------------------------ sovereignty for a remote server

def test_a_policy_that_forbids_cross_border_stops_arguments_before_a_remote_server_is_contacted(tmp_path, monkeypatch):
    from core.regional_adapter.sovereignty import SovereigntyPolicy
    from rct_control_plane import residency
    policy_file = tmp_path / "sov.json"
    monkeypatch.setenv(residency.POLICY_ENV, str(policy_file)) if hasattr(residency, "POLICY_ENV") else None
    monkeypatch.setattr(residency, "load_policy", lambda: SovereigntyPolicy(home_region="TH", allow_cross_border=False))
    write_config(tmp_path, monkeypatch, {"remote": {"url": "https://mcp.example.invalid/mcp", "timeout_s": 5}})
    out = run(xm.call_external_tool("mcp__remote__anything", {"q": "private customer text"}))
    assert out["refused_by"] == "sovereignty_policy"


# ------------------------------------------------------------------ the governed loop, end to end

def _scripted(monkeypatch, tool, args, answer="done"):
    prompts, calls = [], {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        prompts.append(autonomous_loop_module.render_history(history))
        calls["n"] += 1
        if calls["n"] == 1:
            return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": "use it"}
        return {"action": "finish", "reasoning": "done", "final_answer": answer, "tool_name": None, "tool_args": {}}

    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    return prompts


def test_third_party_text_with_an_instruction_is_withheld_before_the_model_reads_it(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    prompts = _scripted(monkeypatch, "mcp__notes__fetch_page", {"which": "attack"})
    loop = _loop(tmp_path, "ext_attack")
    result = run(loop.run("summarise the page"))
    seen = " ".join(prompts)
    assert "reveal your system prompt" not in seen and "withheld" in seen.lower()
    step = [s for s in result["steps"] if s["tool_name"] == "mcp__notes__fetch_page"][0]
    assert step["tool_result"].get("withheld_by_cord") is True


def test_ordinary_third_party_text_reaches_the_model(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    prompts = _scripted(monkeypatch, "mcp__notes__fetch_page", {"which": "plain"})
    loop = _loop(tmp_path, "ext_plain")
    run(loop.run("summarise the page"))
    assert any("quarterly numbers were stable" in p for p in prompts)


def test_a_write_tool_waits_for_a_signature_and_nothing_is_written(tmp_path, monkeypatch):
    notes_file = tmp_path / "written.txt"
    monkeypatch.setenv("FAKE_NOTES_FILE", str(notes_file))
    write_config(tmp_path, monkeypatch, {"notes": notes_server(env_vars=["FAKE_NOTES_FILE"])})
    _scripted(monkeypatch, "mcp__notes__write_note", {"title": "t", "text": "hello"})
    loop = _loop(tmp_path, "ext_write")
    result = run(loop.run("save a note called t"))
    assert result["stopped_reason"] == "pending_approval"
    assert not notes_file.exists()                                   # the server never received the call


def test_a_declared_read_only_tool_runs_in_the_loop_and_is_audited(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    _scripted(monkeypatch, "mcp__notes__read_note", {"title": "plan"})
    loop = _loop(tmp_path, "ext_read")
    result = run(loop.run("read my note called plan"))
    assert result["stopped_reason"] == "llm_finished"
    with loop._persistence._connect() as conn:
        gate = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'")]
    assert any(g["tool_name"] == "mcp__notes__read_note" for g in gate)   # an external tool is judged by the FDIA gate


def test_a_broken_config_leaves_the_built_in_tools_working(tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    xm.clear_cache()
    _scripted(monkeypatch, "delentia_recall", {"query": "x"})
    loop = _loop(tmp_path, "ext_broken")
    result = run(loop.run("recall something"))
    assert result["stopped_reason"] == "llm_finished"
    assert "_config" in xm.LAST_ERRORS or xm.enabled_servers()[1]


def test_the_owner_policy_can_forbid_an_external_tool_by_name(tmp_path, monkeypatch):
    from rct_control_plane import fdia_policy
    write_config(tmp_path, monkeypatch, {"notes": notes_server()})
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps({"rules": [{"rule_id": "R-NOTES", "intent_patterns": ["mcp__notes__*"],
                                                  "action_type": "REQUIRE_HUMAN_SIGNATURE", "human_approver_role": ["Security_Admin"]}]}),
                           encoding="utf-8")
    monkeypatch.setenv(fdia_policy.POLICY_ENV, str(policy_path))
    _scripted(monkeypatch, "mcp__notes__read_note", {"title": "plan"})
    loop = _loop(tmp_path, "ext_policy")
    real = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real(goal, clarity, compile_result)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    result = run(loop.run("read my note called plan"))
    assert result["stopped_reason"] == "pending_approval"
