# งานพัฒนารอบถัดไปและเกณฑ์ก่อนสื่อสารสาธารณะ

22 ตุลาคม 2026 (Asia/Bangkok). แผนนี้แยกสิ่งที่มี implementation จากการทดสอบคุณค่า; ไม่ใช่ release certification.

## สถานะหลังงาน Codex รอบนี้

มี opt-in acceptance contracts สำหรับงานอ่าน/ตอบบน CLI/API: แผนก่อน model/tool execution, เกณฑ์ที่ประกาศ, mismatch→ถาม/รอ, versioned continuation และ original intent/revisions ใน SQLite. กลไกเดิมเรื่อง tool policy/ลายเซ็นยังบังคับใช้. รายละเอียดและข้อจำกัดอยู่ [intent-contracts](../concepts/intent-contracts.md).

ยังไม่ใช่ RCT-7 ครบทั้งหมด: backward links เป็นเพียงเงื่อนไขที่ผู้ใช้ประกาศ, unknowns/components ยังไม่ใช่ goal-dependent decomposition ครบ, legacy/default path และ gateways/Desk ไม่ได้ถูกย้ายเข้ากลไกใหม่นี้โดยอัตโนมัติ. การตรวจภาษาเป็น script heuristic ไม่ใช่การตัดสินคุณภาพภาษาหรือความจริง.

## แบ่งงาน Codex / Claude

- Codex ใช้ branch `codex/rct-clarification-full-validation-20261022`; แยก runtime/evidence changes จาก branch ของ Claude ไม่ push เข้า main หรือ merge แทนเจ้าของ
- ก่อนแต่ละรอบอ่าน HEAD/status และ fetch main ใหม่; ระบุ base SHA และ files ที่จะเปลี่ยนใน handoff
- รอบนี้ Codex ดูแล `intent_contract.py`, integration ใน governed loop/API/CLI และ regression/demo ที่เกี่ยวข้อง. หาก Claude จะเปลี่ยนไฟล์เดียวกันให้ส่งต่อผ่าน commit/PR และตกลงผู้ลงมือหนึ่งคนก่อน ไม่แก้ checkout เดียวกันพร้อมกัน
- ลิงก์ commit, diff, actual test commands/outcomes และ blockers ทุกครั้ง ไม่ใช้ชื่อ AI เป็นหลักฐานคุณภาพโค้ด

## รอบ 1 — ปิดข้อจำกัดของ contract ก่อนขยาย default

ผลส่งมอบ: criteria/plan schema ที่ versioned, retention/export/erasure roundtrip และการตรวจพร้อมกัน/เสียกลางงาน. เชื่อม contract กับ signed action และ approval resume ก่อนเปิดเครื่องมือที่มีผลข้างเคียงใน path นี้; รุ่นแรกจำกัดเครื่องมืออ่านเพื่อไม่ให้ approval continuation ทำเกณฑ์หลุด.

เกณฑ์ผ่าน:
- competing continuation ได้ผู้ claim เพียงรายเดียว; stale version/replayed response ไม่ execute
- แยก waiting, pending signature, interrupted และ unknown outcome; ไม่ retry side effect โดยคาดเดา
- erasure/backup/restore ไม่คืนข้อความโดยไม่มี namespace key; ทดสอบ schema migration และ corruption
- unknown/custom tools กับ path alias/symlink/parallel batch ไม่ข้าม preservation constraints
- เปรียบ false-positive/false-negative ของภาษา/contains/JSON กับ known fixtures; อย่าใช้ predicate success แทน truth
- ออกแบบ recovery ของ contract ที่เสียกลาง `running` โดยอิง episode journal/observable state ก่อน ไม่ย้ายกลับ ready จาก timeout อย่างเดียว

## รอบ 2 — R1–R5 ตามความหมายผู้สร้าง

ผลส่งมอบ: knowns/sources/unknowns/assumptions, goal-dependent components/dependencies, backward conditions และ clarification ก่อนลงมือเมื่อข้อมูลสำคัญขาด.

เกณฑ์ผ่าน: เปลี่ยน goal แต่ facts เดิมแล้ว analysis/plan ต้องเปลี่ยนตาม; ทุก criterion มี component/input/output/evidence; missing prerequisite เกิดคำถามที่มีผลต่อการตัดสินใจ; ไม่อ้าง risk score หรือเจ็ดหัวข้อเป็น backward reasoning สำเร็จ. เก็บ original intent และ provenance ของคำตอบผู้ใช้.

## รอบ 3 — R6/R7 ทุก entry point ที่จะประกาศ

ผลส่งมอบ: plan events ที่ Desk/chat/jobs/gateways/subagents แสดงก่อน artifact, deterministic criteria ที่เหมาะกับ workflow และ end-to-end waiting/revision/replan.

เกณฑ์ผ่าน: CLI/API/Desk/job ที่เลือกมี trace ordering; mismatch ไม่ถูกส่งเป็น final success, ไม่เรียนเป็น successful skill, restart ไม่ข้าม waiting; correct-short-answer ไม่ถูกตัดสินจาก similarity อย่างเดียว. อย่าเปิด default จน regression/compatibility coverage และนิยามความเปลี่ยนแปลงชัด.

## รอบ 4 — W02 capable-model development smoke

ยังไม่รันในรอบนี้ตามคำขอผู้ใช้ว่าไม่ใช้ paid API.

