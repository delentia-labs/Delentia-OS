"""
Round 54: does a small local model, asked one narrow question, catch what CORD's rules miss on text the authors did not write?

Uses the same external set and the same protocol as measure_cord_external.py (TEST split first; misses are read from TRAIN only)
and the real Ollama model you name, with the exact prompt the agent would use (rct_control_plane/injection_classifier.py).
Reports the rules alone, the model alone, and the combination (rules OR model), with false blocks on harmless text.

    python scripts/measure_cord_classifier.py --file deepset_test.parquet --model llama3.2:3b [--limit 60] [--json out.json]

The model is slow on CPU (seconds per text); --limit takes an evenly spaced sample of both classes so the first look is quick.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def sample(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0 or limit >= len(rows):
        return rows
    attacks = [r for r in rows if r["label"] == 1]
    benign = [r for r in rows if r["label"] == 0]
    half = max(1, limit // 2)
    pick = lambda items, n: [items[int(i * len(items) / n)] for i in range(min(n, len(items)))]   # noqa: E731
    return pick(attacks, half) + pick(benign, limit - half)


async def run(rows: List[Dict[str, Any]], model: str, endpoint: str) -> Dict[str, Any]:
    from rct_control_plane.cord_security import CORDEngine, CORDVerdict
    from rct_control_plane.injection_classifier import classify
    from rct_control_plane.llm_provider import OllamaProvider
    engine = CORDEngine()
    provider = OllamaProvider(model=model, base_url=endpoint) if endpoint else OllamaProvider(model=model)
    counts = {"attacks": 0, "benign": 0, "rules_attacks": 0, "model_attacks": 0, "either_attacks": 0, "rules_benign": 0, "model_benign": 0,
              "either_benign": 0, "no_opinion": 0}
    seconds: List[float] = []
    missed_by_both: List[str] = []
    for row in rows:
        by_rules = engine.check(row["text"]).verdict == CORDVerdict.REJECTED
        started = time.perf_counter()
        opinion = await classify(provider, row["text"])
        seconds.append(time.perf_counter() - started)
        by_model = opinion.attack is True
        counts["no_opinion"] += int(opinion.attack is None)
        key = "attacks" if row["label"] == 1 else "benign"
        counts[key] += 1
        counts[f"rules_{key}"] += int(by_rules)
        counts[f"model_{key}"] += int(by_model)
        counts[f"either_{key}"] += int(by_rules or by_model)
        if row["label"] == 1 and not (by_rules or by_model):
            missed_by_both.append(row["text"][:120])
    a, b = max(1, counts["attacks"]), max(1, counts["benign"])
    seconds.sort()
    return {
        "model": model, "texts": len(rows), **counts,
        "attack_rate": {"rules": round(counts["rules_attacks"] / a, 3), "model": round(counts["model_attacks"] / a, 3), "rules_or_model": round(counts["either_attacks"] / a, 3)},
        "false_block_rate": {"rules": round(counts["rules_benign"] / b, 3), "model": round(counts["model_benign"] / b, 3), "rules_or_model": round(counts["either_benign"] / b, 3)},
        "seconds_per_text": {"median": round(seconds[len(seconds) // 2], 2), "p90": round(seconds[int(len(seconds) * 0.9) - 1], 2), "total": round(sum(seconds), 1)},
        "missed_by_both_examples": missed_by_both[:8],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from measure_cord_external import load
    report = asyncio.run(run(sample(load(args.file), args.limit), args.model, args.endpoint))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
