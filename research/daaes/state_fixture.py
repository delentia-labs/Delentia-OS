"""
TC-009 fixture and the INDEPENDENT reference reducer (specification section V).

`make_fixture(seed, profile)` builds, deterministically from a seeded PRNG, an initial state and a list of operations:

  full profile    100 projects, 1,000 tasks, 50 intents, 500 memories, 100 links; 890 state operations + 10 snapshot markers = 900 steps
                  (create 200, update 300, delete 100, link/unlink 100, reorder/status 100, intent revision 90)
  memory profile  the 500 memories only, with create / update / delete (the part of the state Delentia's memory event log can carry); same seed discipline
  small profile   a tenth of the full one, for the fast tests

`reduce(state, op)` is the full-state reducer that serves as the oracle. It shares no code with any store under test: it is a plain function over plain dictionaries.
`state_hash` uses the canonical serialization of core.py (sorted keys, NFC, normalized numbers).

The fixture includes Thai text and a composed/decomposed accent pair on purpose: canonical serialization is part of what is being tested.
"""
from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from research.daaes.core import digest

ENTITIES = ("projects", "tasks", "intents", "memories", "links")
PROFILES = {
    "full": {"projects": 100, "tasks": 1000, "intents": 50, "memories": 500, "links": 100, "ops": {"create": 200, "update": 300, "delete": 100, "link": 50, "unlink": 50, "reorder": 50, "status": 50, "intent_revision": 90}, "snapshots": 10},
    "small": {"projects": 10, "tasks": 100, "intents": 5, "memories": 50, "links": 10, "ops": {"create": 20, "update": 30, "delete": 10, "link": 5, "unlink": 5, "reorder": 5, "status": 5, "intent_revision": 9}, "snapshots": 4},
    "memory": {"projects": 0, "tasks": 0, "intents": 0, "memories": 500, "links": 0, "ops": {"create": 150, "update": 250, "delete": 100}, "snapshots": 10},
}
WORDS = ["ledger", "invoice", "สัญญา", "ใบเสนอราคา", "audit", "café", "café", "delta", "replay", "ตั๋ว", "storage", "intent", "สรุป", "migration", "quote"]
STATUSES = ["open", "in_progress", "blocked", "done"]


def _text(rng: random.Random, n: int = 3) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


def initial_state(seed: int, profile: str = "full") -> Dict[str, Dict[str, Any]]:
    cfg, rng = PROFILES[profile], random.Random(seed)
    state: Dict[str, Dict[str, Any]] = {e: {} for e in ENTITIES}
    for i in range(cfg["projects"]):
        state["projects"][f"p{i:04d}"] = {"name": _text(rng, 2), "owner": f"u{rng.randrange(20)}", "budget": round(rng.uniform(1000, 90000), 2)}
    pids = sorted(state["projects"])
    for i in range(cfg["tasks"]):
        state["tasks"][f"t{i:05d}"] = {"project": rng.choice(pids), "title": _text(rng, 3), "status": rng.choice(STATUSES), "position": i}
    for i in range(cfg["intents"]):
        state["intents"][f"i{i:03d}"] = {"goal": _text(rng, 4), "constraints": [_text(rng, 2) for _ in range(rng.randint(1, 3))], "version": 1}
    for i in range(cfg["memories"]):
        state["memories"][f"m{i:04d}"] = {"content": _text(rng, 6), "importance": round(rng.random(), 3), "revoked": False}
    tids, iids = sorted(state["tasks"]), sorted(state["intents"])
    for i in range(cfg["links"]):
        state["links"][f"l{i:04d}"] = {"intent_id": rng.choice(iids), "task_id": rng.choice(tids)} if tids and iids else {}
    return state


