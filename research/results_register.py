"""
Round 103: one register for every measurement that is run with a real (paid or local) model.

Why. Each tool writes its result somewhere of its own (the orchestrator a JSON report, the holdout runners a sealed sheet next to the sheet, the DAAES runs a sealed bundle). Nothing tied a
result to the commit it was run on, to the rule that was written BEFORE it was run, and to what it cost. Without that, a later reader cannot tell a pre-registered pass from a number found
afterwards, and a Master-document row can drift from the evidence under it.

An entry is one line of `research/RESULTS_REGISTER.jsonl` (append-only; a correction is a NEW entry that names the one it replaces, nothing is edited or deleted).

    python -m research.results_register add --stage P1 --model qwen/qwen3.5-flash-02-23 --provider openrouter \\
        --criteria research/rct7_round98_criteria.md --result research/results_round103/p1.json \\
        --verdict pass --est-usd 0.05 --actual-usd 0.04 --note "K.1.5 tool choice 27/30"
    python -m research.results_register render      # writes research/RESULTS_REGISTER.md from the JSONL
    python -m research.results_register verify      # every referenced file still has the hash it had; exits 1 if not

Rules the code enforces:
  * the criteria file must exist and is hashed at the moment of the entry; if the criteria file was last committed AFTER the result file was written, the entry is marked `criteria_after_result`
    (a rule written after the number is not a pre-registration, and the register says so);
  * the verdict is one of pass / fail / inconclusive / not_run (an arm that mostly errored is inconclusive, never a quiet fail or pass);
  * a paid provider needs an actual cost (the register has no use for a paid run whose cost is unknown); a local model may leave it at 0;
  * the commit is the repository's HEAD and the entry says whether the working tree was dirty;
  * beside the verdict and the cost an entry keeps what lets two entries be compared: the ARM measured (b0, d0, h0, an ablation arm), the seed, n (how many units the verdict stands on), a fixed vocabulary of
    metrics (speed: latency p50/p95/total, calls, errors; size: prompt/completion/cached tokens; behaviour: hard failures, false stops, found; plus `x_` free-form numbers), the upstream providers that answered,
    and an optional A/B block (baseline entry, effect, interval, n, paired, method). A name outside the vocabulary, a non-finite number, a baseline that is not in the register, an effect outside its own
    interval, or a paired comparison without n is refused. When the result file is a JSON object from one of our runners, its `metrics` and its count of hard failures are taken from it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "research" / "RESULTS_REGISTER.jsonl"
RENDERED = ROOT / "research" / "RESULTS_REGISTER.md"
VERDICTS = ("pass", "fail", "inconclusive", "not_run")
PROVIDERS = ("ollama", "openrouter", "none")
PAID = ("openrouter",)
# What an entry may carry beside the verdict and the cost. A fixed vocabulary, so that two entries can be compared; anything else must start with `x_` (free-form, numeric).
METRICS = ("model_calls", "model_errors", "tool_calls", "episodes", "successes", "hard_failures",
           "latency_p50_s", "latency_p95_s", "latency_total_s", "seconds", "prompt_tokens", "completion_tokens", "cached_tokens", "tokens_per_second",
           "false_stops", "found", "n_items")
COMPARE_KEYS = ("baseline_id", "effect", "ci_low", "ci_high", "n", "paired", "method", "metric")


def clean_metrics(raw: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Keep only numbers whose name is in the vocabulary (or starts with `x_`); a name outside it, or a value that is not a finite number, is refused rather than dropped."""
    out: Dict[str, float] = {}
    for key, value in (raw or {}).items():
        if key not in METRICS and not str(key).startswith("x_"):
            raise RegisterError(f"metric {key!r} is not in the vocabulary ({', '.join(METRICS)}) and does not start with x_")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
            raise RegisterError(f"metric {key!r} must be a finite number, not {value!r}")
        out[str(key)] = value
    return out


