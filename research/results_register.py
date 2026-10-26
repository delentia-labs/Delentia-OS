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
  * the commit is the repository's HEAD and the entry says whether the working tree was dirty.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
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


class RegisterError(ValueError):
    """An entry the register refuses, with the reason."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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


def read_entries(register: Path = REGISTER) -> List[Dict[str, Any]]:
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


def add_entry(*, stage: str, model: str, provider: str, criteria: Path, result: Path, verdict: str, est_usd: float = 0.0,
              actual_usd: Optional[float] = None, note: str = "", replaces: Optional[str] = None, register: Path = REGISTER,
              now: Optional[_dt.datetime] = None) -> Dict[str, Any]:
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
    }
    register.parent.mkdir(parents=True, exist_ok=True)
    with open(register, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def verify(register: Path = REGISTER, root: Path = ROOT) -> List[str]:
    """Problems found; an empty list means every referenced file still has the hash it was registered with."""
    problems: List[str] = []
    seen: set = set()
    for e in read_entries(register):
        if e.get("id") in seen:
            problems.append(f"{e.get('id')}: the id is used twice")
        seen.add(e.get("id"))
        for key in ("criteria", "result"):
            ref = e.get(key) or {}
            path = (root / ref.get("file", "")) if not Path(ref.get("file", "")).is_absolute() else Path(ref["file"])
            if not path.is_file():
                problems.append(f"{e.get('id')}: the {key} file {ref.get('file')} is missing")
            elif sha256_file(path) != ref.get("sha256"):
                problems.append(f"{e.get('id')}: the {key} file {ref.get('file')} changed after it was registered")
    return problems


def render(register: Path = REGISTER) -> str:
    entries = read_entries(register)
    replaced = {e["replaces"] for e in entries if e.get("replaces")}
    lines = ["# Results register", "",
             "Generated by `python -m research.results_register render` from `RESULTS_REGISTER.jsonl` (append-only). A row marked **late rule** had its criteria committed after the result was written: it is a description, not a pre-registered test.", "",
             "| id | date | stage | model | verdict | cost (est / actual) | commit | rule | note |", "|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        cost = f"${e['estimated_usd']:.4f} / " + ("n/a" if e.get("actual_usd") is None else f"${e['actual_usd']:.4f}")
        rule = "**late rule**" if e["criteria"].get("criteria_after_result") else "before"
        status = e["verdict"] + (" (replaced)" if e["id"] in replaced else "")
        lines.append(f"| {e['id']} | {e['date']} | {e['stage']} | `{e['model']}` | {status} | {cost} | `{e['commit'][:7]}`{'+dirty' if e.get('tree_dirty') else ''} | {rule} | {e.get('note', '')} |")
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
    sub.add_parser("render")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            e = add_entry(stage=args.stage, model=args.model, provider=args.provider, criteria=args.criteria, result=args.result, verdict=args.verdict,
                          est_usd=args.est_usd, actual_usd=args.actual_usd, note=args.note, replaces=args.replaces)
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
