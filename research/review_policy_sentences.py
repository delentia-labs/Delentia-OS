"""
Review the owner's REAL sentences against the text-to-policy mapper (Round 87). The mapper's 60 test sentences were written by its author; the only honest next test is sentences written by the person
whose policy it will be, and judged by that person.

    python -m research.review_policy_sentences my_sentences.txt            # one sentence per line (Thai or English); a line starting with # is ignored
    python -m research.review_policy_sentences my_sentences.txt --out review.md

For every sentence it prints what the mapper proposes (nothing is changed or saved), whether the proposal would LOOSEN the gate (allow anything other than reading), and the questions it asks. The last
column of the written table is left for you: does this say what you meant? y / n / too loose / too strict. Count those; a development set that you also tune on does not count, so keep half of the
sentences aside, write the mapper's fixes against the first half only, and read the second half once.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rct_control_plane import policy_from_text  # noqa: E402


def read_sentences(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def loosens(proposal: policy_from_text.Proposal) -> bool:
    return any(r["stance"] == policy_from_text.ALLOW and r["group"] != "read" for r in proposal.rules)


def review(sentences: List[str]) -> str:
    lines = ["| # | your sentence | status | what it would set | loosens? | questions asked | did it say what you meant? |", "|---|---|---|---|---|---|---|"]
    loosening = 0
    for index, sentence in enumerate(sentences, 1):
        proposal = policy_from_text.propose(sentence)
        rules = "; ".join(f"{r['stance'].upper()} {r['group']}" for r in proposal.rules) or "-"
        flag = loosens(proposal)
        loosening += int(flag)
        questions = " / ".join(proposal.questions) or "-"
        lines.append(f"| {index} | {sentence.replace('|', '/')} | {proposal.status} | {rules} | {'YES' if flag else 'no'} | {questions.replace('|', '/')} |  |")
    lines += ["", f"{len(sentences)} sentences; {loosening} would loosen the gate. Fill the last column by hand: y / n / too loose / too strict."]
    return "\n".join(lines) + "\n"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="show what the text-to-policy mapper would do with your own sentences")
    parser.add_argument("file")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    sentences = read_sentences(Path(args.file))
    if not sentences:
        print("no sentences found", file=sys.stderr)
        return 2
    text = review(sentences)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
