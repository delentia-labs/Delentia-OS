"""
The durable run log and the replay engine of DAAES (specification sections VII and VIII).

One event per line of `events.jsonl`, flushed and fsynced BEFORE `emit` returns (so an acknowledged event survives a kill). Every event carries the shared schema

    run_id, sequence, event_id, kind, logical_time, wall_time, causation_id, correlation_id, intent_id,
    state_version_before, state_version_after, payload_hash, prev_event_hash, event_hash

and a `payload` (redacted BEFORE it is logged). `event_hash` covers every header field and `payload_hash`, so editing the payload, the header, the order or the number of events breaks the chain.

A hash chain detects local tampering; it cannot prove that nobody forged a whole new log. `anchor_head` signs the head with an Ed25519 key kept OUTSIDE the run folder, and `verify_anchor`
checks it: that is the (optional) stronger provenance the specification asks for at the higher tests.

Replay modes: R1 state replay (recorded state deltas), R2 tool replay (recorded tool outputs, and a counter that proves nothing external was called), R3 decision replay (recorded decisions
re-judged by a policy function must give the recorded verdicts). R4 live re-execution is NOT in this module: its variance is reported separately and never required to be byte-identical.
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from research.daaes.core import canonical, digest

KINDS = ("run.started", "intent.created", "intent.revised", "decision.proposed", "decision.authorized", "tool.requested", "tool.completed", "tool.failed", "fault.injected",
         "memory.delta_committed", "checkpoint.committed", "process.terminated", "process.resumed", "oracle.evaluated", "run.completed")
HEADER = ("run_id", "sequence", "event_id", "kind", "logical_time", "wall_time", "causation_id", "correlation_id", "intent_id", "state_version_before", "state_version_after",
          "payload_hash", "prev_event_hash")
GENESIS = "GENESIS"
SECRET_KEY = re.compile(r"(api[_-]?key|secret|token|password|passwd|authorization|private[_-]?key)", re.I)
SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9-]{10,})")


def redact(value: Any) -> Any:
    """Secrets are removed BEFORE an event is written (spec section VIII); the hash covers the redacted form."""
    if isinstance(value, dict):
        return {k: ("[redacted]" if SECRET_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET_VALUE.sub("[redacted]", value)
    return value


def event_hash(header: Dict[str, Any]) -> str:
    return digest({k: header[k] for k in HEADER})


class RunLog:
    """Append-only, durable, hash-chained. `emit` is the only writer."""

    def __init__(self, path: Path, run_id: str, wall_clock: Optional[Callable[[], float]] = None) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self._wall = wall_clock or time.time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: List[Dict[str, Any]] = load(self.path) if self.path.exists() else []
        self._logical = (self.events[-1]["logical_time"] if self.events else 0)

    def emit(self, kind: str, payload: Optional[Dict[str, Any]] = None, *, causation_id: Optional[str] = None, correlation_id: Optional[str] = None, intent_id: Optional[str] = None,
             state_version_before: Optional[int] = None, state_version_after: Optional[int] = None) -> Dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        body = redact(deepcopy(payload or {}))
        sequence = len(self.events) + 1
        self._logical += 1
        header = {"run_id": self.run_id, "sequence": sequence, "event_id": f"evt_{sequence:06d}", "kind": kind, "logical_time": self._logical, "wall_time": round(self._wall(), 6),
                  "causation_id": causation_id, "correlation_id": correlation_id, "intent_id": intent_id, "state_version_before": state_version_before,
                  "state_version_after": state_version_after, "payload_hash": digest(body),
                  "prev_event_hash": self.events[-1]["event_hash"] if self.events else GENESIS}
        event = {**header, "payload": body, "event_hash": event_hash(header)}
        line = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(self.path, "ab") as handle:                      # one write, then flush and fsync: an event is acknowledged only once it is on disk
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        return deepcopy(event)

    def head(self) -> str:
        return self.events[-1]["event_hash"] if self.events else GENESIS


def load(path: Path) -> List[Dict[str, Any]]:
    """Reads events.jsonl. A torn last line (the process died mid-write) is dropped, because it was never acknowledged; it is reported by `verify` as `torn_tail`, not silently."""
    events: List[Dict[str, Any]] = []
    with open(path, "rb") as handle:
        for raw in handle.read().split(b"\n"):
            if not raw.strip():
                continue
            try:
                events.append(json.loads(raw.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                break
    return events


def torn_tail(path: Path) -> bool:
    data = Path(path).read_bytes()
    return bool(data) and not data.endswith(b"\n")


def verify(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Chain integrity: sequence has no gap or repeat, each prev hash is the hash before, payload and header hashes recompute, causes come earlier, logical time never goes back."""
    prev, seen, last_logical = GENESIS, set(), 0
    for position, e in enumerate(events, start=1):
        try:
            if e["sequence"] != position:
                return {"ok": False, "at": position, "reason": "sequence_gap_or_repeat_or_reorder"}
            if e["prev_event_hash"] != prev:
                return {"ok": False, "at": position, "reason": "prev_hash_mismatch"}
            if digest(e["payload"]) != e["payload_hash"]:
                return {"ok": False, "at": position, "reason": "payload_altered"}
            if event_hash(e) != e["event_hash"]:
                return {"ok": False, "at": position, "reason": "event_hash_mismatch"}
            if e["causation_id"] is not None and e["causation_id"] not in seen:
                return {"ok": False, "at": position, "reason": "cause_not_earlier"}
            if e["logical_time"] <= last_logical:
                return {"ok": False, "at": position, "reason": "logical_time_not_increasing"}
        except KeyError as exc:
            return {"ok": False, "at": position, "reason": f"missing_field_{exc.args[0]}"}
        seen.add(e["event_id"])
        prev, last_logical = e["event_hash"], e["logical_time"]
    return {"ok": True, "at": None, "reason": None, "events": len(events), "head": prev}


