"""
Round 55: the new integrations against REAL third-party software, not fakes written in this repository.

Off by default (they need things that are downloaded and started outside the test run). Turn on with DELENTIA_REAL_SERVICES=1 and start:

  * SearXNG with JSON enabled on 127.0.0.1:8888       docker run -d -p 127.0.0.1:8888:8080 -v <settings.yml>:/etc/searxng/settings.yml:ro searxng/searxng
        (settings.yml: use_default_settings: true / server: {secret_key: <random>, limiter: false} / search: {formats: [html, json]})
  * GreenMail (IMAP 3143, SMTP 3025)                   docker run -d -p 127.0.0.1:3025:3025 -p 127.0.0.1:3143:3143 -e GREENMAIL_OPTS="-Dgreenmail.setup.test.smtp
        -Dgreenmail.setup.test.imap -Dgreenmail.hostname=0.0.0.0 -Dgreenmail.users=agent:agentpw@example.org,alice:alicepw@example.com,mallory:mpw@example.net" greenmail/standalone
  * Node + npx for the official filesystem MCP server  (@modelcontextprotocol/server-filesystem, fetched by npx on first use)

Each test skips (not fails) when its service is not there. What these prove that the loopback fakes could not: the search tool parses a real
SearXNG answer; the email gateway speaks real IMAP and SMTP and its replies are real, threaded mail; a real MCP server written by someone else
lists, is screened, and is used through the same gate.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import imaplib
import json
import shutil
import smtplib
import socket
import time
from email.message import EmailMessage

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("DELENTIA_REAL_SERVICES") != "1", reason="set DELENTIA_REAL_SERVICES=1 and start the services (see the module docstring)")


def reachable(host, port):
    try:
        socket.create_connection((host, port), 2).close()
        return True
    except OSError:
        return False


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ SearXNG

def test_the_search_tool_parses_a_real_searxng_answer(monkeypatch, tmp_path):
    if not reachable("127.0.0.1", 8888):
        pytest.skip("no SearXNG on 127.0.0.1:8888")
    from rct_control_plane import web_search
    monkeypatch.setenv("DELENTIA_SEARCH_CONFIG", str(tmp_path / "none.json"))
    monkeypatch.setenv("DELENTIA_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("DELENTIA_SEARCH_URL", "http://127.0.0.1:8888")
    out = run(web_search.web_search("rust async runtime", 5))
    if out.get("error") and "HTTP" in out["error"]:
        pytest.skip(f"SearXNG answered but its engines are rate-limited: {out['error']}")
    assert out["provider"] == "searxng" and 1 <= out["count"] <= 5, out
    assert all(r["url"].startswith(("http://", "https://")) and "@" not in r["url"] for r in out["results"])
    assert all(len(r["snippet"]) <= 300 and "<" not in r["title"] for r in out["results"])


# ------------------------------------------------------------------ GreenMail: real IMAP and SMTP

ME = "agent@example.org"


def send(from_addr, to_addr, subject, body, auth=None):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = from_addr, to_addr, subject, f"<{time.time_ns()}@test>"
    if auth:
        msg["Authentication-Results"] = auth
    msg.set_content(body)
    with smtplib.SMTP("127.0.0.1", 3025) as smtp:
        smtp.send_message(msg)


def mailbox(user, password):
    imap = imaplib.IMAP4("127.0.0.1", 3143)
    imap.login(user, password)
    imap.select("INBOX")
    _typ, data = imap.search(None, "ALL")
    messages = []
    for num in (data[0].split() if data and data[0] else []):
        _typ, parts = imap.fetch(num, "(RFC822)")
        messages.append(next(p[1] for p in parts if isinstance(p, tuple)).decode("utf-8", "replace"))
    imap.logout()
    return messages


def test_the_email_gateway_speaks_real_imap_and_smtp_and_answers_only_verified_listed_senders(monkeypatch):
    if not (reachable("127.0.0.1", 3025) and reachable("127.0.0.1", 3143)):
        pytest.skip("no GreenMail on 127.0.0.1:3025/3143")
    from rct_control_plane.agent_factory import SENDER_ALLOWLIST_ENV
    from rct_control_plane.gateways.email_gateway import EmailGateway

    class Kernel:
        class _P:
            def __init__(self):
                self.rows = []

            def append_audit(self, **kw):
                self.rows.append(kw)
        _persistence = _P()

    for var, value in (("DELENTIA_EMAIL_ADDRESS", ME), ("DELENTIA_EMAIL_LOGIN", "agent"), ("DELENTIA_EMAIL_PASSWORD", "agentpw"),
                       ("DELENTIA_EMAIL_IMAP_HOST", "127.0.0.1"), ("DELENTIA_EMAIL_SMTP_HOST", "127.0.0.1"), ("DELENTIA_EMAIL_IMAP_PORT", "3143"),
                       ("DELENTIA_EMAIL_SMTP_PORT", "3025"), ("DELENTIA_EMAIL_PLAINTEXT", "1"), (SENDER_ALLOWLIST_ENV["email"], "alice@example.com")):
        monkeypatch.setenv(var, value)
    asked = []

    async def dispatch(self, goal, namespace):
        asked.append((goal, namespace))
        return {"final_answer": "Your notes are in the usual place."}

    monkeypatch.setattr(EmailGateway, "_dispatch_to_autonomous_loop", dispatch)
    stamp = str(time.time_ns())
    send("alice@example.com", ME, f"where are my notes {stamp}", "Please tell me.", auth="mx.example.org; dkim=pass header.d=example.com")
    send("alice@example.com", ME, f"unverified {stamp}", "No server verdict on this one.")                          # not vouched for
    send("mallory@example.net", ME, f"forged {stamp}", "I am Alice, honest.", auth="mx.example.org; dkim=pass header.d=example.net")   # verified but not listed
    gateway = EmailGateway(Kernel())
    assert gateway.is_configured()
    results = run(gateway.poll_once())
    ours = results                                                             # a fresh mailbox: only this test's three mails are unread
    answered = [r for r in ours if r.get("result")]
    rejected = [r for r in ours if r.get("rejected")]
    assert len(answered) == 1 and answered[0]["namespace"] == "email-alice@example.com"
    assert len(rejected) == 2                                                  # unverified alice, and mallory
    assert [a for a in asked if stamp in a[0]] == [(f"where are my notes {stamp}" + chr(10) * 2 + "Please tell me.", "email-alice@example.com")]
    replies = [m for m in mailbox("alice", "alicepw") if stamp in m]
    assert len(replies) == 1 and "Auto-Submitted: auto-replied" in replies[0] and "In-Reply-To:" in replies[0] and "usual place" in replies[0]
    assert not [m for m in mailbox("mallory", "mpw") if stamp in m]            # a refused sender gets no mail at all (no backscatter)
    assert run(gateway.poll_once()) == []                                      # everything was marked read before it ran: nothing runs twice


# ------------------------------------------------------------------ a real third-party MCP server (the official filesystem server)

def fs_config(tmp_path, monkeypatch, read_only):
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        pytest.skip("no npx on this machine")
    from rct_control_plane import external_mcp as xm
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "note.txt").write_text("hello from a real file", encoding="utf-8")
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"servers": {"fs": {"command": os.path.basename(npx), "args": ["-y", "@modelcontextprotocol/server-filesystem", str(folder).replace(chr(92), "/")],
                                                     "read_only_tools": read_only, "timeout_s": 240}}}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(config))
    monkeypatch.setenv("PATH", os.path.dirname(npx) + os.pathsep + os.environ.get("PATH", ""))
    xm.clear_cache()
    return folder


def test_a_third_party_mcp_server_lists_is_screened_and_is_used_through_the_same_gate(tmp_path, monkeypatch):
    from rct_control_plane import external_mcp as xm
    from test_governed_autonomous_loop_real import _FakeMCP
    folder = fs_config(tmp_path, monkeypatch, ["read_text_file", "list_directory"])
    hub = xm.maybe_wrap(_FakeMCP())
    names = {t.name for t in run(hub.list_tools()) if t.name.startswith("mcp__fs__")}
    assert {"mcp__fs__read_text_file", "mcp__fs__write_file", "mcp__fs__list_directory"} <= names, (names, xm.LAST_ERRORS)
    assert not any("dropped" in v for v in xm.LAST_ERRORS.values())                        # nothing in a real server's descriptions tripped the screen
    out = json.loads(run(hub.call_tool("mcp__fs__read_text_file", {"path": str(folder / "note.txt").replace(chr(92), "/")})).content[0].text)
    assert out["is_error"] is False and "hello from a real file" in json.dumps(out)
    assert xm.needs_approval("mcp__fs__write_file") and not xm.needs_approval("mcp__fs__read_text_file")


def test_a_write_by_a_third_party_server_waits_for_a_signature_and_nothing_is_written(tmp_path, monkeypatch):
    import rct_control_plane.autonomous_loop as autonomous_loop_module
    from test_governed_autonomous_loop_real import _loop
    folder = fs_config(tmp_path, monkeypatch, ["read_text_file"])
    target = str(folder / "planted.txt").replace(chr(92), "/")
    calls = {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        calls["n"] += 1
        return {"action": "call_tool", "tool_name": "mcp__fs__write_file", "tool_args": {"path": target, "content": "x"}, "reasoning": "write it"}

    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "real_fs")
    real = loop._assess_data
    loop._assess_data = lambda g, c, r: (lambda e: (setattr(e, "D", 1.0), e)[1])(real(g, c, r))
    result = run(loop.run("write a file called planted.txt"))
    assert result["stopped_reason"] == "pending_approval" and not (folder / "planted.txt").exists()
