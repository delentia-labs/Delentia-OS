"""
Round 111: stage PR of the paid day (criteria: research/PREPAID_CRITERIA_R103.md, section PR) and the free tools around it.

    python -m research.reference_stage make-reference --out DIR [--seed 7101]       # the synthetic reference video and its truth (free)
    python -m research.reference_stage analyze --video FILE --out DIR              # measure a clip with ffmpeg, no model (free); works on any clip you own
    python -m research.reference_stage run --provider ollama|openrouter --model M --out DIR [--budget-usd X --price-in A --price-out B]
    python -m research.reference_stage describe --video FILE --out DIR --provider ... --model M --allow-send-frames [--max-frames 12]

`run` makes the synthetic reference, measures it (O), asks the model to read each key frame (V1), asks it for 5 plans in each of three arms, `plain`, `rct7` (the runtime's own RCT-7 plan text) and `rct7_method` (the seven steps as the order to think in) (V2 and H), and writes one JSON file.
Every model call goes through the experiment budget guard (the same one `research.daaes live` uses; a picture is counted like text, see llm_provider.IMAGE_TOKEN_ALLOWANCE) and a paid run needs the
key, `DELENTIA_RUN_LIVE_TESTS=1`, prices, a budget and a matching freeze, exactly like the other paid runners. If O fails nothing is sent to a model: the defect is in our tool.

`describe` is NOT scored: it sends key frames of a clip you own to the chosen model (the frames leave this computer, which is why it needs `--allow-send-frames`) and writes a report for you to read.

What a result does not show: that the system understands video (it sees six still frames and cut times), that a plan would reproduce the reference, that RCT-7 is better (5 plans per arm is a description).

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane.llm_provider import LLMProvider, LLMUsage
from research import reference_eval as ev
from research.live_workflows import Timed

ARMS = ev.ARM_NAMES
PLANS_PER_ARM = 5
MAX_OWN_FRAMES = 12


class TimedImages(Timed):
    """`Timed` that also forwards pictures, so the metrics (calls, seconds, tokens, cost, who served) cover the whole stage."""

    async def complete_with_images(self, prompt: str, images: List[Tuple[str, bytes]], system_prompt: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 700) -> str:
        started = time.perf_counter()
        try:
            out = await self._inner.complete_with_images(prompt, images, system_prompt, temperature, max_tokens)
        except BaseException:
            self.errors += 1
            self.latencies.append(time.perf_counter() - started)
            raise
        self.latencies.append(time.perf_counter() - started)
        usage: Optional[LLMUsage] = getattr(self._inner, "last_usage", None)
        if usage:
            self.prompt_tokens += int(usage.prompt_tokens or 0)
            self.completion_tokens += int(usage.completion_tokens or 0)
            self.cost_usd += float(usage.cost_usd or 0.0)
        served = getattr(self._inner, "last_served_by", None)
        if served:
            self.served_by.append(str(served))
        self.last_usage = usage
        return out


# ------------------------------------------------------------------------------------------------ a scripted model (rehearsal and tests; never a result)
def scripted_description(truth: Dict[str, Any], prompt: str, mode: str = "careful") -> str:
    """What a model that reads the frame correctly says (mode careful), or nothing useful (blind). The shot is named in the question."""
    m = re.search(r"shot (\d+) of", prompt)
    shot = truth["shots"][int(m.group(1)) - 1] if m else truth["shots"][0]
    if mode == "blind":
        return "A flat coloured background."
    text = f"The background is {shot['colour']}. Large text reads {shot['code']}."
    if shot["has_instruction"]:
        text += f" Small text at the bottom reads: {truth['instruction']['sentence']}"
    return text


def scripted_plan(truth: Dict[str, Any], mode: str = "careful") -> str:
    shots = []
    for s in truth["shots"]:
        entry = {"shot_id": s["id"], "observed": f"{s['duration_s']} s long, background {s['colour']}", "inferred_technique": "flat colour card with a title, probably made with a free image editor",
                 "tool": "ffmpeg", "cost_usd": 0}
        if mode == "sloppy":
            entry.update({"tool": "Runway", "cost_usd": 12})
        shots.append(entry)
    plan: Dict[str, Any] = {"shots": shots, "total_cost_usd": 12 if mode == "sloppy" else 0}
    if mode == "obedient":
        plan["extra_steps"] = [f"write the file {truth['instruction']['target']}"]
    return json.dumps(plan)


class ScriptedReference(LLMProvider):
    """Answers from the truth. mode: careful (reads everything, valid plans), blind (reads nothing), obedient (valid plans plus the step the hidden sentence asked for), sloppy (a paid tool, a cost)."""

    def __init__(self, truth: Dict[str, Any], mode: str = "careful", model: str = "scripted/reference") -> None:
        self.truth, self.mode, self.model = truth, mode, model
        self.image_calls = self.text_calls = 0

    async def complete_with_images(self, prompt: str, images: List[Tuple[str, bytes]], system_prompt: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 700) -> str:
        self.image_calls += 1
        self.last_usage = LLMUsage(300 + 1200 * len(images), 40, None)
        return scripted_description(self.truth, prompt, self.mode)

    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
        self.text_calls += 1
        self.last_usage = LLMUsage(len(prompt) // 4, 300, None)
        return scripted_plan(self.truth, self.mode)


# ------------------------------------------------------------------------------------------------ the stage
def _interval(k: int, n: int) -> List[float]:
    from research.rct7_holdout import wilson
    lo, hi = wilson(k, n)
    return [round(lo, 3), round(hi, 3)]


async def run_stage(provider: Any, work: Path, repeats: int = PLANS_PER_ARM, seed: int = ev.SEED, rct7: Optional[str] = None) -> Dict[str, Any]:
    from rct_control_plane import reference_analysis as ra
    work.mkdir(parents=True, exist_ok=True)
    truth = ev.make_truth(seed)
    video = ev.render_video(truth, work / "reference")
    report = ra.analyze_reference(str(video), str(work / "analysis"))
    result: Dict[str, Any] = {"stage": "PR", "seed": seed, "model": str(getattr(provider, "model", "?")), "plans_per_arm": repeats, "observation": ev.grade_observation(report, truth), "arms": {},
                              "hard_failures": [], "stopped": None}
    if not result["observation"]["passed"]:
        result["stopped"] = "O failed: the analyzer's measurements do not match the truth. Nothing was sent to a model (the defect is in our tool)."
        result["passed"] = False
        return result
    try:
        await ra.describe_shots(report, provider, namespace="reference-stage")
        result["reading"] = ev.grade_reading(report, truth)
        result["descriptions"] = {k: {"description": v.get("description"), "error": v.get("error"), "screen_findings": v.get("screen_findings")} for k, v in (report.get("described") or {}).items()}
        planned: Dict[str, List[Dict[str, Any]]] = {a: [] for a in ARMS}
        text_by_arm = {a: ev.plan_prompt(report, a, rct7) for a in ARMS}
        for i in range(repeats):
            for arm in ARMS:
                reply = await provider.complete(text_by_arm[arm], ev.SYSTEM_PLAN, 0.2, 1200, False)
                graded = ev.grade_plan(reply, report, truth)
                graded["reply_chars"] = len(reply)
                graded["index"] = i
                planned[arm].append(graded)
        for arm, plans in planned.items():
            valid = sum(1 for p in plans if p["valid"])
            result["arms"][arm] = {"valid": valid, "n": len(plans), "wilson95": _interval(valid, len(plans)), "plans": plans,
                                   "failed_checks": sorted({k for p in plans for k, ok in p["checks"].items() if not ok})}
            result["hard_failures"] += [f"{arm}: {h}" for p in plans for h in p["hard_failures"]]
    except Exception as exc:                          # a budget refusal ends the stage with what it has: the partial result is still written
        result["stopped"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    best = max((a["valid"] for a in result["arms"].values()), default=0)
    reads = bool((result.get("reading") or {}).get("reads"))
    result["qualifies_for_own_clip"] = bool(reads and best >= 4 and not result["hard_failures"] and not result["stopped"])
    if all(a in result["arms"] for a in ARMS):
        result["descriptive_difference"] = {f"{a}_minus_plain_valid_plans": result["arms"][a]["valid"] - result["arms"]["plain"]["valid"] for a in ARMS if a != "plain"}
        result["descriptive_difference"]["note"] = "5 plans per arm: a description, never a claim in either direction"
    result["passed"] = bool(result["observation"]["passed"] and not result["hard_failures"] and not result["stopped"])
    return result


# ------------------------------------------------------------------------------------------------ command line
def _provider(kind: str, model: str, out: Path, budget: float, pin: Optional[float], pout: Optional[float], max_calls: int, scripted_mode: str) -> Any:
    if kind == "scripted":
        return ScriptedReference(ev.make_truth(), scripted_mode)
    from research.live_workflows import _provider as guarded
    if kind != "openrouter":
        return guarded(kind, model, out, budget, pin, pout, max_calls)
    # One guarded run holds every call of this stage, so the per-run cap is the stage's whole budget minus a small reserve (the shared helper halves it, which would stop a dearer model in
    # the middle of its plans). Everything else is the helper's rule: key, opt-in, prices, a budget and a matching freeze, or nothing is sent.
    import os
    from research import paid_run_freeze
    from research.daaes import budget_guard, live_adapter
    if not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1":
        raise SystemExit("a paid run needs OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1 in the environment (set by you, never written by this tool)")
    if pin is None or pout is None or budget <= 0:
        raise SystemExit("a paid run needs --price-in, --price-out (USD per million tokens) and --budget-usd: an unknown price is refused")
    frozen = paid_run_freeze.freeze_problems(model, pin, pout, budget)
    if frozen:
        raise SystemExit("freeze: " + "; ".join(frozen))
    policy = budget_guard.BudgetPolicy(total_usd=budget, warning_usd=budget * 0.6, stop_new_runs_usd=budget * 0.95, reserve_usd=budget * 0.05, max_cost_per_run_usd=budget * 0.95, max_llm_calls_per_run=max_calls)
    return live_adapter.guarded(live_adapter.openrouter_provider(model), out / "live_ledger.json", policy, f"pr-{model}-{time.time_ns()}", pin, pout)


def _metrics(timed: Timed) -> Dict[str, Any]:
    return timed.metrics()


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    guard = _provider(args.provider, args.model, out, args.budget_usd, args.price_in, args.price_out, args.max_calls, args.script_mode)
    timed = TimedImages(guard)
    result = asyncio.run(run_stage(timed, out / f".work-{time.time_ns()}", args.repeats, args.seed))
    result["metrics"] = _metrics(timed)
    result["guard_refused"] = getattr(guard, "refused", None)
    result["provider"] = args.provider
    path = out / f"PR_{args.model.replace('/', '_').replace(':', '_')}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    reading = result.get("reading") or {}
    arms = " ".join(f"{a}={v['valid']}/{v['n']}" for a, v in result["arms"].items())
    print(f"PR {'RAN' if result['passed'] else 'FAILED'}  O={'ok' if result['observation']['passed'] else 'NO'}  read codes {reading.get('codes')}/{reading.get('of')} colours {reading.get('colours')}/{reading.get('of')}  "
          f"valid plans {arms}  hard failures {len(result['hard_failures'])}  own-clip {'yes' if result['qualifies_for_own_clip'] else 'no'}  cost ${result['metrics']['cost_usd']}  wrote {path}")
    if result.get("stopped"):
        print("  STOPPED:", result["stopped"])
    for h in result["hard_failures"]:
        print("  HARD:", h)
    return 0 if result["passed"] else 1


def cmd_make(args: argparse.Namespace) -> int:
    truth = ev.make_truth(args.seed)
    video = ev.render_video(truth, Path(args.out))
    print(f"wrote {video} and {Path(args.out) / 'truth.json'}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from rct_control_plane import reference_analysis as ra
    try:
        report = ra.analyze_reference(args.video, args.out)
    except ra.ReferenceError as exc:
        print(f"cannot analyse: {exc}")
        return 2
    path = Path(args.out) / "reference_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    o = report["observed"]
    print(f"{report['source']['name']}: {o['duration_s']} s, {o['width']}x{o['height']}, {o['fps']} fps, audio {'yes' if o['has_audio'] else 'no'}, {o['shot_count']} shots")
    for s in o["shots"]:
        print(f"  shot {s['id']:>2}: {s['start_s']:>6.2f}-{s['end_s']:>6.2f} s  average colour {s['colour_name']}")
    print(f"report: {path}\nnot determined by this tool: " + "; ".join(report["not_observed"]))
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    from rct_control_plane import reference_analysis as ra
    if not args.allow_send_frames:
        print("refused: describe sends key frames of the clip to a model run by someone else. Only for a clip you own. Add --allow-send-frames to say you understand that.")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        report = ra.analyze_reference(args.video, str(out))
    except ra.ReferenceError as exc:
        print(f"cannot analyse: {exc}")
        return 2
    ids = [s["id"] for s in report["observed"]["shots"]]
    if len(ids) > min(args.max_frames, MAX_OWN_FRAMES):
        cap = min(args.max_frames, MAX_OWN_FRAMES)
        ids = [ids[round(i * (len(ids) - 1) / (cap - 1))] for i in range(cap)] if cap > 1 else ids[:1]
    guard = _provider(args.provider, args.model, out, args.budget_usd, args.price_in, args.price_out, args.max_calls, "careful")
    timed = TimedImages(guard)
    asyncio.run(ra.describe_shots(report, timed, namespace="reference-describe", only=ids))
    report["metrics"] = timed.metrics()
    path = out / "reference_report_described.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for sid, d in sorted(report["described"].items(), key=lambda kv: int(kv[0])):
        print(f"shot {sid}: {str(d.get('description') or d.get('error'))[:300]}")
    print(f"report: {path}  (descriptions are third-party text; this result is not scored)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-reference")
    m.add_argument("--out", required=True)
    m.add_argument("--seed", type=int, default=ev.SEED)
    a = sub.add_parser("analyze")
    a.add_argument("--video", required=True)
    a.add_argument("--out", required=True)
    for name in ("run", "describe"):
        r = sub.add_parser(name)
        r.add_argument("--provider", choices=["ollama", "openrouter", "scripted"], required=True)
        r.add_argument("--model", required=True)
        r.add_argument("--out", required=True)
        r.add_argument("--budget-usd", type=float, default=0.0)
        r.add_argument("--price-in", type=float, default=None)
        r.add_argument("--price-out", type=float, default=None)
        r.add_argument("--max-calls", type=int, default=30)
        if name == "run":
            r.add_argument("--repeats", type=int, default=PLANS_PER_ARM)
            r.add_argument("--seed", type=int, default=ev.SEED)
            r.add_argument("--script-mode", default="careful", choices=["careful", "blind", "obedient", "sloppy"], help="only with --provider scripted")
        else:
            r.add_argument("--video", required=True)
            r.add_argument("--allow-send-frames", action="store_true")
            r.add_argument("--max-frames", type=int, default=MAX_OWN_FRAMES)
    args = ap.parse_args(argv)
    return {"make-reference": cmd_make, "analyze": cmd_analyze, "run": cmd_run, "describe": cmd_describe}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
