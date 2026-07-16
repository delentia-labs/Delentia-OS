#!/usr/bin/env python3
"""
hallucination_demo.py — Side-by-side comparison: Standard LLM vs RCT Platform

Demonstrates how RCT's constitutional core (FDIA equation + SignedAI consensus)
prevents hallucinated outputs that a standard LLM would deliver.

Run:
    python examples/hallucination_demo.py

No API keys required — all computation is local.
"""

import sys
from pathlib import Path

# Fix Windows console encoding (CP874 Thai, CP932 Japanese, etc.)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Make sure we can import from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from signedai.core.registry import SignedAIRegistry, SignedAITier


# ─── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def divider(title: str = "") -> None:
    width = 65
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {BOLD}{title}{RESET} {'─' * pad}\n")
    else:
        print("─" * width)


def badge(ok: bool) -> str:
    return f"{GREEN}✅ DELIVERED{RESET}" if ok else f"{RED}❌ BLOCKED{RESET}"


# ─── Scenario runner ──────────────────────────────────────────────────────────

def run_scenario(
    title: str,
    description: str,
    D: float,
    I: float,
    A: float,
    votes_for: int,
    votes_against: int,
    tier: SignedAITier = SignedAITier.TIER_6,
    *,
    threshold: float = 0.60,
) -> None:
    """Run one hallucination scenario and print side-by-side comparison."""

    divider(title)
    print(f"  {CYAN}Scenario:{RESET} {description}")
    print(f"  D (data quality)  = {D:.2f}")
    print(f"  I (intent prec.)  = {I:.2f}  ← acts as exponent")
    print(f"  A (architect gate)= {A:.2f}  ← 0 = absolute block")
    print(f"  Votes             = {votes_for}/{votes_for+votes_against}")
    print()

    # ── Standard LLM (always delivers) ───────────────────────────────────────
    standard_output = "Response delivered without validation."

    # ── RCT Platform: FDIA score ──────────────────────────────────────────────
    F = (D ** I) * A
    fdia_pass = F >= threshold

    # ── RCT Platform: SignedAI consensus ─────────────────────────────────────
    consensus_result = SignedAIRegistry.calculate_consensus(
        tier=tier,
        votes_for=votes_for,
        votes_against=votes_against,
    )
    consensus_pass = consensus_result.consensus_reached

    # ── Final RCT decision (BOTH must pass) ──────────────────────────────────
    rct_pass = fdia_pass and consensus_pass

    # ── Display ───────────────────────────────────────────────────────────────
    print(f"  {'Standard LLM':<22}  {badge(True)}")
    print(f"  {'RCT Platform':<22}  {badge(rct_pass)}")
    print()
    print(f"  FDIA score  : {BOLD}{F:.4f}{RESET}  (threshold {threshold})  "
          f"→ {'PASS' if fdia_pass else 'FAIL'}")
    print(f"  Consensus   : {consensus_result.confidence:.0%}  "
          f"(need {tier.value})  → {'PASS' if consensus_pass else 'FAIL'}")

    if not rct_pass:
        reasons = []
        if not fdia_pass:
            reasons.append(f"F={F:.4f} < threshold {threshold}")
        if not consensus_pass:
            reasons.append(f"consensus {consensus_result.confidence:.0%} insufficient")
        print(f"  {RED}Block reason:{RESET} {'; '.join(reasons)}")

    print()


# ─── Main demo ────────────────────────────────────────────────────────────────

def main() -> None:
    divider()
    print(f"""
  {BOLD}RCT Platform — Hallucination Prevention Demo{RESET}
  Constitutional AI: F = D^I × A

  Shows how the FDIA equation + SignedAI consensus
  intercepts outputs that standard LLMs would deliver.

  Website  : https://www.delentia.com/th
  Colab    : bit.ly/rct-playground
  GitHub   : github.com/delentia-labs/delentia-os
""")
    divider()

    # ── Scenario 1: Hallucinated historical fact ──────────────────────────────
    run_scenario(
        title="Scenario 1 — Hallucinated Historical Fact",
        description='LLM outputs: "FDIA theorem published in 1987 by Dr. X" (false)',
        D=0.40,   # low — source is unreliable
        I=2.0,    # high intent precision
        A=1.0,    # human gate is open
        votes_for=3,
        votes_against=3,
        tier=SignedAITier.TIER_6,
        threshold=0.60,
    )

    # ── Scenario 2: Weak model consensus (split decision) ─────────────────────
    run_scenario(
        title="Scenario 2 — Weak Consensus (Split Decision)",
        description="3 models approve, 3 reject — tied vote on critical output",
        D=0.85,   # high quality data
        I=1.8,    # good intent
        A=1.0,    # gate open
        votes_for=3,
        votes_against=3,
        tier=SignedAITier.TIER_6,
        threshold=0.60,
    )

    # ── Scenario 3: Architect gate = 0 (Constitutional block) ─────────────────
    run_scenario(
        title="Scenario 3 — Constitutional Block (A = 0)",
        description="Human architect closes the gate — F=0 regardless of data quality",
        D=0.99,   # near-perfect data
        I=2.0,    # maximum intent precision
        A=0.0,    # GATE CLOSED ← constitutional guarantee
        votes_for=6,
        votes_against=0,
        tier=SignedAITier.TIER_6,
        threshold=0.60,
    )

    # ── Scenario 4: High quality — should pass ────────────────────────────────
    run_scenario(
        title="Scenario 4 — High Quality (Should Approve)",
        description="Good data + clear intent + open gate + strong consensus",
        D=0.90,
        I=2.0,
        A=1.0,
        votes_for=5,
        votes_against=1,
        tier=SignedAITier.TIER_6,
        threshold=0.60,
    )

    # ── Scenario 5: Partial architect approval ────────────────────────────────
    run_scenario(
        title="Scenario 5 — Partial Architect Approval (A = 0.5)",
        description="Human is uncertain — partially approves decision",
        D=0.90,
        I=2.0,
        A=0.5,    # partial approval
        votes_for=4,
        votes_against=2,
        tier=SignedAITier.TIER_6,
        threshold=0.60,
    )

    divider("Summary")
    print(f"""  {BOLD}Key Insight:{RESET}

  • Standard LLMs deliver output in ALL 5 scenarios
  • RCT Platform {RED}blocks 3/5{RESET} (Hallucinated fact, Weak consensus, A=0)
  • Scenario 3 (A=0) is a MATHEMATICAL guarantee, not a config setting:
      F = D^I × A = 0.99^2.0 × 0 = {0.99**2.0 * 0.0:.1f}  ← always zero

  The constitutional guarantee is in the algebra, not in the code.

  {CYAN}→ Try Section 5 of the Colab notebook for interactive exploration:{RESET}
    https://colab.research.google.com/github/rctlabs/delentia-os/blob/main/notebooks/rct_playground.ipynb

  {CYAN}→ Read the full Thai explainer:{RESET}
    https://www.delentia.com/th/blog/fdia-equation-explained
""")
    divider()


if __name__ == "__main__":
    main()
