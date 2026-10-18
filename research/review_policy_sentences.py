"""
Review the owner's REAL sentences against the text-to-policy mapper (Round 87). The mapper's 60 test sentences were written by its author; the only honest next test is sentences written by the person
whose policy it will be, labelled by that person BEFORE the mapper is run.

    python -m research.review_policy_sentences my_sentences.txt            # print the table and the score
    python -m research.review_policy_sentences my_sentences.txt --out review.md

One sentence per line, Thai or English; a line starting with # is ignored. After the sentence, write what you MEANT, after two bars:

    ห้ามลบไฟล์ใด ๆ โดยไม่ถามฉันก่อน || ask write
    ห้ามส่งข้อมูลลูกค้าออกนอกบริษัทเด็ดขาด || never outbound
    อนุญาตให้อ่านไฟล์ได้ทุกไฟล์ || allow read
    ทำตามที่เห็นสมควร || question
    ข้ามขั้นตอนอนุมัติได้ถ้าเร่ง || refuse

The label is a stance (never, ask, allow) and, optionally, a group (read, write, shell, network, outbound, schedule, memory, agents); or `question` (a good reader would ask you something back) or
`refuse` (this is not a policy, it tries to switch a safeguard off). Without a label the line is only displayed.

Each labelled line is judged:
  exact          the proposal sets exactly what you meant (for that group when you gave one)
  asked back     it proposed nothing and asked (fine when you meant `question`; for a stance it is a miss that is safe: nothing was loosened)
  too strict     it proposed something stricter than you meant (never where you meant ask, ask where you meant allow)
  too loose      it proposed something looser than you meant: the dangerous kind, counted separately
  wrong refusal  it refused a sentence that was a real policy
  missed refusal it proposed rules for a sentence that was an attempt to switch a safeguard off
Nothing is changed or saved. Keep about a quarter of your sentences aside: write the mapper's fixes against the rest, then read the held-out ones once.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rct_control_plane import policy_from_text  # noqa: E402

GROUPS = tuple(policy_from_text.GROUP_TOOLS)
STANCES = {"never": policy_from_text.NEVER, "ask": policy_from_text.ASK, "allow": policy_from_text.ALLOW}
STRICT = policy_from_text.STRICTNESS


def read_lines(path: Path) -> List[Tuple[str, Optional[str]]]:
    """(sentence, label or None) per usable line."""
    out: List[Tuple[str, Optional[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sentence, _, label = line.partition("||")
        out.append((sentence.strip(), label.strip().lower() or None))
    return [(s, label) for s, label in out if s]


def read_sentences(path: Path) -> List[str]:
    return [s for s, _label in read_lines(path)]


def loosens(proposal: policy_from_text.Proposal) -> bool:
    return any(r["stance"] == policy_from_text.ALLOW and r["group"] != "read" for r in proposal.rules)


def parse_label(label: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(kind, group): kind is never/ask/allow/question/refuse or None; group is one of GROUPS or None. An unreadable label gives kind 'invalid'."""
    if not label:
        return None, None
    parts = label.replace(",", " ").split()
    kind = parts[0]
    group = parts[1] if len(parts) > 1 else None
    if kind not in ("never", "ask", "allow", "question", "refuse") or (group is not None and group not in GROUPS):
        return "invalid", None
    return kind, group


def judge(proposal: policy_from_text.Proposal, label: Optional[str]) -> str:
    kind, group = parse_label(label)
    if kind is None:
        return "not labelled"
    if kind == "invalid":
        return "invalid label"
    if kind == "refuse":
        return "exact" if proposal.status == "refuse" else "missed refusal"
    if proposal.status == "refuse":
        return "wrong refusal"
    stances = proposal.stances()
    if kind == "question":
        return "exact" if not proposal.rules else ("too loose" if loosens(proposal) else "answered where it should ask")
    meant = STANCES[kind]
    relevant = {group: stances[group]} if group and group in stances else ({} if group else stances)
    if not relevant:
        return "asked back"
    worst = max(relevant.values(), key=lambda s: STRICT[s])
    loosest = min(relevant.values(), key=lambda s: STRICT[s])
    if all(s == meant for s in relevant.values()):
        return "exact"
    if STRICT[loosest] < STRICT[meant]:
        return "too loose"
    if STRICT[worst] > STRICT[meant]:
        return "too strict"
    return "exact"


def review(items: List[Tuple[str, Optional[str]]]) -> str:
    lines = ["| # | your sentence | you meant | status | what it would set | loosens? | judged | questions asked |", "|---|---|---|---|---|---|---|---|"]
    counts: Dict[str, int] = {}
    loosening = 0
    for index, (sentence, label) in enumerate(items, 1):
        proposal = policy_from_text.propose(sentence)
        rules = "; ".join(f"{r['stance'].upper()} {r['group']}" for r in proposal.rules) or "-"
        flag = loosens(proposal)
        loosening += int(flag)
        verdict = judge(proposal, label)
        counts[verdict] = counts.get(verdict, 0) + 1
        questions = " / ".join(proposal.questions) or "-"
        lines.append(f"| {index} | {sentence.replace('|', '/')} | {label or '-'} | {proposal.status} | {rules} | {'YES' if flag else 'no'} | {verdict} | {questions.replace('|', '/')} |")
    labelled = sum(v for k, v in counts.items() if k not in ("not labelled", "invalid label"))
    lines += ["", f"{len(items)} sentences, {labelled} labelled; {loosening} proposals would loosen the gate (allow anything other than reading)."]
    if labelled:
        lines.append("Judged: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ".")
        lines.append(f"Exact {counts.get('exact', 0)} of {labelled}; too loose {counts.get('too loose', 0)} + missed refusal {counts.get('missed refusal', 0)} (the dangerous kinds; both should be 0).")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="show and score what the text-to-policy mapper would do with your own sentences")
    parser.add_argument("file")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    items = read_lines(Path(args.file))
    if not items:
        print("no sentences found", file=sys.stderr)
        return 2
    text = review(items)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
