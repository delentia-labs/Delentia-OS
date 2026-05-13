"""
IntentFarmer Demo — Phase 3 SDK Example

Run from the rct-platform root::

    python examples/intent_farming_demo.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_loop import IntentFarmer, IntentBlueprint, FarmResult


def main():
    farmer = IntentFarmer(fdia_threshold=0.25)

    # ── Single farm ────────────────────────────────────────────────────────
    print("=== Single Farm ===")
    result: FarmResult = farmer.farm(
        "Analyze market trends for Q1 2026",
        domain="finance",
        tier=3,
    )
    print(f"Seed:        {result.seed_intent}")
    print(f"Total farmed:{result.total_farmed}")
    print(f"Elapsed:     {result.elapsed_ms:.1f} ms")
    if result.blueprints:
        bp: IntentBlueprint = result.blueprints[0]
        print(f"Hash:        {bp.intent_hash}")
        print(f"FDIA score:  {bp.fdia_score}")
        print(f"Domain:      {bp.domain}")
        print(f"Tier:        {bp.tier}")
    print()

    # ── Warm recall ────────────────────────────────────────────────────────
    print("=== Warm Recall ===")
    if result.blueprints:
        cached = farmer.warm_recall(result.blueprints[0].intent_hash)
        print(f"Cache hit: {cached is not None}")
    print()

    # ── Bulk farm ──────────────────────────────────────────────────────────
    print("=== Bulk Farm ===")
    seeds = [
        "Research regulatory compliance for Southeast Asia",
        "Build a recommendation engine for e-commerce",
        "วิเคราะห์ตลาดหุ้นไทย ไตรมาสที่ 2",
        "Optimize supply chain logistics",
        "Design a secure authentication flow",
    ]
    results = farmer.bulk_farm(seeds, domain="technology", tier=4)
    total_farmed = sum(r.total_farmed for r in results)
    total_rejected = sum(r.rejected_count for r in results)
    print(f"Seeds:    {len(seeds)}")
    print(f"Farmed:   {total_farmed}")
    print(f"Rejected: {total_rejected}")
    for r in results:
        status = "✅" if r.total_farmed else "❌"
        print(f"  {status} {r.seed_intent[:50]}")
    print()

    print("Demo complete.")


if __name__ == "__main__":
    main()
