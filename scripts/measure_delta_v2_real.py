"""
Round 52: Delta v2 context compression on real files from this repository.

For each file: how many characters are removed, and does the compressed text still hold the
lines a question would need? Retention is measured with needle lines (a content line of the
file that the question is about): the intent focus is built from the needle's own words
("literal" focus) and from only two of them ("partial" focus, closer to a paraphrased question).
Needles are drawn with a fixed seed. No model is called.

    python scripts/measure_delta_v2_real.py [--out delta_v2_real.json]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rct_control_plane.delta_v2 import compress_context  # noqa: E402

FILES = [
    "README.md", "docs/whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md", "rct_control_plane/governed_autonomous_loop.py",
    "rct_control_plane/api.py", "rct_control_plane/cli.py", "core/delta_engine/memory_delta.py",
    "rct_control_plane/tests/test_sovereignty_round52_real.py", "pyproject.toml",
]
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def needles(text: str, n: int, seed: int = 7) -> List[str]:
    rng = random.Random(seed)
    pool = [ln.strip() for ln in text.split("\n") if len(WORD.findall(ln)) >= 4 and 30 <= len(ln.strip()) <= 200]
    return rng.sample(pool, min(n, len(pool)))


def run(path: Path, n: int = 25) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    plain = compress_context(text)
    row: Dict[str, Any] = {"file": str(path.relative_to(ROOT)), "chars": len(text),
                           "reduction_pct_no_focus": round(plain.reduction_percentage, 1)}
    kept = {"none": 0, "literal": 0, "partial": 0}
    pool = needles(text, n)
    for needle in pool:
        words = WORD.findall(needle)
        for mode, focus in (("none", None), ("literal", " ".join(words)), ("partial", " ".join(words[:2]))):
            if needle in compress_context(text, intent_focus=focus).compressed_delta_text:
                kept[mode] += 1
    row["needles"] = len(pool)
    row["needle_kept_pct"] = {k: round(100 * v / max(len(pool), 1), 1) for k, v in kept.items()}
    row["reduction_pct_literal_focus_avg"] = round(sum(
        compress_context(text, intent_focus=" ".join(WORD.findall(x))).reduction_percentage for x in pool[:5]) / max(len(pool[:5]), 1), 1)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rows = [r for f in FILES if (r := run(ROOT / f))]
    print(f"{'file':<58}{'chars':>8}{'cut':>7}{'cut(focus)':>11}   needle kept: none/literal/partial")
    for r in rows:
        k = r["needle_kept_pct"]
        print(f"{r['file']:<58}{r['chars']:>8}{r['reduction_pct_no_focus']:>6}%{r['reduction_pct_literal_focus_avg']:>10}%   {k['none']}% / {k['literal']}% / {k['partial']}%")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
