# HTTP review gate และ combined Desk — 31 ตุลาคม 2026

## เป้าหมายและ revision

เป้าหมายยังเป็น open-source self-install; ไม่มี paid model calls หรือ merge/release ในรอบนี้
Implementation: ddd02065 บน branch Codex; combined ที่ตรวจ: 166f9c64
Combined รวม main b0110ef4 ซึ่งรับ #217 Thai Desk/Delta ของ Claude แล้ว
#219 freeze และ #220 preview guides ยังเปิดอยู่; #221 ใหม่แก้ stale whole-file writes
Codex ไม่แก้ research, UI หรือ plan approval hooks ของ Claude
ใน governed_autonomous_loop.py แก้เฉพาะ continue_intent ให้ส่ง review bindings ไป store
ไม่เปลี่ยน JobService, episode journal, resume หรือ idempotency semantics

## สิ่งที่เปิดใช้ได้จริง

Operator เปิด `intent_review_required: true` ใน read-only service policy ที่มีอยู่
ค่าเริ่มต้นเป็น false; hash ของ policy เดิมที่ไม่มี optional fields คงเดิม
HTTP budget route สร้าง typed review snapshot ฝั่ง server พร้อม actor/workspace/policy/catalog digest
request ส่ง proposal, binding หรือ catalog มาเลือกเองไม่ได้

วงจรที่ทดสอบ: POST รับงาน → public plan → POST confirm → governed execution → status/receipts
ใช้ routes เดิม /v1/agent/readonly/budget และ /{id}/confirm ไม่มี generic agent fallback
คำยืนยันผูก contract/version/plan digest ส่วน current binding มาจาก server ไม่ใช่ request
ตรวจ policy/token revocation ก่อน backend; catalog เปลี่ยนทำให้ confirmation ไม่ผ่านและยัง plan_ready
redact workspace_root ใน nested intent_review ก่อน public response และไม่ mutate stored plan

## สิ่งที่ยังไม่ได้เปิด

เป็น server-generated proposal ของ bounded budget workflow ไม่ใช่โมเดลตีความ goal ทั่วไป
catalog เป็น versioned description ของ executor เดียว ไม่ใช่ registry ที่มี semantic oracle ทุก domain
ยังไม่รับ model-generated criteria ผ่าน HTTP, ไม่มี generic clarification/invalidation หรือ write authority เพิ่ม
ห้ามนำผลนี้ไปอ้างว่า general RCT-7 หรือโมเดลเข้าใจทุกโจทย์แล้ว

## การทดสอบ

- HTTP tests ใหม่ 10 กรณี: ผ่าน 1.67 วินาที
- Source regressions 322 passed, 248 warnings, 28.71 วินาที
- Combined รวม state-log/Thai governance ของ main ใหม่: 345 passed, 768 warnings, 31.00 วินาที
- ชุดข้างต้นซ้อนกัน ไม่บวกเป็นยอดรวม
- Ruff ผ่านทั้ง source/combined; Linux Mypy source 282 files / combined 283 files ผ่าน
- Desk npm test ผ่าน รวม server-text ภาษาไทย, fonts และ static accessibility
- Desk production build ผ่าน Next.js 16.4.2, TypeScript และ static generation 30 pages
- Build เตือนว่า Next headers ไม่ใช้กับ output:export; deployment ต้องตั้ง headers ที่ serving layer
- ไม่มี full Python suite ใหม่ของ 166f9c64; ผล 9262/13/68/1 ของ 11e65b9f รอบก่อนใช้แทนไม่ได้
- ยังไม่มี real-model holdout, GUI contract lifecycle video หรือ native Windows/macOS first-run ใหม่

## CI/review

ตรวจ #218 checkpoint เก่า 5b916a92 พบ install check, safety, bandit และ CodeQL Python/actions ผ่าน
ยังมี Python matrix, lint, packaging และ checks อื่น queued; CodeQL aggregate neutral ไม่ใช่ผ่านทั้งหมด
ต้องตรวจ SHA ล่าสุดหลัง push อีกครั้ง ห้ามใช้ผล checkpoint เก่ารับรอง revision ใหม่

## งานที่ต้องเก็บก่อน phase ถัดไป

1. Review และ CI ของ combined revision ใหม่ โดยเฉพาะ changes จาก #217 และ HTTP gate
2. Public typed-intent schema สำหรับ goal ทั่วไป: แยก proposed/reviewed/unsupported,
   map material criteria สู่ trusted semantic verifiers และ expose clarification โดยมี actor/version bindings
3. Capability catalog 2–3 กลุ่มงาน: สรุปพร้อม citation, เปรียบเทียบเอกสาร, วิเคราะห์ตาราง
   ต้องมี oracle ที่จับ citation ไม่รองรับ claim, ข้อมูลขัดแย้ง, source identity และ rounding/currency ตามขอบเขต
4. Selective invalidation: เปลี่ยน input แล้ว invalidate descendants และ approval ที่เกี่ยวข้อง
   เก็บ history แยก revision; uncertain effects ต้อง reconcile ก่อน replay
5. Claude ปิด budget policy-entry NaN, in-flight token reservation และ loopback freeze exemption ใน #219
   ไม่มี revision ใหม่ของ fixes เหล่านี้ให้รับรองในรอบนี้; ใช้ reproduction จากรายงานก่อนหน้า
6. Freeze SHA/model/provider/settings/prompts/policy/roles/retries/children และ holdout ก่อน tuning
   ซ้อม fake billing ทั้ง configuration; กำหนดวงเงินจริงก่อน paid canary
7. Desk ต้องแสดง lifecycle ของ contract ใหม่จริง ไม่ใช่เพียง DOM accessibility ผ่าน
   ทดสอบ identity/reconnect/cancel/restart พร้อมวิดีโอ และ native self-install/upgrade/rollback/uninstall

เกณฑ์ marketing: เปิด experimental self-install preview ได้เมื่อหลักฐานติดตั้งและ first-task ครบ
พร้อม known limitations และ claims ที่ตรงกับ evidence; ไม่ต้องมี host กลางของ Delentia
สถานะยังเป็น experimental local-first runtime ที่มี bounded reviewed HTTP execution เพิ่มขึ้น

## ผล browser accessibility ที่รันจบ

บน combined 166f9c64: 112 page loads (28 หน้า × th/en × 375/1280 px)
ไม่มี axe violations และไม่มี horizontal overflow ตาม script a11y-e2e.mjs
ใช้ CHROME_PATH=/workspace/.delentia-cloud/desk-chromium-container และ unset CI
เพื่อรักษา sandbox (runner นี้ปฏิเสธ --no-sandbox)
ตรวจหน้าแบบไม่ได้เชื่อม API; ไม่ครอบคลุม real-data states, screen-reader/manual Tab walk,
contract lifecycle, native first-run หรือ video demo
ไม่มีการแก้ UI ของ Claude เพื่อให้ผลผ่าน
