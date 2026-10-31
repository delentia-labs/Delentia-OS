"""
Round 106: count the friction an outside tester reports, the same way for every tester.

    python scripts/tally_tester_feedback.py <folder of filled forms> [--out report.md]

A filled form is the text of docs/demo/TESTER_FEEDBACK_FORM_EN.md (or _TH) with the blanks filled in and saved as a .md file. The lines it reads:

    tester: <an alias, never a real name>
    real_task: yes | no
    help: none | docs_only | asked_someone
    1. download_and_install: done | 7 | S3
         (a step) (result)      (minutes) (severity)

Results: done, done_with_help, blocked, skipped. Severities: none, S3 (cosmetic), S2 (confusing), S1 (needed a workaround), S0 (could not go on).
A FRICTION POINT is a step marked S0, S1 or S2, or one whose result is blocked or done_with_help. It is counted per step and per tester, and reported as k of n testers with a 95% Wilson interval:
with a handful of testers the interval is wide, and that width is the honest reading. A form with an unknown step, result or severity is refused by line number, never guessed at.
Nothing here judges a tester; it counts what they wrote. Only the structured lines are read; free text is never parsed, copied or printed.
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STEPS = ("download_and_install", "first_start", "first_approver", "choose_model", "first_request", "approve_something", "backup", "uninstall")
RESULTS = ("done", "done_with_help", "blocked", "skipped")
SEVERITIES = ("none", "S3", "S2", "S1", "S0")
FRICTION_SEVERITIES = ("S2", "S1", "S0")
HELP = ("none", "docs_only", "asked_someone")
STEP_LINE = re.compile(r"^\s*(\d+)\.\s*([a-z_]+)\s*:\s*([a-z_]+)\s*\|\s*(\d+)\s*\|\s*(none|S[0-3])\s*$")
STEP_LIKE = re.compile(r"^\s*\d+\.\s*[A-Za-z_]+\s*:.*\|")           # looks like a step line: a number, a name, a colon and a bar. If it then does not parse in full it is refused, not skipped.
FIELD_LINE = re.compile(r"^\s*(tester|real_task|help|os|installed_with|date)\s*:\s*(.*?)\s*$")


class FormError(ValueError):
    pass


def parse_form(text: str, name: str = "form") -> Dict[str, Any]:
    fields: Dict[str, str] = {}
    steps: Dict[str, Dict[str, Any]] = {}
    for number, line in enumerate(text.splitlines(), 1):
        field = FIELD_LINE.match(line)
        if field and field.group(1) not in fields:
            fields[field.group(1)] = field.group(2)
            continue
        step = STEP_LINE.match(line)
        if not step:
            if STEP_LIKE.match(line):
                raise FormError(f"{name} line {number}: cannot read this step line (expected 'n. step: result | minutes | severity', minutes a whole number, severity none or S0-S3)")
            continue
        _, key, result, minutes, severity = step.groups()
        if key not in STEPS:
            raise FormError(f"{name} line {number}: unknown step {key!r} (known: {', '.join(STEPS)})")
        if result not in RESULTS:
            raise FormError(f"{name} line {number}: unknown result {result!r} (one of {', '.join(RESULTS)})")
        if severity not in SEVERITIES:
            raise FormError(f"{name} line {number}: unknown severity {severity!r} (one of {', '.join(SEVERITIES)})")
        if key in steps:
            raise FormError(f"{name} line {number}: step {key!r} appears twice")
        steps[key] = {"result": result, "minutes": int(minutes), "severity": severity}
    if not fields.get("tester"):
        raise FormError(f"{name}: no 'tester:' line (an alias, never a real name)")
    if fields.get("real_task") not in ("yes", "no"):
        raise FormError(f"{name}: 'real_task:' must be yes or no")
    if fields.get("help") not in HELP:
        raise FormError(f"{name}: 'help:' must be one of {', '.join(HELP)}")
    if not steps:
        raise FormError(f"{name}: no step lines were found")
    return {"tester": fields["tester"], "real_task": fields["real_task"] == "yes", "help": fields["help"], "steps": steps}


def is_friction(entry: Dict[str, Any]) -> bool:
    return entry["severity"] in FRICTION_SEVERITIES or entry["result"] in ("blocked", "done_with_help")


def tally(forms: List[Dict[str, Any]]) -> Dict[str, Any]:
    from research.rct7_holdout import wilson
    n = len(forms)
    per_step: Dict[str, Any] = {}
    for step in STEPS:
        entries = [f["steps"][step] for f in forms if step in f["steps"] and f["steps"][step]["result"] != "skipped"]
        friction = sum(is_friction(e) for e in entries)
        blocked = sum(e["result"] == "blocked" for e in entries)
        per_step[step] = {"testers": len(entries), "friction": friction, "friction_interval": wilson(friction, len(entries)) if entries else None, "blocked": blocked,
                          "median_minutes": statistics.median(e["minutes"] for e in entries) if entries else None}
    first = [f for f in forms if "first_request" in f["steps"] and f["steps"]["first_request"]["result"] != "skipped"]
    unaided = sum(f["steps"]["first_request"]["result"] == "done" and f["help"] in ("none", "docs_only") for f in first)
    return {"testers": n, "used_for_a_real_task": sum(f["real_task"] for f in forms), "per_step": per_step,
            "first_request_without_asking": {"k": unaided, "of": len(first), "interval": wilson(unaided, len(first)) if first else None},
            "any_blocked": sorted({s for f in forms for s, e in f["steps"].items() if e["result"] == "blocked"})}


def render(result: Dict[str, Any]) -> str:
    lines = ["# Tester feedback, counted\n", f"{result['testers']} tester(s); {result['used_for_a_real_task']} used it for something they actually needed.\n",
             "| step | testers | friction points | 95% interval | blocked | median minutes |", "|---|---|---|---|---|---|"]
    for step, row in result["per_step"].items():
        interval = "-" if row["friction_interval"] is None else f"{row['friction_interval'][0]:.2f}-{row['friction_interval'][1]:.2f}"
        lines.append(f"| {step} | {row['testers']} | {row['friction']} | {interval} | {row['blocked']} | {row['median_minutes'] if row['median_minutes'] is not None else '-'} |")
    first = result["first_request_without_asking"]
    lines.append("")
    if first["of"]:
        lines.append(f"First request done without asking anyone: {first['k']} of {first['of']} (95% interval {first['interval'][0]:.2f}-{first['interval'][1]:.2f}).")
    else:
        lines.append("First request: nobody reached it.")
    if result["any_blocked"]:
        lines.append("Steps where at least one tester was blocked: " + ", ".join(result["any_blocked"]) + ".")
    lines.append("\nA friction point is a step marked S0, S1 or S2, or one that was blocked or needed help. With a few testers the intervals are wide: read them as such. This counts what testers wrote; it says nothing about people who did not try.")
    return "\n".join(lines) + "\n"


def load_folder(folder: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    forms, problems = [], []
    for path in sorted(folder.glob("*.md")):
        try:
            forms.append(parse_form(path.read_text(encoding="utf-8"), path.name))
        except FormError as exc:
            problems.append(str(exc))
    return forms, problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    forms, problems = load_folder(Path(args.folder))
    for p in problems:
        print("refused:", p, file=sys.stderr)
    if not forms:
        print("no usable form found", file=sys.stderr)
        return 2
    text = render(tally(forms))
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
