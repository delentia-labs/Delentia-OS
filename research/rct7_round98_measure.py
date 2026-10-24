"""DEV measurement of the round-98 model-assisted RCT-7 parts with a LOCAL model (criteria: research/rct7_round98_criteria.md).

    DELENTIA_OLLAMA_THINK=off python -m research.rct7_round98_measure --model qwen3:8b --out result.json

One call per case, through the same code the loop uses (rct7_judge); every raw reply is kept and parsed twice, with and without the cite guard, so the guard's effect is measured on the very
same answers. Nothing is executed. The cases are the author's own: the numbers decide whether the code is worth keeping, they are not a claim.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any, Dict, List

from rct_control_plane import rct7_judge
from rct_control_plane.llm_provider import OllamaProvider
from research import rct7_model_judge_cases as request_cases
from research import rct7_round98_cases as cases


class Recorder:
    """Wraps a provider and keeps the last raw reply and its time."""

    def __init__(self, inner: Any):
        self.inner, self.reply, self.seconds = inner, "", 0.0

    async def complete(self, *args: Any, **kwargs: Any) -> str:
        started = time.time()
        try:
            self.reply = await self.inner.complete(*args, **kwargs)
        finally:
            self.seconds = round(time.time() - started, 1)
        return self.reply


async def measure_judge(rec: Recorder) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for request, must_ask in request_cases.CASES:
        try:
            await rct7_judge.judge_request(rec, request)
            reply, seconds = rec.reply, rec.seconds
        except Exception as exc:                                 # noqa: BLE001
            reply, seconds = "", 0.0
            _ = exc
        rows.append({"request": request, "must_ask": must_ask, "reply": reply[:500], "seconds": seconds})
    out: Dict[str, Any] = {"cases": len(rows)}
    for guard in (True, False):
        found = false_pauses = malformed = 0
        for r in rows:
            v = rct7_judge.parse_request_verdict(r["reply"], r["request"], guard=guard)
            asked = v.clear is False and bool(v.unknowns)
            malformed += v.error == "unreadable answer"
            found += asked and r["must_ask"]
            false_pauses += asked and not r["must_ask"]
        unclear = sum(1 for r in rows if r["must_ask"])
        out["guard_on" if guard else "guard_off"] = {"found": found, "of": unclear, "recall": round(found / unclear, 3), "false_pauses": false_pauses, "of_clear": len(rows) - unclear,
                                                     "false_pause_rate": round(false_pauses / (len(rows) - unclear), 3), "malformed": malformed}
    out["median_seconds"] = sorted(r["seconds"] for r in rows)[len(rows) // 2]
    out["misses_with_guard"] = [r["request"] for r in rows if r["must_ask"] and not (lambda v: v.clear is False and v.unknowns)(rct7_judge.parse_request_verdict(r["reply"], r["request"], guard=True))]
    out["false_pauses_with_guard"] = [r["request"] for r in rows if not r["must_ask"] and (lambda v: v.clear is False and v.unknowns)(rct7_judge.parse_request_verdict(r["reply"], r["request"], guard=True))]
    return out


async def measure_critic(rec: Recorder) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for request, answer, meets in cases.CRITIC:
        try:
            await rct7_judge.judge_result(rec, request, answer)
            reply, seconds = rec.reply, rec.seconds
        except Exception:                                        # noqa: BLE001
            reply, seconds = "", 0.0
        rows.append({"request": request, "answer": answer, "meets": meets, "reply": reply[:500], "seconds": seconds})
    out: Dict[str, Any] = {"cases": len(rows)}
    for guard in (True, False):
        found = false_stops = malformed = 0
        for r in rows:
            v = rct7_judge.parse_result_verdict(r["reply"], r["request"], guard=guard)
            stopped = v.meets is False and bool(v.unmet)
            malformed += v.error == "unreadable answer"
            found += stopped and not r["meets"]
            false_stops += stopped and r["meets"]
        unmet = sum(1 for r in rows if not r["meets"])
        out["guard_on" if guard else "guard_off"] = {"found": found, "of": unmet, "recall": round(found / unmet, 3), "false_stops": false_stops, "of_meeting": len(rows) - unmet,
                                                     "false_stop_rate": round(false_stops / (len(rows) - unmet), 3), "malformed": malformed}
    out["median_seconds"] = sorted(r["seconds"] for r in rows)[len(rows) // 2]
    return out


async def measure_chain(rec: Recorder) -> Dict[str, Any]:
    faithful_claims = faithful_verified = 0
    invented_total = invented_flagged = invented_omitted = invented_flagged_by_gap = 0
    rows: List[Dict[str, Any]] = []
    for name, request, steps, answer, invented in cases.EPISODES:
        result = await rct7_judge.cite_claims(rec, request, answer, steps)
        claims = result.get("claims", [])
        if invented is None:
            faithful_claims += len(claims)
            faithful_verified += sum(1 for c in claims if c["status"] == "verified")
        else:
            invented_total += 1
            hit = [c for c in claims if invented.casefold() in c["claim"].casefold()]
            gap = any(invented.casefold() in g.casefold() for g in result.get("gaps", []))
            if not hit:
                invented_omitted += 1
                invented_flagged_by_gap += int(gap)
            elif any(c["status"] != "verified" for c in hit):
                invented_flagged += 1
        rows.append({"episode": name, "error": result.get("error"), "statuses": [c["status"] for c in claims], "gaps": result.get("gaps", []), "seconds": rec.seconds})
    return {"episodes": len(rows), "faithful_claims": faithful_claims, "faithful_verified": faithful_verified,
            "faithful_verified_rate": round(faithful_verified / faithful_claims, 3) if faithful_claims else None,
            "invented_episodes": invented_total, "invented_flagged": invented_flagged, "invented_omitted_by_the_model": invented_omitted,
            "omitted_but_reported_as_a_gap_by_the_code": invented_flagged_by_gap, "invented_detected_total": invented_flagged + invented_flagged_by_gap,
            "faithful_gaps": sum(len(r["gaps"]) for r in rows if r["episode"].startswith("F")), "rows": rows}


async def run(model: str, only: str = "") -> Dict[str, Any]:
    rec = Recorder(OllamaProvider(model=model))
    out: Dict[str, Any] = {"model": model, "set": "DEV (author-written; not a claim)", "prompt_version": 2}
    if only in ("", "judge"):
        out["judge"] = await measure_judge(rec)
    if only in ("", "critic"):
        out["critic"] = await measure_critic(rec)
    if only in ("", "chain"):
        out["chain"] = await measure_chain(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", choices=("", "judge", "critic", "chain"))
    args = ap.parse_args()
    result = asyncio.run(run(args.model, args.only))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
