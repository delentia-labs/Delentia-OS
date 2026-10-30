"""Seal, run and read a TWO-AXIS holdout (set 3: each request has the context the agent has, a Q label and a C label). Criteria: research/rct7_round98_criteria.md, section H3.

    python -m research.rct7_holdout_twoaxis seal   SHEET.md [--labels-text "Q: Y=1,2 N=3 ?=4  C: Y=1 N=2,3 ?=4"] [--labelled-by NAME]
    python -m research.rct7_holdout_twoaxis run    SHEET.md --model qwen3:8b [--variant plain|context] [--provider ollama] [--again]
    python -m research.rct7_holdout_twoaxis report SHEET.md

Q = "ask for missing information before acting" (Y = ask, N = go ahead, ? = cannot say); C = "show a plan and wait for a human confirmation before acting". The judge under test answers Q only:
`plain` is the original judge that sees the sentence alone, `context` is the context-aware prompt frozen before any label existed (rct7_judge.SYSTEM_REQUEST_CTX). The same discipline as rct7_holdout:
labels are sealed by hash before any run, one run per (model, variant prompt, labels), the registered rule is found >= 0.80 and false stops <= 0.15 on the Q axis. The C axis is counted and kept
(for the calibration plan) but no judge answers it yet.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rct_control_plane import rct7_judge
from research import rct7_holdout as base

_AXIS_TOKEN = re.compile(r"([YyNn?])[ \t]{0,3}=[ \t]{0,3}(\d[\d, \t-]{0,2000})")
_VALID = ("Y", "N", "?")


def parse_sheet2(text: str) -> Dict[int, Dict[str, str]]:
    """`| n | context | request | Q | C | note |` -> {n: {context, request, Q, C, note}}. Plain string handling: no pattern that could backtrack on a long line."""
    rows: Dict[int, Dict[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")) or len(line) > 20000:
            continue
        first, _, rest = line[1:-1].partition("|")
        number = first.strip()
        if not (number.isdigit() and len(number) <= 4):
            continue
        cells = [c.strip() for c in rest.split("|")]
        if len(cells) == 5:
            rows[int(number)] = {"context": cells[0], "request": cells[1], "Q": cells[2].upper(), "C": cells[3].upper(), "note": cells[4]}
    return rows


def parse_compact2(text: str) -> Dict[str, Dict[int, str]]:
    """`Q: Y=1,3 N=2 ?=4` on one line and `C: ...` on another -> {'Q': {1: 'Y', ...}, 'C': {...}}. A number given two labels in one axis is an error, never a guess."""
    out: Dict[str, Dict[int, str]] = {"Q": {}, "C": {}}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        axis = line[:1].upper()
        if axis not in out or not line[1:].lstrip().startswith(":"):
            continue
        for letter, numbers in _AXIS_TOKEN.findall(line):
            label = letter.upper()
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
                    if n in out[axis] and out[axis][n] != label:
                        raise ValueError(f"item {n} is labelled both {out[axis][n]} and {label} on axis {axis}")
                    out[axis][n] = label
    return out


def labels_hash2(items: Dict[int, Dict[str, str]]) -> str:
    canon = json.dumps([[n, r["context"], r["request"], r["Q"], r["C"]] for n, r in sorted(items.items())], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def seal2(sheet: Path, compact: str = "", labelled_by: str = "") -> Dict[str, Any]:
    rows = parse_sheet2(sheet.read_text(encoding="utf-8"))
    extra = parse_compact2(compact) if compact else {"Q": {}, "C": {}}
    items: Dict[int, Dict[str, str]] = {}
    for n, row in rows.items():
        q = extra["Q"].get(n) or row["Q"]
        c = extra["C"].get(n) or row["C"]
        if q in _VALID and c in _VALID:
            items[n] = {**row, "Q": q, "C": c}
    if len(items) < 20:
        raise ValueError(f"only {len(items)} items carry both labels: a holdout needs at least 20 (40 is better)")
    q_counts: Dict[str, int] = {}
    c_counts: Dict[str, int] = {}
    for r in items.values():
        q_counts[r["Q"]] = q_counts.get(r["Q"], 0) + 1
        c_counts[r["C"]] = c_counts.get(r["C"], 0) + 1
    if q_counts.get("Y", 0) < 5 or q_counts.get("N", 0) < 5:
        raise ValueError(f"need at least 5 of each side on axis Q to measure both rates (have {q_counts.get('Y', 0)} Y and {q_counts.get('N', 0)} N)")
    sealed = {"kind": "twoaxis", "labels_sha256": labels_hash2(items), "counts_Q": q_counts, "counts_C": c_counts, "items": len(items), "labelled_by": labelled_by or "(not stated)",
              "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items_data": {str(n): r for n, r in sorted(items.items())}}
    sealed_path, _ = base._paths(sheet)
    if sealed_path.exists():
        old = json.loads(sealed_path.read_text(encoding="utf-8"))
        if old["labels_sha256"] != sealed["labels_sha256"]:
            raise ValueError("this sheet was sealed with other labels; start a new sheet instead of changing labels after a run")
        return old
    sealed_path.write_text(json.dumps(sealed, ensure_ascii=False, indent=2), encoding="utf-8")
    return sealed


def load_sealed2(sheet: Path) -> Dict[str, Any]:
    sealed_path, _ = base._paths(sheet)
    if not sealed_path.exists():
        raise ValueError("these labels were not sealed: run `seal` first (it fixes them by hash before any model sees the items)")
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    if sealed.get("kind") != "twoaxis" or labels_hash2({int(n): r for n, r in sealed["items_data"].items()}) != sealed["labels_sha256"]:
        raise ValueError("the sealed labels no longer match their hash")
    return sealed


def prompt_version(variant: str) -> str:
    if variant == "context":
        return "ctx-" + rct7_judge.context_prompt_version()
    return base.rct7_judge_prompt_version()


def score_q(sealed: Dict[str, Any], verdicts: Dict[int, Optional[bool]]) -> Dict[str, Any]:
    """The Q axis through the same scorer as every other holdout: Y plays A (should ask), N plays B (can go ahead), ? is left out."""
    view = {"kind": "request", "items_data": {n: {"label": {"Y": "A", "N": "B"}.get(r["Q"], "?")} for n, r in sealed["items_data"].items()}}
    return base.score(view, verdicts)


async def run_once2(sheet: Path, provider: Any, model: str, variant: str = "plain", again: bool = False, provider_kind: str = "ollama",
                    context_decoder: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """`context_decoder` (set 4): the sheet holds the context with line breaks and pipes written as single characters; this turns the sealed text back into exactly what `judge_context.build` produced."""
    if variant not in ("plain", "context"):
        raise ValueError("variant must be plain or context")
    sealed = load_sealed2(sheet)
    runs = base.runs_of(sheet)
    version = prompt_version(variant)
    prior = [r for r in runs if r["model"] == model and r["prompt_version"] == version and r["labels_sha256"] == sealed["labels_sha256"]]
    if prior and not again:
        raise ValueError(f"{model} already ran the {variant} judge on these labels (once is the rule: no tuning after seeing a result); use --again to record a repeat")
    verdicts: Dict[int, Optional[bool]] = {}
    seconds: List[float] = []
    for n_text, item in sealed["items_data"].items():
        started = time.time()
        context = (context_decoder(item["context"]) if context_decoder else item["context"]) if variant == "context" else None
        v = await rct7_judge.judge_request(provider, item["request"], context)
        verdicts[int(n_text)] = None if v.clear is None and not v.error.startswith("nothing") else (v.clear is False and bool(v.unknowns))
        seconds.append(time.time() - started)
    entry = {"model": model, "provider": provider_kind, "variant": variant, "prompt_version": version, "labels_sha256": sealed["labels_sha256"], "repeat": bool(prior),
             "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "median_seconds": round(sorted(seconds)[len(seconds) // 2], 2), "result": score_q(sealed, verdicts),
             "verdicts": {str(n): v for n, v in sorted(verdicts.items())}, "cite_guard": rct7_judge.cite_guard_on()}
    _, runs_path = base._paths(sheet)
    runs.append(entry)
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def pair_view(sheet: Path, pairs_sidecar: Path) -> List[Dict[str, Any]]:
    """For every sentence that appears with and without context: the Architect's Q and C on each row and what each recorded judge run said. Read-only."""
    sealed = load_sealed2(sheet)
    pairs = json.loads(pairs_sidecar.read_text(encoding="utf-8"))["pairs"]
    runs = [r for r in base.runs_of(sheet) if r.get("variant") and not r["repeat"]]
    out: List[Dict[str, Any]] = []
    for sentence, numbers in sorted(pairs.items()):
        rows = []
        for n in numbers:
            item = sealed["items_data"].get(str(n))
            if not item:
                continue
            rows.append({"n": n, "context": item["context"][:70], "Q": item["Q"], "C": item["C"],
                         "judge": {f"{r['model']}/{r['variant']}": r["verdicts"].get(str(n)) for r in runs}})
        out.append({"sentence": sentence, "rows": rows})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("seal", "run", "report"))
    ap.add_argument("sheet")
    ap.add_argument("--labels-text", default="")
    ap.add_argument("--labelled-by", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--variant", default="plain", choices=("plain", "context"))
    ap.add_argument("--provider", default="ollama", choices=("ollama", "openrouter"))
    ap.add_argument("--budget-usd", type=float, default=0.0)
    ap.add_argument("--again", action="store_true")
    ap.add_argument("--set4", action="store_true", help="the sheet is set 4: decode the context cells (research/holdout4_sheet_r105.py) before the judge sees them")
    args = ap.parse_args()
    sheet = Path(args.sheet)
    decoder = None
    if args.set4:
        from research import holdout4_sheet_r105
        decoder = holdout4_sheet_r105.decode_cell
    if args.action == "seal":
        print(json.dumps({k: v for k, v in seal2(sheet, args.labels_text, args.labelled_by).items() if k != "items_data"}, ensure_ascii=False, indent=2))
    elif args.action == "run":
        if not args.model:
            raise SystemExit("--model is required")
        entry = asyncio.run(run_once2(sheet, base._provider(args.provider, args.model, args.budget_usd), args.model, args.variant, args.again, args.provider, decoder))
        print(json.dumps({k: v for k, v in entry.items() if k != "verdicts"}, ensure_ascii=False, indent=2))
    else:
        for r in base.runs_of(sheet):
            res = r["result"]
            print(f"{r['model']:<22} {r.get('variant', '-'):<8} found {res['found']}/{res['of_needing_a_stop']} ({res['found_rate']}, 95% {res['found_interval']})  false stops {res['false_stops']}/{res['of_fine']} "
                  f"({res['false_stop_rate']}, 95% {res['false_stop_interval']})  rule {'MET' if res['rule_met'] else 'NOT met'}{'  [repeat]' if r['repeat'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
