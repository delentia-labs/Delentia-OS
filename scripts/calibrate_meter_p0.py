"""
Round 106: stage P0 of research/PREPAID_CRITERIA_R103.md - does our cost meter agree with the provider's own figure?

    python scripts/calibrate_meter_p0.py <model> --price-in 0.1 --price-out 0.5 [--calls 24] [--prompt-tokens 1500] [--budget-usd 0.10] [--json p0.json]

It sends `--calls` short requests (at least 20) through the same MeteredProvider the agent uses, adds up what the meter says they cost, then reads the key's own
usage figure from OpenRouter before and after and compares the two. The rule is the one written before any key existed: over at least 20 completed calls the two
sums differ by at most 10% (relative to the provider's figure). It also prints how far a plain tokens x price estimate is from the provider, as information:
the orchestrator's estimates are that kind of number.

Spends real money (about $0.01-0.05 with a cheap model), so it refuses without OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1, without prices, and when the worst
case of the whole run with a 1.5 x margin is above --budget-usd. The key is only ever sent as the Authorization header, and nothing it prints contains it.
Exit code 0 = within the tolerance, 1 = outside it or not comparable, 2 = refused before spending.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

MIN_CALLS = 20
TOLERANCE = 0.10
MARGIN = 1.5
WORDS = ("amber", "bridge", "candle", "delta", "ember", "falcon", "garden", "harbor", "island", "jungle", "kernel", "lantern", "meadow", "nectar", "orchard",
         "pebble", "quartz", "river", "saddle", "timber", "umber", "valley", "willow", "yonder", "zephyr")


def filler(call_index: int, target_tokens: int) -> str:
    """A prompt of about `target_tokens` tokens that differs from every other call's from its FIRST characters on, so that a provider's prefix cache cannot make one call cheaper than the next."""
    from rct_control_plane.llm_provider import _count_tokens
    words: List[str] = [f"Reference {call_index:04d}-{hashlib.sha256(str(call_index).encode()).hexdigest()[:10]}."]
    n = 0
    while _count_tokens(" ".join(words)) < target_tokens:
        digest = hashlib.sha256(f"{call_index}:{n}".encode()).digest()
        words.extend(WORDS[b % len(WORDS)] for b in digest[:8])
        n += 1
    return " ".join(words) + "\n\nIgnore the text above and reply with the single word OK."


def estimate(calls: int, prompt_tokens: int, max_tokens: int, price_in: float, price_out: float) -> float:
    return calls * (prompt_tokens * price_in + max_tokens * price_out) / 1_000_000


def refusals(args: argparse.Namespace, env: Dict[str, str]) -> List[str]:
    problems: List[str] = []
    if not env.get("OPENROUTER_API_KEY"):
        problems.append("OPENROUTER_API_KEY is not set")
    if env.get("DELENTIA_RUN_LIVE_TESTS") != "1":
        problems.append("DELENTIA_RUN_LIVE_TESTS=1 is not set")
    for name in ("price_in", "price_out"):
        value = getattr(args, name)
        if not isinstance(value, float) or value != value or value < 0 or value in (float("inf"),) or (name == "price_in" and value == 0):
            problems.append(f"--{name.replace('_', '-')} must be the model's real price per million tokens (a missing price is not zero)")
    if args.calls < MIN_CALLS:
        problems.append(f"--calls {args.calls} is below the {MIN_CALLS} the rule asks for")
    if args.budget_usd is None or not args.budget_usd > 0:
        problems.append("--budget-usd must be above zero")
    elif not problems:
        worst = estimate(args.calls, args.prompt_tokens, args.max_tokens, args.price_in, args.price_out) * MARGIN
        if worst > args.budget_usd:
            problems.append(f"the worst case ${worst:.4f} (with a {MARGIN} x margin) is above --budget-usd ${args.budget_usd}")
    return problems


def settled_usage(read: Callable[[], float], *, tries: int = 8, wait: float = 5.0, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """The key's usage figure can lag behind the calls. Read it until two reads in a row agree (or the tries run out) and say which happened."""
    seen: List[float] = [read()]
    for _ in range(tries):
        sleep(wait)
        seen.append(read())
        if len(seen) >= 2 and seen[-1] == seen[-2]:
            return {"value": seen[-1], "settled": True, "reads": seen}
    return {"value": seen[-1], "settled": False, "reads": seen}


def spy_on(provider_class: Any) -> Any:
    """A provider that remembers, per call, whether the reply carried the provider's own cost (the meter prefers that figure to tokens x price)."""
    class Spy(provider_class):                                     # type: ignore[misc, valid-type]
        reported: List[bool]

        async def complete(self, *a: Any, **k: Any) -> str:
            text = await super().complete(*a, **k)
            self.reported = getattr(self, "reported", []) + [getattr(self.last_usage, "cost_usd", None) is not None]
            return text
    return Spy