ก่อนเริ่มต้องมี provider/model, capability screen ตาม scope, เพดานเงิน/token/time/attempt และ stop conditions. รัน dev 1–2 attempts ด้วย synthetic fixtures, fresh namespace/workspace และเก็บทุกความล้มเหลว. ถ้าใช้ state ต่อเนื่องให้บอกว่าเป็น trajectory ไม่ใช่ independent samples. ห้ามเปิด sealed test เพื่อ debug.

ระบุ purpose=development_smoke, implementation_fidelity=partial จนกว่าจะผ่าน fidelity ของ treatment. Scripted model ใช้ทดสอบ plumbing ได้ แต่ไม่แทน model capability.

## รอบ 5 — Freeze และ formal evaluation

ตรึง commit/model/settings/policy/fixtures/oracle/protocol และปรับ protocol version หาก R treatment เปลี่ยนจาก prompt representation เดิมไปเป็น contract semantics. Primary contrast A111−GP; hard floor ไม่ปิดเมื่อ F0; warm cache แยก sub-ablation. วัด spec fidelity, causal effect, interaction และ user utility แยกกัน. รายงาน failures/infra exclusions/cost/CI ตาม protocol ไม่เลือก comparator อ่อนกว่าหลังเห็นผล.

## ก่อนโพสต์แรก ยังตกหล่นอะไรได้บ้าง

| หัวข้อ | สำหรับโพสต์แนะนำ/เดโม | สำหรับเปิด pilot/อ้างประโยชน์ |
|---|---|---|
| ทางเข้าสาธารณะ | main README, org/personal และหน้าที่โพสต์ใช้ต้องมีนิยาม/วันที่ตรงกัน; local branch ยังไม่เปลี่ยนหน้า main | รวม deployment/operator docs ที่ใช้จริง |
| ระดับหลักฐาน | ระบุ SCRIPTED/experimental, exact source+package, expected/actual และ full recording | capable-model results และ protocol-frozen comparisons |
| Full tests | เปิดเผย failed/skipped/unrun/network blockers; ไม่เขียน all green เมื่อไม่ครบ | แก้ blockers ของ workflow/surface ที่เปิดและ rerun |
| Scope RCT/FDIA | ระบุ opt-in path และข้อจำกัด; ไม่อ้าง full fidelity/weight-level/zero-hallucination | treatment manipulation และ semantic fidelity ตาม scope |
| โมเดล/ค่าใช้จ่าย | ไม่จำเป็นต่อโพสต์แนะนำที่มาหรือ scripted mechanism | capability, caps, provider receipts และ incident stops |
| Host/witness/privacy | ไม่อ้าง service ที่ยังไม่ได้ validate; ไม่เผย keys/private logs | authentication/tenant isolation, key custody, backup/erasure, recovery, witness และ soak บน host จริง |
| คนนอกทำซ้ำ | ขอ feedback/reproduction ของ scope เล็กได้ โดยไม่ประกาศว่าเกิดแล้ว | ต้องมี outside reproduction/operator ตาม release gates |
| GUI/Action/package | ระบุ build/test ที่ยังไม่ผ่าน ไม่ใช้ source มีอยู่แทน package readiness | แก้ปัญหาเฉพาะ distribution ที่จะส่งให้ผู้ใช้ |
| โพสต์/วิดีโอ | full transcript และป้าย scripted; edited clip ต้องบอกว่าตัดย่อ | ไม่ตัด intervention/failure ที่เปลี่ยนข้อสรุป |

ไม่จำเป็นต้องอ่าน PDF archive ทั้งหมดหรือทำทุก feature ก่อนแนะนำโครงการเชิงทดลอง แต่ต้องไม่ประกาศ stable/public-service/pilot หรือเหนือ baseline ก่อนผ่าน gates ของคำกล่าวอ้างนั้น.

## “เป็นของจริง” หมายถึงอะไร

มี executable Python runtime, real file tools, policy/signatures, persistence และ audit ที่ตรวจพฤติกรรมจริงได้ จึงไม่ใช่แค่ภาพหน้าจอหรือเอกสารแนวคิด. ในการทดสอบ scripted ระบบและเครื่องมือทำงานจริง แต่คำตัดสินจากโมเดลถูกกำหนดด้วยโปรแกรม. สิ่งนี้ไม่ยืนยันว่าผู้ใช้ทั่วไปจะทำงานสำเร็จกับโมเดลใดก็ได้ ไม่ยืนยัน novel scientific law, complete safety, main-LLM self-training หรือ product readiness.

คุณภาพควรสรุปจาก behaviour/evidence/failures และความตรงขอบเขต ไม่ให้คะแนนรวมเป็นเปอร์เซ็นต์โดยไม่มี rubric. ดู [release levels](../release/RELEASE_LEVELS.md), [research protocol](../../research/PROTOCOL.md) และ actual run artifacts ของ branch นี้ควบคู่.

## Dependency review เพิ่มเติมจาก GitHub

ระหว่าง push GitHub แจ้ง default branch มี14 vulnerabilities (7 high,6 moderate,1 low). นี่เป็นข้อความแจ้งของremote ไม่ใช่ dependency audit ที่ทำซ้ำครบในรอบนี้; ต้องเปิดรายการจริง ระบุ dependency/version/reachability แก้ตามdistributionที่จะเปิด แล้วรันlockfile/build/regressionก่อนpilot. ไม่อ้างว่ารอบนี้ปิดsecurity findingsทั้งหมด.
