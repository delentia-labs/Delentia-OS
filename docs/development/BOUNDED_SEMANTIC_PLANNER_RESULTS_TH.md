# ผลพัฒนารอบ bounded bilingual semantic planner และวิเคราะห์ช่องว่าง RCT-7

22 ตุลาคม 2026 — branch `codex/rct-domain-planning-provenance-20261022`, base `4044f1fcecfb9e66b6ffada8c9645e1b1b2c9e65`. รอบนี้เริ่มทำตามลำดับ prerequisites→semantic planner โดยทำงานพัฒนาที่ไม่ติด host ควบคู่กัน ไม่ได้ประกาศว่ารอบ signed effects, channel expansion, capable-model evaluation หรือ pilot เสร็จแล้ว

## สิ่งที่ทำจริง

### A. Integration host และ configuration

รัน preflight ใหม่: Ollama tags ยังว่าง, native DNS ของ example.com ยัง gaierror, Chromium sandbox ยัง abort เพราะ helper ownership ไม่ถูกต้อง ส่วน SSH config isolation ผ่าน

รอบนี้ configuration reader ใช้งานได้ จึงอ่าน custom allowlist เดิมก่อนเพิ่มเฉพาะ official model CDN `dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com` และ `example.com` รักษา5custom domains เดิมและ package-manager presets พร้อมปรับ start_skill ให้ตรงกับ dependency patch และ bounded planner ที่ทดสอบแล้ว ไม่มีการเพิ่ม secret หรือเปลี่ยน install script/repository membership

Tool ยืนยัน saved และ requires_publish=true โดยอ่านกลับตรวจรายการโดเมนแล้ว นี่เป็นการเตรียม draft ให้ review/save และ Publish ใน environment settings ไม่ใช่การ apply network ให้เครื่องนี้ ไม่ใช่หลักฐานว่า pull/inference/DNS ใช้ได้แล้ว Browser/native DNS ยังต้องแก้ host/runtime ที่รองรับจริง รายการ failures พร้อมวิธีแก้ทุกกรณีอยู่ใน [failure catalog](INTEGRATION_FAILURE_CATALOG_TH.md)

### B. Planner ที่อนุมาน task dependencies ได้ในขอบเขตจำกัด

เพิ่ม [semantic_plan.py](../../rct_control_plane/semantic_plan.py) สำหรับ summary และ budget comparison จาก cues ไทย/อังกฤษใน goal เมื่อให้ facts เดิมแต่เปลี่ยนโจทย์จากสรุปเป็นเทียบงบ ระบบสร้าง component graph ต่างกันเอง ไม่ต้องให้ผู้ใช้เขียน graph/unknowns ก่อน

Summary: inspect sources→compose answer→predicate preparations/checks. Budget: inspect sources→compare budget→compose answer→predicate checks. Backward chain รวม prerequisite closure ตาม graph ที่ตรวจ cycle/references/coverage แล้ว

ถ้าไม่มี source facts จะสร้าง critical source_text question; ถ้างานเทียบงบไม่มีงบจะสร้าง critical budget question และ persist waiting_for_input ก่อน model/tools คำตอบ yes/looks good หรือ15000ที่ไม่บอกสกุลเงินไม่เพียงพอ ต้องเป็นจำนวนบวกพร้อม THB/USD/EUR/บาท เช่น15,000บาท หรือ15000THB ไม่มี currency conversion หรือ general locale parsing ในรอบนี้

หาก revise จาก summary ไป budget task อาจมีคำถามใหม่ จึงแก้ continuation ให้คืน waiting_for_input โดยไม่พยายามเริ่มงาน และ CLI แสดง exit1 สำหรับ wait นี้ตามรูปแบบเดิมของ agent ไม่รีเซ็ต state หรือปล่อยผ่านเพราะมีคำยืนยันทั่วไป

Metadata แยก classification เป็น rule_inferred กับ source facts เป็น user_reported เก็บ ruleset, cue, original goal hash และ per-source text hash/locator Unknown answers มี confirmed_user_input revision provenance การมี hash หรือ source string ไม่ทำให้ข้อมูลเป็น observed/verified และไม่เพิ่ม tool authority Contract/default-agent/write fence ยังไม่เปิดเพิ่ม

โจทย์นอกขอบเขต โจทย์ปฏิเสธที่กฎรองรับ หรือผสม summary+comparison จะถูกปฏิเสธก่อนเรียกโมเดล แทนการสร้างแผนเหมือนว่าระบบเข้าใจแล้ว การตรวจ cue ไม่ใช่หลักฐานความเข้าใจภาษาอย่างทั่วไป และข้อปฏิเสธนี้ยังไม่ใช่ conversational ambiguity-resolution ที่สมบูรณ์

