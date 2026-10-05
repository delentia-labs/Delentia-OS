"""
Round 62: delentia_browser_act - click and type on one page, with the whole step list under ONE signature.

Governance is tested in a real governed episode (the approval carries the exact address and steps); the behaviour is tested with a REAL headless Chrome/Edge against real HTTP servers on loopback,
one of which stands in for "somewhere else" and must never see a request. Where no browser can be started the browser tests are skipped, not weakened.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import browser_tool
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.governed_autonomous_loop import (EXTERNAL_CONTENT_TOOLS, OWNER_ONLY_TOOLS, PERSON_NEUTRAL_TOOLS, RISKY_TOOLS, TAINT_EGRESS_TOOLS, TAINT_SOURCE_TOOLS,
                                                        needs_signature_always)
from test_taint_gate_round58_real import episode

NAME = "delentia_browser_act"


def run(coro):
    return asyncio.run(coro)


class TestValidation:
    def test_good_steps_are_cleaned(self):
        steps = browser_tool.validate_steps([{"action": "type", "selector": "#name", "text": "Ann"}, {"action": "click", "text": "Say hello"}, {"action": "press", "key": "Enter"},
                                              {"action": "scroll", "pixels": 99999}, {"action": "wait", "seconds": 99}])
        assert steps[0] == {"action": "type", "selector": "#name", "text": "Ann"} and steps[1] == {"action": "click", "text": "Say hello"}
        assert steps[3]["pixels"] == 5000 and steps[4]["seconds"] == 3.0

    @pytest.mark.parametrize("bad,why", [
        ([], "non-empty"), ("click", "non-empty"), ([{"action": "click", "text": "x"}] * 9, "at most 8"), ([{"action": "hover"}], "action must be"),
        ([{"action": "click"}], "exactly one of selector"), ([{"action": "click", "selector": "#a", "text": "b"}], "exactly one of selector"),
        ([{"action": "type", "text": "x"}], "needs a selector"), ([{"action": "type", "selector": "#a", "text": "x" * 501}], "at most 500"),
        ([{"action": "press", "key": "F12"}], "key must be"), ([{"action": "click", "selector": "x" * 201}], "too long"), (["click"], "must be an object"),
    ])
    def test_bad_steps_are_refused_before_anything_runs(self, bad, why):
        with pytest.raises(ValueError, match=why):
            browser_tool.validate_steps(bad)

    @pytest.mark.parametrize("label", ["Buy now", "Place order", "Checkout", "Pay", "Confirm payment", "Delete my account", "Donate", "ชำระเงิน", "สั่งซื้อ", "ลบบัญชี"])
    def test_a_payment_purchase_or_deletion_control_is_never_clicked(self, label):
        with pytest.raises(ValueError, match="payment, purchase or account-deletion"):
            browser_tool.validate_steps([{"action": "click", "text": label}])

    @pytest.mark.parametrize("label", ["Say hello", "Sign up", "Next page", "Paypal-free zone", "Pager", "Repay later notes"])
    def test_ordinary_labels_pass(self, label):
        assert browser_tool.validate_steps([{"action": "click", "text": label}])


class TestGovernance:
    def test_the_tool_is_classified_everywhere(self):
        assert NAME in RISKY_TOOLS and NAME in EXTERNAL_CONTENT_TOOLS and NAME in TAINT_SOURCE_TOOLS and NAME in TAINT_EGRESS_TOOLS and NAME in PERSON_NEUTRAL_TOOLS
        assert needs_signature_always(NAME) and NAME not in OWNER_ONLY_TOOLS

    def test_it_is_a_registered_mcp_tool(self):
        from rct_control_plane.mcp_server import mcp
        assert NAME in {t.name for t in run(mcp.list_tools())}

    def test_a_governed_episode_stops_for_a_signature_that_names_the_address_and_every_step(self, tmp_path, monkeypatch):
        steps = [{"action": "type", "selector": "#name", "text": "Ann"}, {"action": "click", "text": "Say hello"}]
        result, mcp, persistence, _ = episode(tmp_path, monkeypatch, [(NAME, {"url": "https://example.org/form", "steps": steps})])
        assert result["stopped_reason"] == "pending_approval" and mcp.dispatched == []
        (pending,) = PendingActionStore(persistence).list("PENDING")
        assert pending.tool_name == NAME and pending.tool_args["url"] == "https://example.org/form" and pending.tool_args["steps"] == steps

    def test_changing_a_step_changes_what_is_signed(self, tmp_path, monkeypatch):
        a = episode(tmp_path / "a", monkeypatch, [(NAME, {"url": "https://example.org/form", "steps": [{"action": "click", "text": "Next"}]})])
        b = episode(tmp_path / "b", monkeypatch, [(NAME, {"url": "https://example.org/form", "steps": [{"action": "click", "text": "Back"}]})])
        da = PendingActionStore(a[2]).list("PENDING")[0].action_sha256
        db = PendingActionStore(b[2]).list("PENDING")[0].action_sha256
        assert da != db

    def test_refusals_happen_before_the_browser_and_a_private_address_is_refused(self, monkeypatch):
        from rct_control_plane import mcp_server
        monkeypatch.delenv("DELENTIA_CRAWL_ALLOW_PRIVATE", raising=False)
        monkeypatch.setattr(browser_tool, "find_browser", lambda: pytest.fail("no browser may start"))
        assert run(mcp_server.delentia_browser_act("https://example.org/", [{"action": "click", "text": "Buy now"}]))["refused_by"] == "browser_act"
        assert run(mcp_server.delentia_browser_act("http://127.0.0.1:8000/", [{"action": "click", "text": "Next"}]))["refused_by"] == "url_safety"


class Other(BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):                                        # noqa: N802
        Other.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def make_site(other_port):
    class Site(BaseHTTPRequestHandler):
        def do_GET(self):                                    # noqa: N802
            if self.path.startswith("/about"):
                body = "<html><head><title>About</title></head><body><h1>About page</h1><p>We make small tools.</p></body></html>"
            elif self.path.startswith("/submitted"):
                body = "<html><body><h1>Form submitted</h1></body></html>"
            else:
                body = f"""<html><head><title>Form</title></head><body>
