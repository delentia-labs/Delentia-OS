# RCT-7: the definition, and what the runtime implements today

Checked by reading the code at commit `19d5fe8` (2026-10-23). Nothing here is a new test result. Thai summary at the end.

**RCT-7, Reverse Component Thinking**, is the creator's way of working in seven steps. The table separates the **requirement** (the creator's definition of each step) from the **implementation** (what the runtime does now). A step that is only partly implemented is not described as done anywhere else in this repository.

| ID | Step | Requirement | What the runtime does today | Status |
|---|---|---|---|---|
| R1 | Observe | Collect what is known **and what is unknown**, with sources and assumptions kept apart | Step 1 of `algo_04_rct7` records the first 60 characters of the goal. There is no structure for unknowns. (FDIA's `missing_data` list is about data quality, not about RCT-7.) | Not implemented |
| R2 | Analyze | Relations, constraints and ambiguities from the intent and the observed data | Records the intent type and scope | Partial |
| R3 | Deconstruct | Components, dependencies, inputs and outputs, as deep as the goal needs | Records how many constraints were extracted | Partial |
| R4 | Reverse reasoning | An inspectable chain from the wanted result back to the necessary conditions and the evidence or actions that support them | Records a risk profile and the strictness bonuses derived from it. A risk score is not a backward chain | Not implemented |
| R5 | Identify core intent | When the intent is not clear, **ask the user and wait** | Records whether validation passed and its warnings. The loop has no "waiting for an answer" state; the only wait it has is for a signature | Not implemented |
| R6 | Reconstruct | The user **sees the plan before** the real artifact is built | The plan is put into the model's prompt. The Desk shows "RCT-7 plan" after the answer, at the end of the episode | Does not meet the requirement |
| R7 | Compare with intent | If the result does not match, **report the difference, stop and ask**, then analyse again with the answer | The end-of-episode check compares similarity and grounding. Its outcome decides whether the episode may be learned as a skill; it does not stop the work and ask. A hash of the compiled intent is also recorded; a hash is not a result check | Not implemented |

## What this does not say

- It does not say the runtime has no clarification anywhere. Only the governed loop, `algo_04_rct7`, the Desk stream and the HTTP API were read; every entry point and tool was not.
- A "backward chain" means a plan structure that can be checked. It is not a claim about what happens inside a language model.
- Showing a plan does not mean every plan needs a new approval. Approvals follow the owner's policy and the risk of each action.

## Acceptance cases proposed for the work (not yet written as tests)

RC01 a missing key fact is recorded as unknown and asked about when it blocks the goal; RC02 the same data with a different goal changes the analysis; RC03 an important dependency is kept and the backward chain cites it; RC04 a risk report without backward links does not pass R4; RC05 an ambiguous intent with two outcomes asks and waits; RC06 the plan is shown before any effect; RC07 a wrong-language or wrong-format result is reported and paused, with no repair effect; RC08 a goal revised after a question keeps the original, the revision and the confirmation; RC09 a correct but short or paraphrased answer is judged by criteria and evidence, not by similarity alone; RC10 a restart while waiting keeps the pending state and runs nothing by itself.

## สรุปภาษาไทย

ตารางข้างบนแยก "ข้อกำหนด" (นิยามของผู้สร้าง) ออกจาก "สิ่งที่โค้ดทำ" ขั้น R1, R4, R5, R7 ยังไม่มีตามนิยาม R2/R3 มีบางส่วน R6 แสดงแผนหลังจบงาน ไม่ใช่ก่อนสร้างผล ตรวจจากการอ่านโค้ดที่ commit ข้างต้น ไม่ใช่ผลทดสอบใหม่
