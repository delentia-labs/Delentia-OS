"""
Round 59: DNS rebinding and the crawler.

`delentia_crawl_url` checked a name with url_safety and then let httpx resolve it again. A DNS server that answers with a public address the first time and 127.0.0.1 (this runtime's own
API) or 169.254.169.254 (cloud credentials) the second time walked through. The crawler now connects through a transport that resolves ONCE, inside the connection, checks the addresses
there and opens the socket to the checked address. These tests make the resolver lie exactly that way (socket.getaddrinfo is replaced; everything else is real: real sockets, a real
HTTP server on loopback that counts the requests it receives, the real httpx client).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import url_safety
from rct_control_plane.algo_34_swcar import WebCrawler

run = asyncio.run
PUBLIC = "93.184.216.34"


class Internal(BaseHTTPRequestHandler):
    """Stands for the internal service an attacker wants to reach: counts every request."""
    hits = []

    def do_GET(self):                                        # noqa: N802
        Internal.hits.append((self.path, self.headers.get("Host")))
        body = b"<html><body>INTERNAL SECRET</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def internal():
    Internal.hits = []
    s = HTTPServer(("127.0.0.1", 0), Internal)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s.server_port
    s.shutdown()


@pytest.fixture(autouse=True)
def no_private(monkeypatch):
    monkeypatch.delenv(url_safety.ALLOW_PRIVATE_ENV, raising=False)


def lying_resolver(monkeypatch, name, answers):
    """getaddrinfo for `name` returns answers[0] the first time, answers[1] the second, and so on (the last one repeats)."""
    real = socket.getaddrinfo
    calls = []

    def fake(host, port, *args, **kwargs):
        if host == name:
            answer = answers[min(len(calls), len(answers) - 1)]
            calls.append(answer)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answer, port or 0))]
        return real(host, port, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    return calls


def test_a_name_that_answers_public_for_the_check_and_loopback_for_the_connection_never_connects(monkeypatch, internal):
    calls = lying_resolver(monkeypatch, "rebind.example", [PUBLIC, "127.0.0.1"])
    crawler = WebCrawler(block_private=True, respect_robots_txt=False, max_retries=1)
    with pytest.raises(Exception, match="not a public address"):
        run(crawler.crawl(f"http://rebind.example:{internal}/"))
    assert Internal.hits == []                                # the internal service never saw a request
    assert calls[0] == PUBLIC and "127.0.0.1" in calls         # the lie WAS told: the first answer passed the check, the second was the connection's


def test_the_same_lie_about_cloud_metadata_is_refused(monkeypatch):
    lying_resolver(monkeypatch, "meta.example", [PUBLIC, "169.254.169.254"])
    crawler = WebCrawler(block_private=True, respect_robots_txt=False, max_retries=1)
    with pytest.raises(Exception, match="not a public address"):
        run(crawler.crawl("http://meta.example/latest/meta-data/"))


def test_a_name_that_resolves_to_both_a_public_and_a_private_address_is_refused(monkeypatch, internal):
    real = socket.getaddrinfo

    def both(host, port, *args, **kwargs):
        if host == "both.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, port or 0)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 0))]
        return real(host, port, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", both)
    crawler = WebCrawler(block_private=True, respect_robots_txt=False, max_retries=1)
    with pytest.raises(Exception, match="not a public address"):
        run(crawler.crawl(f"http://both.example:{internal}/"))
    assert Internal.hits == []


def test_with_private_fetches_allowed_the_connection_goes_to_the_checked_address_with_the_original_host_header(monkeypatch, internal):
    """DELENTIA_CRAWL_ALLOW_PRIVATE=1 is the owner's choice; the pinned transport must still work (and send the name, not the address, as Host)."""
    monkeypatch.setenv(url_safety.ALLOW_PRIVATE_ENV, "1")
    lying_resolver(monkeypatch, "docs.internal-wiki.example", ["127.0.0.1"])
    crawler = WebCrawler(block_private=True, respect_robots_txt=False, max_retries=1)
    page = run(crawler.crawl(f"http://docs.internal-wiki.example:{internal}/page"))
    assert page.status_code == 200 and "INTERNAL SECRET" in (page.html or "")
    assert Internal.hits == [("/page", f"docs.internal-wiki.example:{internal}")]


def test_an_address_literal_for_loopback_is_refused(internal):
    crawler = WebCrawler(block_private=True, respect_robots_txt=False, max_retries=1)
    with pytest.raises(Exception, match="not a public address"):
        run(crawler.crawl(f"http://127.0.0.1:{internal}/"))
    assert Internal.hits == []


def test_a_crawler_that_blocks_private_addresses_is_pinned_and_one_that_does_not_is_not():
    async def pinned(block):
        crawler = WebCrawler(block_private=block)
        await crawler._init_client()
        try:
            return crawler.dns_pinned
        finally:
            await crawler._close_client()
    assert run(pinned(True)) is True and run(pinned(False)) is False


def test_the_pinned_transport_exists_with_the_installed_httpx():
    """If an httpx/httpcore upgrade removes the internals this relies on, this fails loudly instead of the crawler silently losing the protection."""
    assert url_safety.pinned_async_transport() is not None


def test_check_resolved_returns_one_checked_address(monkeypatch):
    lying_resolver(monkeypatch, "ok.example", [PUBLIC])
    assert str(url_safety.check_resolved("ok.example", 443)) == PUBLIC
    lying_resolver(monkeypatch, "bad.example", ["10.0.0.5"])
    with pytest.raises(url_safety.UnsafeURLError):
        url_safety.check_resolved("bad.example", 443)


def test_the_mcp_tool_reports_the_refusal_as_url_safety(monkeypatch, internal):
    import rct_control_plane.mcp_server as mcp_server
    lying_resolver(monkeypatch, "rebind2.example", [PUBLIC, "127.0.0.1"])
    result = run(mcp_server.delentia_crawl_url(f"http://rebind2.example:{internal}/"))
    assert result.get("refused_by") == "url_safety" and Internal.hits == []
