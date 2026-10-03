"""
Round 55: one place that builds the runtime's HTTP clients.

`httpx.AsyncClient()` builds a TLS context every time it is created, and loading the system's certificate bundle costs about 200-300 ms
of CPU on this machine (Windows; Linux is faster but not free). The runtime built a new client for every model call, so a governed
episode with two model calls spent ~0.6 s of its 0.76 s just loading certificates, and because that work is synchronous it also blocked
the event loop: six episodes started together finished one after another (host_sizing.py measured 6.0 s for six, against ~1 s for one).

The context is read-only once built, so it is built once per process and shared. Clients themselves are still created per call (a client
is tied to an event loop; sharing one across loops, as the tests do, would break).

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from typing import Any

import httpx


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    return httpx.create_ssl_context()


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """An httpx.AsyncClient that reuses the process-wide TLS context unless the caller chose its own `verify`."""
    kwargs.setdefault("verify", shared_ssl_context())
    return httpx.AsyncClient(**kwargs)
