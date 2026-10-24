"""Probe: can a local model act as the proposer of RCT-7 R1/R5 questions? Criteria: research/rct7_model_judge_criteria.md. DEV cases only.

    python -m research.rct7_model_judge_probe --model qwen3:8b [--out result.json]

Talks to a local Ollama only (127.0.0.1:11434), one request per case, no tools, thinking off, temperature 0. Nothing is executed. Exit status is always 0: this reports, it does not gate.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from typing import Any, Dict, List

from research import rct7_model_judge_cases as cases

URL = "http://127.0.0.1:11434/api/chat"


def ask(model: str, request: str, timeout: float = 300.0) -> Dict[str, Any]:
    body = {"model": model, "stream": False, "think": False, "format": "json", "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [{"role": "system", "content": cases.SYSTEM}, {"role": "user", "content": request}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = str((raw.get("message") or {}).get("content") or "")
    try:
        parsed = json.loads(text)
        clear = parsed.get("clear")
        verdict = bool(clear) if isinstance(clear, bool) else None
        unknowns = [str(u) for u in parsed.get("unknowns") or []] if isinstance(parsed.get("unknowns"), list) else []
    except (ValueError, AttributeError):
        verdict, unknowns = None, []
    return {"clear": verdict, "unknowns": unknowns, "raw": text[:400], "seconds": round(time.time() - started, 1)}


def run(model: str) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for request, must_ask in cases.CASES:
        got = ask(model, request)
        asked = got["clear"] is False                    # a malformed reply is NOT a stop
        rows.append({"request": request, "must_ask": must_ask, "asked": asked, **got})
    unclear = [r for r in rows if r["must_ask"]]
    clear = [r for r in rows if not r["must_ask"]]
    found = sum(1 for r in unclear if r["asked"])
    false_pauses = sum(1 for r in clear if r["asked"])
    malformed = sum(1 for r in rows if r["clear"] is None)
    return {"model": model, "prompt_version": cases.PROMPT_VERSION, "set": "DEV (author-labelled; not a claim)", "unclear": len(unclear), "found": found,
            "recall": round(found / len(unclear), 3), "clear": len(clear), "false_pauses": false_pauses, "false_pause_rate": round(false_pauses / len(clear), 3),
            "malformed": malformed, "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
            "rule": "recall >= 0.80 and false pause rate <= 0.15 on a HOLDOUT labelled by someone else", "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    result = run(args.model)
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in result["rows"]:
        if r["asked"] != r["must_ask"]:
            print("MISS" if r["must_ask"] else "FALSE PAUSE", "|", r["request"], "|", r["raw"][:120].replace("\n", " "))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
