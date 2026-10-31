# R1 contract integration และแนวทางพัฒนางานทั่วไป

## เป้าหมายและขอบเขต

การรับงานทั่วไปต้องใช้ capable model แปลโจทย์เป็น typed intent/criteria, ระบุ ambiguity และเงื่อนไขจำเป็น แล้วให้ framework ตรวจแผน สิทธิ์ หลักฐาน และผลลัพธ์ ตัว DAG หรือ hashes ไม่ทำให้เข้าใจภาษาได้เอง ต้องประเมิน task success และ process quality บน holdout แยกกัน ไม่สามารถรับรองความเข้าใจโจทย์ทุกประเภทด้วย finite test suite

## Implementation รอบนี้

เพิ่ม EvidenceRequirement schema_version=1: policy, observations, claims, max_age_seconds มี bounds และ strict timestamp/wire validation

IntentContractStore.create รับ evidence_requirement เป็น optional keyword สำหรับ application ไม่เพิ่ม request field/HTTP route หรือให้โมเดลตั้ง source trust เอง เก็บ requirement ใน plan ก่อนคำนวณ digest เพื่อผูก policy/evidence กับแผนที่ต้องยืนยัน

ก่อน claim เปลี่ยน plan_ready เป็น running จะ parse requirement และประเมิน freshness ด้วยเวลาปัจจุบัน แล้ว apply declared policy หากไม่ผ่านจะหยุดก่อนเปลี่ยน state/version หากผ่านเก็บ evidence_decision ที่ผูก snapshots ผลนี้ไม่แทน tool approval หรือ source truth

การ replan สองเส้นทางคง requirement เดิมและล้าง decision เดิม ไม่อนุญาตให้คำตอบ clarification ลบ gate เงียบ ๆ การเปลี่ยน requirement ต้องสร้าง contract ใหม่ในเวอร์ชันนี้ ไม่มี automatic selective replay/effects

การตรวจประวัติไม่ประเมิน freshness ด้วยเวลาปัจจุบันใหม่ การตรวจ gate ทำตอน claim เท่านั้น ตัว source date ยังเป็นคำกล่าวอ้าง ไม่มี source authentication หรือ independent witness เพิ่มในรอบนี้

## ทดสอบ

187 passed / 218 warnings ใน 5.10 วินาที: evidence contract gate, evidence assessment/policy, receipt integrity, verified budget, read-only service, semantic plan และ derived plan receipts

ครอบคลุม current/stale/missing/disagreement/unknown-date, อายุที่เปลี่ยนระหว่าง create และ claim โดยไม่ sleep, digest tampering, snapshot ไม่ alias caller input, requirement คงอยู่หลัง replan และ decision เก่าถูกล้าง รวม negative/regression ของ workflows เดิม

Ruff CI directory scope ผ่าน; Linux Mypy ผ่าน 279 source files; strict MkDocs ต้องผ่านก่อน commit ไม่มี local full suite ใหม่ในรอบนี้ ไม่ใช้ผล full suite เดิมรับรองโค้ดใหม่นี้ CI หลัง push ต้องตรวจใหม่

## สถานะ GitHub/งานร่วม

main ที่ตรวจ 1ccc1c7c รวม #216 แล้ว; #217/#219 ยังเปิด; Claude เปิด #220 สำหรับ public preview guides ด้วย ไม่แก้ research/Desk ของ Claudeในรอบนี้

CI ของ combined 02738953 ยัง queued/in progress หลายรายการ ณ ตอนเริ่มรอบ ผลนั้นไม่ใช่ของ gate ใหม่

Review finding #219 เดิมยังใช้กับ head 4c89d37: loopback URL ยกเว้น freeze แต่ local gateway อาจ forward paid calls ได้ ต้องให้ Claude ปิดพร้อม budget policy-entry/in-flight token findings ก่อน paid canary ไม่ได้ทดสอบ paid dispatch

## ลำดับการพัฒนาต่อ

1. ตรวจ CI gate ใหม่ แล้วให้ application/service เลือก EvidenceRequirement จาก policy ที่เจ้าของกำหนด; public endpoint ต้องมี actor/workspace/version binding และรองรับ evidence correction ที่ชัดเจนก่อนเปิด
2. R1 source identity/authentication และ freshness policy ตาม domain; แยก observation time กับ claimed date และหลักฐานที่ยังไม่ยืนยัน
3. R2 แปลงโจทย์ผ่าน model adapter เดิมเป็น intent + material criteria + unknowns พร้อม provenance; unsupported domain ต้องถาม/แสดงขอบเขต ไม่ fallback ไป general writes
4. R3/R4 registry ต้องมี capability schemas และ necessary-condition coverage; ตรวจว่า criteria จาก intent ไม่ตกหล่น ไม่ถือว่า graph ครบเท่ากับ intent ครบ
5. R5 ข้อมูลใหม่ต้องมี dependency invalidation และ approval version ใหม่ตามผลกระทบ; read-only ก่อน write; ห้าม replay effect ที่ผลไม่แน่ชัด
6. R7 เพิ่ม domain verifier ทีละประเภท เช่น ภาษี/ส่วนลด/สกุลเงิน/rounding พร้อม oracle และ adversarial evidence ไม่ใช้ JSON validity แทน business correctness
7. R6 รวม #217 หลัง review แล้วทำ Desk lifecycle E2E/video ที่ combined SHA เดียวกัน; ใช้หลักฐาน native first-run ของผู้ทดลองสำหรับ self-install preview
8. Claude ปิด budget/freeze findings และ review #219 ก่อน freeze configuration ทุก role/retry/child; free rehearsal ต้องเทียบ billing/ledger/recovery บน configuration เดียวกับ paid run
9. เมื่อมี model/provider/วงเงินอนุมัติ จึง canary → holdout ไทย/อังกฤษที่ล็อกก่อน tuning → เผยแพร่ experimental self-install preview ด้วย claims ที่หลักฐานรองรับ

สถานะยังเป็น experimental local-first runtime ที่มี execution/verification เฉพาะ domain เพิ่ม durable contract evidence gate แบบ opt-in แล้ว แต่ยังไม่ครบ autonomous RCT-7 ทั่วไป ไม่มี paid API, merge หรือ release ในรอบนี้
