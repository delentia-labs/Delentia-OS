#!/usr/bin/env python3
"""
RCT Hexa-Core Architecture Demo

Demonstrates:
1. All 6 core models
2. Model capabilities and pricing
3. Task routing examples
4. Cost comparison
5. Geopolitical balance
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rct_platform.config import (
    HexaCoreRole,
    HexaCoreRegistry,
    TaskIntent,
    ModelRouter
)


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def demo_all_models():
    """Display all 6 Hexa-Core models."""
    print_header("RCT HEXA-CORE ARCHITECTURE - ALL MODELS")
    
    for i, (role, model) in enumerate(HexaCoreRegistry.MODELS.items(), 1):
        print(f"{i}. {role.value.upper().replace('_', ' ')}")
        print(f"   Model: {model.id}")
        print(f"   Provider: {model.provider} ({model.country})")
        print(f"   Pricing: ${model.cost_input:.2f} / ${model.cost_output:.2f} per 1M tokens")
        print(f"   Context: {model.context_window:,} tokens")
        print(f"   Specialties: {', '.join(model.specialties[:3])}")
        
        if model.programming_rank:
            print(f"   Programming Rank: #{model.programming_rank}")
        if model.reasoning_rank:
            print(f"   Reasoning Rank: #{model.reasoning_rank}")
        
        print(f"   Use Cases: {', '.join(model.use_cases[:2])}")
        print()


def demo_geopolitical_balance():
    """Demonstrate geopolitical balance."""
    print_header("GEOPOLITICAL BALANCE")
    
    balance = HexaCoreRegistry.get_geopolitical_balance()
    
    print("Model Distribution:")
    for country, count in balance.items():
        print(f"  {country}: {count} models")
    
    print("\nWest (US) Models:")
    us_models = HexaCoreRegistry.get_models_by_country("US")
    for model in us_models:
        print(f"  • {model.id} ({model.role.value})")
    
    print("\nEast (CN) Models:")
    cn_models = HexaCoreRegistry.get_models_by_country("CN")
    for model in cn_models:
        print(f"  • {model.id} ({model.role.value})")
    
    print(f"\n✅ Balance: {balance['US']} West + {balance['CN']} East = Perfect parity")


def demo_task_routing():
    """Demonstrate task routing."""
    print_header("TASK ROUTING EXAMPLES")
    
    examples = [
        (TaskIntent.CODING_COMPLEX, "Complex system design with visual analysis"),
        (TaskIntent.CODING_SIMPLE, "Write unit tests for API endpoint"),
        (TaskIntent.FINANCE, "Analyze quarterly financial report"),
        (TaskIntent.RAG_RETRIEVAL, "Search 100,000 lines of documentation"),
        (TaskIntent.CHAT, "Natural user conversation in Thai"),
        (TaskIntent.CRITICAL, "Critical architecture decision")
    ]
    
    for intent, description in examples:
        model_id, role = ModelRouter.route_task(intent)
        model = HexaCoreRegistry.get_model(role)
        
        print(f"Task: {description}")
        print(f"  Intent: {intent.value}")
        print(f"  → Routes to: {role.value.replace('_', ' ').title()}")
        print(f"  → Model: {model.id}")
        print(f"  → Why: {model.specialties[0]}")
        print()


def demo_cost_comparison():
    """Demonstrate cost optimization."""
    print_header("COST OPTIMIZATION - SIMPLE VS COMPLEX CODING")
    
    tokens_in = 10_000
    tokens_out = 5_000
    
    # Simple task → Cheap model
    simple_cost = ModelRouter.estimate_cost(
        TaskIntent.CODING_SIMPLE,
        input_tokens=tokens_in,
        output_tokens=tokens_out
    )
    
    # Complex task → Expensive model
    complex_cost = ModelRouter.estimate_cost(
        TaskIntent.CODING_COMPLEX,
        input_tokens=tokens_in,
        output_tokens=tokens_out
    )
    
    # Architecture → Most expensive
    critical_cost = ModelRouter.estimate_cost(
        TaskIntent.ARCHITECTURE,
        input_tokens=tokens_in,
        output_tokens=tokens_out
    )
    
    print(f"Token count: {tokens_in:,} input + {tokens_out:,} output\n")
    
    print(f"1. SIMPLE CODING (Unit tests, bug fixes)")
    print(f"   Model: {simple_cost['model_id']}")
    print(f"   Cost: ${simple_cost['cost_usd']:.4f}")
    print()
    
    print(f"2. COMPLEX CODING (System integration, visual)")
    print(f"   Model: {complex_cost['model_id']}")
    print(f"   Cost: ${complex_cost['cost_usd']:.4f}")
    print()
    
    print(f"3. ARCHITECTURE (Critical decisions)")
    print(f"   Model: {critical_cost['model_id']}")
    print(f"   Cost: ${critical_cost['cost_usd']:.4f}")
    print()
    
    # Calculate savings
    savings_vs_complex = (
        (complex_cost['cost_usd'] - simple_cost['cost_usd']) / 
        complex_cost['cost_usd'] * 100
    )
    savings_vs_critical = (
        (critical_cost['cost_usd'] - simple_cost['cost_usd']) / 
        critical_cost['cost_usd'] * 100
    )
    
    print(f"💡 SAVINGS:")
    print(f"   • Simple vs Complex: {savings_vs_complex:.1f}% cheaper")
    print(f"   • Simple vs Critical: {savings_vs_critical:.1f}% cheaper")
    print(f"\n✅ Strategy: Delegate simple tasks to Junior Builder, save 40-60%!")


def demo_specialist_capabilities():
    """Demonstrate specialist model capabilities."""
    print_header("SPECIALIST MODELS - DOMAIN EXPERTISE")
    
    specialists = [
        (HexaCoreRole.SPECIALIST, "Finance & Health #1"),
        (HexaCoreRole.LIBRARIAN, "Long Context (2M tokens), Science #1"),
        (HexaCoreRole.HUMANIZER, "Roleplay #1, Natural Language")
    ]
    
    for role, expertise in specialists:
        model = HexaCoreRegistry.get_model(role)
        print(f"{role.value.upper().replace('_', ' ')}")
        print(f"  Expertise: {expertise}")
        print(f"  Model: {model.id}")
        print(f"  Best for: {', '.join(model.use_cases[:3])}")
        print()


def demo_ranking_summary():
    """Display ranking summary."""
    print_header("PERFORMANCE RANKINGS")
    
    print("Programming #1 (Tied):")
    print(f"  • Supreme Architect: {HexaCoreRegistry.get_model_id(HexaCoreRole.SUPREME_ARCHITECT)}")
    print(f"  • Lead Builder: {HexaCoreRegistry.get_model_id(HexaCoreRole.LEAD_BUILDER)}")
    print()
    
    print("Programming #2:")
    print(f"  • Junior Builder: {HexaCoreRegistry.get_model_id(HexaCoreRole.JUNIOR_BUILDER)}")
    print()
    
    print("Reasoning #1:")
    architect = HexaCoreRegistry.get_model(HexaCoreRole.SUPREME_ARCHITECT)
    print(f"  • Supreme Architect: {architect.id}")
    print()
    
    print("Reasoning #2:")
    humanizer = HexaCoreRegistry.get_model(HexaCoreRole.HUMANIZER)
    print(f"  • Humanizer: {humanizer.id}")
    print()
    
    print("Context Window King:")
    librarian = HexaCoreRegistry.get_longest_context()
    print(f"  • Librarian: {librarian.id} ({librarian.context_window:,} tokens)")
    print()
    
    print("Cost Champion:")
    junior = HexaCoreRegistry.get_cheapest_coder()
    print(f"  • Junior Builder: ${junior.cost_input}/{junior.cost_output} per 1M tokens")


def main():
    """Run all demos."""
    print("\n" + "🌟" * 35)
    print(" " * 10 + "RCT HEXA-CORE ARCHITECTURE DEMO")
    print("🌟" * 35)
    
    demo_all_models()
    demo_geopolitical_balance()
    demo_task_routing()
    demo_cost_comparison()
    demo_specialist_capabilities()
    demo_ranking_summary()
    
    print("\n" + "="*70)
    print("  Demo Complete! 🚀")
    print("  For API usage, see: examples/api_usage_demo.py")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
