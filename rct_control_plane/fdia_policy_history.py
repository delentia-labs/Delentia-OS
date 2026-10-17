"""
Policy versioning (DAAES T12): every saved version of the owner's policy is kept, in order, hash-chained, so that for any decision in the audit trail the exact policy that made it can be shown, two
versions can be compared rule by rule, and an older version can be proposed again.

Why: the gate's verdict depends on the policy. An audit row says "rule R-WRITE-FILES, digest abc..."; without the policy text behind that digest an auditor cannot check the decision, and an owner who
loosened a rule last week cannot see what changed. Today the policy file is overwritten in place.

How:
  <policy file>.history.jsonl   one JSON line per saved version, appended by `fdia_policy.save_policy`:
                                {seq, at, digest, prev_hash, row_hash, label, actor, reason, policy}
                                row_hash = sha256(prev_hash | seq | digest | canonical policy json)
  `verify()`                    recomputes the chain; reports the first broken row; says whether the file now in use is the newest recorded version (a policy edited outside the program is "out of sync")
  `policy_for_digest(d)`        the stored policy for a digest found in an audit row
  `diff(a, b)`                  rules added, removed and changed (which fields), and the top-level settings that changed
  `proposal_from(seq)`          an older version as a policy dictionary. It SAVES nothing: putting it back goes through the same signed change as any other edit

What it is not: the history sits next to the policy file, so whoever can write that folder can rewrite both. It makes accidents and unrecorded edits visible and gives an auditor the text; it is not a
defence against the host owner. Anchoring the head at the witness (as for the audit chain) is the next step and is not built.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG = logging.getLogger(__name__)
GENESIS = "0" * 64
SUFFIX = ".history.jsonl"


def history_path(policy_file: Optional[Path] = None) -> Path:
    from rct_control_plane import fdia_policy
    target = Path(policy_file) if policy_file else fdia_policy.policy_path()
    return target.with_name(target.name + SUFFIX)


def _canonical(policy: Dict[str, Any]) -> str:
    return json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_hash(prev: str, seq: int, digest: str, policy: Dict[str, Any]) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{digest}|{_canonical(policy)}".encode("utf-8")).hexdigest()


def _read(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"_unreadable": True})
    return rows


def record(policy: Any, policy_file: Optional[Path] = None, *, actor: str = "", reason: str = "") -> Optional[Dict[str, Any]]:
    """Append this version unless it is the one already newest (saving an unchanged policy adds nothing). Returns the row, or None when nothing was added."""
    path = history_path(policy_file)
    rows = _read(path)
    digest = policy.digest()
    if rows and not rows[-1].get("_unreadable") and rows[-1].get("digest") == digest:
        return None
    data = policy.to_dict()
    prev = rows[-1].get("row_hash", GENESIS) if rows and not rows[-1].get("_unreadable") else GENESIS
    seq = (rows[-1].get("seq", len(rows)) if rows and not rows[-1].get("_unreadable") else len(rows)) + 1
    row = {"seq": seq, "at": round(time.time(), 3), "digest": digest, "prev_hash": prev, "row_hash": _row_hash(prev, seq, digest, data),
           "label": f"{getattr(policy, 'policy_id', '')}@{getattr(policy, 'version', '')}", "actor": str(actor)[:80], "reason": str(reason)[:300], "policy": data}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def history(policy_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The recorded versions, oldest first, without the policy bodies (use `policy_for_digest` or `proposal_from` for those)."""
    return [{k: v for k, v in r.items() if k != "policy"} for r in _read(history_path(policy_file)) if not r.get("_unreadable")]


def verify(policy_file: Optional[Path] = None) -> Dict[str, Any]:
    path = history_path(policy_file)
    rows = _read(path)
    prev, expected_seq = GENESIS, 1
    for row in rows:
        if row.get("_unreadable"):
            return {"ok": False, "rows": len(rows), "broken_at": expected_seq, "why": "a line cannot be read", "in_sync": None}
        policy = row.get("policy") or {}
        if row.get("seq") != expected_seq or row.get("prev_hash") != prev or row.get("row_hash") != _row_hash(prev, int(row.get("seq", 0)), str(row.get("digest")), policy):
            return {"ok": False, "rows": len(rows), "broken_at": expected_seq, "why": "the chain does not recompute here (an edit, a removed or a reordered line)", "in_sync": None}
        prev, expected_seq = row["row_hash"], expected_seq + 1
    in_sync: Optional[bool] = None
    try:
        from rct_control_plane import fdia_policy
        current = fdia_policy.load_policy(Path(policy_file) if policy_file else None)
        if current is None:
            in_sync = None if not rows else False
        else:
            in_sync = bool(rows) and rows[-1]["digest"] == current.digest()
    except ValueError:
        in_sync = False
    return {"ok": True, "rows": len(rows), "broken_at": None, "head": prev if rows else None, "in_sync": in_sync}


