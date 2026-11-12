"""
Round 112C: waiting for something that is not there.

On Windows a refused connection to a closed port on THIS computer takes about 2 seconds (measured 2.05 s with a plain socket, urllib and httpx; 4.08 s for the name `localhost`, which tries IPv6 first),
because the operating system retries before it reports the refusal. A program that is listening accepts a loopback connection in milliseconds. So a short connect timeout for loopback addresses changes
nothing for a working local model server and turns "no model program installed" from a long wait into a short one. Anything that is not a loopback address keeps its normal timeouts.

Standard library only (httpx is imported lazily by the one helper that returns an httpx.Timeout).
"""
from __future__ import annotations

import os
import socket
from typing import Any, Optional
from urllib.parse import urlparse

LOCAL_CONNECT_TIMEOUT_ENV = "DELENTIA_LOCAL_CONNECT_TIMEOUT_S"
DEFAULT_LOCAL_CONNECT_TIMEOUT_S = 0.75
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def local_connect_timeout() -> float:
    try:
        value = float(os.environ.get(LOCAL_CONNECT_TIMEOUT_ENV, DEFAULT_LOCAL_CONNECT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_LOCAL_CONNECT_TIMEOUT_S
    return value if value > 0 else DEFAULT_LOCAL_CONNECT_TIMEOUT_S


def _host_port(url: str) -> "tuple[str, Optional[int]]":
    parsed = urlparse(url if "://" in url else "http://" + url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    return host, port


def is_loopback_url(url: str) -> bool:
    host, _ = _host_port(url)
    return host in LOOPBACK_HOSTS or host == "::1"


def timeout_for(url: str, read_seconds: float) -> Any:
    """An httpx timeout: the caller's `read_seconds` for everything, but only `local_connect_timeout()` for connecting when the address is on this computer. For any other address, the plain number."""
    if not is_loopback_url(url):
        return read_seconds
    import httpx
    return httpx.Timeout(read_seconds, connect=min(read_seconds, local_connect_timeout()))


def quick_connect_ok(url: str) -> bool:
    """Is anything accepting connections at this address? Only a loopback address is checked (with the short timeout); any other address returns True because it is not ours to hurry."""
    if not is_loopback_url(url):
        return True
    host, port = _host_port(url)
    if port is None:
        port = 443 if url.startswith("https") else 80
    try:
        with socket.create_connection((host.strip("[]") or "127.0.0.1", port), timeout=local_connect_timeout()):
            return True
    except OSError:
        return False
