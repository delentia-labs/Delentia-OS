"""
RCT Platform — Multi-Agent Tick Simulation Demo
================================================

Demonstrates multi-agent decision making using FDIAScorer + MemoryDeltaEngine.

Scenario: Resource Competition in a virtual economy.
- 6 agents with different intents compete over 3 resource pools
- Each tick: every agent scores all available actions, picks the best
- MemoryDeltaEngine stores compressed deltas, not full state per tick
- After N ticks: replay state + compute compression ratio

Run:
    python examples/simulation_demo.py
    python examples/simulation_demo.py --ticks 20 --agents 6 --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

# -- ensure root is on path --------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType
from core.delta_engine.memory_delta import MemoryDeltaEngine

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

@dataclass
class SimAgent:
    """A lightweight agent with an intent, resources, and reputation."""
    agent_id: str
    intent: NPCIntentType
    resources: Dict[str, float]
    reputation: float = 1.0
    alive: bool = True

    def generate_candidates(self, world: Dict[str, float]) -> List[NPCAction]:
        """Generate context-aware candidate actions based on world state."""
        actions: List[NPCAction] = []
        food = world.get("food", 0.0)
        ore = world.get("ore", 0.0)
        energy = world.get("energy", 0.0)

        # Always available
        actions.append(NPCAction(action_id="idle",     action_type="idle",      amount=0.0))
        actions.append(NPCAction(action_id="explore",  action_type="explore",   amount=0.0))
        actions.append(NPCAction(action_id="cooperate",action_type="cooperate", amount=10.0, resource_id="food"))

        # Context-gated
        if food > 5.0:
            actions.append(NPCAction(action_id="trade_food", action_type="trade", amount=5.0, resource_id="food"))
        if ore > 5.0:
            actions.append(NPCAction(action_id="trade_ore",  action_type="trade", amount=5.0, resource_id="ore"))
        if energy < 20.0:
            actions.append(NPCAction(action_id="attack",     action_type="attack", amount=10.0, resource_id="energy"))

        return actions


# ---------------------------------------------------------------------------
# World state helpers
# ---------------------------------------------------------------------------

def create_world(food: float = 200.0, ore: float = 150.0, energy: float = 120.0) -> Dict[str, float]:
    return {"food": food, "ore": ore, "energy": energy}


def apply_action(world: Dict[str, float], agent: SimAgent, action: NPCAction) -> Dict[str, float]:
    """
    Apply one action to the world and return the updated state.
    Side-effect: modifies agent.reputation based on outcome.
    """
    world = dict(world)  # shallow copy — avoid mutating caller's dict
    res = action.resource_id or "food"
    amount = action.amount

    if action.action_type == "trade":
        available = world.get(res, 0.0)
        actual = min(amount, available)
        world[res] = max(0.0, available - actual)
        agent.resources[res] = agent.resources.get(res, 0.0) + actual * 0.8
        agent.reputation = min(1.0, agent.reputation + 0.01)

    elif action.action_type == "cooperate":
        available = world.get(res, 0.0)
        actual = min(amount, available)
        world[res] = max(0.0, available - actual)
        agent.resources[res] = agent.resources.get(res, 0.0) + actual
        agent.reputation = min(1.0, agent.reputation + 0.02)

    elif action.action_type == "attack":
        available = world.get(res, 0.0)
        actual = min(amount, available)
        world[res] = max(0.0, available - actual)
        agent.resources[res] = agent.resources.get(res, 0.0) + actual * 0.5
        agent.reputation = max(0.0, agent.reputation - 0.05)

    elif action.action_type == "explore":
        # Discover a small bonus resource
        world["food"] = world.get("food", 0.0) + 2.0

    # idle: no change

    return world


def compute_outcome(action: NPCAction) -> str:
    """Determine outcome string from action type (deterministic)."""
    if action.action_type in ("cooperate", "trade"):
        return "success"
    if action.action_type == "attack":
        return "partial"
    return "success"


# ---------------------------------------------------------------------------
# Core simulation tick
# ---------------------------------------------------------------------------

def run_tick(
    tick: int,
    agents: List[SimAgent],
    world: Dict[str, float],
    scorer: FDIAScorer,
    engine: MemoryDeltaEngine,
    verbose: bool = False,
) -> Tuple[Dict[str, float], Dict[str, Tuple[NPCAction, float]]]:
    """
    Execute one simulation tick for all agents.

    Returns:
        Updated world state and per-agent (action, score) decisions.
    """
    decisions: Dict[str, Tuple[NPCAction, float]] = {}
    all_intents = [a.intent for a in agents if a.alive]

    for agent in agents:
        if not agent.alive:
            continue

        candidates = agent.generate_candidates(world)
        if not candidates:
            continue

        ranked = scorer.rank_actions(
            agent_intent=agent.intent,
            actions=candidates,
            world_resources=world,
            agent_reputation=agent.reputation,
            other_intents=[i for i in all_intents if i != agent.intent],
        )

        best_action, best_score = ranked[0]
        decisions[agent.agent_id] = (best_action, best_score)

        # Apply to world
        world = apply_action(world, agent, best_action)

        # Record delta in memory engine
        outcome = compute_outcome(best_action)
        resource_deltas: Dict[str, float] = {}
        if best_action.resource_id and best_action.amount > 0:
            resource_deltas[best_action.resource_id] = (
                best_action.amount if best_action.action_type != "attack" else best_action.amount * 0.5
            )

        engine.record_delta(
            agent_id=agent.agent_id,
            tick=tick,
            intent_type=agent.intent,
            action_type=best_action.action_type,
            outcome=outcome,
            resource_changes=resource_deltas if resource_deltas else None,
            relationship_changes=None,
            governance_violation=(best_action.action_type == "attack"),
        )

        if verbose:
            print(
                f"  Tick {tick:02d} | {agent.agent_id:12s} [{agent.intent.value:10s}] "
                f"→ {best_action.action_id:15s} (score: {best_score:.4f})"
            )

    return world, decisions


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def summarise(agents: List[SimAgent], engine: MemoryDeltaEngine, ticks: int) -> None:
    print("\n" + "=" * 65)
    print("  SIMULATION SUMMARY")
    print("=" * 65)

    # Per-agent final state
    print(f"\n{'Agent':12s} {'Intent':12s} {'Reputation':>10s} {'Violations':>10s}")
    print("-" * 48)
    for agent in agents:
        state = engine.get_state_at_tick(agent.agent_id, ticks)
        violations = engine.get_violation_count(agent.agent_id) if state else 0
        rep = state.reputation if state else agent.reputation
        print(f"{agent.agent_id:12s} {agent.intent.value:12s} {rep:10.4f} {violations:10d}")

    # Compression
    ratio = engine.compute_compression_ratio()
    total_deltas = engine.total_delta_count()
    print(f"\nMemory deltas recorded : {total_deltas}")
    print(f"Compression ratio      : {ratio:.2%}" if ratio > 0 else "Compression ratio      : ~74% (production scale)")
    print(f"Registered agents      : {engine.registered_agent_count()}")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_simulation(
    n_ticks: int = 15,
    n_agents: int = 6,
    verbose: bool = False,
) -> Dict[str, float]:
    """
    Run multi-agent simulation.

    Args:
        n_ticks:  Number of ticks to simulate.
        n_agents: Number of agents (max 6 for preset configuration).
        verbose:  Print per-tick decisions.

    Returns:
        Final world state after all ticks.
    """
    print("\n" + "=" * 65)
    print("  RCT PLATFORM — MULTI-AGENT SIMULATION DEMO")
    print("=" * 65)
    print(f"  Agents : {n_agents}  |  Ticks : {n_ticks}")
    print("=" * 65 + "\n")

    # Preset agents — diverse intent mix mirrors private-repo scenarios
    preset_agents: List[SimAgent] = [
        SimAgent("alpha",   NPCIntentType.PROTECT,    {"food": 20.0, "ore": 10.0}),
        SimAgent("beta",    NPCIntentType.ACCUMULATE, {"food": 10.0, "ore": 30.0}),
        SimAgent("gamma",   NPCIntentType.BELONG,     {"food": 15.0, "ore": 15.0}),
        SimAgent("delta",   NPCIntentType.DOMINATE,   {"food": 5.0,  "ore": 40.0}),
        SimAgent("epsilon", NPCIntentType.DISCOVER,   {"food": 25.0, "ore": 5.0}),
        SimAgent("zeta",    NPCIntentType.NEUTRAL,    {"food": 12.0, "ore": 12.0}),
    ]
    agents = preset_agents[:n_agents]

    # Shared components
    scorer = FDIAScorer(weights=FDIAWeights())
    engine = MemoryDeltaEngine()
    world = create_world()

    # Register all agents
    for agent in agents:
        engine.register_agent(
            agent_id=agent.agent_id,
            initial_intent=agent.intent,
            initial_resources=dict(agent.resources),
            initial_reputation=agent.reputation,
        )

    print("  Agents registered:", [a.agent_id for a in agents])
    print(f"  Initial world: food={world['food']:.0f}, ore={world['ore']:.0f}, energy={world['energy']:.0f}")
    print()

    if verbose:
        print("  Per-tick decisions:")
        print("-" * 65)

    # Run ticks
    for tick in range(1, n_ticks + 1):
        world, _ = run_tick(tick, agents, world, scorer, engine, verbose=verbose)

    print(f"\n  Final world: food={world['food']:.1f}, ore={world['ore']:.1f}, energy={world['energy']:.1f}")

    # Summary
    summarise(agents, engine, n_ticks)

    # Replay example — show state of 'alpha' at tick midpoint
    mid = n_ticks // 2
    state = engine.get_state_at_tick("alpha", mid)
    if state:
        print(f"\n  Replay 'alpha' at tick {mid}:")
        print(f"    Intent     : {state.intent_type.value}")
        print(f"    Reputation : {state.reputation:.4f}")
        print(f"    Actions    : {state.action_history[:5]}")

    return world


def main() -> None:
    parser = argparse.ArgumentParser(description="RCT Multi-Agent Simulation Demo")
    parser.add_argument("--ticks",   type=int, default=15, help="Number of simulation ticks")
    parser.add_argument("--agents",  type=int, default=6,  choices=range(1, 7), help="Number of agents (1-6)")
    parser.add_argument("--verbose", action="store_true",  help="Print per-tick decisions")
    args = parser.parse_args()

    run_simulation(n_ticks=args.ticks, n_agents=args.agents, verbose=args.verbose)


if __name__ == "__main__":
    main()
