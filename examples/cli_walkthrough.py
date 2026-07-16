"""
RCT Platform — CLI Walkthrough Demo
=====================================

Demonstrates the full RCT Control Plane pipeline using the Python API
(equivalent to the `rct` CLI commands) — no external API keys required.

Pipeline:
  1. compile  — Natural language → IntentObject
  2. build    — IntentObject → ExecutionGraph
  3. evaluate — ExecutionGraph + policies → governance decision
  4. status   — Inspect compiled state
  5. audit    — Replay signed execution record

Run:
    python examples/cli_walkthrough.py
    python examples/cli_walkthrough.py --verbose
    python examples/cli_walkthrough.py --intent "Optimize database query performance"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.dsl_parser import DSLParser
from rct_control_plane.policy_language import (
    PolicyEvaluator,
    PolicyRule,
    PolicyCondition,
    PolicyAction,
    PolicyPriority,
    PolicyScope,
    ConditionOperator,
)
from rct_control_plane.control_plane_state import ControlPlanePhase
from rct_control_plane.intent_schema import IntentObject
from rct_control_plane.observability import ControlPlaneObserver
from rct_control_plane.default_policies import (
    create_cost_cap_policy,
    create_risk_escalation_policy,
)


def _enum_val(x):
    """Get string value from an enum-or-str field (handles use_enum_values=True)."""
    return x.value if hasattr(x, 'value') else x


# ---------------------------------------------------------------------------
# Step 1 — Compile
# ---------------------------------------------------------------------------

def step_compile(
    natural_language: str,
    user_id: str = "demo-user-001",
    verbose: bool = False,
) -> IntentObject:
    """
    Step 1: rct compile "<intent>"

    Translates a natural language instruction into a structured IntentObject.
    Equivalent to: rct compile "..." --user-id demo-user-001
    """
    observer = ControlPlaneObserver()
    compiler = IntentCompiler(observer=observer)

    print("\n── Step 1: COMPILE ─────────────────────────────────────────")
    print(f"  Input : \"{natural_language}\"")

    result = compiler.compile(
        natural_language=natural_language,
        user_id=user_id,
        user_tier="enterprise",
    )

    intent = result.intent
    print(f"  Intent ID      : {intent.id}")
    print(f"  Intent type    : {_enum_val(intent.intent_type)}")
    print(f"  Risk profile   : {_enum_val(intent.risk_profile)}")
    print(f"  Priority       : {_enum_val(intent.priority)}")
    print(f"  Template match : {intent.matched_template or 'none'} ({intent.template_confidence:.0%})")
    print(f"  Budget         : ${intent.budget.max_cost_usd if intent.budget else 'N/A'}")

    if verbose:
        print("\n  Full intent (JSON excerpt):")
        d = {
            "id": str(intent.id),
            "goal": intent.goal,
            "intent_type": _enum_val(intent.intent_type),
            "risk_profile": _enum_val(intent.risk_profile),
            "priority": _enum_val(intent.priority),
        }
        print("  " + json.dumps(d, indent=2).replace("\n", "\n  "))

    print("  Status: ✓ Compiled successfully")
    return intent


# ---------------------------------------------------------------------------
# Step 2 — Build
# ---------------------------------------------------------------------------

def step_build(intent: IntentObject, verbose: bool = False) -> Any:
    """
    Step 2: rct build --intent-id <id>

    Constructs the ExecutionGraph from the compiled IntentObject.
    Uses the intent template system to generate DSL, then parses it.
    Equivalent to: rct build --dsl-text <generated> --intent-id <id>
    """
    from rct_control_plane.execution_graph_ir import ExecutionGraph
    from rct_control_plane.intent_templates import RefactorTemplate, BuildAppTemplate

    observer = ControlPlaneObserver()
    parser = DSLParser(observer=observer)

    print("\n── Step 2: BUILD ───────────────────────────────────────────")
    print(f"  Building execution graph for intent: {intent.id}")

    # Select template based on intent type and generate DSL
    intent_type = _enum_val(intent.intent_type)
    if intent_type in ("BUILD_APP",):
        template = BuildAppTemplate()
    else:
        template = RefactorTemplate()  # default/catch-all template

    plan = template.to_plan(intent)
    dsl_text = template.to_dsl(plan)
    graph: ExecutionGraph = parser.parse(dsl_text, str(intent.id))

    node_count = len(graph.nodes)
    edge_count = len(graph.edges)
    errors = graph.validate()

    print(f"  Nodes          : {node_count}")
    print(f"  Edges          : {edge_count}")
    print(f"  Graph valid    : {'✓ yes' if not errors else '✗ ' + str(errors)}")

    if verbose and graph.nodes:
        print("\n  Node types:")
        from collections import Counter
        node_types = Counter(_enum_val(n.node_type) for n in graph.nodes.values())
        for nt, cnt in node_types.items():
            print(f"    {nt}: {cnt}")

    estimated_cost = sum(
        float(n.estimated_cost) for n in graph.nodes.values()
    )
    print(f"  Estimated cost : ${estimated_cost:.4f}")
    print("  Status: ✓ Graph built")
    return graph


# ---------------------------------------------------------------------------
# Step 3 — Evaluate (Governance)
# ---------------------------------------------------------------------------

def step_evaluate(intent: IntentObject, verbose: bool = False) -> bool:
    """
    Step 3: rct evaluate --intent-id <id>

    Runs all registered policies against the intent.
    Equivalent to: rct evaluate --intent-id <id>
    """
    observer = ControlPlaneObserver()
    evaluator = PolicyEvaluator(observer=observer)

    # Register default policies
    evaluator.add_rule(create_cost_cap_policy(max_cost_usd=Decimal("1000.00")))
    evaluator.add_rule(create_risk_escalation_policy())

    # Register a custom demo policy
    evaluator.add_rule(PolicyRule(
        name="Production Safety Gate",
        description="Require approval for DEPLOY intents",
        scope=PolicyScope.INTENT,
        priority=PolicyPriority.HIGH,
        conditions=[
            PolicyCondition(
                field="intent_type",
                operator=ConditionOperator.EQUALS,
                value="DEPLOY",
            )
        ],
        action=PolicyAction.REQUIRE_APPROVAL,
        action_metadata={"approver": "ops-lead", "reason": "Production deploy gate"},
    ))

    print("\n── Step 3: EVALUATE (Governance) ───────────────────────────")
    print(f"  Evaluating intent: {intent.id}")
    print(f"  Policies registered: {len(evaluator.rules)}")

    eval_result = evaluator.evaluate_intent(intent)

    if eval_result.decision == PolicyAction.APPROVE and not eval_result.requires_approval:
        print("  Result         : ✓ APPROVED — no policy violations")
        approved = True
    elif eval_result.decision in (PolicyAction.REJECT, PolicyAction.ESCALATE):
        print(f"  Result         : ✗ BLOCKED — {eval_result.decision_reason or 'governance violation'}")
        for v in eval_result.violations:
            print(f"    • {v}")
        approved = False
    else:
        # REQUIRE_APPROVAL or NOTIFY
        print(f"  Result         : ⚠ REQUIRES APPROVAL — {eval_result.decision_reason or 'policy triggered'}")
        for w in eval_result.warnings:
            print(f"    • {w}")
        approved = True  # Soft block — proceed in demo

    if verbose:
        print(f"\n  All policy checks: {len(evaluator.rules)} rules evaluated")

    return approved


# ---------------------------------------------------------------------------
# Step 4 — Status
# ---------------------------------------------------------------------------

def step_status(intent: IntentObject, approved: bool, verbose: bool = False) -> None:
    """
    Step 4: rct status <id>

    Shows the current control plane phase and metadata.
    Equivalent to: rct status <id>
    """
    phase = ControlPlanePhase.APPROVED if approved else ControlPlanePhase.FAILED

    print("\n── Step 4: STATUS ──────────────────────────────────────────")
    print(f"  Intent ID  : {intent.id}")
    print(f"  Goal       : {intent.goal[:60]}...")
    print(f"  Phase      : {phase.value}")
    print(f"  Compiled   : {intent.compiled_at}")
    print(f"  Version    : {intent.compiler_version}")

    phase_map = {
        ControlPlanePhase.APPROVED: "✓ Ready for execution",
        ControlPlanePhase.FAILED:   "✗ Blocked by governance",
    }
    print(f"  Disposition: {phase_map.get(phase, phase.value)}")


# ---------------------------------------------------------------------------
# Step 5 — Audit
# ---------------------------------------------------------------------------

def step_audit(intent: IntentObject, verbose: bool = False) -> None:
    """
    Step 5: rct audit <id>

    Shows the immutable audit trail for this intent.
    Equivalent to: rct audit <id>
    """
    print("\n── Step 5: AUDIT ───────────────────────────────────────────")
    print(f"  Audit trail for intent: {intent.id}")

    # Build a deterministic audit record from intent metadata
    audit_events = [
        {
            "seq": 1,
            "event": "intent_received",
            "actor": "user",
            "timestamp": intent.compiled_at.isoformat() if intent.compiled_at else "n/a",
            "detail": f"NL input: \"{intent.natural_language_input or intent.goal[:40]}...\"",
        },
        {
            "seq": 2,
            "event": "intent_compiled",
            "actor": "IntentCompiler",
            "timestamp": intent.compiled_at.isoformat() if intent.compiled_at else "n/a",
            "detail": f"template={intent.matched_template or 'none'}, confidence={intent.template_confidence:.0%}",
        },
        {
            "seq": 3,
            "event": "graph_built",
            "actor": "DSLParser",
            "timestamp": "n/a",
            "detail": "ExecutionGraph validated",
        },
        {
            "seq": 4,
            "event": "policy_evaluated",
            "actor": "PolicyEvaluator",
            "timestamp": "n/a",
            "detail": "default_policies + 1 custom rule",
        },
    ]

    for ev in audit_events:
        print(f"  [{ev['seq']}] {ev['event']:25s} | {ev['actor']:20s} | {ev['detail']}")

    print("\n  Note: In production, audit events are cryptographically")
    print("  chained via Ed25519-signed JITNA packets. Use:")
    print(f"    rct audit {intent.id} --verify")
    print("  to verify the chain integrity.")


# ---------------------------------------------------------------------------
# Full walkthrough
# ---------------------------------------------------------------------------

def run_walkthrough(
    intent_text: str = "Refactor the authentication module to use JWT tokens",
    verbose: bool = False,
) -> None:
    print("\n" + "=" * 65)
    print("  RCT PLATFORM — CONTROL PLANE CLI WALKTHROUGH")
    print("=" * 65)
    print("  This demo replicates the full `rct` CLI pipeline:")
    print("  compile → build → evaluate → status → audit")
    print("=" * 65)

    # Step 1: Compile
    intent = step_compile(intent_text, verbose=verbose)

    # Step 2: Build execution graph
    graph = step_build(intent, verbose=verbose)

    # Step 3: Governance evaluation
    approved = step_evaluate(intent, verbose=verbose)

    # Step 4: Status
    step_status(intent, approved, verbose=verbose)

    # Step 5: Audit trail
    step_audit(intent, verbose=verbose)

    # Final summary
    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE")
    print(f"  Intent : {str(intent.id)[:8]}...")
    print(f"  Result : {'✓ APPROVED — would proceed to execute' if approved else '✗ BLOCKED — governance intervention'}")
    print("=" * 65)
    print()
    print("  Equivalent CLI commands:")
    print(f'    rct compile "{intent_text}" --user-id demo-user-001')
    print(f"    rct build   --intent-id {str(intent.id)[:8]}...")
    print(f"    rct evaluate --intent-id {str(intent.id)[:8]}...")
    print(f"    rct status  {str(intent.id)[:8]}...")
    print(f"    rct audit   {str(intent.id)[:8]}...")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="RCT Control Plane CLI Walkthrough")
    parser.add_argument(
        "--intent",
        default="Refactor the authentication module to use JWT tokens",
        help="Natural language intent to compile (default: refactor auth module)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print extended detail")
    args = parser.parse_args()

    run_walkthrough(intent_text=args.intent, verbose=args.verbose)


if __name__ == "__main__":
    main()
