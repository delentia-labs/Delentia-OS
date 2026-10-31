"""
Round 106: would the owner's plan-first list have shown a plan where the Architect wanted one? A free measurement on labels that already exist.

Plan-first approval (Round 101) triggers on the KIND of an effect a tool call would have (delete, outward, money, permissions, publish, restore/cancel, move/shutdown; the Architect's decision of 2026-10-25,
document edits excluded in the starter). A request is not a tool call, so this script reads each request of holdout set 3 with a fixed list of words per kind, written BEFORE it was run on the labels
(committed first), and asks one thing: for the requests where the Architect marked axis C = Y ("show a plan and wait for my confirmation"), how many would the kind list have caught, and for C = N
how many would it have caught wrongly?

It is a proxy: a person's request is read by words, not by the tool call the agent would later make, so it says how well the LIST OF KINDS matches his wishes, not how well the system detects them in use.
The word lists are fixed here and are not tuned afterwards; a result is reported as it comes out.

    python -m research.plan_kinds_text_proxy_r106 --sheet C:/.../RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.sealed.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

KINDS: Dict[str, List[str]] = {
    "delete": ["delete", "remove", "erase", "wipe", "drop", "purge", "clear out", "ลบ", "เคลียร์ทิ้ง", "ล้าง"],
    "outward": ["send", "email", "e-mail", "mail", "reply", "message", "post", "share", "upload", "forward", "notify", "invite", "ส่ง", "ตอบกลับ", "แชร์", "อีเมล", "โพสต์"],
    "money": ["pay", "transfer", "buy", "purchase", "book", "refund", "charge", "invoice", "order", "subscribe", "โอน", "จ่าย", "ซื้อ", "จอง", "คืนเงิน", "ชำระ"],
    "permissions": ["permission", "access", "admin", "role", "grant", "revoke", "kick", "ban", "unblock", "block", "สิทธิ์", "แอดมิน", "เตะ", "บล็อก"],
    "publish": ["publish", "deploy", "release", "go live", "launch", "push to prod", "ship", "เผยแพร่", "ปล่อย", "เปิดตัว"],
    "restore_cancel": ["restore", "roll back", "rollback", "cancel", "unsubscribe", "undo", "revert", "ยกเลิก", "กู้คืน", "ย้อนกลับ"],
    "move_shutdown": ["restart", "reboot", "shut down", "shutdown", "stop the server", "stop the service", "move", "rename", "reschedule", "postpone", "รีสตาร์ท", "ปิดเครื่อง", "ปิดเซิร์ฟเวอร์", "ย้าย", "เลื่อน", "เปลี่ยนชื่อ"],
}


def kinds_in(request: str) -> List[str]:
    text = request.lower()
    found = []
    for kind, words in KINDS.items():
        for w in words:
            pattern = (r"(?<![a-z])" + re.escape(w) + r"(?![a-z])") if re.fullmatch(r"[a-z \-]+", w) else re.escape(w)
            if re.search(pattern, text):
                found.append(kind)
                break
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    items = json.loads(args.sheet.read_text(encoding="utf-8"))["items_data"]
    rows = []
    for key in sorted(items, key=int):
        it = items[key]
        rows.append({"n": int(key), "request": it["request"], "Q": it["Q"], "C": it["C"], "kinds": kinds_in(it["request"])})
    caught_y = [r for r in rows if r["C"] == "Y" and r["kinds"]]
    missed_y = [r for r in rows if r["C"] == "Y" and not r["kinds"]]
    wrong_n = [r for r in rows if r["C"] == "N" and r["kinds"]]
    ok_n = [r for r in rows if r["C"] == "N" and not r["kinds"]]
    out = {"C_yes": sum(1 for r in rows if r["C"] == "Y"), "C_no": sum(1 for r in rows if r["C"] == "N"), "caught_among_C_yes": len(caught_y), "missed_among_C_yes": len(missed_y),
           "plan_shown_though_C_no": len(wrong_n), "no_plan_and_C_no": len(ok_n),
           "missed": [(r["n"], r["request"], r["Q"]) for r in missed_y], "wrongly_caught": [(r["n"], r["request"], r["kinds"]) for r in wrong_n]}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    if args.out:
        args.out.write_text(json.dumps({**out, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
