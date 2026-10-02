"""
Round 54: how does CORD do on prompt-injection text that its author did not write?

The Round 53 corpora (scripts/measure_cord_screening.py) were written by the people who wrote the rules, so even their
"first look" numbers are optimistic. This reads a public labelled set from disk and measures the same engine on it. Nothing
from it is copied into the repository: pass the file you downloaded.

Default source used in the Round 54 report: deepset/prompt-injections (Apache-2.0; 662 short texts, English and German,
label 1 = injection, 0 = harmless), parquet from the Hugging Face dataset viewer export.

    python scripts/measure_cord_external.py --file deepset_test.parquet            # the first look
    python scripts/measure_cord_external.py --file deepset_train.parquet --misses  # what to learn from

Protocol that keeps the numbers honest: look at the TEST split once, before reading anything else from the set; read misses
only from the TRAIN split; re-measure TEST after the rule changes and report both figures (the second one is a tuned
figure on the rule side but still unseen text).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(path: Path) -> List[Dict[str, Any]]:
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return [{"text": str(t), "label": int(l)} for t, l in zip(*[pq.read_table(path).column(c).to_pylist() for c in ("text", "label")], strict=True)]
    if path.suffix in (".jsonl", ".ndjson"):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    raise SystemExit(f"unsupported file type {path.suffix}; use .parquet or .jsonl with text and label (1 = injection)")


GERMAN_HINTS = (" der ", " die ", " das ", " und ", " nicht ", " ich ", " sie ", " bitte ", " ein ", " eine ", " wie ", " warum ", " wieso ", " vergiss", " ignorier", " aufgabe", " anweisung")


def is_german(text: str) -> bool:
    padded = f" {text.lower()} "
    return sum(hint in padded for hint in GERMAN_HINTS) >= 2


def measure(rows: List[Dict[str, Any]], show_misses: int, untrusted: bool = False) -> Dict[str, Any]:
    """`untrusted` treats the text as third-party content (a web page, a stored memory), which is where the context-switch rules apply."""
    from rct_control_plane.cord_security import CORDEngine, CORDVerdict
    from rct_control_plane.injection_screen import InjectionScreen
    engine, screen = CORDEngine(), InjectionScreen()

    def blocked_by_cord(text: str) -> tuple:
        verdict = engine.check(text)
        hard = verdict.verdict == CORDVerdict.REJECTED
        if untrusted and not hard:
            hard = any(f.severity == "hard" for f in screen.check(text, trusted=False))
        return hard, (not verdict.is_clean)

    def block_stats(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        attacks = [r for r in subset if r["label"] == 1]
        benign = [r for r in subset if r["label"] == 0]
        missed, false_blocked = [], []
        blocked = flagged = 0
        for row in attacks:
            hard, flag = blocked_by_cord(row["text"])
            if hard:
                blocked += 1
            else:
                flagged += int(flag)
                missed.append(row["text"])
        for row in benign:
            if blocked_by_cord(row["text"])[0]:
                false_blocked.append(row["text"])
        out = {"attacks": len(attacks), "attacks_blocked": blocked, "attack_block_rate": round(blocked / max(1, len(attacks)), 3),
               "benign": len(benign), "benign_blocked": len(false_blocked), "benign_block_rate": round(len(false_blocked) / max(1, len(benign)), 3)}
        if show_misses:
            out["missed_examples"] = [m[:140] for m in missed[:show_misses]]
            out["false_block_examples"] = [m[:140] for m in false_blocked[:show_misses]]
        return out

    german = [r for r in rows if is_german(r["text"])]
    english = [r for r in rows if not is_german(r["text"])]
    return {"mode": "untrusted content" if untrusted else "goal", "all": block_stats(rows), "english_like": block_stats(english), "german_like": block_stats(german)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--misses", nargs="?", const=15, type=int, default=0, help="print up to N missed attacks and false blocks (read these only from the TRAIN split)")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--untrusted", action="store_true", help="treat the text as third-party content (web page, stored memory)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = measure(load(args.file), args.misses, args.untrusted)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