def policy_for_digest(digest: str, policy_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The policy that carried this digest, with when it was saved and by whom; None when no recorded version has it (an audit row older than the history, or an edit made outside the program)."""
    for row in reversed(_read(history_path(policy_file))):
        if not row.get("_unreadable") and row.get("digest") == digest:
            return {"seq": row["seq"], "at": row["at"], "actor": row.get("actor", ""), "reason": row.get("reason", ""), "label": row.get("label", ""), "policy": row.get("policy")}
    return None


def proposal_from(seq: int, policy_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for row in _read(history_path(policy_file)):
        if not row.get("_unreadable") and row.get("seq") == seq:
            return json.loads(_canonical(row["policy"]))
    return None


def _rules(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(r.get("rule_id")): r for r in (policy.get("rules") or []) if isinstance(r, dict)}


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """What changed between two policy dictionaries: rules added, removed, and for the rules in both, which fields differ; plus the top-level settings (not the rule list) that differ."""
    a, b = _rules(before), _rules(after)
    changed = []
    for rid in sorted(set(a) & set(b)):
        fields = sorted(k for k in set(a[rid]) | set(b[rid]) if a[rid].get(k) != b[rid].get(k))
        if fields:
            changed.append({"rule_id": rid, "fields": fields, "before": {k: a[rid].get(k) for k in fields}, "after": {k: b[rid].get(k) for k in fields}})
    top = sorted(k for k in set(before) | set(after) if k != "rules" and before.get(k) != after.get(k))
    return {"added_rules": sorted(set(b) - set(a)), "removed_rules": sorted(set(a) - set(b)), "changed_rules": changed,
            "changed_settings": {k: {"before": before.get(k), "after": after.get(k)} for k in top}, "same": not (set(a) ^ set(b) or changed or top)}


def diff_versions(seq_a: int, seq_b: int, policy_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    a, b = proposal_from(seq_a, policy_file), proposal_from(seq_b, policy_file)
    return diff(a, b) if a is not None and b is not None else None


def loosened(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """A plain list of the changes that make the gate easier to pass (a rule removed, a signature requirement lowered or dropped, a denied path or blocked pattern removed, an action changed to ALLOW).
    Heuristic and conservative: it names what it can see and says nothing about what it cannot."""
    out: List[str] = []
    d = diff(before, after)
    for rid in d["removed_rules"]:
        out.append(f"rule {rid} was removed")
    for ch in d["changed_rules"]:
        b, a = ch["before"], ch["after"]
        if "action_type" in ch["fields"] and str(a.get("action_type")).upper() == "ALLOW" and str(b.get("action_type")).upper() != "ALLOW":
            out.append(f"rule {ch['rule_id']} now ALLOWs what asked for a signature or a condition")
        if "required_signatures" in ch["fields"] and int(a.get("required_signatures") or 0) < int(b.get("required_signatures") or 0):
            out.append(f"rule {ch['rule_id']} asks for fewer signatures")
        if "denied_paths" in ch["fields"] and len(a.get("denied_paths") or []) < len(b.get("denied_paths") or []):
            out.append(f"rule {ch['rule_id']} denies fewer paths")
    for key in ("blocked_action_patterns", "require_human_dual_signoff"):
        if len(after.get(key) or []) < len(before.get(key) or []):
            out.append(f"{key} lists fewer entries")
    if float(after.get("default_fallback_A", 0) or 0) > float(before.get("default_fallback_A", 0) or 0):
        out.append("the fallback for an action no rule covers is higher")
    if float(after.get("custom_safety_threshold", 0.5) or 0) < float(before.get("custom_safety_threshold", 0.5) or 0):
        out.append("the safety threshold is lower")
    return out
