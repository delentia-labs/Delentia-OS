"""
HexaCore Integration Example

Demonstrates the complete workflow of:
1. Task routing to optimal model
2. API key selection
3. Cost tracking
4. Circuit breaker protection
5. Fallback chain execution

This example shows how all HexaCore components work together.
"""

import asyncio
from typing import Dict, Any
import logging

from config.key_manager import get_key
from config.hexa_core_registry import (
    TaskType, HexaCoreRegistry, SignedAITiers
)
from core.task_router import (
    route_task, ComplexityLevel, CostPriority
)
from core.cost_tracker import track_request, get_summary, get_cost_tracker
from core.circuit_breaker import (
    get_circuit_breaker_manager, call_with_fallback
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


# Mock LLM API call function
def mock_llm_call(model_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """
    Mock LLM API call for demonstration.
    
    In production, this would make actual API calls to OpenRouter or Google.
    """
    logger.info(f"Making API call to {model_id}")
    
    # Simulate response
    response = {
        "model": model_id,
        "prompt": prompt,
        "response": f"Response from {model_id}: [Generated content here]",
        "usage": {
            "input_tokens": len(prompt.split()) * 2,  # Rough estimate
            "output_tokens": 150
        }
    }
    
    return response


async def mock_llm_call_async(model_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """Async version of mock LLM call."""
    await asyncio.sleep(0.1)  # Simulate network delay
    return mock_llm_call(model_id, prompt, **kwargs)


def example_1_basic_routing():
    """Example 1: Basic task routing and execution."""
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Task Routing")
    print("="*80)
    
    # Define task
    prompt = "Write a Python function to sort a list using quicksort algorithm"
    
    # Route task to optimal model
    decision = route_task(
        task_type=TaskType.CODING_COMPLEX,
        complexity=ComplexityLevel.COMPLEX,
        cost_priority=CostPriority.BALANCED
    )
    
    print("\n📍 Routing Decision:")
    print(f"   Model: {decision.model_config.model_id}")
    print(f"   Role: {decision.model_role.value}")
    print(f"   Reasoning: {decision.reasoning}")
    print(f"   Estimated Cost: ${decision.estimated_cost_per_1k:.4f}/1K tokens")
    print(f"   Alternatives: {[alt.value for alt in decision.alternatives]}")
    
    # Get API key
    api_key = get_key(decision.key_context)
    print(f"\n🔑 API Key Context: {decision.key_context.value}")
    print(f"   Key: {api_key[:20]}...")
    
    # Make API call (mocked)
    response = mock_llm_call(
        model_id=decision.model_config.model_id,
        prompt=prompt
    )
    
    print("\n✅ Response received:")
    print(f"   Input tokens: {response['usage']['input_tokens']}")
    print(f"   Output tokens: {response['usage']['output_tokens']}")
    
    # Track cost
    entry = track_request(
        input_tokens=response['usage']['input_tokens'],
        output_tokens=response['usage']['output_tokens'],
        key_context=decision.key_context,
        model_role=decision.model_role,
        task_type=TaskType.CODING_COMPLEX.value
    )
    
    print("\n💰 Cost Tracking:")
    print(f"   Input cost: ${entry.input_cost:.4f}")
    print(f"   Output cost: ${entry.output_cost:.4f}")
    print(f"   Total cost: ${entry.total_cost:.4f}")


def example_2_circuit_breaker_fallback():
    """Example 2: Circuit breaker with fallback chain."""
    print("\n" + "="*80)
    print("EXAMPLE 2: Circuit Breaker with Fallback Chain")
    print("="*80)
    
    # Get circuit breaker manager
    cb_manager = get_circuit_breaker_manager()
    
    # Define fallback chain
    primary_model = "moonshotai/kimi-k2.5"
    fallback_models = [
        "minimax/minimax-m2.1",
        "anthropic/claude-opus-4.6"
    ]
    
    print("\n🔄 Fallback Chain:")
    print(f"   Primary: {primary_model}")
    print(f"   Fallbacks: {fallback_models}")
    
    # Execute with fallback
    try:
        result = call_with_fallback(
            primary_model=primary_model,
            fallback_models=fallback_models,
            func=mock_llm_call,
            prompt="Explain quantum computing"
        )
        
        print(f"\n✅ Request succeeded with: {result['model']}")
        
    except Exception as e:
        print(f"\n❌ All models failed: {e}")
    
    # Show circuit breaker stats
    stats = cb_manager.get_all_stats()
    print("\n📊 Circuit Breaker Stats:")
    for model_id, stat in list(stats.items())[:3]:  # Show first 3
        print(f"\n   {model_id}:")
        print(f"      State: {stat['state']}")
        print(f"      Total requests: {stat['total_requests']}")
        print(f"      Success rate: {stat['success_rate']:.1%}")


def example_3_cost_optimization():
    """Example 3: Cost optimization strategies."""
    print("\n" + "="*80)
    print("EXAMPLE 3: Cost Optimization Strategies")
    print("="*80)
    
    tasks = [
        ("Simple chat", TaskType.CHAT_CREATIVE, ComplexityLevel.SIMPLE),
        ("Routine code", TaskType.CODING_SIMPLE, ComplexityLevel.SIMPLE),
        ("Complex code", TaskType.CODING_COMPLEX, ComplexityLevel.COMPLEX),
        ("Critical decision", TaskType.CRITICAL_DECISION, ComplexityLevel.CRITICAL)
    ]
    
    print("\n💰 Cost Comparison by Task Type:")
    print(f"\n{'Task':<20} {'Model':<25} {'Cost/1K':<12} {'Savings':<10}")
    print("-" * 70)
    
    for task_name, task_type, complexity in tasks:
        # Route with cost minimization
        decision_min = route_task(
            task_type=task_type,
            complexity=complexity,
            cost_priority=CostPriority.MINIMIZE
        )
        
        # Route with quality priority
        decision_quality = route_task(
            task_type=task_type,
            complexity=complexity,
            cost_priority=CostPriority.QUALITY
        )
        
        cost_min = decision_min.estimated_cost_per_1k
        cost_quality = decision_quality.estimated_cost_per_1k
        savings = ((cost_quality - cost_min) / cost_quality * 100) if cost_quality > 0 else 0
        
        print(f"{task_name:<20} {decision_min.model_config.model_id:<25} "
              f"${cost_min:<10.4f} {savings:>6.1f}%")


def example_4_tier_consensus():
    """Example 4: SignedAI tier consensus."""
    print("\n" + "="*80)
    print("EXAMPLE 4: SignedAI Tier Consensus")
    print("="*80)
    
    tiers = ["S", "4", "6", "8"]
    
    print("\n🏛️ Tier Comparison:")
    print(f"\n{'Tier':<8} {'Models':<10} {'Consensus':<15} {'Cost/1K':<12} {'Use Case':<20}")
    print("-" * 80)
    
    for tier in tiers:
        info = SignedAITiers.get_tier_info(tier)
        threshold = info['consensus_threshold']
        required = info['consensus_required']
        
        # Estimate cost for 1K input + 1K output
        cost = SignedAITiers.calculate_tier_cost(tier, 1000, 1000)
        
        use_cases = {
            "S": "Fast, cheap tasks",
            "4": "Standard operations",
            "6": "Production consensus",
            "8": "Critical decisions"
        }
        
        print(f"{tier:<8} {info['model_count']:<10} "
              f"{threshold:.0%} ({required}/{info['model_count']}){'':<5} "
              f"${cost:<10.2f} {use_cases[tier]:<20}")
    
    # Show geopolitical balance
    print("\n🌍 Geopolitical Balance:")
    for tier in tiers:
        info = SignedAITiers.get_tier_info(tier)
        balance = info['geopolitical_balance']
        print(f"   Tier {tier}: {balance['ratio']} (W:{balance['western']}, E:{balance['eastern']})")


def example_5_cost_tracking_summary():
    """Example 5: Cost tracking and reporting."""
    print("\n" + "="*80)
    print("EXAMPLE 5: Cost Tracking Summary")
    print("="*80)
    
    # Simulate multiple requests
    scenarios = [
        (TaskType.CHAT_CREATIVE, 500, 300),
        (TaskType.CODING_SIMPLE, 800, 400),
        (TaskType.CODING_COMPLEX, 1200, 600),
        (TaskType.FINANCE_HEALTH, 600, 400),
        (TaskType.LONG_READING, 5000, 1000)
    ]
    
    print("\n📝 Simulating requests...")
    for task_type, input_tokens, output_tokens in scenarios:
        decision = route_task(task_type=task_type)
        track_request(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            key_context=decision.key_context,
            model_role=decision.model_role,
            task_type=task_type.value
        )
    
    # Get summary
    summary = get_summary()
    
    print("\n💰 Cost Summary:")
    print(f"   Total cost: ${summary['total']['cost']:.4f}")
    print(f"   Total tokens: {summary['total']['tokens']:,}")
    print(f"   Total requests: {summary['total']['requests']}")
    print(f"   Avg cost per request: ${summary['total']['cost'] / summary['total']['requests']:.4f}")
    
    print("\n📊 Cost by Model:")
    for model, cost in sorted(summary['by_model'].items(), key=lambda x: x[1], reverse=True):
        print(f"   {model}: ${cost:.4f}")
    
    print("\n🔑 Cost by Context:")
    for context, cost in summary['by_context'].items():
        print(f"   {context}: ${cost:.4f}")


async def example_6_async_execution():
    """Example 6: Async execution with circuit breaker."""
    print("\n" + "="*80)
    print("EXAMPLE 6: Async Execution")
    print("="*80)
    
    # Get circuit breaker manager
    cb_manager = get_circuit_breaker_manager()
    
    # Define multiple tasks
    tasks = [
        ("Task 1: Code review", TaskType.CODING_COMPLEX),
        ("Task 2: Chat response", TaskType.CHAT_CREATIVE),
        ("Task 3: Document analysis", TaskType.LONG_READING)
    ]
    
    print(f"\n🚀 Executing {len(tasks)} tasks concurrently...")
    
    async def execute_task(name: str, task_type: TaskType):
        decision = route_task(task_type=task_type)
        
        try:
            result = await cb_manager.call_with_fallback_async(
                primary_model=decision.model_config.model_id,
                fallback_models=[
                    HexaCoreRegistry.get_model(alt).model_id 
                    for alt in decision.alternatives[:2]
                ],
                func=mock_llm_call_async,
                prompt=f"Execute {name}"
            )
            
            print(f"   ✅ {name} completed with {result['model']}")
            return result
            
        except Exception as e:
            print(f"   ❌ {name} failed: {e}")
            return None
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*[
        execute_task(name, task_type)
        for name, task_type in tasks
    ])
    
    successful = sum(1 for r in results if r is not None)
    print(f"\n📊 Results: {successful}/{len(tasks)} tasks completed successfully")


def example_7_budget_alerts():
    """Example 7: Budget alerts and limits."""
    print("\n" + "="*80)
    print("EXAMPLE 7: Budget Alerts")
    print("="*80)
    
    # Get cost tracker
    tracker = get_cost_tracker()
    
    # Set budgets
    tracker.set_daily_budget(10.0)
    tracker.set_monthly_budget(300.0)
    tracker.set_alert_threshold(0.80)  # 80%
    
    print("\n💵 Budget Configuration:")
    print("   Daily budget: $10.00")
    print("   Monthly budget: $300.00")
    print("   Alert threshold: 80%")
    
    # Simulate high-cost requests
    print("\n📝 Simulating high-cost requests...")
    for i in range(5):
        decision = route_task(
            task_type=TaskType.CRITICAL_DECISION,
            complexity=ComplexityLevel.CRITICAL
        )
        
        track_request(
            input_tokens=2000,
            output_tokens=1000,
            key_context=decision.key_context,
            model_role=decision.model_role
        )
    
    # Check alerts
    alerts = tracker.get_alerts()
    
    if alerts:
        print(f"\n⚠️  Budget Alerts ({len(alerts)}):")
        for alert in alerts[-3:]:  # Show last 3
            print(f"\n   Type: {alert['type']}")
            print(f"   Current: ${alert['current']:.2f}")
            print(f"   Budget: ${alert['budget']:.2f}")
            print(f"   Usage: {alert['percent']:.1f}%")
            print(f"   Exceeded: {'Yes' if alert['exceeded'] else 'No'}")
    else:
        print("\n✅ No budget alerts")


def main():
    """Run all examples."""
    print("\n" + "="*80)
    print("HEXACORE INTEGRATION EXAMPLES")
    print("="*80)
    print("\nDemonstrating complete HexaCore workflow with:")
    print("  • Task routing")
    print("  • API key management")
    print("  • Cost tracking")
    print("  • Circuit breaker")
    print("  • Fallback chains")
    print("  • Budget alerts")
    
    try:
        # Run synchronous examples
        example_1_basic_routing()
        example_2_circuit_breaker_fallback()
        example_3_cost_optimization()
        example_4_tier_consensus()
        example_5_cost_tracking_summary()
        example_7_budget_alerts()
        
        # Run async example
        print("\n" + "="*80)
        asyncio.run(example_6_async_execution())
        
        print("\n" + "="*80)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
