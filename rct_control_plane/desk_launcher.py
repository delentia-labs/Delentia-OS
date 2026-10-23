"""
Round 92: a way to open the Desk with a double click, no code, no pasting a token.

The Desk is a static web app (apps/gui, built to apps/gui/out). It needs three things to be useful on the owner's own machine: the app served from somewhere, the address of the host, and the owner's API token.
This module serves the built app on 127.0.0.1 and hands the address and the token to the page through ONE loopback-only path, `/__delentia_local.json`. The token is not put in the address (a token in a URL
ends up in browser history and logs); the page keeps it in memory only.

What keeps this from being a way to leak the token:
  * the server listens on 127.0.0.1 only;
  * a request whose Host header is not a loopback name is refused (a web page on another site that points its own name at 127.0.0.1 - "DNS rebinding" - arrives with ITS Host, not ours);
  * `/__delentia_local.json` answers only a request the browser says came from this same page (Sec-Fetch-Site same-origin or none) or has no such header (curl); a request marked cross-site is refused,
    and the response is never cached;
  * files are served only from the built folder; a path that leaves it is refused.
It is for the owner on their own machine. It is not how outside people will reach a hosted Desk: they get their own token (delentia tokens create) and paste it on the Settings page.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import unquote, urlsplit

LOCAL_PATH = "/__delentia_local.json"
_HEADER_VALUE = re.compile(r"^[A-Za-z0-9 ;=/.+,_-]{1,120}$")           # printable ASCII only: no CR, no LF, nothing that could start a second header
_LOOPBACK_HOST = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", re.IGNORECASE)

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")


def is_loopback_host(value: str) -> bool:
    return bool(_LOOPBACK_HOST.match((value or "").strip()))


def resolve_static(root: Path, url_path: str) -> Optional[Path]:
    """The file for a URL path, the way the static export lays them out: /chat -> chat.html, /x/ -> x/index.html, / -> index.html. None when nothing matches or the path leaves `root`."""
    clean = unquote(urlsplit(url_path).path)
    if "\x00" in clean:
        return None
    relative = clean.lstrip("/")
    candidates = [relative] if relative else ["index.html"]
    if relative:
        candidates += [relative + ".html", relative.rstrip("/") + "/index.html"]
    # The request text is only ever used as a KEY into a table of the files that really are under `root`
    # (found by walking the folder, links that leave it left out). It never reaches a file-system call, so
    # there is no path to climb out with, whatever the text says.
    for refresh in (False, True):
        index = _file_index(root, refresh)
        for candidate in candidates:
            found = index.get(candidate)
            if found is not None and os.path.isfile(found):
                return Path(found)
    return None


_INDEX_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_INDEX_LOCK = threading.Lock()


def _file_index(root: Path, refresh: bool) -> Dict[str, str]:
    """{url-style relative path: real file} for every file under `root`. Rebuilt when asked, and at most once a second, so a Desk that is rebuilt while this runs is picked up."""
    base = os.path.realpath(str(root))
    now = time.monotonic()
    with _INDEX_LOCK:
        cached = _INDEX_CACHE.get(base)
        if cached is not None and (not refresh or now - cached[0] < 1.0):
            return cached[1]
        index: Dict[str, str] = {}
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                full = os.path.join(dirpath, name)
                real = os.path.realpath(full)
                if not real.startswith(base + os.sep):
                    continue                                 # a link inside the folder that points outside it is not served
                index[os.path.relpath(full, base).replace(os.sep, "/")] = real
        _INDEX_CACHE[base] = (now, index)
        return index


def make_server(root: Path, port: int, gateway: str, token_reader: Callable[[], str], host: str = "127.0.0.1") -> ThreadingHTTPServer:
    root = Path(root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "DelentiaDeskLauncher"

        def log_message(self, *args) -> None:                   # keep the console readable; nothing here is worth logging and a token must never be
            return

        def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
            if not _HEADER_VALUE.match(ctype):                  # a header value is never built from the request; this also keeps a line break out of it
                ctype = "application/octet-stream"
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                if _HEADER_VALUE.match(v):
                    self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _guard(self) -> bool:
            if not is_loopback_host(self.headers.get("Host", "")):
                self._send(421, b"misdirected request", "text/plain; charset=utf-8")
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            self._serve()

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve()

        def _serve(self) -> None:
            if not self._guard():
                return
            path = urlsplit(self.path).path
            if path == LOCAL_PATH:
                site = (self.headers.get("Sec-Fetch-Site") or "").lower()
                if site not in ("", "same-origin", "none"):
                    self._send(403, b"cross-site request refused", "text/plain; charset=utf-8")
                    return
                try:
                    token = token_reader()
                except Exception:                              # noqa: BLE001 - no token file: the page asks the person to paste one
                    token = ""
                self._send(200, json.dumps({"gateway": gateway, "token": token}).encode("utf-8"), "application/json", {"Cache-Control": "no-store"})
                return
            file = resolve_static(root, path)
            if file is None:
                missing = root / "404.html"
                body = missing.read_bytes() if missing.is_file() else b"not found"
                self._send(404, body, "text/html; charset=utf-8")
                return
            ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, file.read_bytes(), ctype, {"Cache-Control": "no-cache"})

    class ExclusiveServer(ThreadingHTTPServer):
        allow_reuse_address = False                       # on Windows SO_REUSEADDR lets a second program take a port that is already in use; a busy port must be reported as busy
        daemon_threads = True

    return ExclusiveServer((host, port), Handler)


def serve_in_background(server: ThreadingHTTPServer) -> Tuple[threading.Thread, str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = server.server_address
    host = address[0].decode() if isinstance(address[0], bytes) else address[0]
    return thread, f"http://{host}:{address[1]}"
