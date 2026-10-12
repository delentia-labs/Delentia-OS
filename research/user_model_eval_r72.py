"""
Round 72: measure the user-model detector (rct_control_plane/user_model.py) on the labelled sentences of research/user_model_dataset_r72.py. Criteria: research/round72_criteria.md section 3.

    python research/user_model_eval_r72.py            # DEV only (what the rules were written against)
    python research/user_model_eval_r72.py --holdout  # HOLDOUT, once (refuses a second run)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
import user_model_dataset_r72 as data  # noqa: E402


def wilson(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def score(items):
    from rct_control_plane import user_model
    right = wrong = missed = clean = 0
    positives = sum(1 for _, e in items if e)
    negatives = len(items) - positives
    details = []
    for text, expected in items:
        found = [(d["facet"], d["value"]) for d in user_model.detect(text)]
        if expected is None:
            clean += not found
            if found:
                details.append(("FALSE", text, found))
            continue
        if expected in found:
            right += 1
        else:
            missed += 1
            details.append(("MISS", text, found))
        wrong += sum(1 for f in found if f != expected)
    detections = right + wrong + sum(1 for t, e in items if e is None and user_model.detect(t))
    precision = right / detections if detections else 1.0
    return {"positives": positives, "negatives": negatives, "right": right, "missed": missed, "detections": detections, "precision": round(precision, 3), "recall": round(right / positives, 3),
            "recall_interval": wilson(right, positives), "negatives_clean": clean, "negatives_clean_interval": wilson(clean, negatives)}, details


def main() -> int:
    data.verify_frozen()
    report, details = score(data.DEV)
    print("DEV", json.dumps(report))
    for d in details:
        print("  ", d)
    if "--holdout" not in sys.argv:
        return 0
    marker = ROOT / "user_model_holdout_r72.json"
    if marker.exists():
        print("the holdout was already measured once:", marker.read_text(encoding="utf-8"))
        return 1
    report, details = score(data.HOLDOUT)
    report["passes"] = report["precision"] >= 0.90 and report["recall"] >= 0.70 and report["negatives_clean"] >= 18
    report["misses_and_false"] = [list(map(str, d)) for d in details]
    marker.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("HOLDOUT (once)", json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
