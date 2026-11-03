"""
Goal-aware COMPRESS, before and after (Round 109). Rules: research/COMPRESS_POLICY_CRITERIA_R109.md (written before the code).

    DELENTIA_COMPRESS_POLICY=off python scripts/measure_delta_tokens_r109.py --out off.json
    python scripts/measure_delta_tokens_r109.py --out on.json
    python scripts/compare_compress_policy_r109.py off.json on.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

LOOKUP = ("literal", "partial", "single")
WHOLE = ("generic", "unrelated")


def load(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def by_item(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["name"]: r for r in report["corpus"]}


def med(values: List[float]) -> float:
    return round(statistics.median(values), 1) if values else float("nan")


def main(off_path: str, on_path: str) -> int:
    off, on = load(off_path), load(on_path)
    a, b = by_item(off), by_item(on)
    verdicts: List[str] = []
    print("goal kind   | share filtered (off -> on) | saved % when filtered (off -> on) | saved % overall (off -> on) | needle kept % (off -> on)")
    for kind in LOOKUP + ("edit",) + WHOLE:
        row = {"applied": ([], []), "when": ([], []), "overall": ([], []), "kept": ([], [])}
        for name in a:
            for idx, item in ((0, a[name]), (1, b[name])):
                g = item["goals"][kind]
                row["applied"][idx].append(g["applied_pct"])
                row["overall"][idx].append(g["saved_pct_median"])
                row["kept"][idx].append(g["needle_kept_pct"])
                if g.get("saved_pct_median_when_applied") is not None:
                    row["when"][idx].append(g["saved_pct_median_when_applied"])
        print(f"{kind:<11} | {statistics.mean(row['applied'][0]):>5.0f} -> {statistics.mean(row['applied'][1]):<5.0f}            | {med(row['when'][0]):>6} -> {med(row['when'][1]):<6}               | "
              f"{med(row['overall'][0]):>6} -> {med(row['overall'][1]):<6}          | {statistics.mean(row['kept'][0]):>5.1f} -> {statistics.mean(row['kept'][1]):<5.1f}")
    print()
    # R1: whole-text and no-signal goals lose nothing
    losers = [(n, k, b[n]["goals"][k]["needle_kept_pct"]) for n in b for k in WHOLE if b[n]["goals"][k]["needle_kept_pct"] < 100.0]
    verdicts.append(f"R1 whole-text / no-signal goals lose nothing: {'PASS' if not losers else 'FAIL'} {losers}")
    # R2: lookups keep what they had
    r2_bad = []
    for n in a:
        for k in LOOKUP:
            if b[n]["goals"][k]["needle_kept_pct"] < a[n]["goals"][k]["needle_kept_pct"]:
                r2_bad.append((n, k, "kept", a[n]["goals"][k]["needle_kept_pct"], b[n]["goals"][k]["needle_kept_pct"]))
    r2_save = []
    for k in LOOKUP:
        before = [a[n]["goals"][k]["saved_pct_median"] for n in a]
        after = [b[n]["goals"][k]["saved_pct_median"] for n in a]
        drop = med(before) - med(after)
        r2_save.append((k, med(before), med(after), round(drop, 1)))
    verdicts.append(f"R2 lookups: needle kept never lower: {'PASS' if not r2_bad else 'FAIL'} {r2_bad}")
    verdicts.append("R2 lookups: median saving over all items (off, on, drop) " + str(r2_save) + " -> rule 'drop at most 5 points, single not lower': "
                    + ("PASS" if all(d <= 5 for _, _, _, d in r2_save) and r2_save[2][3] <= 0 else "FAIL (see the filtered-only columns above: the drop comes from requests with no content word, which are no longer filtered)"))
    # R3: edit goals are shown whole
    r3 = [(n, b[n]["goals"]["edit"]["lines_shown_pct_median"]) for n in b if b[n]["goals"]["edit"]["lines_shown_pct_median"] < 100.0 or b[n]["goals"]["edit"]["needle_kept_pct"] < 100.0]
    verdicts.append(f"R3 edit goals are not filtered: {'PASS' if not r3 else 'FAIL'} {r3}")
    # R4: a lookup keeps most of the whole-episode saving
    r4 = {k: v["saved_pct"] for k, v in on["episodes"].items() if "task=lookup" in k and "menu=full" in k and "4 calls" in k}
    large = {k: v for k, v in r4.items() if "table" not in k and "log" not in k}
    verdicts.append(f"R4 lookup episodes (full menu, 4 calls after the read): {r4} -> items other than the generated table and log at least 40%: {'PASS' if all(v >= 40 for v in large.values()) else 'FAIL'}")
    verdicts.append(f"R5 never worse: {'PASS' if not on['q6_never_worse_violations'] else 'FAIL'}; exact recovery: {'PASS' if not on['q7_recovery_mismatches'] else 'FAIL'}; time: {on['q8_time_ms']}")
    print("\n".join(verdicts))
    print()
    print("whole episode, full menu, 4 calls after the read: saved % (off -> on)")
    for k, v in on["episodes"].items():
        if "menu=full" in k and "4 calls" in k:
            before = off["episodes"][k]["saved_pct"]
            print(f"  {k:<100} {before:>5.1f} -> {v['saved_pct']:>5.1f}")
    print()
    print("average whole-episode saving over a workload with this share of whole-text requests (the 4 large items, full menu, 4 calls; 'off' is a saving that removes information):")
    lookup_on = statistics.mean(v["saved_pct"] for k, v in on["episodes"].items() if "task=lookup" in k and "menu=full" in k and "4 calls" in k)
    lookup_off = statistics.mean(v["saved_pct"] for k, v in off["episodes"].items() if "task=lookup" in k and "menu=full" in k and "4 calls" in k)
    whole_off = statistics.mean(v["saved_pct"] for k, v in off["episodes"].items() if "task=whole" in k and "menu=full" in k and "4 calls" in k)
    whole_on = statistics.mean(v["saved_pct"] for k, v in on["episodes"].items() if "task=whole" in k and "menu=full" in k and "4 calls" in k)
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        print(f"  {int(share * 100):>3}% whole-text requests:  off {(1 - share) * lookup_off + share * whole_off:>5.1f}%   on {(1 - share) * lookup_on + share * whole_on:>5.1f}%")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
