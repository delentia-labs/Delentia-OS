# Service evidence gate และเส้นทางสู่งานทั่วไป

## สิ่งที่พัฒนา

ServicePolicy เพิ่ม optional evidence_requirements mapping actor → authorized relative file → EvidenceRequirement v1 ซึ่งเป็น operator-owned startup configuration ผู้ใช้ API ส่งทับไม่ได้

load_policy ปฏิเสธ mapping ไป actor/file ที่ไม่ได้รับอนุญาต และ observation locator ที่ไม่ตรงกับไฟล์ Request ต้องใช้ source SHA ตรงกับ operator observation ก่อนสร้าง contract Requirement ถูกส่งเข้า IntentContractStore.create และผูกกับ plan digest/service policy binding เดิม

Confirm ใช้ actor/workspace/policy/version/digest checks เดิม แล้ว contract gate ประเมิน freshness ใหม่ก่อน running PublicContract เพิ่ม evidence_decision เป็น nullable typed field แสดง policy/assessment digests, reason codes และ grants_execution=False

กรณีไม่ตั้ง evidence_requirements ใช้ canonical policy payload เดิมเพื่อรักษา digest ของ contracts เดิมเมื่ออัปเกรด optional feature นี้ การตั้งหรือเปลี่ยน requirement เปลี่ยน policy digest และเพิกถอนการยืนยันภายใต้ policy เก่า ต้อง restart เพื่อใช้นโยบายใหม่ตามพฤติกรรมเดิม

## Validation

93 passed / 128 warnings ใน 3.79 วินาที: HTTP evidence policy, existing read-only service, contract gate และ verified budget. Ruff ผ่าน; Linux Mypy และ strict MkDocs ตรวจเพิ่มเติมก่อน commit ไม่ใช่ full suite ใหม่

HTTP tests ครอบคลุม current evidence ทำงานครบ, stale evidence ปฏิเสธและคง version/state/receipts, request inject requirement, actor อื่น, stale version, source hash ไม่ตรง, policy เปลี่ยน และ operator mapping ข้ามสิทธิ์

ไม่มี paid API, model evaluation, merge หรือ GUI video ในรอบนี้ และไม่อ้างว่า source claims กลายเป็นความจริงจาก policy pass

## ทำอย่างไรให้ครอบคลุมงานทั่วไป

ควรขยายเป็น task families ที่มีขอบเขตและ oracle เช่น อ่าน/เปรียบเทียบเอกสาร, สรุปพร้อมอ้างแหล่ง, วิเคราะห์ตาราง และวางแผนงาน ไม่ประกาศความเข้าใจงานทุกชนิดจากจำนวน tests

1. Intent adapter ใช้ model provider เดิม สร้าง typed goal/material criteria/constraints/unknowns พร้อม source spans; เมื่อ ambiguous หรือ unsupported ต้องถามหรือแสดงขอบเขต ทดสอบ negation และหลายเจตนาโดยเฉพาะ
2. Coverage compiler ตรวจ criterion → necessary condition → trusted handler → receipt → verifier; graph ที่เชื่อมครบแต่ตกหล่น material criterion ต้องไม่ผ่าน ส่วนความครบของ criteria เองต้องมี independent task oracle
3. Evidence acquisition ต้องผูก observations กับ tool receipts และ source identity จริง; claimed date แยกจาก observed time; semantic conflicts ต้องมี normalization ของหน่วย/สกุลเงิน/บริบท ไม่เทียบข้อความอย่างเดียว
4. Correction ต้องผูก actor/version และสร้าง invalidation closure ของ dependencies พร้อมล้าง downstream verdict/approval; ผลของ effects ที่ไม่แน่นอนต้อง reconcile ไม่ replay
5. Domain verifiers เพิ่มทีละประเภท โดยเริ่มจาก arithmetic/tax/discount/rounding/currency และ document citation integrity ไม่ใช้ format success แทน business correctness
6. Model evaluation แยก development/holdout ก่อน tuning ใช้ model/settings/fixtures/budget เดียวกันสำหรับ baseline และ RCT-7; วัด correctness, false acceptance, unnecessary clarification, completion rate, latency และ cost per correct task คู่กับ process violations
7. ระดับใช้งาน: deterministic domain checks → supervised model workflows → self-install preview ที่มี known limits; การเปลี่ยนระดับต้องมี evidence ไม่ใช่เพิ่ม labels ในเอกสาร

## งานที่ยังติดและการแบ่งเลน

Codex: backend evidence/service bindings, coverage compiler, invalidation และ verifiers. Claude: #217 Desk lifecycle, #219 paid freeze/budget และ #220 preview guides. API/event schema ต้องประสานก่อนแก้ shared surfaces ไม่แก้ไฟล์ research/Desk ซ้ำ

ก่อน paid phase ยังต้องปิด budget entry/token reservations และ loopback freeze exemption ของ #219; freeze roles/retries/children และซ้อม exact configuration กับ fake billing ก่อนมี model/provider/วงเงินอนุมัติ

ก่อน marketing: native first-run, update/rollback/uninstall, privacy/key/cost guides, Desk E2E/video บน combined SHA และผู้ทดลองติดตั้งเอง

สถานะ: R1 เชื่อมกับ read-only service ได้จริงแบบ operator opt-in แต่ R2/R3/R4/R5/R6/R7 ทั่วไปและ capable-model evidence ยังไม่ครบ ไม่ใช่ autonomous RCT-7 ที่พร้อมรับงานทุกชนิด
