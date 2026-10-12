"""
Round 69: when a fact changes, does recall put the NEWER value first? (set H3 of research/recall_dataset_r69.py)

20 facts are stored with an old value and later with a newer one that says it changed; 160 distractors are stored too. The question asks for the current value. Measured: is the top-1 memory the newer one,
is the newer above the older, is the older in the top 3 at all (it should still be findable: history is not deleted). Variants: C = raw cosine (the ranking that ships since Round 69),
R = C with the older memory demoted when a newer memory that announces a change (a marker word) is almost the same text.

    python research/recall_updates_r69.py
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
import recall_dataset_r69 as h  # noqa: E402
import recall_lab_r69 as lab  # noqa: E402

MARKERS = re.compile(r"\b(now|changed|change|moved|switched|instead|no longer|renamed|replaced|replacing|extended|raised|from now on|updated|has been|is now)\b|ตอนนี้|เปลี่ยนเป็น|ย้ายไป|แทน", re.IGNORECASE)
TAU = 0.80                      # cosine between the older text and the newer one
DEMOTE = 0.15                   # subtracted from the older memory's cosine


def main() -> int:
    h.verify_frozen()
    d = h.dataset()
    updates, background = d["h3"]["updates"], d["h1"]["distractors"]
    texts, order = [], []
    for u in updates:
        texts += [u["old"], u["new"]]
    texts += list(background)
    ids = list(range(len(texts)))
    corpus = lab.Corpus(texts)
    for variant in ("C", "R"):
        top1_new = above = old_in3 = top1_old = 0
        for k, u in enumerate(updates):
            new_i, old_i = 2 * k + 1, 2 * k
            qv = lab.embed([u["question"]])[0]
            cos = [lab.cosine(qv, corpus.plain[i]) for i in ids]
            if variant == "R":
                for j in range(len(texts)):
                    if MARKERS.search(texts[j]):
                        older = [i for i in range(j) if lab.cosine(corpus.plain[j], corpus.plain[i]) >= TAU]
                        for i in older:
                            cos[i] -= DEMOTE
            ranking = sorted(ids, key=lambda i: -cos[i])
            top1_new += ranking[0] == new_i
            top1_old += ranking[0] == old_i
            above += ranking.index(new_i) < ranking.index(old_i)
            old_in3 += old_i in ranking[:3]
        print(f"{variant}: top-1 is the newer {top1_new}/20, top-1 is the older {top1_old}/20, newer above older {above}/20, older still in the top 3: {old_in3}/20")
    random.seed(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
