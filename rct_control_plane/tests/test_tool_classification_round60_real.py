"""
Round 60: every tool the runtime exposes is classified for the taint gate.

The taint gate (Round 58) can only stop what it knows about. A tool added later that sends data out or runs code, and that nobody put in the gated set, would be an open door the
injection measurement never exercises. This audit makes the decision unavoidable: each real MCP tool must be a SOURCE of outside text, GATED (a signature once the episode is tainted),
or INERT (reviewed: reads, computes, or writes one bounded artefact and sends nothing anywhere). The first run of this audit found three tools the Round 58 list had missed
(`delentia_synthesize_function`, `delentia_process_intent`, `delentia_check_reminders`: they run code or stored goals).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest

from rct_control_plane.governed_autonomous_loop import (RISKY_TOOLS, TAINT_EGRESS_TOOLS, TAINT_GATED_TOOLS, TAINT_INERT_TOOLS, TAINT_SOURCE_TOOLS, GovernedAutonomousLoop)
from rct_control_plane.mcp_server import mcp

NAMES = sorted(t.name for t in asyncio.run(mcp.list_tools()))


def test_every_exposed_tool_is_classified():
    unclassified = [n for n in NAMES if n not in TAINT_SOURCE_TOOLS and n not in TAINT_GATED_TOOLS and n not in TAINT_INERT_TOOLS]
    assert not unclassified, (f"{unclassified} are in none of TAINT_SOURCE_TOOLS (returns text from outside), TAINT_GATED_TOOLS (needs a signature once the episode is tainted) or "
                              "TAINT_INERT_TOOLS (reviewed: cannot cause a side effect or move data out) in governed_autonomous_loop.py. Decide, then add it to exactly one.")


def test_no_tool_is_both_inert_and_dangerous():
    assert not (TAINT_INERT_TOOLS & TAINT_GATED_TOOLS), TAINT_INERT_TOOLS & TAINT_GATED_TOOLS
    assert not (TAINT_INERT_TOOLS & TAINT_SOURCE_TOOLS), TAINT_INERT_TOOLS & TAINT_SOURCE_TOOLS


def test_the_sets_name_only_real_tools():
    for name in TAINT_SOURCE_TOOLS | TAINT_GATED_TOOLS | TAINT_INERT_TOOLS | TAINT_EGRESS_TOOLS:
        assert name in NAMES, f"{name} is named in a taint set but is not an exposed tool"


def test_a_tool_the_fdia_gate_calls_risky_is_never_silently_inert_without_a_reason():
    """RISKY tools that are INERT must be few and explained in the source; today exactly the forged-tool runner (a human-signed pure function)."""
    assert sorted(RISKY_TOOLS & TAINT_INERT_TOOLS) == ["delentia_run_forged_tool"]


@pytest.mark.parametrize("tool", sorted(TAINT_GATED_TOOLS))
def test_a_tainted_episode_cannot_call_a_gated_tool_without_a_signature(tool):
    loop = GovernedAutonomousLoop.__new__(GovernedAutonomousLoop)
    loop._episode_taint, loop._episode_seen_urls = "delentia_crawl_url", set()
    reason = loop._taint_reason("summarise it", tool, {"url": "https://evil.example/?d=1"})
    assert reason and "signature" in reason, tool


@pytest.mark.parametrize("tool", sorted(TAINT_INERT_TOOLS))
def test_an_inert_tool_is_not_gated_by_taint_so_reading_stays_free(tool):
    loop = GovernedAutonomousLoop.__new__(GovernedAutonomousLoop)
    loop._episode_taint, loop._episode_seen_urls = "delentia_crawl_url", set()
    assert loop._taint_reason("summarise it", tool, {}) is None


def test_a_clean_episode_gates_nothing():
    loop = GovernedAutonomousLoop.__new__(GovernedAutonomousLoop)
    loop._episode_taint, loop._episode_seen_urls = None, set()
    assert all(loop._taint_reason("g", t, {}) is None for t in TAINT_GATED_TOOLS)