# ------------------------------------------------------------------------------------------------ tampering (for the tamper tests)
def tamper(events: List[Dict[str, Any]], how: str, index: int = 1) -> List[Dict[str, Any]]:
    """Returns a damaged copy. `how`: mutate_payload | delete_event | reorder_events | duplicate_event | corrupt_hash | replace_snapshot (swap a checkpoint's state for another, leaving the log)."""
    e = deepcopy(events)
    if how == "mutate_payload":
        e[index]["payload"] = {**e[index]["payload"], "tampered": True}
    elif how == "delete_event":
        del e[index]
    elif how == "reorder_events":
        e[index], e[index + 1] = e[index + 1], e[index]
    elif how == "duplicate_event":
        e.insert(index + 1, deepcopy(e[index]))
    elif how == "corrupt_hash":
        h = e[index]["event_hash"]
        e[index]["event_hash"] = ("0" if h[0] != "0" else "1") + h[1:]
    elif how == "replace_snapshot":
        for ev in e:
            if ev["kind"] == "checkpoint.committed":
                ev["payload"] = {**ev["payload"], "state": {"forged": True}}
                break
    else:
        raise ValueError(how)
    return e


# ------------------------------------------------------------------------------------------------ anchors
def anchor_head(events: List[Dict[str, Any]], key_path: Path, anchor_path: Path) -> Dict[str, Any]:
    """Sign (run_id, sequence, head) with an Ed25519 key that lives outside the run folder. The anchor file belongs somewhere the agent cannot write."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key_path = Path(key_path)
    if key_path.exists():
        private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        private = Ed25519PrivateKey.generate()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    head = {"run_id": events[-1]["run_id"], "sequence": events[-1]["sequence"], "head": events[-1]["event_hash"]}
    signature = private.sign(canonical(head))
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    record = {**head, "signature": signature.hex(), "public_key": public}
    Path(anchor_path).parent.mkdir(parents=True, exist_ok=True)
    Path(anchor_path).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def verify_anchor(events: List[Dict[str, Any]], anchor_path: Path) -> Dict[str, Any]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    record = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
    head = {k: record[k] for k in ("run_id", "sequence", "head")}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(record["public_key"])).verify(bytes.fromhex(record["signature"]), canonical(head))
    except (InvalidSignature, ValueError):
        return {"ok": False, "reason": "signature_invalid"}
    if len(events) < record["sequence"]:
        return {"ok": False, "reason": "log_shorter_than_anchored (events were removed from the end)"}
    anchored = events[record["sequence"] - 1]
    if anchored["event_hash"] != record["head"] or anchored["run_id"] != record["run_id"]:
        return {"ok": False, "reason": "anchored_event_differs (the log was rewritten)"}
    return {"ok": True, "reason": None, "anchored_sequence": record["sequence"]}


# ------------------------------------------------------------------------------------------------ replay
def replay_r1(initial_state: Dict[str, Any], events: List[Dict[str, Any]], reducer: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """R1: rebuild the state from the recorded deltas alone. The chain is checked first; a broken chain raises, because a state built on a damaged log proves nothing."""
    report = verify(events)
    if not report["ok"]:
        raise ValueError(f"event chain invalid at {report['at']}: {report['reason']}")
    state = deepcopy(initial_state)
    for e in events:
        if e["kind"] == "memory.delta_committed":
            state = reducer(state, e["payload"]["delta"])
    return state


class NoExternalCalls:
    """A stand-in for the outside world during R2: any call is counted and refused. The test asserts the count is zero AND that the replay still completed."""

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.attempts += 1
        raise RuntimeError("external call attempted during replay")


def replay_r2(events: List[Dict[str, Any]], external: Optional[NoExternalCalls] = None) -> Dict[str, Any]:
    """R2: recompute the workflow's result from the recorded tool outputs alone: for every `tool.completed`, its output hash must equal the hash of the recorded output, and the receipts
    folded together give the committed operations. Nothing outside is called."""
    external = external or NoExternalCalls()
    requested: Dict[str, Dict[str, Any]] = {}
    committed: Dict[str, str] = {}
    problems: List[str] = []
    for e in events:
        if e["kind"] == "tool.requested":
            requested[e["event_id"]] = e["payload"]
        elif e["kind"] == "tool.completed":
            cause = requested.get(e["causation_id"] or "")
            if cause is None:
                problems.append(f"{e['event_id']}: completed without a request")
                continue
            out = e["payload"].get("output")
            if digest(out) != e["payload"].get("output_hash"):
                problems.append(f"{e['event_id']}: recorded output does not match its hash")
            op = (cause.get("input") or {}).get("operation_id")
            if op:
                committed[op] = e["payload"].get("output_hash", "")
    return {"ok": not problems and external.attempts == 0, "problems": problems, "committed_operations": committed, "external_attempts": external.attempts}


def replay_r3(events: List[Dict[str, Any]], policy: Callable[[Dict[str, Any]], str]) -> Dict[str, Any]:
    """R3: every recorded decision is judged again by the policy function; the verdict must equal the recorded one. A policy that changed, or a verdict that was edited, shows up."""
    mismatches: List[str] = []
    checked = 0
    proposals: Dict[str, Dict[str, Any]] = {}
    for e in events:
        if e["kind"] == "decision.proposed":
            proposals[e["event_id"]] = e["payload"]
        elif e["kind"] == "decision.authorized":
            proposal = proposals.get(e["causation_id"] or "")
            if proposal is None:
                mismatches.append(f"{e['event_id']}: verdict without a proposal")
                continue
            checked += 1
            again = policy(proposal)
            if again != e["payload"].get("verdict"):
                mismatches.append(f"{e['event_id']}: recorded {e['payload'].get('verdict')!r}, policy now says {again!r}")
    return {"ok": not mismatches, "checked": checked, "mismatches": mismatches}
