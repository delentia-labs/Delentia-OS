"""
Round 61: the skill curator - keeps the learned-skill library worth reading, without a model and without deleting anything.

The library learns from verified episodes, and learning accumulates clutter: a skill that was reused and kept failing, a skill that was a refusal in disguise (two were saved before Round 50's
fix), a skill nobody has ever been offered, two skills that are nearly the same. Hermes' curator uses a model to prune. This one uses the evidence the library already keeps:

  weak           a skill that was reused at least twice and whose reliability (Laplace-smoothed success rate) is below 0.4: it has been offered and has not helped;
  refusal        its problem or solution says the agent declined ("I am unable to ...", "none of the tools ..."): a refusal learned as a skill;
  duplicate      two active skills with keyword overlap of at least 0.6 (the writer merges at 0.8): keep the more reliable / more reinforced one, archive the other;
  stale          never reused in 90 days and never reinforced: it is not helping, but it is not shown to be harmful either, so it is only PROPOSED.

`review()` changes nothing. `apply()` ARCHIVES (the row, its solution and its counts stay; an archived skill is simply no longer offered; `unarchive` brings it back) and only the categories with
evidence (weak, refusal, duplicate) unless the caller asks for stale ones too. Starter ("bundled") and imported skills are never touched: a person put them there. Every action is an audit row.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from rct_control_plane.skill_library import SkillLibrary, SkillRecord, _jaccard

WEAK_MIN_USES = 2
WEAK_RELIABILITY = 0.4
DUPLICATE_OVERLAP = 0.6
STALE_DAYS = 90
EVIDENCE_KINDS = ("weak", "refusal", "duplicate")


def _text_of(record: SkillRecord) -> str:
    return f"{record.problem_statement} {json.dumps(record.solution, ensure_ascii=False, default=str)}"


def _age_days(created_at: str) -> float:
    try:
        when = datetime.fromisoformat(created_at)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0
    except (TypeError, ValueError):
        return 0.0


def _last_used(library: SkillLibrary) -> Dict[str, Optional[str]]:
    with sqlite3.connect(library.db_path) as conn:
        try:
            return {r[0]: r[1] for r in conn.execute("SELECT id, last_used_at FROM skills").fetchall()}
        except sqlite3.OperationalError:
            return {}


def review(library: SkillLibrary) -> Dict[str, Any]:
    """What the curator would archive and why. Changes nothing."""
    from rct_control_plane.governed_autonomous_loop import answer_declines_goal
    records = [r for r in library.list_active(limit=5000) if not r.bundled and not r.imported]
    last_used = _last_used(library)
    proposals: List[Dict[str, Any]] = []
    claimed: set = set()

    def add(record: SkillRecord, kind: str, reason: str, **extra: Any) -> None:
        if record.id in claimed:
            return
        claimed.add(record.id)
        proposals.append({"id": record.id, "kind": kind, "reason": reason, "problem": record.problem_statement[:120], "uses": record.uses, "reliability": round(record.reliability, 3), **extra})

    for r in records:
        if answer_declines_goal(_text_of(r)):
            add(r, "refusal", "it records a refusal, not a way of doing the task")
    for r in records:
        if r.uses >= WEAK_MIN_USES and r.reliability < WEAK_RELIABILITY:
            add(r, "weak", f"reused {r.uses} times, reliability {r.reliability:.2f} (below {WEAK_RELIABILITY})")
    by_id = {r.id: r for r in records}
    ordered = sorted(records, key=lambda r: (r.reliability, r.reinforced, r.created_at), reverse=True)
    for i, keep in enumerate(ordered):
        if keep.id in claimed:
            continue
        for other in ordered[i + 1:]:
            if other.id in claimed:
                continue
            overlap = _jaccard(set(keep.keywords), set(other.keywords))
            if overlap >= DUPLICATE_OVERLAP:
                add(other, "duplicate", f"overlaps {overlap:.2f} with skill {keep.id}, which is at least as reliable", keep=keep.id)
    for r in records:
        if r.uses == 0 and r.reinforced <= 1 and not last_used.get(r.id) and _age_days(r.created_at) >= STALE_DAYS:
            add(r, "stale", f"never reused and never reinforced in {int(_age_days(r.created_at))} days")
    counts: Dict[str, int] = {}
    for p in proposals:
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    return {"skills_reviewed": len(by_id), "proposals": proposals, "counts": counts, "protected": sum(1 for r in library.list_active(limit=5000) if r.bundled or r.imported)}


def apply(library: SkillLibrary, persistence: Any, kinds: tuple = EVIDENCE_KINDS) -> Dict[str, Any]:
    """Archive the proposals of the given kinds. Returns what was archived. Never deletes."""
    report = review(library)
    done: List[Dict[str, Any]] = []
    for p in report["proposals"]:
        if p["kind"] not in kinds:
            continue
        if library.archive(p["id"]):
            done.append(p)
            try:
                persistence.append_audit(entity_type="skill_curator", entity_id=p["id"], action="archived", actor="curator",
                                         changes={"kind": p["kind"], "reason": p["reason"], "uses": p["uses"], "reliability": p["reliability"]})
            except Exception:                                          # noqa: BLE001
                pass
    return {"archived": done, "left_as_proposals": [p for p in report["proposals"] if p["kind"] not in kinds]}