<h1>Say hello</h1>
<form id="f" action="/submitted" method="get"><input id="name" name="name" placeholder="your name"><input id="pw" type="password" name="pw">
<button type="button" id="hello" onclick="document.getElementById('out').textContent = 'Hello, ' + document.getElementById('name').value + '!'">Greet me</button>
<input id="go" type="submit" value="Send form"></form>
<div id="out"></div><a href="/about">About us</a> <a href="http://127.0.0.1:{other_port}/elsewhere">Elsewhere</a>
<button id="buy" onclick="document.getElementById('out').textContent='BOUGHT'">Buy now</button>
</body></html>"""
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    return Site


@pytest.fixture
def servers(monkeypatch, tmp_path):
    if not browser_tool.status()["available"]:
        pytest.skip("no Chrome/Chromium/Edge (or no websockets) on this machine")
    monkeypatch.setenv("DELENTIA_CRAWL_ALLOW_PRIVATE", "1")
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    Other.hits = []
    other = HTTPServer(("127.0.0.1", 0), Other)
    site = HTTPServer(("127.0.0.1", 0), make_site(other.server_port))
    for s in (other, site):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield site.server_port
    for s in (other, site):
        s.shutdown()


def act(port, steps, **kw):
    from rct_control_plane import mcp_server
    result = run(mcp_server.delentia_browser_act(f"http://127.0.0.1:{port}/", steps, **kw))
    if "did not start" in str(result.get("error", "")):
        pytest.skip(result["error"])
    return result


class TestRealBrowser:
    def test_type_then_click_changes_the_page_and_the_report_does_not_echo_the_typed_text(self, servers):
        r = act(servers, [{"action": "type", "selector": "#name", "text": "Ann Example"}, {"action": "click", "text": "Greet me"}])
        assert "error" not in r, r
        assert "Hello, Ann Example!" in r["text"] and r["steps_done"] == 2 and r["steps_asked"] == 2
        assert [s["action"] for s in r["steps"]] == ["type", "click"] and r["steps"][0]["chars_typed"] == 11 and "Ann Example" not in json.dumps(r["steps"])
        assert "Third-party content" in r["note"]

    def test_submitting_a_form_on_the_same_host(self, servers):
        r = act(servers, [{"action": "type", "selector": "#name", "text": "Bo"}, {"action": "click", "selector": "#go"}])
        assert "error" not in r, r
        assert "Form submitted" in r["text"] and r["url"].endswith("/submitted?name=Bo&pw=")

    def test_a_click_that_navigates_on_the_same_host_works(self, servers):
        r = act(servers, [{"action": "click", "text": "About us"}])
        assert "About page" in r["text"] and r["url"].endswith("/about")

    def test_a_click_that_would_leave_the_host_never_reaches_the_other_server(self, servers):
        r = act(servers, [{"action": "click", "text": "Elsewhere"}])
        assert Other.hits == []
        assert r.get("refused_by") == "browser_scope" or "error" in r, r

    def test_typing_into_a_password_field_is_refused_even_when_asked(self, servers):
        r = act(servers, [{"action": "type", "selector": "#pw", "text": "hunter2"}])
        assert r["steps"][0]["ok"] is False and r["steps"][0]["refused_by"] == "browser_act" and r["steps_done"] == 0

    def test_a_purchase_button_is_refused_whatever_the_steps_say(self, servers):
        r = act(servers, [{"action": "click", "selector": "#buy"}])                  # named by selector, not by label: the label on the page is still checked
        assert r["steps"][0]["ok"] is False and "BOUGHT" not in r["text"]

    def test_the_first_failing_step_stops_the_rest(self, servers):
        r = act(servers, [{"action": "click", "text": "No such button"}, {"action": "type", "selector": "#name", "text": "late"}])
        assert [s["ok"] for s in r["steps"]] == [False] and r["steps_done"] == 0 and r["steps"][0]["error"] == "no such element"

    def test_scroll_wait_and_press_work_and_a_screenshot_can_be_taken(self, servers):
        r = act(servers, [{"action": "scroll", "pixels": 200}, {"action": "wait", "seconds": 0.2}, {"action": "type", "selector": "#name", "text": "x"}, {"action": "press", "key": "Tab"}],
                screenshot=True)
        assert r["steps_done"] == 4 and r["screenshot"]["bytes"] > 0
