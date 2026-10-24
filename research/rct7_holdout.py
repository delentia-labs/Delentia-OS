"""Run the model-as-judge on a HOLDOUT that a person labelled, with the pre-registration enforced by the code (criteria: research/rct7_model_judge_criteria.md, research/rct7_round98_criteria.md).

    python -m research.rct7_holdout seal   SHEET.md  [--labels-text "A: 1,3,5 B: 2,4 ?: 9"] [--labelled-by NAME]   # fix the labels (hash) before any run
    python -m research.rct7_holdout run    SHEET.md  --model qwen3:8b [--provider ollama]                          # one run per (model, prompt, labels)
    python -m research.rct7_holdout report SHEET.md                                                                  # every run so far, with 95% intervals

What the code refuses, so that nobody (including the author) can tune until it passes:
  * a run on labels that were not sealed first;
  * a second run for the same (model, prompt version, labels hash) unless `--again` is given, and then the entry says it is a repeat;
  * a sheet whose labels changed after sealing (the hash no longer matches);
  * a paid provider without OPENROUTER_API_KEY, DELENTIA_RUN_LIVE_TESTS=1 and --budget-usd.
Two sheet kinds: a REQUEST sheet (`| n | request | A/B/? | note |`: A = ask first, B = go ahead) and a RESULT sheet (`| n | request | answer | M/N/? | note |`: M = the answer meets the
request, N = it does not). The pass rule is the one written before: found >= 0.80 and false stops <= 0.15; the intervals are shown because a small holdout cannot support more.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane import rct7_judge

RULE = {"found_at_least": 0.80, "false_stops_at_most": 0.15}
_COMPACT = re.compile(r"([ABMNabmn?])[ \t]{0,5}[:=][ \t]{0,5}(\d[\d, \t-]{0,2000})")        # the digits start the group, so the spaces before them have one owner


def wilson(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a proportion (a small holdout is wide: the interval is the honest reading)."""
    if total <= 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def parse_sheet(text: str) -> Dict[int, Dict[str, str]]:
    """The rows of a sheet: number -> {request, answer?, label, note}. A table with three or four cells after the number is read as a request sheet or a result sheet."""
    rows: Dict[int, Dict[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")) or len(line) > 20000:     # plain string handling, no pattern that could backtrack on a long line
            continue
        first, _, rest = line[1:-1].partition("|")
        number = first.strip()
        if not (number.isdigit() and len(number) <= 4):
            continue
        cells = [c.strip() for c in rest.split("|")]
        if len(cells) == 3:
            rows[int(number)] = {"request": cells[0], "label": cells[1].upper(), "note": cells[2]}
        elif len(cells) == 4:
            rows[int(number)] = {"request": cells[0], "answer": cells[1], "label": cells[2].upper(), "note": cells[3]}
    return rows


def parse_compact(text: str) -> Dict[int, str]:
    """`A: 1,3,5-7 B: 2,4 ?: 9` -> {1: 'A', 3: 'A', ...}. A number given twice with different labels is an error, never a guess."""
    labels: Dict[int, str] = {}
    for letter, numbers in _COMPACT.findall(text or ""):
        for part in re.split(r"[,\s]+", numbers.strip()):
            if not part:
                continue
            span = part.split("-")
            if len(span) == 2 and span[0].isdigit() and span[1].isdigit() and int(span[0]) <= int(span[1]) <= int(span[0]) + 200:
                nums = range(int(span[0]), int(span[1]) + 1)
            elif part.isdigit():
                nums = range(int(part), int(part) + 1)
            else:
                continue
            for n in nums:
                if n in labels and labels[n] != letter.upper():
                    raise ValueError(f"item {n} is labelled both {labels[n]} and {letter.upper()}")
                labels[n] = letter.upper()
    return labels


def kind_of(rows: Dict[int, Dict[str, str]]) -> str:
    return "result" if any("answer" in r for r in rows.values()) else "request"


def valid_labels(kind: str) -> Tuple[str, ...]:
    return ("M", "N", "?") if kind == "result" else ("A", "B", "?")


def labelled(rows: Dict[int, Dict[str, str]], extra: Optional[Dict[int, str]] = None) -> Dict[int, Dict[str, str]]:
    out = {}
    kind = kind_of(rows)
    for n, row in rows.items():
        label = (extra or {}).get(n) or row.get("label") or ""
        if label not in valid_labels(kind):
            continue
        out[n] = {**row, "label": label}
    return out


def labels_hash(rows: Dict[int, Dict[str, str]]) -> str:
    canon = json.dumps([[n, r["request"], r.get("answer", ""), r["label"]] for n, r in sorted(rows.items())], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _paths(sheet: Path) -> Tuple[Path, Path]:
    return sheet.with_suffix(".sealed.json"), sheet.with_suffix(".runs.json")


def seal(sheet: Path, compact: str = "", labelled_by: str = "") -> Dict[str, Any]:
    rows = parse_sheet(sheet.read_text(encoding="utf-8"))
    extra = parse_compact(compact) if compact else None
    final = labelled(rows, extra)
    kind = kind_of(rows)
    if len(final) < 20:
        raise ValueError(f"only {len(final)} labelled items: a holdout needs at least 20 (40 is better)")
    counts: Dict[str, int] = {}
    for r in final.values():
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    positives = counts.get("A" if kind == "request" else "N", 0)
    negatives = counts.get("B" if kind == "request" else "M", 0)
    if positives < 5 or negatives < 5:
        raise ValueError(f"need at least 5 of each side to measure both rates (have {positives} and {negatives})")
    sealed = {"kind": kind, "labels_sha256": labels_hash(final), "counts": counts, "items": len(final), "labelled_by": labelled_by or "(not stated)",
              "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items_data": {str(n): r for n, r in sorted(final.items())}}
    sealed_path, _ = _paths(sheet)
    if sealed_path.exists():
        old = json.loads(sealed_path.read_text(encoding="utf-8"))
        if old["labels_sha256"] != sealed["labels_sha256"]:
            raise ValueError("this sheet was sealed with other labels; start a new sheet instead of changing labels after a run")
        return old
    sealed_path.write_text(json.dumps(sealed, ensure_ascii=False, indent=2), encoding="utf-8")
    return sealed


def load_sealed(sheet: Path) -> Dict[str, Any]:
    sealed_path, _ = _paths(sheet)
    if not sealed_path.exists():
        raise ValueError("these labels were not sealed: run `seal` first (it fixes them by hash before any model sees the items)")
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    current = labelled({int(n): r for n, r in sealed["items_data"].items()})
    if labels_hash(current) != sealed["labels_sha256"]:
        raise ValueError("the sealed labels no longer match their hash")
    return sealed


def runs_of(sheet: Path) -> List[Dict[str, Any]]:
    _, runs_path = _paths(sheet)
    return json.loads(runs_path.read_text(encoding="utf-8")) if runs_path.exists() else []


def score(sealed: Dict[str, Any], verdicts: Dict[int, Optional[bool]]) -> Dict[str, Any]:
    """verdicts[n] is True when the model STOPPED (asked / said not met), False when it let the item go, None when it gave no usable answer (counted as 'did not stop')."""
    kind = sealed["kind"]
    pos_label, neg_label = ("A", "B") if kind == "request" else ("N", "M")
    found = false_stops = 0
    positives = negatives = malformed = 0
    for n_text, item in sealed["items_data"].items():
        verdict = verdicts.get(int(n_text))
        malformed += verdict is None
        stopped = bool(verdict)
        if item["label"] == pos_label:
            positives += 1
            found += stopped
        elif item["label"] == neg_label:
            negatives += 1
            false_stops += stopped
    recall, fpr = found / positives, false_stops / negatives
    return {"found": found, "of_needing_a_stop": positives, "found_rate": round(recall, 3), "found_interval": wilson(found, positives),
            "false_stops": false_stops, "of_fine": negatives, "false_stop_rate": round(fpr, 3), "false_stop_interval": wilson(false_stops, negatives), "malformed": malformed,
            "rule_met": recall >= RULE["found_at_least"] and fpr <= RULE["false_stops_at_most"], "rule": RULE}


def _provider(kind: str, model: str, budget_usd: float) -> Any:
    from rct_control_plane.llm_provider import MeteredProvider, OllamaProvider, OpenRouterProvider
    if kind == "ollama":
        return OllamaProvider(model=model)
    if not (os.environ.get("OPENROUTER_API_KEY") and os.environ.get("DELENTIA_RUN_LIVE_TESTS") == "1" and budget_usd > 0):
        raise ValueError("a paid run needs OPENROUTER_API_KEY, DELENTIA_RUN_LIVE_TESTS=1 and --budget-usd > 0 (nothing was sent)")
    from rct_control_plane.model_config import lookup_openrouter_prices
    prices = lookup_openrouter_prices(model)
    if not prices:
        raise ValueError(f"no price for {model}: a budget that cannot be checked is not a budget")
    return MeteredProvider(OpenRouterProvider(model=model), max_cost_usd=budget_usd, prompt_price_per_mtok=prices[0], completion_price_per_mtok=prices[1])


async def run_once(sheet: Path, provider: Any, model: str, again: bool = False, provider_kind: str = "ollama") -> Dict[str, Any]:
    sealed = load_sealed(sheet)
    runs = runs_of(sheet)
    prior = [r for r in runs if r["model"] == model and r["prompt_version"] == rct7_judge_prompt_version() and r["labels_sha256"] == sealed["labels_sha256"]]
    if prior and not again:
        raise ValueError(f"{model} already ran on these labels with this prompt (once is the rule: no tuning after seeing a result); use --again to record a repeat")
    verdicts: Dict[int, Optional[bool]] = {}
    seconds: List[float] = []
    for n_text, item in sealed["items_data"].items():
        started = time.time()
        if sealed["kind"] == "request":
            v = await rct7_judge.judge_request(provider, item["request"])
            verdicts[int(n_text)] = None if v.clear is None and not v.error.startswith("nothing") else (v.clear is False and bool(v.unknowns))
        else:
            r = await rct7_judge.judge_result(provider, item["request"], item["answer"])
            verdicts[int(n_text)] = None if r.meets is None and not r.error.startswith("nothing") else (r.meets is False and bool(r.unmet))
        seconds.append(time.time() - started)
    entry = {"model": model, "provider": provider_kind, "prompt_version": rct7_judge_prompt_version(), "labels_sha256": sealed["labels_sha256"], "repeat": bool(prior),
             "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "median_seconds": round(sorted(seconds)[len(seconds) // 2], 2), "result": score(sealed, verdicts),
             "cite_guard": rct7_judge.cite_guard_on()}
    _, runs_path = _paths(sheet)
    runs.append(entry)
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def rct7_judge_prompt_version() -> str:
    """A hash of the three system prompts, so a changed prompt is a new version and an unchanged one cannot be re-run to get a better number."""
    return hashlib.sha256((rct7_judge.SYSTEM_REQUEST + rct7_judge.SYSTEM_RESULT).encode("utf-8")).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("seal", "run", "report"))
    ap.add_argument("sheet")
    ap.add_argument("--labels-text", default="")
    ap.add_argument("--labelled-by", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--provider", default="ollama", choices=("ollama", "openrouter"))
    ap.add_argument("--budget-usd", type=float, default=0.0)
    ap.add_argument("--again", action="store_true")
    args = ap.parse_args()
    sheet = Path(args.sheet)
    if args.action == "seal":
        print(json.dumps({k: v for k, v in seal(sheet, args.labels_text, args.labelled_by).items() if k != "items_data"}, ensure_ascii=False, indent=2))
    elif args.action == "run":
        if not args.model:
            raise SystemExit("--model is required")
        entry = asyncio.run(run_once(sheet, _provider(args.provider, args.model, args.budget_usd), args.model, args.again, args.provider))
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        for r in runs_of(sheet):
            res = r["result"]
            print(f"{r['model']:<28} found {res['found']}/{res['of_needing_a_stop']} ({res['found_rate']}, 95% {res['found_interval']})  false stops {res['false_stops']}/{res['of_fine']} "
                  f"({res['false_stop_rate']}, 95% {res['false_stop_interval']})  rule {'MET' if res['rule_met'] else 'NOT met'}{'  [repeat]' if r['repeat'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
