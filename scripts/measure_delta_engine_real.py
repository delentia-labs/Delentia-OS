"""
Round 52: what does the Delta Engine's compression really measure?

`MemoryDeltaEngine.compute_compression_ratio()` (and so the README's "91.5% measured" and the
benchmark script's 95.3%) does not measure stored bytes. It adds up two formulas:

    naive bytes  += 150 + 12 x (deltas so far)        # an assumed size for "a full snapshot now"
    delta bytes  += 40 + len(str(changed fields))     # an assumed fixed cost per record

Because the naive formula grows with the tick count and the delta formula does not, the ratio
rises as a simulation gets longer whatever the data look like. This script measures what the
two storage strategies actually occupy: it runs the same kind of simulation, then serialises

    full      the whole state at every tick (JSON, including the action history)
    delta     one JSON record per tick plus a full checkpoint every `checkpoint_interval` ticks
    + zstd    each of the two compressed as a single stream (the honest baseline: generic
              compression of the full-snapshot log needs no Delta Engine at all)

for sparse, typical and dense change rates, and prints the reduction of each against the full log.

    python scripts/measure_delta_engine_real.py
    python scripts/measure_delta_engine_real.py --agents 50 --ticks 200 --out delta_real.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import zstandard  # noqa: E402

from core.delta_engine.memory_delta import MemoryDeltaEngine  # noqa: E402
from core.fdia.fdia import NPCIntentType  # noqa: E402

ACTIONS = ["trade", "explore", "attack", "defend", "build"]
OUTCOMES = ["success", "partial", "blocked"]
RESOURCES = ["gold", "food", "energy", "influence", "land"]


def full_state(state: Any) -> Dict[str, Any]:
    """Everything a full snapshot has to hold, including the action history that makes it grow."""
    return {
        "agent_id": state.agent_id, "tick": state.tick, "intent_type": state.intent_type.value,
        "resources": {k: round(v, 6) for k, v in sorted(state.resources.items())}, "reputation": round(state.reputation, 6),
        "relationships": {k: round(v, 6) for k, v in sorted(state.relationships.items())},
        "action_history": list(state.action_history), "violation_count": state.violation_count,
    }


def simulate(agents: int, ticks: int, change_rate: float, seed: int = 42) -> MemoryDeltaEngine:
    rng = random.Random(seed)
    engine = MemoryDeltaEngine()
    intents = list(NPCIntentType)
    for i in range(agents):
        engine.register_agent(f"agent_{i}", rng.choice(intents), initial_resources={"gold": 50.0, "energy": 100.0})
    for tick in range(1, ticks + 1):
        for i in range(agents):
            changes = None
            if rng.random() < change_rate:
                changes = {k: round(rng.uniform(0.1, 100.0), 2) for k in rng.sample(RESOURCES, rng.randint(1, 3))}
            rel = {f"agent_{rng.randrange(agents)}": round(rng.uniform(-0.1, 0.1), 3)} if rng.random() < change_rate * 0.75 else {}
            engine.record_delta(
                agent_id=f"agent_{i}", tick=tick, intent_type=rng.choice(intents), action_type=rng.choice(ACTIONS),
                outcome=rng.choice(OUTCOMES), resource_changes=changes, relationship_changes=rel,
                governance_violation=rng.random() < 0.05)
    return engine


def measure(agents: int, ticks: int, change_rate: float) -> Dict[str, Any]:
    engine = simulate(agents, ticks, change_rate)
    full_log: List[bytes] = []
    delta_log: List[bytes] = []
    for agent_id in engine.deltas:
        for delta in engine.deltas[agent_id]:
            state = engine.get_state_at_tick(agent_id, delta.tick)
            full_log.append(json.dumps(full_state(state), sort_keys=True).encode())
            delta_log.append(json.dumps(delta.to_dict(), sort_keys=True).encode())
        for state in engine._checkpoints.get(agent_id, {}).values():
            delta_log.append(json.dumps(full_state(state), sort_keys=True).encode())      # checkpoints are part of the cost
    full_bytes, delta_bytes = sum(map(len, full_log)), sum(map(len, delta_log))
    compressor = zstandard.ZstdCompressor(level=9)
    full_zstd = len(compressor.compress(b"\n".join(full_log)))
    delta_zstd = len(compressor.compress(b"\n".join(delta_log)))
    ratio_estimate = engine.compute_compression_ratio()

    def cut(x: int) -> float:
        return round(100 * (1 - x / full_bytes), 1)

    return {
        "agents": agents, "ticks": ticks, "change_rate": change_rate, "records": len(delta_log),
        "full_snapshot_log_bytes": full_bytes, "delta_log_bytes": delta_bytes,
        "full_zstd_bytes": full_zstd, "delta_zstd_bytes": delta_zstd,
        "reduction_vs_full_pct": {"delta": cut(delta_bytes), "zstd_of_full": cut(full_zstd), "zstd_of_delta": cut(delta_zstd)},
        "engine_reported_pct": round(100 * ratio_estimate, 1),
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", type=int, default=50)
    ap.add_argument("--ticks", type=int, default=200)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    rows = [measure(args.agents, args.ticks, rate) for rate in (0.1, 0.4, 0.9)]
    print(f"{args.agents} agents x {args.ticks} ticks. Reduction of storage against a full snapshot at every tick, measured in bytes:\n")
    print(f"{'change rate':>11} {'engine says':>12} {'delta log':>10} {'zstd(full)':>11} {'zstd(delta)':>12}")
    for r in rows:
        red = r["reduction_vs_full_pct"]
        print(f"{r['change_rate']:>11} {str(r['engine_reported_pct']) + '%':>12} {str(red['delta']) + '%':>10} "
              f"{str(red['zstd_of_full']) + '%':>11} {str(red['zstd_of_delta']) + '%':>12}")
    for ticks in (20, 100, 500):
        r = measure(10, ticks, 0.4)
        print(f"  length check, 10 agents x {ticks:>3} ticks: engine says {r['engine_reported_pct']}%, measured delta log "
              f"{r['reduction_vs_full_pct']['delta']}%, zstd(full) {r['reduction_vs_full_pct']['zstd_of_full']}%")
        rows.append(r)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
