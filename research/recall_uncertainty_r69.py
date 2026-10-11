"""
Round 69: when should the memory say "I am not sure"? For variant C (raw cosine) it records, per question, whether the answer was in the top 3, the top-1 cosine and the margin to the 2nd.
A rule `uncertain = top1 < T or margin < M` is chosen on DEV only (all DEV misses flagged is the goal, then the fewest hits flagged) and measured once on H1.

    python research/recall_uncertainty_r69.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
import recall_lab_r69 as lab  # noqa: E402


def stats(set_name: str):
    texts, qa = lab.load_set(set_name)
    corpus = lab.Corpus(texts)
    rows = []
    for question, answer in qa:
        sc = corpus.scores("C", question)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        pat = __import__("recall_dataset_r69")._boundary(answer)
        rank = next((p + 1 for p, i in enumerate(order) if pat.search(corpus.docs[i].lower())), None)
        rows.append({"hit3": bool(rank and rank <= 3), "top1": sc[order[0]], "margin": sc[order[0]] - sc[order[1]], "rank": rank})
    return rows


def flagged(row, t, m):
    return row["top1"] < t or row["margin"] < m


def main() -> int:
    dev, h1 = stats("dev"), stats("h1")
    best = None
    for t, m in itertools.product([x / 100 for x in range(50, 80, 2)], [x / 100 for x in range(0, 12)]):
        miss = [r for r in dev if not r["hit3"]]
        hits = [r for r in dev if r["hit3"]]
        caught = sum(flagged(r, t, m) for r in miss)
        false = sum(flagged(r, t, m) for r in hits)
        key = (-caught, false)                                              # catch as many misses as possible, then flag as few hits as possible
        if best is None or key < best[0]:
            best = (key, t, m)
    _, t, m = best
    print(f"chosen on DEV: uncertain = top1 < {t} or margin < {m}")
    for name, rows in (("DEV", dev), ("H1 (measured once)", h1)):
        miss = [r for r in rows if not r["hit3"]]
        hits = [r for r in rows if r["hit3"]]
        print(f"{name}: misses {len(miss)}, flagged {sum(flagged(r, t, m) for r in miss)}; hits {len(hits)}, wrongly flagged {sum(flagged(r, t, m) for r in hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
