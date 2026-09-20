"""
Round 35: real, live end-to-end verification of every HexaCore role's
OpenRouter model ID that CAN be reached via OpenRouter today.

Round 32 built real HTTP client code for 7 roles with zero prior live
verification (no key was available in-session then). This round got a
real OPENROUTER_API_KEY and found 2 of the 7 declared model IDs were
stale/deprecated (confirmed via OpenRouter's own real error bodies) and
fixed them to real, currently-valid replacements (see registry.py's
inline Round 35 comments for the exact evidence). REGIONAL_THAI's
"scb10x/typhoon-v2-70b-instruct" is confirmed genuinely absent from
OpenRouter's entire model catalog today - honestly left unfixed rather
than silently substituted with an unrelated model.

All tests here require a real OPENROUTER_API_KEY and are skipped
honestly without one, matching this session's established pattern.
"""

import os

import pytest

from signedai.core.openrouter_adapter import call_hexacore_role
from signedai.core.registry import HexaCoreRole

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="no live OPENROUTER_API_KEY in this environment - real live verification skipped honestly",
)

_REACHABLE_ROLES = [
    HexaCoreRole.SUPREME_ARCHITECT,
    HexaCoreRole.LEAD_BUILDER,
    HexaCoreRole.JUNIOR_BUILDER,
    HexaCoreRole.SPECIALIST,
    HexaCoreRole.LIBRARIAN,
    HexaCoreRole.HUMANIZER,
]


@pytest.mark.parametrize("role", _REACHABLE_ROLES, ids=[r.value for r in _REACHABLE_ROLES])
def test_role_is_genuinely_reachable_live(role):
    result = call_hexacore_role(role, "Reply with exactly one word: OK", max_tokens=100)
    assert isinstance(result, str)
    assert len(result) > 0


def test_regional_thai_is_confirmed_still_unreachable_via_openrouter():
    """Documents the real, known, unfixed gap - Typhoon is not on
    OpenRouter's catalog at all as of Round 35. This test fails loudly
    (rather than silently passing) if OpenRouter ever lists it again,
    prompting a real fix instead of leaving stale documentation."""
    from signedai.core.openrouter_adapter import OpenRouterGenerateError
    with pytest.raises(OpenRouterGenerateError):
        call_hexacore_role(HexaCoreRole.REGIONAL_THAI, "Reply with exactly one word: OK", max_tokens=20)
