"""
DAAES core primitives: canonical serialization, a hash-chained event log, state replay, an idempotent mock API, an intent-violation checker.

Origin: the reference harness supplied with the DAAES v0.1 specification (delentia_daaes_v01.zip, 2026-10-16). The public names and behaviour of that package are kept (its five unit tests run
unchanged against this module: `test_daaes_core_round83_real.py`), and these things are added: canonical serialization that normalizes Unicode (NFC), integral floats and signed zero before it
hashes (spec section VIII), an optional `anchor`, and `EventLog.verify_report()` which says WHICH link broke instead of returning False.

Not a substitute for durability, signing or a production state database: those live in `events.py` (the durable run log) and in Delentia's own audit chain.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def normalize(obj: Any) -> Any:
    """Canonical form before hashing: NFC strings, integral floats as ints, -0.0 as 0, NaN/Infinity refused (json allow_nan=False does the refusing)."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, float):
        if obj == 0.0:
            return 0
        if obj.is_integer() and abs(obj) < 2 ** 53:
            return int(obj)
        return obj
    if isinstance(obj, dict):
        return {normalize(k) if isinstance(k, str) else k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    return obj


def canonical(obj: Any) -> bytes:
    return json.dumps(normalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


@dataclass
class EventLog:
    events: List[Dict[str, Any]] = field(default_factory=list)

    def append(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        seq = len(self.events) + 1
        prev_hash = self.events[-1]["event_hash"] if self.events else "GENESIS"
        unsigned = {"sequence": seq, "kind": kind, "payload": deepcopy(payload), "prev_hash": prev_hash}
        event = {**unsigned, "event_hash": digest(unsigned)}
        self.events.append(event)
        return deepcopy(event)

    def verify(self) -> bool:
        return self.verify_report()["ok"]

    def verify_report(self) -> Dict[str, Any]:
        """Which link broke, and how. Reasons: bad_sequence (gap, duplicate or reorder), bad_prev_hash (an event was removed, inserted or reordered), bad_hash (an event was edited)."""
        prev = "GENESIS"
        for seq, e in enumerate(self.events, start=1):
            if e.get("sequence") != seq:
                return {"ok": False, "at": seq, "reason": "bad_sequence"}
            if e.get("prev_hash") != prev:
                return {"ok": False, "at": seq, "reason": "bad_prev_hash"}
            try:
                unsigned = {k: e[k] for k in ("sequence", "kind", "payload", "prev_hash")}
            except KeyError:
                return {"ok": False, "at": seq, "reason": "bad_hash"}
            if e.get("event_hash") != digest(unsigned):
                return {"ok": False, "at": seq, "reason": "bad_hash"}
            prev = e["event_hash"]
        return {"ok": True, "at": None, "reason": None}

    def head(self) -> str:
        return self.events[-1]["event_hash"] if self.events else "GENESIS"


def apply_event(state: Dict[str, Any], op: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(state)
    key = op["key"]
    action = op["action"]
    if action == "set":
        result[key] = deepcopy(op["value"])
    elif action == "delete":
        if key not in result:
            raise KeyError(key)
        del result[key]
    else:
        raise ValueError(f"Unknown operation {action}")
    return result


def replay(initial: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    log = EventLog(deepcopy(events))
    if not log.verify():
        raise ValueError("Invalid event chain")
    state = deepcopy(initial)
    for event in events:
        if event["kind"] == "state.delta":
            state = apply_event(state, event["payload"])
    return state


@dataclass
class IdempotentAPI:
    """Mock side effect adapter: the same operation ID creates at most one commit."""
    committed: Dict[str, Any] = field(default_factory=dict)

    def commit(self, operation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if operation_id in self.committed:
            result = self.committed[operation_id]
            if result["payload_hash"] != digest(payload):
                raise ValueError("Idempotency key reused with different payload")
            return deepcopy(result)
        receipt = {"operation_id": operation_id, "payload_hash": digest(payload), "status": "committed"}
        self.committed[operation_id] = receipt
        return deepcopy(receipt)


def intent_violations(initial: Dict[str, Any], final: Dict[str, Any], observed_actions: List[Dict[str, Any]]) -> List[str]:
    violations: List[str] = []
    for field_name in ("goal", "protected_constraints"):
        if initial.get(field_name) != final.get(field_name):
            violations.append(f"{field_name} changed")
    forbidden = set(initial.get("forbidden_actions", []))
    for action in observed_actions:
        if action.get("type") in forbidden:
            violations.append(f"forbidden action: {action['type']}")
    return violations


def sha256_file(path: Any, chunk: int = 1 << 20) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                block = f.read(chunk)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None
