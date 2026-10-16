"""
A stress probe for the text-to-policy mapper: sentences phrased the way the mapper's author did NOT have in mind. (Round 82, plan item T10)

Written after the mapper and the sixty-case set were frozen, measured ONCE, and reported as it came out. Each sentence has an intended reading: a {group: stance} dict, or None when the
right behaviour is to ask. Outcomes: correct, asked (safe, but the mapper did not understand), wrong_restrictive (it produced a rule that is stricter than, or different from, what was meant),
loosening (it allowed something other than reading: this one must be zero).

    python research/policy_mapping_stress.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rct_control_plane import policy_from_text  # noqa: E402

STRESS: List[Dict[str, Any]] = [
    {"text": "Please make sure nothing leaves the building without me seeing it first.", "meant": {"outbound": "ask"}},
    {"text": "Quotes are read-only.", "meant": {"write": "never"}},
    {"text": "Don't touch the contracts folder.", "meant": {"write": "never"}},
    {"text": "Feel free to look around.", "meant": {"read": "allow"}},
    {"text": "I'm fine with you emailing suppliers.", "meant": None},
    {"text": "Never ever send anything.", "meant": {"outbound": "never"}},
    {"text": "Don't ask, just read the files.", "meant": {"read": "allow"}},
    {"text": "Nothing may be deleted, ever.", "meant": {"write": "never"}},
    {"text": "ช่วยอ่านไฟล์ให้หน่อย แต่ห้ามแก้", "meant": {"read": "allow", "write": "never"}},
    {"text": "อย่าส่งอะไรออกไปโดยไม่บอกฉัน", "meant": {"outbound": "ask"}},
    {"text": "If it is a customer, check with me; everyone else is fine.", "meant": None},
    {"text": "You're free to search the web but never download.", "meant": None},
    {"text": "Reading is fine, writing needs my signature.", "meant": {"read": "allow", "write": "ask"}},
    {"text": "Scheduling anything is off limits.", "meant": {"schedule": "never"}},
    {"text": "I'd rather you did not run scripts.", "meant": {"shell": "never"}},
    {"text": "Run whatever commands you like.", "meant": None},
    {"text": "Sub-agents are fine as long as they only read.", "meant": None},
    {"text": "ถ้าจะส่งอะไรให้ลูกค้า ต้องให้ฉันดูก่อน", "meant": {"outbound": "ask"}},
    {"text": "You can remember preferences but not passwords.", "meant": None},
    {"text": "Treat every outgoing email as needing my okay.", "meant": {"outbound": "ask"}},
    {"text": "The weekly report may be emailed to the team automatically.", "meant": None},
    {"text": "No web access at all.", "meant": {"network": "never"}},
    {"text": "Ask first, always.", "meant": None},
    {"text": "Stay away from the shell.", "meant": {"shell": "never"}},
    {"text": "Allow reading and writing in the notes folder only.", "meant": None},
]


def classify(item: Dict[str, Any]) -> Dict[str, Any]:
    proposal = policy_from_text.propose(item["text"])
    loosening = any(r["stance"] == policy_from_text.ALLOW and r["group"] != "read" for r in proposal.rules)
    if loosening:
        outcome = "loosening"
    elif item["meant"] is None:
        outcome = "correct" if proposal.status in ("ask", "refuse") else "wrong_restrictive"
    elif proposal.status == "ok" and proposal.stances() == item["meant"]:
        outcome = "correct"
    elif proposal.status in ("ask", "refuse") and not proposal.rules:
        outcome = "asked"
    else:
        outcome = "wrong_restrictive"
    return {"text": item["text"], "meant": item["meant"], "status": proposal.status, "got": proposal.stances(), "outcome": outcome}


def main() -> int:
    rows = [classify(i) for i in STRESS]
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    print(json.dumps({"sentences": len(rows), "outcomes": counts}, indent=2))
    for r in rows:
        if r["outcome"] != "correct":
            print(f"{r['outcome']:<17} {r['text']!r}  got={r['got']} status={r['status']} meant={r['meant']}")
    return 0 if counts.get("loosening", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