async def send_calls(provider: Any, model: str, calls: int, prompt_tokens: int, max_tokens: int) -> Dict[str, Any]:
    done, failed = 0, []
    for i in range(calls):
        try:
            await provider.complete(filler(i, prompt_tokens), "You are a calibration probe. Answer in one word.", 0.0, max_tokens)
            done += 1
        except Exception as exc:                                   # noqa: BLE001 - recorded, not hidden: an uncertain call is still counted by the meter
            failed.append(f"call {i}: {type(exc).__name__}: {str(exc)[:100]}")
            if len(failed) >= 3:
                break
    return {"completed": done, "failed": failed}


def judge(summary: Dict[str, Any], completed: int, usage_before: float, usage: Dict[str, Any], price_in: float, price_out: float, reported_cost_calls: int = 0) -> Dict[str, Any]:
    """The rule written before any run. `summary` is MeteredProvider.summary(). `reported_cost_calls` = how many replies carried the provider's own cost figure; for the others the
    meter multiplied tokens by OUR price list, and a pass then says less about the provider's billing."""
    provider = round(usage["value"] - usage_before, 10)
    meter = summary.get("cost_usd")
    priced = (summary["prompt_tokens"] * price_in + summary["completion_tokens"] * price_out) / 1_000_000
    out: Dict[str, Any] = {"calls_with_provider_reported_cost": reported_cost_calls, "calls_completed": completed, "provider_usd": provider, "meter_usd": meter, "price_estimate_usd": round(priced, 10), "usage_settled": usage["settled"],
                           "tolerance": TOLERANCE, "cached_prompt_tokens": summary.get("cached_prompt_tokens", 0), "uncertain_calls": summary.get("uncertain_calls", 0)}
    if completed < MIN_CALLS:
        return {**out, "verdict": "fail", "why": f"only {completed} calls completed; the rule needs at least {MIN_CALLS}"}
    if meter is None or not summary.get("cost_known", True):
        return {**out, "verdict": "fail", "why": "the meter could not price every call (an unknown cost is not zero)"}
    if provider <= 0:
        return {**out, "verdict": "inconclusive", "why": "the provider's usage figure did not move, so there is nothing to compare with (the figure may lag or be rounded: more calls or longer prompts)"}
    relative = abs(meter - provider) / provider
    out["meter_vs_provider"] = round(relative, 4)
    out["price_estimate_vs_provider"] = round(abs(priced - provider) / provider, 4)
    if not usage["settled"]:
        return {**out, "verdict": "inconclusive", "why": "the provider's usage figure was still changing at the last read, so the comparison may be early"}
    if relative <= TOLERANCE:
        return {**out, "verdict": "pass", "why": f"the meter is within {TOLERANCE:.0%} of the provider's figure ({relative:.1%})"}
    return {**out, "verdict": "fail", "why": f"the meter differs from the provider's figure by {relative:.1%}, more than {TOLERANCE:.0%}"}


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model")
    parser.add_argument("--price-in", type=float, default=None, help="USD per million prompt tokens")
    parser.add_argument("--price-out", type=float, default=None, help="USD per million completion tokens")
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--prompt-tokens", type=int, default=1500)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--budget-usd", type=float, default=0.10)
    parser.add_argument("--wait", type=float, default=5.0, help="seconds between reads of the key's usage figure")
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    env = dict(os.environ if env is None else env)
    problems = refusals(args, env)
    if problems:
        print("P0 refused, nothing was sent and nothing was spent:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    import logging
    logging.disable(logging.WARNING)
    from full_test_orchestrator import openrouter_usage
    from rct_control_plane.llm_provider import MeteredProvider, OpenRouterProvider
    key = env["OPENROUTER_API_KEY"]
    inner = spy_on(OpenRouterProvider)(api_key=key, model=args.model)
    provider = MeteredProvider(inner, max_cost_usd=args.budget_usd, prompt_price_per_mtok=args.price_in, completion_price_per_mtok=args.price_out)
    before = openrouter_usage(key)
    sent = asyncio.run(send_calls(provider, args.model, args.calls, args.prompt_tokens, args.max_tokens))
    usage = settled_usage(lambda: openrouter_usage(key), wait=args.wait, sleep=sleep)
    summary = provider.summary()
    result = judge(summary, sent["completed"], before, usage, args.price_in, args.price_out, sum(getattr(inner, "reported", [])))
    report = {"model": args.model, "prices_per_mtok": {"in": args.price_in, "out": args.price_out}, "calls_requested": args.calls, "prompt_tokens_target": args.prompt_tokens,
              "served_by": getattr(inner, "last_served_by", None), "meter": {k: summary[k] for k in ("calls", "prompt_tokens", "completion_tokens", "cost_usd", "cost_known")},
              "usage_before": before, "usage_reads": usage["reads"], "failed": sent["failed"], "result": result}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if key in text:                                                 # cannot happen (the key is never put in the report); checked because it would be unforgivable
        print("the report contained the key; discarded", file=sys.stderr)
        return 2
    print(f"P0 {result['verdict'].upper()}: {result['why']}\n  meter ${result['meter_usd']}, provider ${result['provider_usd']}, tokens x price ${result['price_estimate_usd']}"
          + (f" ({result.get('price_estimate_vs_provider', 0):.1%} from the provider)" if "price_estimate_vs_provider" in result else ""))
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
