"""Round 92: the one-click Desk launcher serves the built Desk and hands the page the host's address and the owner's token without putting the token in the address.

A real HTTP server on a real port, real requests. What is pinned: the page routes of a static export resolve (/chat -> chat.html); a path that climbs out of the folder is refused; a request that
names a non-loopback Host (DNS rebinding) is refused; the token path answers a same-origin or a plain request and refuses a cross-site one; the token is never in a header, a log line or a page.
"""
import http.client
import json

import pytest

from rct_control_plane import desk_launcher as dl

TOKEN = "TOKEN-for-the-test-0123456789"


@pytest.fixture
def served(tmp_path):
    out = tmp_path / "out"
    (out / "_next" / "static").mkdir(parents=True)
    (out / "index.html").write_text("<html>home</html>", encoding="utf-8")
    (out / "chat.html").write_text("<html>chat</html>", encoding="utf-8")
    (out / "law").mkdir()
    (out / "law" / "index.html").write_text("<html>law</html>", encoding="utf-8")
    (out / "404.html").write_text("<html>nothing here</html>", encoding="utf-8")
    (out / "_next" / "static" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the folder", encoding="utf-8")
    server = dl.make_server(out, 0, "http://127.0.0.1:8000", lambda: TOKEN)
    thread, url = dl.serve_in_background(server)
    port = server.server_address[1]
    yield port
    server.shutdown()


def get(port, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers=headers or {})
    response = conn.getresponse()
    body = response.read()
    return response.status, dict(response.getheaders()), body


def test_the_pages_of_a_static_export_resolve(served):
    assert get(served, "/") [0] == 200 and b"home" in get(served, "/")[2]
    status, headers, body = get(served, "/chat")
    assert status == 200 and b"chat" in body and headers["Content-Type"].startswith("text/html")
    assert get(served, "/law")[0] == 200 and b"law" in get(served, "/law")[2]
    status, headers, _ = get(served, "/_next/static/app.js")
    assert status == 200 and "javascript" in headers["Content-Type"]


def test_an_unknown_path_is_the_404_page_with_a_404_status(served):
    status, _, body = get(served, "/nope")
    assert status == 404 and b"nothing here" in body


def test_a_path_that_climbs_out_of_the_folder_is_refused(served):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/_next/../../secret.txt"):
        status, _, body = get(served, path)
        assert status == 404 and b"outside the folder" not in body, path


def test_a_request_that_names_another_host_is_refused(served):
    status, _, body = get(served, "/__delentia_local.json", {"Host": "evil.example.com"})
    assert status == 421 and TOKEN.encode() not in body
    status, _, body = get(served, "/", {"Host": "127.0.0.1.evil.example.com"})
    assert status == 421


def test_the_page_gets_the_host_address_and_the_token_and_nothing_caches_it(served):
    status, headers, body = get(served, "/__delentia_local.json", {"Sec-Fetch-Site": "same-origin"})
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert json.loads(body) == {"gateway": "http://127.0.0.1:8000", "token": TOKEN}
    assert get(served, "/__delentia_local.json")[0] == 200                               # curl sends no Sec-Fetch-Site
    assert get(served, "/__delentia_local.json", {"Sec-Fetch-Site": "none"})[0] == 200   # a typed address


def test_a_cross_site_request_for_the_token_is_refused(served):
    for site in ("cross-site", "same-site"):
        status, _, body = get(served, "/__delentia_local.json", {"Sec-Fetch-Site": site})
        assert status == 403 and TOKEN.encode() not in body, site


def test_the_token_is_never_in_a_page_or_a_header(served):
    for path in ("/", "/chat", "/law", "/nope", "/_next/static/app.js"):
        status, headers, body = get(served, path)
        assert TOKEN.encode() not in body and TOKEN not in json.dumps(headers), path


def test_a_missing_token_file_gives_an_empty_token_not_an_error(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("x", encoding="utf-8")

    def boom():
        raise FileNotFoundError("no token file")
    server = dl.make_server(out, 0, "http://127.0.0.1:8000", boom)
    thread, _ = dl.serve_in_background(server)
    try:
        status, _, body = get(server.server_address[1], "/__delentia_local.json")
        assert status == 200 and json.loads(body)["token"] == ""
    finally:
        server.shutdown()


def test_loopback_names_are_recognised_exactly():
    for ok in ("127.0.0.1", "127.0.0.1:3010", "localhost", "localhost:3010", "[::1]:3010", "LOCALHOST"):
        assert dl.is_loopback_host(ok), ok
    for bad in ("", "127.0.0.1.evil.com", "evil.com", "localhost.evil.com", "10.0.0.5:3010", "0.0.0.0"):
        assert not dl.is_loopback_host(bad), bad
