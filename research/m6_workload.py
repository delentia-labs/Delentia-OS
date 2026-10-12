"""
Round 67, M6: one workload, several memory stores.

The Architect allowed downloads to compare with other systems. This file defines the sequence of memory operations every store is given, and the ground truth the answers are checked against.
Nothing here depends on any store. Each adapter (m6_delentia.py, m6_others.py) replays `make_workload(n, seed)` and reports what it measured; `m6_compare.py` puts the tables together.

Operations on one person's memory (`alice`), plus a little traffic of a second person (`bob`) so that erasing one person has something to leave alone:
    add     a fact with a UNIQUE token, so a returned text can be matched to the add that made it exactly
    revoke  stop using one earlier fact (the person said "forget that")
    touch   the agent used a fact (only stores that have the notion record it)
The ground truth after operation k is the set of tokens of alice's facts that were added and not revoked by then. Texts are English and Thai sentences about a small business; they are
synthetic on purpose (no real person's data), and the first fact of alice carries a canary string so that "erase" can be checked in the raw bytes afterwards.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

SUBJECTS = ["the main vendor", "the cold-storage contact", "the weekend depot", "the quote approver", "the refund window", "the night supervisor", "the packaging supplier", "the customs liaison",
            "ผู้ขายหลัก", "ผู้อนุมัติใบเสนอราคา", "คลังสินค้าสำรอง", "ผู้ติดต่อฝ่ายศุลกากร"]
VERBS = ["is", "changed to", "was set to", "must be", "should stay"]
VALUES = ["Pakwell", "BoxHub", "Chaiwat", "Orawan", "14 days", "30 minutes", "Rayong", "Trang", "08:00-17:00", "bi-weekly", "net 45", "ศรีราชา", "วันศุกร์", "งบ 15000"]
CANARY = "CANARY-LANDLORD-Somchai-081-234-5678"


def make_workload(n: int, seed: int = 7) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    ops: List[Dict[str, Any]] = []
    live: List[str] = []
    for i in range(n):
        r = rng.random()
        if i == 0:
            token = "T0000"
            ops.append({"op": "add", "ns": "alice", "token": token, "text": f"{token} my landlord is {CANARY}"})
            live.append(token)
        elif r < 0.55 or not live:
            token = f"T{i:04d}"
            text = f"{token} {rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(VALUES)}"
            ns = "bob" if rng.random() < 0.08 else "alice"
            ops.append({"op": "add", "ns": ns, "token": token, "text": text})
            if ns == "alice":
                live.append(token)
        elif r < 0.85:
            ops.append({"op": "touch", "ns": "alice", "token": rng.choice(live)})
        else:
            token = rng.choice([t for t in live if t != "T0000"] or live)
            ops.append({"op": "revoke", "ns": "alice", "token": token})
            if token in live:
                live.remove(token)
    return ops


def truth_after(ops: List[Dict[str, Any]], k: int, ns: str = "alice") -> set:
    """Tokens of ns's facts that are live after the first k operations."""
    live: set = set()
    for o in ops[:k]:
        if o["ns"] != ns:
            continue
        if o["op"] == "add":
            live.add(o["token"])
        elif o["op"] == "revoke":
            live.discard(o["token"])
    return live


def checkpoints_for(n: int, seed: int = 11, count: int = 6) -> List[int]:
    rng = random.Random(seed)
    return sorted(rng.sample(range(max(2, n // 10), n), count))