## ผลตรวจสอบและข้อจำกัดของหลักฐาน

Full Python: **7,943 passed / 13 failed / 59 skipped / 1 xfailed**, ใช้เวลา **783.56 วินาที**; warnings6,863; runner exit1 เพราะ integration failures ยังอยู่ Coverage **91.21%** (90782/99528; รวม test modules ไม่ใช่ production-only coverage) 13 failures เป็น node ids ชุดเดิมทั้งหมด: local model9/browser sandbox3/DNS1 ไม่ใช่ all-green และไม่ได้เพิ่ม skips เพื่อปิด failures เวลานี้เป็นการรัน test suite ไม่ใช่ latency ของงานหนึ่งคำขอ

เก็บ [machine-readable results, failure messages, skipped reasons และ raw evidence hashes](evidence/BOUNDED_SEMANTIC_PLANNER_2026-10-22.json) และ [คำอธิบายทุก failureพร้อมวิธีแก้](INTEGRATION_FAILURE_CATALOG_TH.md)

Focused suite ผ่าน **132 tests** รวม semantic planner ใหม่43กรณี กับ derived/declared/contracts/governed loop เดิม ตัวเลขนี้ซ้อนกับ full suite ห้ามบวกเป็น unique test count เพิ่ม

Development cases ครอบคลุม Thai/English goals11แบบ, unsupported/negated/mixed goals6แบบ, invalid budget11แบบ, valid format5แบบ, same facts/different goal, inferred wait/restart/exact answers, missing sources, revision introducing a wait, strict schema/duplicate sources, HTTP, CLI และ maximum input graph ไม่ใช่ holdout benchmark และไม่ได้รายงาน semantic accuracy หรือ causal benefit

Actual CLI subprocess smoke ใช้ local scripted HTTP model: initial budget wait มี0model calls; หลังคำตอบ15,000บาท แสดงแผนก่อนงาน อ่าน quote.md ผ่าน tool จริง ตอบ12,500บาท และตรวจไฟล์ unchanged โดยมี2scripted calls ไม่มีpaidAPI เก็บ source hash, result JSON และ transcript ไม่มี U+FFFD ในคำไทย/ตัวเลขที่ตรวจ เป็น plumbing/integration evidence ไม่ใช่ capable-model evaluation

Pipeline แบบ --no-subagents ผ่าน21/21cases134/134checks ไม่ได้รัน optional subagent cases Ruff ตาม CI package scope และ authored diff check ผ่าน ติดตั้ง wheel ลง validation venv และทดสอบจาก/tmp โดย import จากsite-packages จริง ผ่าน inferred wait/answer/provenance/digest/SQLite ไม่มีการ publish package/native desktop/deployed host และไม่ได้รัน JS build/tests ใหม่เพราะไม่ได้เปลี่ยน JS ในรอบนี้

## หลังพัฒนาแล้ว RCT-7 ยังขาดอะไร

| ขั้น | ก้าวหน้ารอบนี้ | ช่องว่างที่ต้องปิดก่อนอ้างประสิทธิภาพทั่วไป |
|---|---|---|
| R1 Observe | infer source/budget questions; source locator/hash/status | acquisition ของ observed evidence, authenticity/freshness, conflicting sources และข้อมูลสำคัญอื่นที่ยังไม่ค้นพบเอง |
| R2 Analyze | infer task จาก goal ไทย/อังกฤษในสองกลุ่ม | semantic relations/constraints, multi-intent, negation/paraphrases และ scope นอกกฎอย่างถูกต้อง |
| R3 Deconstruct | same facts/different task→different graph จริง | general goal-dependent decomposition, resource feasibility และ source-to-component evidence ที่พิสูจน์ได้ |
| R4 Reverse | source/budget prerequisite links กับ closure | ค้นหา necessary conditions ด้านราคา/ภาษี/สกุลเงิน/เงื่อนไขทางเนื้อหาอย่างครบพอ ไม่ใช่เพียง prompt ให้โมเดลระวัง |
| R5 Core intent | infer missing budget/source และรอก่อน model/tools; reject generic budget acknowledgement | conversational ambiguity resolution, discovery/validation ของ critical inputs ทุกประเภท และ reuse confirmed context อย่างเหมาะสมเมื่อ revise |
| R6 Reconstruct | CLI/HTTP opt-in แสดงแผนและ durable continuation | Desk/jobs/cron/channels, streamed plan events, cancel/disconnect/restart matrix และ durable job waiting |
| R7 Compare | ยังใช้ predicates+heuristic grounding และ mismatch wait เดิม | independent semantic/effect oracle, answer/evidence citation checking, numeric/currency reasoning และ effect reconciliation |

