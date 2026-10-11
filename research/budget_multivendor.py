"""
Round 68: the paid test, priced for MANY vendors (the runtime is not tied to one brand, so neither should the test be).

    python research/budget_multivendor.py --fetch   # reads https://openrouter.ai/api/v1/models (public, no key) and writes research/openrouter_models_<date>.json (trimmed)
    python research/budget_multivendor.py           # prints the shortlist and the cost tables from the newest snapshot

Method (written before the numbers were looked at):
  * eligible = advertises tool use, text in and text out, context >= 32k, a real positive price, not a batch variant (`:batch` is asynchronous), not a moving alias (`~vendor/...-latest`, a result must
    name the model it ran), not an expired model, not OpenRouter's own router. `:free` models are listed separately (rate-limited, a different budget).
  * price does not measure ability and the catalogue has no benchmark, so the shortlist is chosen by a rule that spreads the PRICE BAND within each vendor: the cheapest eligible model at or above
    $0.05 per 1M input tokens with a context of at least 128k ("economy"), and the most expensive one at or below $1.00 per 1M input ("upper-mid"). Whether a model can drive the tools at all is decided by
    the real capability preflight (protocol 22.2: 20 benign tasks, arm A111), never by this table.
  * tokens per episode are the MEASURED ones of Round 64 (scripts/measure_prompt_cost.py and real runs): 6 model calls, ~8,200 prompt tokens each with the full 48-tool menu (~1,500 with the opt-in compact
    menu), ~150 completion tokens. Cached: only for models that publish a cache-read price, and only as a scenario (the real hit rate has never been measured).
  * stages as in research/budget.py: S0 preflight 20 episodes per model; S2 dev pilot 280 episodes; the whole programme 2,498 episodes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
CALLS, PROMPT_FULL, PROMPT_COMPACT, COMPLETION = 6, 8200, 1500, 150
S0, S2, ALL = 20, 280, 2498
MARGIN = 1.5
MAJOR = ["openai", "anthropic", "google", "meta-llama", "mistralai", "qwen", "deepseek", "z-ai", "moonshotai", "x-ai", "nvidia", "amazon", "xiaomi", "minimax", "bytedance-seed", "cohere"]


def fetch() -> Path:
    raw = json.loads(urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60).read())["data"]
    keep: List[Dict[str, Any]] = []
    for m in raw:
        sp = m.get("supported_parameters") or []
        arch = m.get("architecture") or {}
        pr = m.get("pricing") or {}
        try:
            p_in, p_out = float(pr.get("prompt")), float(pr.get("completion"))
        except (TypeError, ValueError):
            continue
        keep.append({"id": m["id"], "slug": m.get("canonical_slug"), "name": m.get("name"), "context": m.get("context_length"), "in_per_m": round(p_in * 1e6, 6), "out_per_m": round(p_out * 1e6, 6),
                     "cache_read_per_m": round(float(pr["input_cache_read"]) * 1e6, 6) if pr.get("input_cache_read") not in (None, "") else None, "tools": "tools" in sp,
                     "json_mode": "response_format" in sp or "structured_outputs" in sp, "text_in": "text" in (arch.get("input_modalities") or []), "text_out": (arch.get("output_modalities") or []) == ["text"],
                     "expires": m.get("expiration_date"), "created": m.get("created")})
    path = HERE / f"openrouter_models_{dt.date.today().isoformat()}.json"
    path.write_text(json.dumps({"fetched": dt.date.today().isoformat(), "source": "https://openrouter.ai/api/v1/models", "models": keep}, indent=1) + "\n", encoding="utf-8")
    return path


def newest() -> Path:
    files = sorted(HERE.glob("openrouter_models_*.json"))
    if not files:
        raise SystemExit("no snapshot: run with --fetch first")
    return files[-1]


def eligible(m: Dict[str, Any]) -> bool:
    mid = m["id"]
    return bool(m["tools"] and m["text_in"] and m["text_out"] and (m["context"] or 0) >= 32000 and m["in_per_m"] > 0 and m["out_per_m"] > 0 and ":batch" not in mid and not mid.startswith("~")
                and not mid.startswith("openrouter/") and not m["expires"] and ":free" not in mid)


def cost_per_episode(m: Dict[str, Any], prompt: int, cached_share: float = 0.0) -> float:
    read = m["cache_read_per_m"] if (m["cache_read_per_m"] is not None and cached_share > 0) else m["in_per_m"]
    prompt_total = CALLS * prompt
    return (prompt_total * (1 - cached_share) * m["in_per_m"] + prompt_total * cached_share * read + CALLS * COMPLETION * m["out_per_m"]) / 1e6


def shortlist(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_vendor: Dict[str, List[Dict[str, Any]]] = {}
    for m in models:
        if eligible(m):
            by_vendor.setdefault(m["id"].split("/")[0], []).append(m)
    chosen: List[Dict[str, Any]] = []
    for vendor in MAJOR:
        pool = by_vendor.get(vendor, [])
        economy = sorted([m for m in pool if m["in_per_m"] >= 0.05 and (m["context"] or 0) >= 128000], key=lambda m: (m["in_per_m"] + m["out_per_m"], m["id"]))
        upper = sorted([m for m in pool if m["in_per_m"] <= 1.0], key=lambda m: (-(m["in_per_m"] + m["out_per_m"]), m["id"]))
        for tier, group in (("economy", economy[:1]), ("upper-mid", upper[:1])):
            for m in group:
                if all(m["id"] != c["id"] for c in chosen):
                    chosen.append({**m, "tier": tier, "vendor": vendor})
    return chosen


W_TOKENS = {"prompt": 400_000, "completion": 30_000}        # scripts/full_test_orchestrator.py tier W (the K.1.5 capability screen), a guess with room


def screen_cost(m: Dict[str, Any]) -> float:
    return (W_TOKENS["prompt"] * m["in_per_m"] + W_TOKENS["completion"] * m["out_per_m"]) / 1e6


def fit_budget(models: List[Dict[str, Any]], budget: float) -> List[Dict[str, Any]]:
    """The models to screen first when only `budget` dollars are available (margin included): one model per vendor, cheapest first, then second models while money remains. Vendors are spread before depth."""
    by_vendor: Dict[str, List[Dict[str, Any]]] = {}
    for m in sorted(models, key=screen_cost):
        by_vendor.setdefault(m["vendor"], []).append(m)
    chosen: List[Dict[str, Any]] = []
    spent = 0.0
    for depth in range(2):
        for _vendor, lst in sorted(by_vendor.items(), key=lambda kv: screen_cost(kv[1][0])):
            if depth < len(lst) and spent + screen_cost(lst[depth]) * MARGIN <= budget:
                chosen.append(lst[depth])
                spent += screen_cost(lst[depth]) * MARGIN
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--json", default=None, help="also write the result as JSON")
    ap.add_argument("--fit-budget", type=float, default=None, help="print which models the capability screen (tier W) can cover for this many dollars, margin included")
    args = ap.parse_args()
    if args.fetch:
        print("wrote", fetch())
    snap = json.loads(newest().read_text(encoding="utf-8"))
    models = snap["models"]
    ok = [m for m in models if eligible(m)]
    vendors = sorted({m["id"].split("/")[0] for m in ok})
    free = [m for m in models if m["tools"] and m["text_in"] and m["text_out"] and ":free" in m["id"] and (m["context"] or 0) >= 32000]
    short = shortlist(models)
    print(f"snapshot {snap['fetched']}: {len(models)} models listed, {len(ok)} eligible paid tool-capable text models from {len(vendors)} vendors, {len(free)} free ones")
    print(f"\nSHORTLIST ({len(short)} models, {len({m['vendor'] for m in short})} vendors): in/out = USD per 1M tokens; per-episode = {CALLS} calls x ({PROMPT_FULL} prompt + {COMPLETION} completion tokens)\n")
    print("| vendor | tier | model | in / out | cache read | context | one episode (full menu) | one episode (compact menu) | S0 preflight (20) |")
    print("|---|---|---|---|---|---|---|---|---|")
    rows = []
    for m in sorted(short, key=lambda m: cost_per_episode(m, PROMPT_FULL)):
        c_full, c_compact = cost_per_episode(m, PROMPT_FULL), cost_per_episode(m, PROMPT_COMPACT)
        rows.append({**m, "episode_full": c_full, "episode_compact": c_compact, "s0": c_full * S0})
        print(f"| {m['vendor']} | {m['tier']} | {m['id']} | {m['in_per_m']:g} / {m['out_per_m']:g} | {m['cache_read_per_m'] if m['cache_read_per_m'] is not None else '-'} | {m['context']:,} | ${c_full:.4f} | ${c_compact:.4f} | ${c_full * S0:.2f} |")
    s0_all = sum(r["s0"] for r in rows)
    print(f"\nS0 for the WHOLE shortlist: ${s0_all:.2f} (x{MARGIN} margin ${s0_all * MARGIN:.2f}); {len(rows)} models x {S0} episodes = {len(rows) * S0} episodes")
    # progressive plan: preflight everything, pilot the best few, run the programme on one or two
    median_ep = sorted(r["episode_full"] for r in rows)[len(rows) // 2]
    cheapest4 = sorted(rows, key=lambda r: r["episode_full"])[:4]
    print("\nPROGRESSIVE PATH (every number x1.5 margin):")
    print(f"  1. S0 preflight, all {len(rows)} models:                     ${s0_all * MARGIN:.2f}")
    pilot_each = [r["episode_full"] * S2 for r in cheapest4]
    print(f"  2. S2 dev pilot (280 episodes) on the 4 CHEAPEST that pass:  ${sum(pilot_each) * MARGIN:.2f}  ({', '.join(r['id'] for r in cheapest4)})")
    mid3 = sorted(rows, key=lambda r: abs(r["episode_full"] - median_ep))[:3]
    print(f"  3. S2 dev pilot on 3 MID-priced models (around ${median_ep:.4f}/episode): ${sum(r['episode_full'] * S2 for r in mid3) * MARGIN:.2f}  ({', '.join(r['id'] for r in mid3)})")
    print("  4. the whole programme (2,498 episodes) on ONE model:")
    for r in cheapest4[:2] + mid3[:1]:
        cached = cost_per_episode(r, PROMPT_FULL, 0.9) if r["cache_read_per_m"] is not None else None
        print(f"       {r['id']:44} ${r['episode_full'] * ALL * MARGIN:8.2f}  (compact menu ${r['episode_compact'] * ALL * MARGIN:7.2f}" + (f"; 90% cached ${cached * ALL * MARGIN:7.2f}" if cached is not None else "") + ")")
    print(f"\nFREE tool-capable models ({len(free)}): " + ", ".join(sorted(m['id'] for m in free)[:14]))
    if args.fit_budget is not None:
        picked = fit_budget(short, args.fit_budget)
        total = sum(screen_cost(m) for m in picked) * MARGIN
        print(f"\nWITHIN ${args.fit_budget:g} (margin included) the capability screen covers {len(picked)} models from {len({m['vendor'] for m in picked})} vendors, ${total:.2f}:")
        for m in picked:
            print(f"   {m['id']:44} screen ${screen_cost(m):.3f} (x{MARGIN} = ${screen_cost(m) * MARGIN:.3f})")
        rows_json = [m["id"] for m in picked]
    else:
        rows_json = None
    if args.json:
        Path(args.json).write_text(json.dumps({"snapshot": snap["fetched"], "shortlist": rows, "s0_all_models": s0_all, "margin": MARGIN, "fit_budget_models": rows_json}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
