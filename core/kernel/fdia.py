"""
RCT NPC Kernel — NPC Intent Types (Plan 21)

Round 45 item O: this file originally also defined a full FDIAScorer
scoring engine (Desire/Intent/Alignment/Governance formula for NPC
game-simulation action selection - a different "FDIA" than the real
constitutional F=(D^I)×A used throughout rct_control_plane/sandbox.py
and governed_autonomous_loop.py, a naming collision, not the same
system). Verified by direct repo-wide grep (not assumed) that
FDIAScorer, and everything it alone depended on (FDIAWeights, NPCAction,
DEFAULT_DESIRE_WEIGHTS, INTENT_ALIGNMENT_MATRIX, intent_alignment()),
had zero real imports anywhere - core/fdia/fdia.py is the real,
actively-used, 99%-covered version of this concept. Removed with
Architect sign-off (Zero-Delete: git history still has it if ever
needed). NPCIntentType below is kept - core/kernel/memory_delta.py
genuinely imports it, which cli.py depends on transitively.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# NPC Intent Types (distinct from control-plane IntentRole)
# ---------------------------------------------------------------------------

class NPCIntentType(str, Enum):
    """
    Primitive intent types for NPC agents.
    Each has a default desire weight representing base drive strength.
    """
    PROTECT   = "PROTECT"    # protect family/faction/territory
    ACCUMULATE = "ACCUMULATE"  # gather resources / wealth
    BELONG    = "BELONG"     # join groups, form alliances
    DISCOVER  = "DISCOVER"   # explore, learn, research
    DOMINATE  = "DOMINATE"   # control others, assert authority
    NEUTRAL   = "NEUTRAL"    # no strong drive; reactive