ประเด็นสำคัญ: component ที่ชื่อ compare_budget ไม่รับรองว่าคำตอบเปรียบเทียบถูกจริง การผ่าน contains/language ไม่รับรองว่าตัวเลขสัมพันธ์กันถูก ต้องมี verifier/oracle และ capable-model evaluation เพิ่ม การมี graph ใช้งานได้จึงยังไม่ใช่ semantic RCT-7 ครบถ้วน

Graph ยังเป็น planning representation ที่ส่งให้ model context ไม่ใช่ scheduler ที่บังคับว่าทุก node ต้องมี completion receipt ก่อน dependent node ทำงาน มี tool policy/journal เดิมอยู่ แต่ยังต้องผูก component→actual tool observation→verification receipt ให้ตรวจการทำตามแผนได้ การเห็นแผนก่อนงานกับการพิสูจน์ว่าทำทุก component ครบเป็นคนละเกณฑ์

## การรันตัวเองอย่างมีประสิทธิภาพต้องมีอะไรเพิ่ม

ระบบควรทำงานเองภายใน intent/policy/budget ที่ชัดเจน และหยุดถามเมื่อข้อมูลสำคัญขาดตาม R5/R7 การลบการถามหรือการอนุมัติที่ policy ต้องการไม่ได้เพิ่มความสมบูรณ์ของ RCT-7 ส่วนงานที่อนุญาตและข้อมูลครบไม่ควรถูกถาม permission ซ้ำเพียงเพราะสร้างแผน

ยังต้องมี capable local model ที่ตอบตามschemaได้, confidence/uncertainty ที่วัดจริง, observed evidence/freshness, semantic result/effect verification, cost/token/time budgets และ routing, exact-action approval ที่ผูก contract/plan/version, crash journal reconciliation และ idempotency ตาม tool capability ไม่อ้าง exactly-once กับ external effect ที่ไม่มี primitive รองรับ

ต้องวัด latency, task completion, critical question recall, unsupported-task refusal, source attribution, numeric reasoning, violations และ recovery บน workload ภาษาไทย/อังกฤษที่ freeze protocol/fixtures/model/settings/commit แล้ว ไม่ใช้ test count หรือ hash เป็นคะแนนประสิทธิภาพ LEARN ยังไม่ใช่การ train weights อัตโนมัติ

## ลำดับงานถัดไปและเกณฑ์รับงาน

1. **Host:** review/save/Publish draft, ตรวจ model/CDN+native DNS+usable sandbox แล้ว rerun failures13และ skipped browser cases; ถ้าเกิด failure ใหม่ให้แยก model capability/transport/implementation ไม่เหมารวม infrastructure
2. **Semantic evidence/verification:** เพิ่ม typed amounts/currencies/taxes/exclusions และ observed-source bindings; deterministic arithmetic checks ก่อนใช้โมเดลสรุป ลดช่องว่างจาก plan description ไปเป็น actual verification พร้อม ambiguity/context revision tests และ component completion receipts/dependency enforcement
3. **Development/evaluation:** ทำ development fixtures และแยก holdout ก่อนปรับระบบรอบถัดไป; screen capable local model โดยไม่ใช้paidAPI และ freeze protocol ก่อน formal comparison
4. **Signed effects/recovery:** ต่อ approval/notary/episode_journal เดิมเข้ากับ contract id/version, plan digest, exact canonical action, actor/workspace/policy/nonce/expiry และ crash matrix ก่อนเปิด write fence ไม่ reset running ด้วย timeout
5. **Entry points:** เลือก Desk หรือ jobs หนึ่งช่องทางก่อน พร้อม plan-before-effects, initial/mismatch waits, version/namespace/replay, restart/cancel/disconnect tests แล้วขยาย channels ตาม [coverage เดิม](RCT_ENTRYPOINT_COVERAGE_TH.md)
6. **Operations/pilot:** host isolation, separate-user notary, scheduled off-host witness, backup/restore drill, operator stop/budgets/alerts,72hsoak และ outside pilot ภายใต้ขอบเขตที่ระบุ การทำเอกสารไม่ได้ทำให้ gates เหล่านี้ผ่าน

สรุปสถานะ: **experimental governed runtime with partial RCT-7, bounded bilingual task planning and reported-source provenance** งานจริงก้าวหน้าด้าน task-dependent planning และ critical-input wait แต่ยังไม่ใช่ autonomous general reasoning system หรือ production/pilot-ready รายละเอียด schema/การใช้งานอยู่ใน [bounded planner](../concepts/bounded-semantic-planner.md)
