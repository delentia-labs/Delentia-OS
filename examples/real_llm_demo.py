#!/usr/bin/env python3
"""
real_llm_demo.py — RCT Platform End-to-End Demo with Real LLM

Demonstrates the full control plane pipeline:
  1. Intent compilation (with real LLM if API key provided, regex fallback otherwise)
  2. Policy evaluation (default enterprise policies)
  3. Approval gate simulation
  4. Execution plan preview

Requirements
------------
Base usage (regex compiler, no API keys needed)::

    python examples/real_llm_demo.py

With OpenAI (richer intent classification)::

    OPENAI_API_KEY=sk-... python examples/real_llm_demo.py

With Anthropic::

    ANTHROPIC_API_KEY=sk-ant-... python examples/real_llm_demo.py

Install optional dependencies::

    pip install delentia-os[llm,persistence]

Environment Variables
---------------------
- ``OPENAI_API_KEY``          — OpenAI API key for GPT-based classification
- ``ANTHROPIC_API_KEY``       — Anthropic API key for Claude-based classification
- ``RCT_LLM_PROVIDER``        — 'openai' | 'anthropic' | 'regex'  (default: auto)
- ``RCT_OPENAI_MODEL``        — OpenAI model (default: gpt-4o-mini)
- ``RCT_ANTHROPIC_MODEL``     — Anthropic model (default: claude-3-haiku-20240307)
- ``RCT_DB_PATH``             — SQLite DB path (default: ./rct_control_plane.db)
"""

from __future__ import annotations

import os
import sys
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow running from repository root without install
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rct_control_plane.intent_compiler import IntentCompiler, _detect_active_provider
from rct_control_plane.policy_language import PolicyEvaluator
from rct_control_plane.plan_engine import PlanEngine
from rct_control_plane.default_policies import get_default_policies
from rct_control_plane.observability import ControlPlaneObserver, get_prometheus_metrics
from rct_control_plane.persistence import ControlPlanePersistence


# ---------------------------------------------------------------------------
# ANSI colour helpers (no external deps)
# ---------------------------------------------------------------------------
_IS_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _IS_TTY else text

def _bold(t: str) -> str: return _c("1", t)
def _green(t: str) -> str: return _c("32", t)
def _yellow(t: str) -> str: return _c("33", t)
def _red(t: str) -> str: return _c("31", t)
def _cyan(t: str) -> str: return _c("36", t)
def _dim(t: str) -> str: return _c("2", t)


# ---------------------------------------------------------------------------
# Demo intents — a mix of low/medium/high risk
# ---------------------------------------------------------------------------
DEMO_INTENTS = [
    {
        "text": "Refactor the authentication module to use clean architecture with max cost $1.50",
        "user_id": "demo-user-001",
        "tier": "PRO",
    },
    {
        "text": "Build a new REST API endpoint for user profile management with validation",
        "user_id": "demo-user-002",
        "tier": "ENTERPRISE",
    },
    {
        "text": "Deploy all microservices to production immediately — system-wide release",
        "user_id": "demo-user-003",
        "tier": "ENTERPRISE",
    },
    {
        "text": "Analyze security vulnerabilities in the payment processing module",
        "user_id": "demo-user-004",
        "tier": "PRO",
    },
]


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------
_SEP = "─" * 72

def _section(title: str) -> None:
    print(f"\n{_SEP}")
    print(f"  {_bold(title)}")
    print(_SEP)


