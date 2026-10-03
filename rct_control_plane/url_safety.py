"""
Round 55: which addresses an agent's web fetch may reach.

`delentia_crawl_url` took any URL. An agent that has read a hostile page (or a user who pastes a link) could therefore make
this machine request `http://169.254.169.254/` (cloud credentials), `http://127.0.0.1:8000/` (this runtime's own API, which is
open on loopback when no token is set) or a router page. This module decides, from the addresses a host name resolves to,
whether a fetch is allowed. The crawler calls it before the first request and again for every redirect hop.

Limit, stated: the name is resolved here and again by the HTTP client, so a DNS server that answers differently the second time
(rebinding) can still slip through. Pinning the connection to the checked address is what mcp_gateway does for its own fetches;
the crawler (algo_34_swcar) uses a shared client and does not pin yet.

DELENTIA_CRAWL_ALLOW_PRIVATE=1 lets the owner crawl internal documentation on purpose.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import List, Union
from urllib.parse import urlsplit

ALLOW_PRIVATE_ENV = "DELENTIA_CRAWL_ALLOW_PRIVATE"
_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


class UnsafeURLError(ValueError):
    """The URL points somewhere an agent's fetch must not go."""


def allow_private() -> bool:
    return (os.environ.get(ALLOW_PRIVATE_ENV) or "").strip() == "1"


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _is_public(ip: IPAddress) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
                or (ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10")))        # carrier-grade NAT, also not public


def addresses_of(host: str, port: int) -> List[IPAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURLError(f"{host} does not resolve ({exc})") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def check_public_url(url: str) -> str:
    """Returns the URL when every address its host resolves to is public; raises UnsafeURLError otherwise."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURLError("only http and https addresses can be fetched")
    if parts.username or parts.password:
        raise UnsafeURLError("an address with a user name or password in it is refused")
    if allow_private():
        return url
    host = parts.hostname.lower()
    if host in _METADATA_HOSTS or host.endswith(".internal") or host.endswith(".localhost") or host == "localhost":
        raise UnsafeURLError(f"{host} is an internal name")
    addresses = addresses_of(host, parts.port or (443 if parts.scheme == "https" else 80))
    if not addresses:
        raise UnsafeURLError(f"{host} has no address")
    for ip in addresses:
        if not _is_public(ip):
            raise UnsafeURLError(f"{host} resolves to {ip}, which is not a public address")
    return url
