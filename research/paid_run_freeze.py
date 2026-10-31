"""
Round 106: freeze the configuration before the first paid call, and refuse to spend if anything differs from what was frozen.

Why. A paid measurement is only worth something if the thing measured is known. Without a frozen record, "the capable-model run" could be on another commit, with another tool menu, with the judge or the critic on or
off, under a policy that changed in between, at other prices, against criteria edited after the fact. This writes one JSON file that says exactly what is about to be measured and how much may be spent, and
`check` compares it with the present state: the orchestrator (`scripts/full_test_orchestrator.py --freeze-file`) refuses a real run when they differ.

What is frozen:
  * the commit (SHA, branch, whether the working tree is dirty: a dirty tree is refused), the package version, the interpreter, the platform;
  * the settings that change what a measurement means (`results_register.CONFIG_ENV`, never a value whose name looks like a secret), and the roles they switch on (judge, critic, evidence chain, ask-and-wait,
    plan-first, warm recall, tool menu, parallel tools, memory by meaning);
  * the owner's policy (its digest and where it came from) and the model-assisted prompt versions;
  * the models, the price per million tokens of each and where those prices came from, the stages, and the spending ceilings (total, per run, reserve), including the statement that a cap exists AT THE PROVIDER
    (`--provider-cap-confirmed`): a default or an estimate is not a budget;
  * the SHA-256 of the criteria file the results will be registered against, and of the orchestrator.

It does not make a run safe by itself; it makes the run reproducible and stops the commonest mistake: measuring something other than what was written down.

    python -m research.paid_run_freeze write --models a/b,c/d --live-prices --stages P0,P1 --budget-usd 15 --provider-cap-confirmed --out freeze.json
    (--live-prices reads OpenRouter's public model list, the same way the orchestrator does, so the frozen prices and the prices of the run are read the same way; --prices-file takes a JSON of your own)
    python -m research.paid_run_freeze check freeze.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research import results_register  # noqa: E402

FORMAT = "delentia-paid-run-freeze-1"
CRITERIA = ROOT / "research" / "PREPAID_CRITERIA_R103.md"
ORCHESTRATOR = ROOT / "scripts" / "full_test_orchestrator.py"
STAGE_CEILINGS_USD = {"P0": 0.10, "P1": 5.00, "P1b": 1.50, "P2": 1.50, "P4": 4.00}         # the ceilings written in PREPAID_CRITERIA_R103.md; a stage that is not listed has no ceiling and is refused

ROLES = {"judge": "DELENTIA_RCT7_JUDGE", "chain": "DELENTIA_RCT7_CHAIN", "judge_context": "DELENTIA_RCT7_JUDGE_CONTEXT", "ask_and_wait": "DELENTIA_ASK_AND_WAIT", "warm_recall": "DELENTIA_WARM_RECALL",
         "tool_menu": "DELENTIA_TOOL_MENU", "parallel_tools": "DELENTIA_PARALLEL_TOOLS", "memory_embed": "DELENTIA_MEMORY_EMBED", "taint_gate": "DELENTIA_TAINT_GATE", "verify_grounding": "DELENTIA_VERIFY_GROUNDING"}


def live_prices(models: List[str]) -> Dict[str, Dict[str, float]]:
    """The price per million tokens of each model in OpenRouter's public list, parsed exactly as scripts/full_test_orchestrator.py does it (so a later run reads the same figures).
    A model that is missing or has no usable price is left out; build() then refuses it by name."""
    import httpx
    from rct_control_plane.llm_provider import openrouter_base_url
    data = httpx.get(f"{openrouter_base_url()}/models", timeout=30).json().get("data", [])
    wanted, found = set(models), {}
    for item in data:
        if not isinstance(item, dict) or item.get("id") not in wanted:
            continue
        pricing = item.get("pricing") or {}
        try:
            found[item["id"]] = {"in": float(pricing["prompt"]) * 1e6, "out": float(pricing["completion"]) * 1e6}
        except (KeyError, TypeError, ValueError):
            continue
    return found


class FreezeError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _finite_nonneg(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def code_state() -> Dict[str, Any]:
    status = _git("status", "--porcelain")
    return {"sha": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "dirty": bool(status) if status is not None else None}


def policy_state() -> Dict[str, Any]:
    try:
        from rct_control_plane import fdia_policy
        policy, source = fdia_policy.effective_policy()
        return {"source": source, "digest": policy.digest() if policy is not None else None}
    except Exception as exc:                                                   # noqa: BLE001 - a broken policy file is itself something to freeze (it fails closed)
        return {"source": "unreadable", "digest": None, "error": type(exc).__name__}


def prompt_versions() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        from rct_control_plane import rct7_judge
        for name in ("SYSTEM_REQUEST", "SYSTEM_REQUEST_CTX", "SYSTEM_RESULT", "SYSTEM_CHAIN"):
            text = getattr(rct7_judge, name, None)
            if isinstance(text, str):
                out[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    except Exception:                                                          # noqa: BLE001
        pass
    return out


def roles_state() -> Dict[str, str]:
    return {role: os.environ.get(var, "(unset)") for role, var in ROLES.items()}


def build(models: List[str], prices: Dict[str, Dict[str, float]], prices_source: str, stages: List[str], budget_usd: float, provider_cap_confirmed: bool,
          max_cost_per_run_usd: float = 0.0, reserve_usd: float = 0.0) -> Dict[str, Any]:
    problems = problems_before_freezing(models, prices, stages, budget_usd, provider_cap_confirmed)
    if problems:
        raise FreezeError("; ".join(problems))
    snap = results_register.config_snapshot()
    ceilings = {s: STAGE_CEILINGS_USD[s] for s in stages}
    record: Dict[str, Any] = {
        "format": FORMAT, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "code": code_state(), "package_version": snap["package_version"], "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}", "config": snap["env"], "roles": roles_state(), "policy": policy_state(), "prompt_versions": prompt_versions(),
        "models": [{"id": m, "price_in_per_mtok": prices[m]["in"], "price_out_per_mtok": prices[m]["out"]} for m in models], "prices_source": prices_source,
        "stages": stages, "stage_ceilings_usd": ceilings, "spending": {"budget_usd": budget_usd, "stage_ceilings_sum_usd": round(sum(ceilings.values()), 4), "reserve_usd": reserve_usd,
                                                                      "max_cost_per_run_usd": max_cost_per_run_usd, "provider_cap_confirmed": bool(provider_cap_confirmed)},
        "criteria_sha256": sha256_file(CRITERIA) if CRITERIA.exists() else None, "orchestrator_sha256": sha256_file(ORCHESTRATOR) if ORCHESTRATOR.exists() else None}
    record["sha256"] = hashlib.sha256(json.dumps({k: v for k, v in record.items() if k not in ("frozen_at", "sha256")}, sort_keys=True).encode("utf-8")).hexdigest()
    return record


def problems_before_freezing(models: List[str], prices: Dict[str, Dict[str, float]], stages: List[str], budget_usd: float, provider_cap_confirmed: bool) -> List[str]:
    problems: List[str] = []
    state = code_state()
    if not state["sha"]:
        problems.append("this is not a git checkout, so the commit cannot be frozen")
    if state["dirty"]:
        problems.append("the working tree has uncommitted changes: commit them first, a freeze names a commit")
    if not models:
        problems.append("no model named")
    for m in models:
        p = prices.get(m)
        if not isinstance(p, dict) or not _finite_nonneg(p.get("in")) or not _finite_nonneg(p.get("out")):
            problems.append(f"no valid price for {m} (a price that is missing, negative, NaN or not a number is refused)")
    if not stages:
        problems.append("no stage named")
    for s in stages:
        if s not in STAGE_CEILINGS_USD:
            problems.append(f"stage {s} has no ceiling in PREPAID_CRITERIA_R103.md (known: {', '.join(sorted(STAGE_CEILINGS_USD))})")
    if not _finite_nonneg(budget_usd) or budget_usd <= 0:
        problems.append("--budget-usd must be a real amount above zero: the credit cap you set at the provider")
    elif sum(STAGE_CEILINGS_USD.get(s, 0) for s in stages) > budget_usd:
        problems.append(f"the ceilings of the chosen stages add up to ${sum(STAGE_CEILINGS_USD.get(s, 0) for s in stages):.2f}, more than the budget ${budget_usd}")
    if not provider_cap_confirmed:
        problems.append("--provider-cap-confirmed is missing: say that a spending cap exists at the provider (a default or an estimate here is not a cap)")
    return problems


def check(frozen: Dict[str, Any]) -> List[str]:
    """What differs between the freeze and now. Empty means the run measures what was written down."""
    diffs: List[str] = []
    if frozen.get("format") != FORMAT:
        return [f"not a freeze file of this format ({frozen.get('format')!r})"]
    body = {k: v for k, v in frozen.items() if k not in ("frozen_at", "sha256")}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest() != frozen.get("sha256"):
        diffs.append("the freeze file itself was edited after it was written")
    now = code_state()
    was = frozen.get("code") or {}
    if now["sha"] != was.get("sha"):
        diffs.append(f"the commit changed: frozen {str(was.get('sha'))[:10]}, now {str(now['sha'])[:10]}")
    if now["dirty"]:
        diffs.append("the working tree has uncommitted changes")
    snap = results_register.config_snapshot()
    for key in sorted(set(snap["env"]) | set(frozen.get("config") or {})):
        a, b = (frozen.get("config") or {}).get(key), snap["env"].get(key)
        if a != b:
            diffs.append(f"setting {key}: frozen {a!r}, now {b!r}")
    if roles_state() != frozen.get("roles"):
        diffs.append("the roles switched on differ from the freeze")
    if policy_state() != frozen.get("policy"):
        diffs.append("the owner's policy differs from the freeze")
    if prompt_versions() != frozen.get("prompt_versions"):
        diffs.append("a model-assisted prompt differs from the freeze")
    if snap["package_version"] != frozen.get("package_version"):
        diffs.append("the package version differs from the freeze")
    if CRITERIA.exists() and sha256_file(CRITERIA) != frozen.get("criteria_sha256"):
        diffs.append("the criteria file was edited after the freeze (a rule written after the number is a description, not a test)")
    if ORCHESTRATOR.exists() and sha256_file(ORCHESTRATOR) != frozen.get("orchestrator_sha256"):
        diffs.append("the orchestrator differs from the freeze")
    if not (frozen.get("spending") or {}).get("provider_cap_confirmed"):
        diffs.append("the freeze does not say that a cap exists at the provider")
    return diffs


def _same_price(a: Any, b: Any) -> bool:
    """A price typed on a command line (0.1) and the same price parsed from a list (1e-07 x 1e6 = 0.09999999999999999) are the same price."""
    return _finite_nonneg(a) and _finite_nonneg(b) and math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-12)


FREEZE_ENV = "DELENTIA_FREEZE_FILE"
_LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)")


def freeze_problems(model: str, price_in: Any, price_out: Any, budget_usd: Any, *, force: bool = False) -> List[str]:
    """What stands between a paid run of ONE model and the freeze: nothing to check against a loopback fake (no money can move), otherwise the file named by DELENTIA_FREEZE_FILE must match.
    Every command that can spend money asks this before it sends anything. `force` = the caller talks to the real endpoint whatever DELENTIA_OPENROUTER_BASE_URL says."""
    from rct_control_plane.llm_provider import openrouter_base_url
    if not force and _LOOPBACK.match(openrouter_base_url()):
        return []
    try:
        budget = float(budget_usd)
    except (TypeError, ValueError):
        return [f"the budget {budget_usd!r} is not a number"]
    return check_for_run(os.environ.get(FREEZE_ENV), [model], {model: {"in": price_in, "out": price_out}}, budget)


def check_for_run(path: Optional[str], models: List[str], prices: Dict[str, Dict[str, float]], budget_usd: float) -> List[str]:
    """What the orchestrator asks before a real run: the file exists, nothing differs, and the run is the one that was frozen (same models, same prices, a budget not above the frozen one)."""
    if not path:
        return ["a frozen configuration is required for a real run: python -m research.paid_run_freeze write --models ... --live-prices --stages ... --budget-usd ... --provider-cap-confirmed --out freeze.json (then --freeze-file, or set DELENTIA_FREEZE_FILE for the research commands)"]
    try:
        frozen = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"the freeze file cannot be read: {type(exc).__name__}"]
    diffs = check(frozen)
    frozen_models = {m["id"]: m for m in frozen.get("models", []) if isinstance(m, dict) and "id" in m}
    if set(models) - set(frozen_models):
        diffs.append(f"the run names models that were not frozen: {', '.join(sorted(set(models) - set(frozen_models)))}")
    for m in models:
        if m in frozen_models and m in prices:
            if not _same_price(prices[m].get("in"), frozen_models[m]["price_in_per_mtok"]) or not _same_price(prices[m].get("out"), frozen_models[m]["price_out_per_mtok"]):
                diffs.append(f"the price of {m} changed since the freeze")
    frozen_budget = (frozen.get("spending") or {}).get("budget_usd")
    if isinstance(frozen_budget, (int, float)) and budget_usd > frozen_budget:
        diffs.append(f"the budget ${budget_usd} is above the frozen ${frozen_budget}")
    return diffs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--models", required=True)
    w.add_argument("--prices-file", default=None, help='JSON {"model-id": {"in": usd_per_Mtok, "out": usd_per_Mtok}}')
    w.add_argument("--live-prices", action="store_true", help="read the prices from OpenRouter's public model list (what the orchestrator's --live-prices reads); a --prices-file entry wins for the same model")
    w.add_argument("--prices-source", default=None)
    w.add_argument("--stages", required=True)
    w.add_argument("--budget-usd", type=float, required=True)
    w.add_argument("--max-cost-per-run-usd", type=float, default=0.0)
    w.add_argument("--reserve-usd", type=float, default=0.0)
    w.add_argument("--provider-cap-confirmed", action="store_true")
    w.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("check")
    c.add_argument("file", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "write":
        try:
            if not args.prices_file and not args.live_prices:
                raise FreezeError("give the prices: --live-prices (OpenRouter's public list) or --prices-file")
            models = [m.strip() for m in args.models.split(",") if m.strip()]
            prices: Dict[str, Any] = {}
            if args.live_prices:
                prices.update(live_prices(models))
            if args.prices_file:
                prices.update(json.loads(Path(args.prices_file).read_text(encoding="utf-8")))
            source = args.prices_source or ("OpenRouter public model list, read " + time.strftime("%Y-%m-%d %H:%M") if args.live_prices and not args.prices_file else "prices file")
            record = build(models, prices, source, [s.strip() for s in args.stages.split(",") if s.strip()], args.budget_usd,
                           args.provider_cap_confirmed, args.max_cost_per_run_usd, args.reserve_usd)
        except (FreezeError, OSError, ValueError) as exc:
            print("refused:", exc, file=sys.stderr)
            return 2
        args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"frozen {record['code']['sha'][:10]} ({record['code']['branch']}), {len(record['models'])} model(s), stages {','.join(record['stages'])}, budget ${record['spending']['budget_usd']} -> {args.out}")
        return 0
    diffs = check(json.loads(args.file.read_text(encoding="utf-8")))
    for d in diffs:
        print("DIFFERS:", d)
    print("the run matches the freeze" if not diffs else f"{len(diffs)} difference(s): do not spend")
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
