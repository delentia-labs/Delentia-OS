"""
What the whole programme costs, stage by stage, from MEASURED token counts and a dated price snapshot.

    python research/budget.py                       # the table the Round 64 report quotes
    python research/budget.py --calls 8 --margin 2  # change an assumption

Measured inputs (all from this repository, not guessed):
  * prompt tokens per model call: ~8,200 with the full 48-tool menu (49,405 tokens over 6 calls on a real run; scripts/measure_prompt_cost.py: 7,637 at the first call, +~170 per step)
  * ~1,500 per call with the ranked compact menu (opt-in)
  * completion tokens per call: ~100-190 on real runs (JSON reply with a short reasoning); 150 is used
  * model calls per episode: 5-7 on the real runs (read three files, answer, plus a retry or two); 6 is used
  * 94% of a prompt is the unchanging menu (98% reusable across episodes with DELENTIA_PROMPT_LAYOUT=cache_friendly)
Assumptions, not measurements: how many episodes each stage needs (below), the cache hit rate on a real provider (never measured: no key), and that the prices in the snapshot hold.
Prices change; re-fetch the catalogue (https://openrouter.ai/api/v1/models, public) before spending.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "price_snapshot_2026-10-09.json"

# (stage, what it is for, episodes). Episodes = tasks x arms x repeats, one episode = one governed run of one task (about 6 model calls).
STAGES: List[Tuple[str, str, int]] = [
    ("S0 preflight", "20 benign dev tasks, arm A111: is the model capable enough to measure anything (protocol 22.2)", 20),
    ("S1 owner demo + P4 claims", "3 clean-start demo runs, 6 claim tests, 3 runs by the owner", 12),
    ("S2 dev pilot", "5 arms (A111, A011, A101, A110, G) x 28 episodes x 2 repeats", 5 * 28 * 2),
    ("S3 validation", "choose the F threshold: 3 gate variants x 28 episodes x 1 (+ a margin)", 100),
    ("S4 screening", "9 arms x 28 episodes x 3 repeats", 9 * 28 * 3),
    ("S5 confirmation", "A111 vs G on a sealed holdout: ~236 units for a 10-point difference (q=0.3), ~2.5 episodes per unit, 2 arms", 236 * 2 * 5 // 2),
    ("S6 reproduction + partners", "an outside reproduction and a few design-partner trials", 150),
]


def load_snapshot(path: Path = SNAPSHOT) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def episode_cost(price: Dict[str, float], *, calls: int, prompt_tokens: int, completion_tokens: int, cached_share: float) -> float:
    """USD for one episode. cached_share = the part of the prompt served at the cache-read price (0 = no caching)."""
    prompt_total = calls * prompt_tokens
    cached = prompt_total * cached_share
    uncached = prompt_total - cached
    return (uncached * price["input"] + cached * (price["cache_read"] or price["input"]) + calls * completion_tokens * price["output"]) / 1_000_000


def table(calls: int, prompt: int, completion: int, margin: float, cached_share: float, models: List[str]) -> str:
    snap = load_snapshot()
    total_eps = sum(n for _, _, n in STAGES)
    lines = ["Episodes by stage: " + ", ".join(f"{name.split()[0]} {n}" for name, _, n in STAGES) + f" = {total_eps} in total; {calls} calls per episode, {prompt} prompt + {completion} completion tokens per call.", "",
             "| model | in / out per 1M | one episode | S0-S2 (the dev pilot) | everything | everything with caching | with a x%.1f margin (cached) |" % margin, "|---|---|---|---|---|---|---|"]
    early = sum(n for name, _, n in STAGES[:3])
    for m in models:
        price = snap["models"][m]
        plain = episode_cost(price, calls=calls, prompt_tokens=prompt, completion_tokens=completion, cached_share=0.0)
        cached = episode_cost(price, calls=calls, prompt_tokens=prompt, completion_tokens=completion, cached_share=cached_share)
        lines.append(f"| {m} | {price['input']} / {price['output']} | ${plain:.4f} | ${plain * early:.2f} | ${plain * total_eps:.2f} | ${cached * total_eps:.2f} | ${cached * total_eps * margin:.2f} |")
    return "\n".join(lines)


def free_tier(calls: int) -> str:
    total_eps = sum(n for _, _, n in STAGES)
    early = sum(n for name, _, n in STAGES[:3])
    out = ["| stage group | requests | days at 1,000 requests/day (>= 10 credits ever bought) | days at 50/day (fewer) |", "|---|---|---|---|"]
    for label, eps in (("S0-S2 (preflight, demo, dev pilot)", early), ("everything", total_eps)):
        req = eps * calls
        out.append(f"| {label} | {req:,} | {req / 1000:.1f} | {req / 50:.0f} |")
    out.append("")
    out.append("Free `:free` models are limited to 20 requests per minute; at 6 calls an episode that is at most 3 episodes a minute, so S2 alone is ~1.6 hours of wall clock before the daily cap.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calls", type=int, default=6)
    parser.add_argument("--prompt", type=int, default=8200)
    parser.add_argument("--completion", type=int, default=150)
    parser.add_argument("--margin", type=float, default=1.5)
    parser.add_argument("--cached-share", type=float, default=0.90, help="share of prompt tokens billed at the cache-read price when DELENTIA_PROMPT_LAYOUT=cache_friendly (assumed: never measured on a real provider)")
    args = parser.parse_args()
    models = [m for m in load_snapshot()["models"] if not m.endswith(":free")]
    print(table(args.calls, args.prompt, args.completion, args.margin, args.cached_share, models))
    print()
    print("Ranked compact menu (about 1,500 tokens a call, opt-in):")
    print(table(args.calls, 1500, args.completion, args.margin, args.cached_share, models[:3]))
    print()
    print(free_tier(args.calls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
