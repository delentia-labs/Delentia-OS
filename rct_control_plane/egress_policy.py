"""
Round 55: the data-sovereignty policy also applies to things that leave through a tool, not only to model calls.

`residency.py` checks every model call before it is sent. A web search sends the user's query to a search provider, and a
remote MCP server receives the tool's arguments; both are data leaving the machine, so the same policy (if the owner set one)
decides whether they may go. No policy = nothing restricts where data goes (as for model calls).

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit


def hosting_for_url(url: str, region: str = "", operator: str = "") -> Any:
    from core.regional_adapter.sovereignty import (GLOBAL, KIND_CROSS_BORDER, KIND_IN_REGION, KIND_LOCAL, HostingProfile, validate_region)
    from rct_control_plane.residency import _is_private_host
    host = (urlsplit(url).hostname or "").lower()
    if _is_private_host(host):
        return HostingProfile(KIND_LOCAL, "LOCAL", operator or f"{host} (this machine or network)")
    if region:
        return HostingProfile(KIND_IN_REGION, validate_region(region), operator or f"{host} (region declared by the owner)")
    return HostingProfile(KIND_CROSS_BORDER, GLOBAL, operator or host, "region not declared")


def check_egress(url: str, text: str, *, region: str = "", operator: str = "") -> Tuple[bool, str, str, Optional[Dict[str, Any]]]:
    """(allowed, reason, text to send, decision record). With no sovereignty policy: allowed and unchanged. A policy that says
    "redact" returns the text with personal data replaced."""
    from core.regional_adapter.sovereignty import evaluate_call, redact_text
    from rct_control_plane import residency
    policy = residency.load_policy()
    if policy is None:
        return True, "no sovereignty policy is set", text, None
    decision = evaluate_call(policy, hosting_for_url(url, region, operator), text)
    record = decision.to_dict()
    if not decision.allowed:
        return False, decision.reason, text, record
    if decision.action == "redact":
        return True, decision.reason, redact_text(text)[0], record
    return True, decision.reason, text, record