def clean_compare(raw: Optional[Dict[str, Any]], existing_ids: List[str]) -> Optional[Dict[str, Any]]:
    """A comparison (an A/B): the baseline entry must exist; an effect must sit inside its own interval; a paired comparison needs n."""
    if not raw:
        return None
    unknown = [k for k in raw if k not in COMPARE_KEYS]
    if unknown:
        raise RegisterError(f"compare has unknown keys {unknown}; allowed: {', '.join(COMPARE_KEYS)}")
    if raw.get("baseline_id") not in existing_ids:
        raise RegisterError(f"the baseline entry {raw.get('baseline_id')!r} is not in the register")
    effect, lo, hi = raw.get("effect"), raw.get("ci_low"), raw.get("ci_high")
    if effect is None or isinstance(effect, bool) or not isinstance(effect, (int, float)):
        raise RegisterError("a comparison needs a numeric effect")
    if (lo is None) != (hi is None):
        raise RegisterError("give both ends of the interval or neither")
    if lo is not None and hi is not None and not (lo <= effect <= hi):
        raise RegisterError("the effect must lie inside its own interval")
    if raw.get("paired") and not raw.get("n"):
        raise RegisterError("a paired comparison needs n")
    return {k: raw[k] for k in COMPARE_KEYS if k in raw}


class RegisterError(ValueError):
    """An entry the register refuses, with the reason."""


TEXT_SUFFIXES = (".md", ".json", ".jsonl", ".txt", ".py", ".csv", ".yml", ".yaml")


def sha256_file(path: Path) -> str:
    """SHA-256 of the file. A text file is hashed with its line endings made LF first: git on Windows may check the same file out with CRLF, and the same content must have the same hash on every machine."""
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(bytes([13, 10]), bytes([10]))
    return hashlib.sha256(data).hexdigest()


def _git(*args: str, cwd: Optional[Path] = None) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd or ROOT), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _commit_time(path: Path) -> Optional[float]:
    """Unix time of the last commit that touched this file, or None when it was never committed."""
    got = _git("log", "-1", "--format=%ct", "--", path.name, cwd=path.resolve().parent)
    return float(got) if got else None


