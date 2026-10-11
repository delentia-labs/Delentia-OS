"""
Round 69: an exact identifier as the whole query ("stg-db-1", "4433", "northwind-core"): do the variants find the memory that contains it? Queries are the answer values of the held-out sets H1 and H5 that look like
identifiers (a digit, hyphen, underscore, dot, @ or # inside), asked bare and as "what is <identifier>". The corpus is the set's own facts + distractors. Variants C (raw cosine), E (0.9 dense + 0.1 BM25), D (BM25 alone).
H1 and H5 were already used for the ranking choice; this asks a different question of the same data and chooses nothing.
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
import recall_dataset_r69b as h5mod  # noqa: E402
import recall_lab_r69 as lab  # noqa: E402

IDENT = re.compile(r"[A-Za-z0-9]*[-_.@#:/0-9][A-Za-z0-9._@#:/-]*")


def main() -> int:
    h.verify_frozen()
    h5mod.verify_frozen()
    for name, data in (("H1", h.dataset()["h1"]), ("H5", h5mod.dataset())):
        texts = [f["text"] for f in data["facts"]] + list(data["distractors"])
        random.Random(7).shuffle(texts)
        corpus = lab.Corpus(texts)
        qa = []
        for f in data["facts"]:
            a = f["answer"]
            if re.search(r"[0-9\-_.@#:/]", a) and " " not in a and len(a) >= 3:
                qa += [(a, a), (f"what is {a}", a)]
        from rct_control_plane import memory_ranking as rk
        hits1 = hits3 = 0
        cands = [{"id": f"m{i}", "content": t, "importance": 0.6, "memory_type": "fact"} for i, t in enumerate(texts)]
        for question, answer in qa:                                          # P = the ranking that ships (rct_control_plane/memory_ranking.py): raw cosine + the exact-identifier bonus
            qv = lab.embed([question])[0]
            cos = {c["id"]: lab.cosine(qv, corpus.plain[i]) for i, c in enumerate(cands)}
            jac = dict(zip(texts, lab.jaccard_scores(question, texts), strict=True))
            got = [c["content"] for _k, _r, _l, c in rk.rank(question, cands, cos, jac)]
            pat = h._boundary(answer)
            rank = next((i + 1 for i, t in enumerate(got) if pat.search(t.lower())), None)
            hits1 += int(rank == 1)
            hits3 += int(bool(rank and rank <= 3))
        print(f"{name} identifiers ({len(qa)} queries) P: hit@1 {hits1}  hit@3 {hits3}")
        for variant, weight in (("C", 1.0), ("E", 0.9), ("D", 0.0)):
            r = lab.evaluate(corpus, qa, variant, weight)
            print(f"{name} identifiers ({len(qa)} queries) {variant}: hit@1 {r['hit@1']}  hit@3 {r['hit@3']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