def _kv(key: str, value: str, width: int = 28) -> None:
    print(f"  {_dim(key.ljust(width))} {value}")


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------
def run_demo() -> None:
    print(_bold("\n🤖 RCT Platform — End-to-End Control Plane Demo"))
    print(_dim("   Constitutional AI operating system pipeline\n"))

    # Setup
    observer = ControlPlaneObserver()
    compiler = IntentCompiler(observer=observer)
    evaluator = PolicyEvaluator(observer=observer)
    for policy in get_default_policies():
        evaluator.add_rule(policy)
    engine = PlanEngine(observer=observer)
    db = ControlPlanePersistence()

    # Report active backend
    active_provider = _detect_active_provider()
    _kv("LLM Provider", _green(active_provider) if active_provider != "regex" else _yellow("regex (fallback)"))
    _kv("Storage", _green(f"SQLite @ {db.db_path}"))
    has_prom = get_prometheus_metrics() is not None
    _kv("Prometheus", _green("enabled (prometheus-client)") if has_prom else _yellow("disabled (install delentia-os[monitoring])"))

    if active_provider == "regex":
        print(_yellow("\n  ⚠  No LLM API key detected — using regex classifier."))
        print(_dim("     Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable real LLM.\n"))

    # Process each demo intent
    for i, demo in enumerate(DEMO_INTENTS, start=1):
        _section(f"Intent {i}/{len(DEMO_INTENTS)}")
        print(f'  "{_cyan(demo["text"])}"')
        print()

        # ---- Step 1: Compile ----
        t0 = time.perf_counter()
        result = compiler.compile(
            demo["text"],
            user_id=demo["user_id"],
            user_tier=demo["tier"],
        )
        compile_ms = (time.perf_counter() - t0) * 1000

        if not result.success or not result.intent:
            _kv("Compile", _red(f"FAILED: {'; '.join(result.errors)}"))
            continue

        intent = result.intent
        _kv("Compile", _green(f"OK ({compile_ms:.1f} ms)"))
        _kv("Intent ID", str(intent.id)[:16] + "…")
        _kv("Type", _cyan(str(intent.intent_type)))
        _kv("Priority", str(intent.priority))
        _kv("Risk Profile", str(intent.risk_profile))
        _kv("Provider Used", result.warnings[0] if result.warnings else active_provider)

        # ---- Step 2: Plan (cost simulation) ----
        plan = engine.simulate(demo["text"], user_id=demo["user_id"], user_tier=demo["tier"])
        _kv("Estimated Cost", f"${plan.estimated_cost_usd:.4f} USD")
        if plan.models_roster:
            model_summary = ", ".join(m.model_id.split("/")[-1] for m in plan.models_roster[:3])
            _kv("Models", model_summary + ("…" if len(plan.models_roster) > 3 else ""))

        # ---- Step 3: Policy evaluation ----
        eval_result = evaluator.evaluate_intent(intent)
        decision_str = str(eval_result.decision)
        if "APPROVE" in decision_str:
            _kv("Policy Gate", _green("ALLOW"))
        elif eval_result.requires_approval:
            _kv("Policy Gate", _yellow("REQUIRE APPROVAL"))
        else:
            _kv("Policy Gate", _red(f"BLOCKED — {eval_result.decision_reason}"))

        if eval_result.triggered_rules:
            rules_str = ", ".join(r.name for r in eval_result.triggered_rules[:3])
            _kv("Triggered Rules", rules_str)

        # ---- Step 4: Persist ----
        db.save_intent(
            intent_id=str(intent.id),
            user_id=demo["user_id"],
            intent_type=str(intent.intent_type),
            goal=demo["text"],
            user_tier=demo["tier"],
            is_valid=result.success,
            errors=result.errors,
        )
        _kv("Persisted", _dim(f"SQLite row saved (id={str(intent.id)[:8]}…)"))

    # ---- Final: metrics summary ----
    _section("Observability Summary")
    metrics = observer.get_metrics_summary()
    _kv("Total Intents", str(metrics["total_intents"]))
    _kv("Compilations", str(metrics["total_compilations"]))
    _kv("Policy Evals", str(metrics["total_policy_evaluations"]))
    _kv("Failures", str(metrics["total_failures"]))
    _kv("Audit Entries", str(metrics["audit_trail_entries"]))

    if has_prom:
        prom_text = get_prometheus_metrics() or ""
        counter_lines = [ln for ln in prom_text.splitlines() if not ln.startswith("#")]
        print(f"\n  {_bold('Prometheus counters:')}")
        for ln in counter_lines[:10]:
            print(f"    {_dim(ln)}")

    persisted = db.list_intents(limit=5)
    print(f"\n  {_bold('Recent SQLite records:')} {len(persisted)} intent(s)")
    for row in persisted:
        print(f"    {_dim(row['id'][:16])}… {row['intent_type']:20s} {row['created_at'][:19]}")

    print(f"\n{_SEP}")
    print(_green(f"  ✓ Demo complete. {len(DEMO_INTENTS)} intents processed successfully."))
    print(_SEP + "\n")


if __name__ == "__main__":
    run_demo()