def read_entries(register: Optional[Path] = None) -> List[Dict[str, Any]]:
    register = register or REGISTER                      # looked up at call time, so a test (or a copy of the register) can point it elsewhere
    if not register.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    for n, line in enumerate(register.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except ValueError as exc:
                raise RegisterError(f"{register.name} line {n} is not JSON: {exc}") from exc
    return entries


def result_defaults(result: Path) -> Dict[str, Any]:
    """If the result file is a JSON object from one of our runners (research/live_workflows.py and friends), take its `metrics` and the number of hard failures from it, so nobody retypes them."""
    try:
        data = json.loads(Path(result).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    found: Dict[str, Any] = {}
    metrics = data.get("metrics")
    if isinstance(metrics, dict):
        found.update({k: v for k, v in metrics.items() if k in METRICS and isinstance(v, (int, float)) and not isinstance(v, bool)})
    if isinstance(data.get("hard_failures"), list):
        found["hard_failures"] = len(data["hard_failures"])
    return found


# The settings that change what a measurement means. Only these are recorded, only their names are read from the environment, and a name that looks like a secret is never recorded.
CONFIG_ENV = ("DELENTIA_TOOL_MENU", "DELENTIA_TOOL_MENU_FORMAT", "DELENTIA_OLLAMA_THINK", "DELENTIA_OLLAMA_NUM_CTX", "DELENTIA_PROMPT_LAYOUT", "DELENTIA_ASK_AND_WAIT", "DELENTIA_WARM_RECALL",
              "DELENTIA_PARALLEL_TOOLS", "DELENTIA_FDIA_POLICY_DEFAULT", "DELENTIA_TAINT_GATE", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_VERIFY_GROUNDING", "DELENTIA_VERIFY_V2", "DELENTIA_VERIFY_V3",
              "DELENTIA_RCT7_JUDGE", "DELENTIA_RCT7_CHAIN", "DELENTIA_RCT7_JUDGE_CONTEXT", "DELENTIA_MEMORY_EMBED", "DELENTIA_MEMORY_EMBED_MODEL", "DELENTIA_MEMORY_POLICY", "DELENTIA_MAX_PINNED_SHOWN",
              "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", "DELENTIA_DAILY_BUDGET_USD", "DELENTIA_OPENROUTER_PROVIDER_ORDER", "DELENTIA_OPENROUTER_PROVIDER_ONLY",
              "DELENTIA_OPENROUTER_PROVIDER_IGNORE", "DELENTIA_OPENROUTER_ALLOW_FALLBACKS", "DELENTIA_OPENROUTER_DATA_COLLECTION", "DELENTIA_OPENROUTER_ZDR", "DELENTIA_OPENROUTER_REQUIRE_PARAMETERS",
              "DELENTIA_OPENROUTER_QUANTIZATIONS", "DELENTIA_OPENROUTER_TIMEOUT_S", "DELENTIA_RESEARCH_MODE")
SECRETISH = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def config_snapshot() -> Dict[str, Any]:
    """What was switched on when a run happened: the settings above that are set, the package version, the interpreter and the platform, and a hash of all of it. Never a value whose name looks like a secret."""
    import platform
    env = {k: os.environ[k] for k in CONFIG_ENV if os.environ.get(k) is not None and not any(w in k for w in SECRETISH)}
    try:
        from rct_control_plane._version import PACKAGE_VERSION as version
    except Exception:                                                # noqa: BLE001 - a register must still work from a bare checkout
        version = "unknown"
    snap: Dict[str, Any] = {"env": dict(sorted(env.items())), "package_version": version, "python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}"}
    snap["sha256"] = hashlib.sha256(json.dumps(snap, sort_keys=True).encode("utf-8")).hexdigest()
    return snap


def result_extras(result: Path) -> Dict[str, Any]:
    """The failure label and the configuration a runner wrote into its own result file (taken at RUN time, which is worth more than a snapshot taken when somebody registers it)."""
    try:
        data = json.loads(Path(result).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    extras: Dict[str, Any] = {}
    if isinstance(data.get("failure_label"), str):
        extras["failure_label"] = data["failure_label"]
    if isinstance(data.get("config"), dict):
        extras["config"] = data["config"]
    return extras


def clean_failure_label(label: Optional[str], verdict: str) -> Optional[str]:
    """A label comes from the project's own taxonomy (research/failure_taxonomy.py). A pass has none; a fail without one is stored as such, never guessed."""
    if label in (None, ""):
        return None
    from research.failure_taxonomy import LABELS
    if label not in LABELS:
        raise RegisterError(f"failure label {label!r} is not one of {', '.join(LABELS)}")
    if verdict == "pass" and label != "none":
        raise RegisterError("a passing entry cannot carry a failure label")
    return label


def add_entry(*, stage: str, model: str, provider: str, criteria: Path, result: Path, verdict: str, est_usd: float = 0.0,
              actual_usd: Optional[float] = None, note: str = "", replaces: Optional[str] = None, register: Optional[Path] = None,
              now: Optional[_dt.datetime] = None, metrics: Optional[Dict[str, Any]] = None, arm: str = "", compare: Optional[Dict[str, Any]] = None,
              seed: Optional[int] = None, n: Optional[int] = None, served_by: Optional[List[str]] = None, from_result: bool = True,
              failure_label: Optional[str] = None, config: Optional[Dict[str, Any]] = None, artifacts: Optional[List[Path]] = None) -> Dict[str, Any]:
    register = register or REGISTER
    if verdict not in VERDICTS:
        raise RegisterError(f"verdict must be one of {', '.join(VERDICTS)}, not {verdict!r}")
    if provider not in PROVIDERS:
        raise RegisterError(f"provider must be one of {', '.join(PROVIDERS)}, not {provider!r}")
    if not stage.strip() or not model.strip():
        raise RegisterError("a stage and a model are required")
    for label, p in (("criteria", criteria), ("result", result)):
        if not Path(p).is_file():
            raise RegisterError(f"the {label} file {p} does not exist")
    if provider in PAID and (actual_usd is None or actual_usd < 0):
        raise RegisterError("a paid run needs its actual cost (from the provider's own usage figures); the register does not accept a paid run whose cost is unknown")
    existing = read_entries(register)
    if replaces is not None and not any(e.get("id") == replaces for e in existing):
        raise RegisterError(f"there is no entry {replaces} to replace")
    criteria, result = Path(criteria), Path(result)
    merged = {**(result_defaults(result) if from_result else {}), **(metrics or {})}              # what the person typed wins over what the file said
    clean = clean_metrics(merged)
    cmp_block = clean_compare(compare, [str(e.get("id")) for e in existing])
    if n is not None and n < 0:
        raise RegisterError("n cannot be negative")
    extras = result_extras(result) if from_result else {}
    flabel = clean_failure_label(failure_label if failure_label is not None else extras.get("failure_label"), verdict)
    if config is not None:
        cfg: Dict[str, Any] = {**config, "source": "given"}
    elif "config" in extras:
        cfg = {**extras["config"], "source": "recorded_by_the_runner"}
    else:
        cfg = {**config_snapshot(), "source": "taken_at_registration"}             # weaker: the environment of the person registering, not of the run
    files: List[Dict[str, Any]] = []
    for art in artifacts or []:
        if not Path(art).is_file():
            raise RegisterError(f"the artifact {art} does not exist")
        files.append({"file": _rel(Path(art)), "sha256": sha256_file(Path(art))})
    ct, rt = _commit_time(criteria), result.stat().st_mtime
    after = bool(ct is not None and ct > rt + 1.0) or ct is None
    when = (now or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dirty = bool(_git("status", "--porcelain"))
    entry: Dict[str, Any] = {
        "id": f"R{len(existing) + 1:04d}",
        "date": when,
        "stage": stage.strip(),
        "model": model.strip(),
        "provider": provider,
        "commit": _git("rev-parse", "HEAD") or "unknown",
        "tree_dirty": dirty,
        "criteria": {"file": _rel(criteria), "sha256": sha256_file(criteria), "criteria_after_result": after},
        "result": {"file": _rel(result), "sha256": sha256_file(result)},
        "verdict": verdict,
        "estimated_usd": round(float(est_usd), 6),
        "actual_usd": None if actual_usd is None else round(float(actual_usd), 6),
        "note": note.strip(),
        "replaces": replaces,
        "arm": arm.strip(),
        "seed": seed,
        "n": n,
        "metrics": clean,
        "served_by": sorted(set(served_by or [])),
        "compare": cmp_block,
        "failure_label": flabel,
        "config": cfg,
        "artifacts": files,
    }
    register.parent.mkdir(parents=True, exist_ok=True)
    with open(register, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def verify(register: Optional[Path] = None, root: Path = ROOT) -> List[str]:
    """Problems found; an empty list means every referenced file still has the hash it was registered with."""
    register = register or REGISTER
    problems: List[str] = []
    seen: set = set()
    for e in read_entries(register):
        if e.get("id") in seen:
            problems.append(f"{e.get('id')}: the id is used twice")
        base = (e.get("compare") or {}).get("baseline_id")
        if base is not None and base not in seen:
            problems.append(f"{e.get('id')}: it compares with {base}, which is not an earlier entry")
        seen.add(e.get("id"))
        refs = [("criteria", e.get("criteria") or {}), ("result", e.get("result") or {})] + [("artifact", a) for a in (e.get("artifacts") or [])]
        for key, ref in refs:
            path = (root / ref.get("file", "")) if not Path(ref.get("file", "")).is_absolute() else Path(ref["file"])
            if not path.is_file():
                problems.append(f"{e.get('id')}: the {key} file {ref.get('file')} is missing")
            elif sha256_file(path) != ref.get("sha256"):
                problems.append(f"{e.get('id')}: the {key} file {ref.get('file')} changed after it was registered")
    return problems


def render(register: Optional[Path] = None) -> str:
    entries = read_entries(register or REGISTER)
    replaced = {e["replaces"] for e in entries if e.get("replaces")}
    lines = ["# Results register", "",
             "Generated by `python -m research.results_register render` from `RESULTS_REGISTER.jsonl` (append-only). A row marked **late rule** had its criteria committed after the result was written: it is a description, not a pre-registered test.", "",
             "| id | date | stage | model / arm | verdict | failure | cost (est / actual) | speed | tokens in / out | A/B | commit / config | rule | note |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        cost = f"${e['estimated_usd']:.4f} / " + ("n/a" if e.get("actual_usd") is None else f"${e['actual_usd']:.4f}")
        rule = "**late rule**" if e["criteria"].get("criteria_after_result") else "before"
        status = e["verdict"] + (" (replaced)" if e["id"] in replaced else "")
        m = e.get("metrics") or {}
        speed = "-" if "latency_p50_s" not in m else f"p50 {m['latency_p50_s']} s" + (f", p95 {m['latency_p95_s']} s" if "latency_p95_s" in m else "") + (f", {m['model_calls']:g} calls" if "model_calls" in m else "")
        tokens = "-" if "prompt_tokens" not in m else f"{m['prompt_tokens']:g} / {m.get('completion_tokens', 0):g}"
        c = e.get("compare")
        ab = "-" if not c else f"vs {c['baseline_id']}: {c['effect']:+g}" + (f" [{c['ci_low']:g}, {c['ci_high']:g}]" if c.get("ci_low") is not None else "") + (f" n={c['n']}" if c.get("n") else "")
        who = f"`{e['model']}`" + (f" / {e['arm']}" if e.get("arm") else "")
        cfg = e.get("config") or {}
        cfgtxt = "-" if not cfg.get("sha256") else f"`{cfg['sha256'][:7]}` ({cfg.get('source', '?').replace('_', ' ')})"
        lines.append(f"| {e['id']} | {e['date']} | {e['stage']} | {who} | {status} | {e.get('failure_label') or '-'} | {cost} | {speed} | {tokens} | {ab} | `{e['commit'][:7]}`{'+dirty' if e.get('tree_dirty') else ''} / {cfgtxt} | {rule} | {e.get('note', '')} |")
    paid = sum(e["actual_usd"] for e in entries if e.get("actual_usd"))
    lines += ["", f"Entries: {len(entries)}. Total actual cost registered: ${paid:.4f}."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--stage", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--provider", choices=PROVIDERS, required=True)
    a.add_argument("--criteria", type=Path, required=True)
    a.add_argument("--result", type=Path, required=True)
    a.add_argument("--verdict", choices=VERDICTS, required=True)
    a.add_argument("--est-usd", type=float, default=0.0)
    a.add_argument("--actual-usd", type=float, default=None)
    a.add_argument("--note", default="")
    a.add_argument("--replaces", default=None)
    a.add_argument("--arm", default="", help="the arm or configuration measured (b0, d0, h0, an ablation arm, a prompt variant)")
    a.add_argument("--seed", type=int, default=None)
    a.add_argument("--n", type=int, default=None, help="how many units (episodes, items, runs) the verdict stands on")
    a.add_argument("--metrics-json", type=Path, default=None, help="a JSON object of numbers from the vocabulary; overrides what the result file carries")
    a.add_argument("--compare-json", type=Path, default=None, help='{"baseline_id": "R0003", "effect": 0.12, "ci_low": 0.02, "ci_high": 0.21, "n": 40, "paired": true, "method": "paired bootstrap"}')
    a.add_argument("--failure-label", default=None, help="one label of research/failure_taxonomy.py; taken from the result file when the runner wrote one")
    a.add_argument("--artifact", type=Path, action="append", default=[], help="a file to link and hash (per-item results, a log, a ledger); repeatable")
    a.add_argument("--served-by", default="", help="comma-separated upstream providers that answered (OpenRouter reports them)")
    sub.add_parser("render")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            def _load(path: Optional[Path]) -> Optional[Dict[str, Any]]:
                return None if path is None else json.loads(Path(path).read_text(encoding="utf-8"))
            e = add_entry(stage=args.stage, model=args.model, provider=args.provider, criteria=args.criteria, result=args.result, verdict=args.verdict,
                          est_usd=args.est_usd, actual_usd=args.actual_usd, note=args.note, replaces=args.replaces, arm=args.arm, seed=args.seed, n=args.n,
                          metrics=_load(args.metrics_json), compare=_load(args.compare_json), served_by=[s for s in args.served_by.split(",") if s.strip()], failure_label=args.failure_label, artifacts=args.artifact)
            print(f"registered {e['id']}: {e['stage']} {e['model']} {e['verdict']}" + ("  (the criteria were committed after the result: marked as a late rule)" if e["criteria"]["criteria_after_result"] else ""))
            return 0
        if args.cmd == "render":
            RENDERED.write_text(render(), encoding="utf-8", newline="\n")
            print(f"wrote {_rel(RENDERED)}")
            return 0
        problems = verify()
        for p in problems:
            print("PROBLEM:", p)
        print("register is intact" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    except RegisterError as exc:
        print("refused:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
