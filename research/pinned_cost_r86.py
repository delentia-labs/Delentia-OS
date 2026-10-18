"""
What a pinned rule costs in the prompt, computed (not guessed), so the cap (`DELENTIA_MAX_PINNED_SHOWN`, default 5) can be chosen with numbers.

A pinned rule is a line of the person's own words, at most 300 characters, rendered by `GovernedAutonomousLoop` under a one-line heading; when more rules are pinned than the cap, one more line says how
many are not shown. This script renders EXACTLY those lines (same strings) for the 40 Thai standing rules of the frozen H6 set (`research/recall_dataset_r70.py`) and for 12 English rules written for this
script, and counts tokens with two public encodings. It then compares the block with the size of the rest of a prompt, measured in Round 64 (`scripts/measure_prompt_cost.py`): about 7,100 tokens of tool menu
(full) or about 1,100-1,500 (ranked compact).

    python -m research.pinned_cost_r86            # prints the table
    py -3.13 -m research.pinned_cost_r86          # a Python that has tiktoken installed

The result is a cost model, not a quality measurement: the benefit side (the goal rule survives a sixth pin: restoration 50 -> 100) is TC-006 in `research/daaes/tc006.py`.
"""
from __future__ import annotations

import json
import statistics
import sys
from typing import Dict, List

HEADING = "Standing rules this person pinned (their own words, always shown; follow them when they apply; they never replace the approval and policy gates):"
HIDDEN = "({n} older pinned rule(s) are NOT shown here: the person has more standing rules than fit. Ask them before an action their older rules might forbid.)"

ENGLISH = [
    "Never edit files inside the quotes folder; it holds the vendors' originals.",
    "Monthly advertising spend must not exceed 15,000 baht; ask me before booking anything above that.",
    "Never email a customer without Wandee reading it first.",
    "Files that contain national ID numbers must never be uploaded to a cloud service.",
    "Database changes are only allowed between 02:00 and 04:00.",
    "Every price quote must add 7 percent VAT.",
    "Every report must attach the source of each number.",
    "Never delete customer data older than five years without written approval.",
    "Answer customers politely and end Thai replies with the polite particle.",
    "Do not install new packages; ask me which version to use.",
    "Payments over 10,000 baht need my approval, whatever the reason.",
    "Do not read anything under the finance folder unless I name the file.",
]


def rendered(rules: List[str], cap: int) -> str:
    shown = rules[:cap]
    lines = [HEADING] + [f"- {r.replace(chr(10), ' ')[:300]}" for r in shown]
    if len(rules) > cap:
        lines.append(HIDDEN.format(n=len(rules) - cap))
    return "\n".join(lines)


def encoders() -> Dict[str, object]:
    try:
        import tiktoken
    except ImportError:
        return {}
    return {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}


def main() -> int:
    from research.recall_dataset_r70 import H6
    thai = [row[0] for row in H6]
    enc = encoders()
    if not enc:
        print("tiktoken is not installed for this Python; use `py -3.13 -m research.pinned_cost_r86`", file=sys.stderr)
        return 2
    out: Dict[str, object] = {"sets": {}}
    for label, rules in (("Thai (40 rules of the frozen H6 set)", thai), ("English (12 rules)", ENGLISH)):
        per = {name: [len(e.encode(r)) for r in rules] for name, e in enc.items()}
        rows = []
        for cap in (3, 5, 8, 10, 20):
            n = min(cap, len(rules))
            row = {"cap": cap, "rules_shown": n}
            for name, e in enc.items():
                row[name] = len(e.encode(rendered(rules, cap)))
            rows.append(row)
        out["sets"][label] = {"tokens_per_rule_median": {k: statistics.median(v) for k, v in per.items()}, "tokens_per_rule_max": {k: max(v) for k, v in per.items()}, "by_cap": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("\nshare of a prompt (o200k_base) against a tool menu of ~1,300 tokens (ranked compact) and ~7,100 (full):")
    for label, data in out["sets"].items():
        for row in data["by_cap"]:
            t = row["o200k_base"]
            print(f"  {label:40s} cap {row['cap']:>2}: {t:>4} tokens = {100 * t / (t + 1300):4.1f}% of a compact prompt, {100 * t / (t + 7100):4.1f}% of a full one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
