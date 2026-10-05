"""
Round 61: every tool the runtime exposes has been asked "does this show one person what another person did, or run as the owner?" - and the answer is written down.

A tool is PINNED to the asking person (the loop overwrites its `namespace` argument), OWNER-ONLY (refused on chat channels and the HTTP agent API), or PERSON-NEUTRAL (reviewed). The first run of this
audit found `delentia_query_audit_log`, `delentia_query_intents` and `delentia_check_reminders` returning everyone's data, and `delentia_autonomous_loop` and `delentia_schedule_reminder` running as the
owner's own namespaces whoever asked. A new tool that is in none of the three sets fails here.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import inspect

import pytest

from rct_control_plane.governed_autonomous_loop import OWNER_ONLY_TOOLS, PERSON_NEUTRAL_TOOLS, GovernedAutonomousLoop
from rct_control_plane.mcp_server import mcp

NAMES = sorted(t.name for t in asyncio.run(mcp.list_tools()))
PINNED = frozenset(GovernedAutonomousLoop.MEMORY_TOOLS)


def test_every_exposed_tool_has_a_person_scope():
    unscoped = [n for n in NAMES if n not in PINNED and n not in OWNER_ONLY_TOOLS and n not in PERSON_NEUTRAL_TOOLS]
    assert not unscoped, (f"{unscoped} are not PINNED (GovernedAutonomousLoop.MEMORY_TOOLS), OWNER-ONLY or PERSON-NEUTRAL. Ask: does it return or act on another person's requests, memories "
                          "or reminders, or run in an owner-level space? Then put it in exactly one set in governed_autonomous_loop.py.")


def test_the_three_sets_do_not_overlap_and_name_only_real_tools():
    assert not (PINNED & OWNER_ONLY_TOOLS) and not (PINNED & PERSON_NEUTRAL_TOOLS) and not (OWNER_ONLY_TOOLS & PERSON_NEUTRAL_TOOLS)
    for name in PINNED | OWNER_ONLY_TOOLS | PERSON_NEUTRAL_TOOLS:
        assert name in NAMES, f"{name} is named in a person-scope set but is not an exposed tool"


@pytest.mark.parametrize("tool", sorted(PINNED))
def test_a_pinned_tool_really_takes_the_namespace_argument(tool):
    """The loop overwrites `namespace`; a tool that has no such parameter would receive nothing to pin (or fail), so the pin would be a lie."""
    import rct_control_plane.mcp_server as module
    assert "namespace" in inspect.signature(getattr(module, tool)).parameters, tool
