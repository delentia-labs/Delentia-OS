#!/usr/bin/env python3
"""
RCT SignedAI Consensus Demo

Demonstrates:
1. All 4 consensus tiers (S, 4, 6, 8)
2. Voting mechanisms
3. Geopolitical balance in consensus
4. Cost multipliers
5. Risk-based tier selection
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rct_platform.config import (
    SignedAITier,
    RiskLevel,
    SignedAIRegistry,
    HexaCoreRegistry
)


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def demo_all_tiers():
    """Display all 4 tiers."""
    print_header("SIGNEDAI CONSENSUS TIERS")
    
    for tier in SignedAITier:
        config = SignedAIRegistry.get_tier(tier)
        
        print(f"{tier.value.upper()}: {len(config.signers)} Signers")
        print(f"  Required Votes: {config.required_votes}/{len(config.signers)}")
        print(f"  Balance: {config.west_count} West + {config.east_count} East")
        print(f"  Cost Multiplier: {config.cost_multiplier}x")
        print(f"  Chairman Veto: {'Yes' if config.chairman_veto else 'No'}")
        print(f"  Recommended for: {', '.join(config.recommended_for[:2])}")
        
        # Show signers
        print(f"  Signers:")
        for role in config.signers[:3]:
            model_id = HexaCoreRegistry.get_model_id(role)
            print(f"    • {model_id}")
        if len(config.signers) > 3:
            print(f"    ... and {len(config.signers) - 3} more")
        print()


def demo_voting_scenarios():
    """Demonstrate voting scenarios."""
    print_header("CONSENSUS VOTING SCENARIOS")
    
    scenarios = [
        ("Unanimous approval (6/6)", SignedAITier.TIER_6, 6, 0, None),
        ("Strong majority (5/6)", SignedAITier.TIER_6, 5, 1, None),
        ("Bare majority (4/6)", SignedAITier.TIER_6, 4, 2, None),
        ("Failed consensus (3/6)", SignedAITier.TIER_6, 3, 3, None),
        ("Chairman approves (override)", SignedAITier.TIER_8, 3, 3, True),
        ("Chairman rejects (override)", SignedAITier.TIER_8, 5, 1, False),
    ]
    
    for description, tier, votes_for, votes_against, chairman in scenarios:
        result = SignedAIRegistry.calculate_consensus(
            tier=tier,
            votes_for=votes_for,
            votes_against=votes_against,
            chairman_override=chairman
        )
        
        status = "✅ APPROVED" if result.consensus_reached else "❌ REJECTED"
        
        print(f"{description}")
        print(f"  Tier: {tier.value.upper()}")
        print(f"  Votes: {votes_for} for, {votes_against} against")
        if chairman is not None:
            print(f"  Chairman: {'Approved' if chairman else 'Rejected'}")
        print(f"  Result: {status}")
        print(f"  Confidence: {result.confidence:.1f}%")
        print()


def demo_risk_mapping():
    """Demonstrate risk level to tier mapping."""
    print_header("RISK-BASED TIER SELECTION")
    
    risk_examples = [
        (RiskLevel.LOW, "User chat, simple queries"),
        (RiskLevel.MEDIUM, "API design, code review"),
        (RiskLevel.HIGH, "Production deployments, DB migrations"),
        (RiskLevel.CRITICAL, "System architecture, crisis management")
    ]
    
    for risk, example in risk_examples:
        tier = SignedAIRegistry.get_tier_by_risk(risk)
        
        print(f"{risk.value.upper()} RISK → {tier.tier.value.upper()}")
        print(f"  Example: {example}")
        print(f"  Signers: {len(tier.signers)}")
        print(f"  Required Votes: {tier.required_votes}")
        print()


def demo_cost_analysis():
    """Demonstrate cost scaling across tiers."""
    print_header("COST ANALYSIS ACROSS TIERS")
    
    tokens_in = 10_000
    tokens_out = 5_000
    
    print(f"Token count: {tokens_in:,} input + {tokens_out:,} output\n")
    
    costs = []
    for tier in SignedAITier:
        total_cost, breakdown = SignedAIRegistry.estimate_tier_cost(
            tier, tokens_in, tokens_out
        )
        costs.append((tier, total_cost, breakdown))
        
        print(f"{tier.value.upper()}: ${total_cost:.4f}")
        print(f"  Signers: {len(breakdown)}")
        print(f"  Cost per signer: ${total_cost / len(breakdown):.4f} avg")
        
        # Show most expensive signer
        most_expensive = max(breakdown.items(), key=lambda x: x[1])
        print(f"  Most expensive: {most_expensive[0].split('/')[-1]} (${most_expensive[1]:.4f})")
        print()
    
    # Cost comparison
    tier_s_cost = costs[0][1]
    tier_8_cost = costs[3][1]
    
    multiplier = tier_8_cost / tier_s_cost if tier_s_cost > 0 else 0
    
    print(f"💡 COST SCALING:")
    print(f"   Tier S → Tier 8: {multiplier:.1f}x increase")
    print(f"   Trade-off: Higher cost = Higher accuracy + More verification")


def demo_geopolitical_balance():
    """Demonstrate geopolitical balance in tiers."""
    print_header("GEOPOLITICAL BALANCE IN CONSENSUS")
    
    for tier in [SignedAITier.TIER_4, SignedAITier.TIER_6, SignedAITier.TIER_8]:
        config = SignedAIRegistry.get_tier(tier)
        is_balanced = SignedAIRegistry.validate_geopolitical_balance(tier)
        
        print(f"{tier.value.upper()}")
        print(f"  West (US): {config.west_count} signers")
        print(f"  East (CN): {config.east_count} signers")
        print(f"  Balance: {'✅ Perfect parity' if is_balanced else '❌ Imbalanced'}")
        print()


def demo_tier_recommendations():
    """Show tier recommendations for common scenarios."""
    print_header("TIER RECOMMENDATIONS BY SCENARIO")
    
    scenarios = [
        ("Chat with user", SignedAITier.TIER_S),
        ("Generate test data", SignedAITier.TIER_S),
        ("Code review (pre-merge)", SignedAITier.TIER_4),
        ("Financial analysis", SignedAITier.TIER_4),
        ("Production deployment", SignedAITier.TIER_6),
        ("Database schema change", SignedAITier.TIER_6),
        ("System architecture change", SignedAITier.TIER_8),
        ("Legal decision", SignedAITier.TIER_8),
    ]
    
    for scenario, recommended_tier in scenarios:
        config = SignedAIRegistry.get_tier(recommended_tier)
        print(f"• {scenario}")
        print(f"  → {recommended_tier.value.upper()} ({len(config.signers)} signers, "
              f"{config.required_votes} votes needed)")


def main():
    """Run all demos."""
    print("\n" + "🔐" * 35)
    print(" " * 8 + "RCT SIGNEDAI CONSENSUS SYSTEM DEMO")
    print("🔐" * 35)
    
    demo_all_tiers()
    demo_voting_scenarios()
    demo_risk_mapping()
    demo_cost_analysis()
    demo_geopolitical_balance()
    demo_tier_recommendations()
    
    print("\n" + "="*70)
    print("  Demo Complete! 🚀")
    print("  For integration demo, see: examples/full_system_demo.py")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
