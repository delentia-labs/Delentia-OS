"""
A model-free way to see the demo (Round 79): `delentia demo run compare --scripted`.

Most people who try the demo for the first time have no model running (no Ollama, no API key), and a small local model completes the demo's tasks only some of the time.
A first run that fails is a person who does not come back. So this module stands in for the MODEL with a fixed program, and nothing else:

  * REAL: the folder, the three tools it calls, the FDIA gate and the owner policy, the taint rule for the untrusted quotes folder, the pause for a signed approval, the
    signature check, the hash-chained and signed audit log, the checks of the answer against what is known to be true.
  * SCRIPTED: the order of the steps and the wording of the answer. The script reads the quote files itself to write the table. It decides nothing a model would decide.

Because of that the report says so on its first lines, and nothing printed in a scripted run says anything about any model's ability.
Supported: `compare`, `budget` (read the quotes, answer) and `edit` (read, ask to change a file: the gate stops it; after `delentia demo approve <id> --scripted` it is changed).
`remember` / `ask` need a model that reads its memory, so they are not scripted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane.llm_provider import LLMProvider

SCRIPTED_KEYS = ("compare", "budget", "edit")
NOTICE = ("ครั้งนี้ใช้ 'ตัวแทนโมเดลแบบสคริปต์' (ไม่ใช่โมเดลจริง): ลำดับขั้นและถ้อยคำของคำตอบถูกเขียนไว้ล่วงหน้า "
          "ส่วนที่เป็นของจริงคือเครื่องมือ ไฟล์ ประตูความปลอดภัย การรอลายเซ็น และ audit chain ผลนี้ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด")


def _read_quotes(workspace: Path, files: List[str]) -> List[Dict[str, Any]]:
    rows = []
    for rel in files:
        text = (workspace / rel).read_text(encoding="utf-8")
        vendor = re.search(r"บริษัท\s+(\S+)", text)
        price = re.search(r"ราคารวม:\s*([\d,]+)", text)
        days = re.search(r"ระยะเวลาทำงาน:\s*(\d+)", text)
        rows.append({"file": rel, "vendor": vendor.group(1) if vendor else rel,
                     "price": int(price.group(1).replace(",", "")) if price else 0, "days": int(days.group(1)) if days else 0})
    return rows


def compare_answer(rows: List[Dict[str, Any]], budget: int) -> str:
    ordered = sorted(rows, key=lambda r: r["price"])
    lines = [f"ตารางเปรียบเทียบใบเสนอราคา (เรียงราคาจากต่ำไปสูง, งบ {budget:,} บาท)", "",
             "| บริษัท | ราคา (บาท) | ระยะเวลา (วัน) | เทียบกับงบ |", "|---|---|---|---|"]
    for r in ordered:
        lines.append(f"| {r['vendor']} | {r['price']:,} | {r['days']} | {'อยู่ในงบ' if r['price'] <= budget else 'เกินงบ'} |")
    inside = [r for r in ordered if r["price"] <= budget]
    lines.append("")
    if inside:
        best = inside[0]
        lines.append(f"สรุป: ราคาต่ำสุดที่อยู่ในงบคือ {best['vendor']} ราคา {best['price']:,} บาท ({best['days']} วัน)")
    else:
        lines.append("สรุป: ไม่มีใบเสนอราคาใดอยู่ในงบ")
    return "\n".join(lines)


class ScriptedDemoProvider(LLMProvider):
    """Returns the next step of a fixed program each time the loop asks the model. Not a model."""

    def __init__(self, key: str, workspace: Path, budget: int = 15000, resumed: bool = False):
        self.key = key
        self.workspace = Path(workspace)
        self.budget = budget
        self.calls = 0
        self.queue: List[Any] = self._plan(resumed)

    # -------------------------------------------------------------- the program
    def _plan(self, resumed: bool) -> List[Any]:
        from rct_control_plane.demo import QUOTES
        files = list(QUOTES)
        if self.key in ("compare", "budget"):
            steps: List[Any] = [{"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": f}, "reasoning": f"อ่าน {f}"} for f in files]
            steps.append(lambda: {"action": "finish", "reasoning": "อ่านครบทุกใบแล้ว", "final_answer": compare_answer(_read_quotes(self.workspace, files), self.budget)})
            return steps
        if self.key == "edit":
            if resumed:
                return [{"action": "finish", "reasoning": "ขั้นที่ต้องมีลายเซ็นถูกทำแล้ว", "final_answer": "แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท ตามที่ได้รับอนุมัติแล้ว"}]
            return [{"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "quotes/vendor_a.md"}, "reasoning": "อ่านไฟล์ก่อนแก้"},
                    lambda: self._patch_step(),
                    {"action": "finish", "reasoning": "แก้เสร็จ", "final_answer": "แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท แล้ว"}]
        raise ValueError(f"'{self.key}' needs a real model; scripted keys are {', '.join(SCRIPTED_KEYS)}")

    def _patch_step(self) -> Dict[str, Any]:
        text = (self.workspace / "quotes/vendor_a.md").read_text(encoding="utf-8")
        old = re.search(r"ราคารวม:\s*[\d,]+\s*บาท", text)
        return {"action": "call_tool", "tool_name": "delentia_patch_repo_file",
                "tool_args": {"relative_path": "quotes/vendor_a.md", "old_text": old.group(0) if old else "ราคารวม:", "new_text": "ราคารวม: 14,000 บาท"},
                "reasoning": "เปลี่ยนราคารวมเป็น 14,000 บาท"}

    # -------------------------------------------------------------- LLMProvider
    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
        self.calls += 1
        if not self.queue:
            return json.dumps({"action": "finish", "reasoning": "สคริปต์จบแล้ว", "final_answer": "(สคริปต์เดโมจบแล้ว)"}, ensure_ascii=False)
        step = self.queue.pop(0)
        if callable(step):
            step = step()
        return json.dumps(step, ensure_ascii=False)