def reduce(state: Dict[str, Dict[str, Any]], op: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The oracle's reducer. Raises KeyError for an operation that does not fit the state (the fixture never emits one)."""
    s = deepcopy(state)
    kind = op["kind"]
    if kind == "snapshot":
        return s
    if kind == "create":
        if op["id"] in s[op["entity"]]:
            raise KeyError(f"{op['entity']}/{op['id']} exists")
        s[op["entity"]][op["id"]] = deepcopy(op["value"])
    elif kind == "update":
        s[op["entity"]][op["id"]].update(deepcopy(op["set"]))
    elif kind == "delete":
        del s[op["entity"]][op["id"]]
    elif kind == "soft_delete":                                    # the memory profile: Delentia's log revokes instead of removing
        s[op["entity"]][op["id"]]["revoked"] = True
    elif kind == "link":
        s["links"][op["id"]] = {"intent_id": op["intent_id"], "task_id": op["task_id"]}
    elif kind == "unlink":
        del s["links"][op["id"]]
    elif kind == "reorder":
        a, b = s["tasks"][op["a"]], s["tasks"][op["b"]]
        a["position"], b["position"] = b["position"], a["position"]
    elif kind == "status":
        s["tasks"][op["id"]]["status"] = op["status"]
    elif kind == "intent_revision":
        i = s["intents"][op["id"]]
        i["version"] += 1
        i["constraints"] = deepcopy(op["constraints"])
    else:
        raise ValueError(f"unknown operation {kind}")
    return s


def state_hash(state: Dict[str, Any]) -> str:
    return digest(state)


def make_ops(seed: int, profile: str = "full", soft_delete: bool = False) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """(initial state, steps). Steps include `snapshot` markers spread evenly. Every operation is valid against the state at the moment it is applied."""
    cfg = PROFILES[profile]
    rng = random.Random(seed * 7919 + 13)
    state = initial_state(seed, profile)
    plan: List[str] = [k for k, n in cfg["ops"].items() for _ in range(n)]
    rng.shuffle(plan)
    ops: List[Dict[str, Any]] = []
    counters = {e: len(state[e]) for e in ENTITIES}
    entity_for = {"create": ("tasks", "memories", "projects"), "update": ("tasks", "memories", "projects"), "delete": ("tasks", "memories")}
    if profile == "memory":
        entity_for = {k: ("memories",) for k in entity_for}
    for kind in plan:
        op: Dict[str, Any]
        if kind == "create":
            entity = rng.choice(entity_for["create"])
            new_id = f"{entity[0]}{counters[entity] + 1000:05d}"
            counters[entity] += 1
            value = ({"content": _text(rng, 6), "importance": round(rng.random(), 3), "revoked": False} if entity == "memories" else
                     {"project": rng.choice(sorted(state["projects"])), "title": _text(rng, 3), "status": "open", "position": 10_000 + counters[entity]} if entity == "tasks" else
                     {"name": _text(rng, 2), "owner": f"u{rng.randrange(20)}", "budget": round(rng.uniform(1000, 90000), 2)})
            op = {"kind": "create", "entity": entity, "id": new_id, "value": value}
        elif kind in ("update", "delete"):
            entity = rng.choice(entity_for[kind])
            pool = [k for k, v in sorted(state[entity].items()) if not (profile == "memory" and v.get("revoked"))]
            if not pool:
                continue
            target = rng.choice(pool)
            if kind == "delete":
                op = {"kind": "soft_delete" if soft_delete else "delete", "entity": entity, "id": target}
            else:
                fields = ({"content": _text(rng, 6)} if entity == "memories" else {"title": _text(rng, 3)} if entity == "tasks" else {"budget": round(rng.uniform(1000, 90000), 2)})
                op = {"kind": "update", "entity": entity, "id": target, "set": fields}
        elif kind == "link":
            if not state["tasks"] or not state["intents"]:
                continue
            counters["links"] += 1
            op = {"kind": "link", "id": f"l{counters['links'] + 5000:05d}", "intent_id": rng.choice(sorted(state["intents"])), "task_id": rng.choice(sorted(state["tasks"]))}
        elif kind == "unlink":
            if not state["links"]:
                continue
            op = {"kind": "unlink", "id": rng.choice(sorted(state["links"]))}
        elif kind == "reorder":
            ids = sorted(state["tasks"])
            if len(ids) < 2:
                continue
            a, b = rng.sample(ids, 2)
            op = {"kind": "reorder", "a": a, "b": b}
        elif kind == "status":
            if not state["tasks"]:
                continue
            op = {"kind": "status", "id": rng.choice(sorted(state["tasks"])), "status": rng.choice(STATUSES)}
        else:                                                               # intent_revision
            if not state["intents"]:
                continue
            op = {"kind": "intent_revision", "id": rng.choice(sorted(state["intents"])), "constraints": [_text(rng, 2) for _ in range(rng.randint(1, 3))]}
        state = reduce(state, op)
        ops.append(op)
    snaps = cfg["snapshots"]
    every = max(1, len(ops) // (snaps + 1))
    steps: List[Dict[str, Any]] = []
    for i, op in enumerate(ops, start=1):
        steps.append(op)
        if i % every == 0 and sum(1 for s in steps if s["kind"] == "snapshot") < snaps:
            steps.append({"kind": "snapshot"})
    return initial_state(seed, profile), steps


def reference_states(initial: Dict[str, Any], steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The oracle's state after every STATE operation (snapshot markers do not change the state): index v is the state after v state operations (index 0 = initial)."""
    states = [deepcopy(initial)]
    for step in steps:
        if step["kind"] == "snapshot":
            continue
        states.append(reduce(states[-1], step))
    return states
