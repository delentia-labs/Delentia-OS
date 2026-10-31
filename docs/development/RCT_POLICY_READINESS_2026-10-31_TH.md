# RCT-7 policy และ readiness review — 31 ตุลาคม 2026

## ผลรอบนี้

main ที่ตรวจล่าสุด 1ccc1c7c รวม #216 W08/W10 แล้ว; #217 Desk/Delta log และ #219 paid-run freeze ยังเปิดอยู่ ไม่แก้ไฟล์ของ Claude

เพิ่ม EvidencePolicy schema_version=1 ที่มี identity และ required claim IDs; ปฏิเสธ version ที่ไม่รองรับและ IDs ซ้ำ/ว่าง ผล EvidenceDecision ผูก policy/assessment SHA-256 และ reason codes ของ missing/unknown/stale/future/disagreement; grants_execution=False เสมอ ค่า satisfied หมายถึงผ่านเงื่อนไขวันที่และ literal disagreement ที่ประกาศ ไม่ใช่พิสูจน์ความจริงหรืออนุญาตให้ทำงาน

ยังเป็น opt-in foundation ไม่เชื่อม acceptance ของ contract เดิมโดยอัตโนมัติ ต้องมี service policy binding และ public response schema ก่อนเชื่อมจริง

124 tests passed / 204 warnings ใน 4.17 วินาที รวม R1 policy, receipts, budget, read-only regressions; Ruff ผ่าน; Linux Mypy ผ่าน 278 source files ไม่ใช่ full suite ใหม่

## Review #219 (head 4c89d37)

research/paid_run_freeze.py:208–219 ยกเว้น freeze เมื่อ base URL เป็น loopback โดยถือว่าเป็น fake แต่ real local gateway สามารถ forward ไป paid provider ได้ URL อย่างเดียวไม่พิสูจน์ว่าไม่มีค่าใช้จ่าย

Probe แบบไม่มี network call: ตั้ง DELENTIA_OPENROUTER_BASE_URL=http://127.0.0.1:9999/api/v1 และลบ DELENTIA_FREEZE_FILE; freeze_problems('model',0.1,0.1,1.0) คืน []; เมื่อ force=True จะปฏิเสธว่าไม่มี freeze file นี่พิสูจน์การยกเว้น guard ไม่ได้อ้างว่ามีเงินจริงถูก dispatch ในการทดลอง

ข้อเสนอให้ Claude: default ต้องตรวจ freeze แม้เป็น loopback; free rehearsal ควรได้รับ explicit fake transport/config จาก harness พร้อมข้อจำกัด egress ไม่อนุมานจาก hostname และมี regression case สำหรับ local forwarding gateway

Budget guard policy-entry validation/in-flight token reservations เดิมยังต้องปิด แยกจาก configuration freeze; ไม่แก้ research module ของ Claude ในรอบนี้

## RCT-7 พร้อมใช้งานหรือยัง

ยังไม่ครบ general autonomous RCT-7 ใช้ตรวจ workflow เฉพาะ domain ภายใต้ขอบเขตที่มีหลักฐานได้ การผ่าน tests ของ schema/policy ไม่พิสูจน์ model comprehension

- R1: มี observation/claim assessment และ versioned policy; ยังไม่มี source authentication, semantic conflicts หรือ contract integration
- R2: ยังขาด capable-model holdout ไทย/อังกฤษสำหรับ ambiguity/negation/multi-intent
- R3/R4: DAG และ criterion receipts ทำงานได้ใน domain ที่รองรับ; การแตกเจตนา/necessary conditions ทั่วไปยังต้องมี oracle
- R5: workflow งบทดสอบ changed answer/stale versions แล้ว; selective invalidation ทั่วไปยังไม่ครบ
- R6: ต้องรวม Desk #217 หลัง review แล้วทำ lifecycle E2E/video บน SHA เดียวกัน
- R7: historical pure criteria/arithmetic ตรวจได้; verifiers หลาย domain และ model false acceptance ยังต้องประเมิน

## ลำดับต่อ

1. รอ CI ใหม่และปิด review policy schema ก่อนต่อเข้า service contract โดยปฏิเสธ unknown versions/missing required evidence
2. Claude แก้ budget entry/token findings และ loopback exemption ของ #219 พร้อม concurrency/crash/gateway cases
3. รวม main ล่าสุดและทดสอบ #217 แยกหลัง review ไม่ merge PR ให้โดยอัตโนมัติ
4. Freeze model/provider/routing/settings/roles/retries/children และ development/holdout; กำหนดวงเงินก่อน paid canary
5. Free rehearsal ผ่าน fake billing และ reservation/settlement/restart ก่อน capable-model runs
6. Self-install preview: native first-run, keys/cost/privacy, update/rollback/uninstall, Desk E2E/video และ known failures

ไม่มี paid API, merge หรือ release ในรอบนี้ เป้าหมายยังเป็น open-source ติดตั้งบนเครื่อง/VPS ผู้ใช้เอง

ผล combined 02738953e774562cfd419e0e747a0d48b4c0545b (รวม main 1ccc1c7c): ชุด R1/receipt/budget/read-only 124 passed ใน 3.95 วินาที; W08/W10 9 passed ใน 2.49 วินาที ผลสองชุดรายงานแยกกัน ไม่ใช้รับรอง full suite ใหม่
