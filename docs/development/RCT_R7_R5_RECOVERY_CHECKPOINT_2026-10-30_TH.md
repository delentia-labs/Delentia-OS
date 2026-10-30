# RCT-7: historical verification และ clarification checkpoint

วันที่ 30 ตุลาคม 2026 (Asia/Bangkok) — เป้าหมายคือ open-source ที่ผู้ใช้ติดตั้งบนเครื่องหรือ VPS ของตนเอง ไม่มี paid API ในรอบนี้

## Revision และผลที่ตรวจแล้ว

- `841e4481`: combined revision เดิมที่รวม main `61cdea9`, fonts `4cb36a3`, budget guard `bce3c91` และ Codex `0c22d5a2`; focused tests 191 ผ่านใน 27.88 วินาที ผลนี้ไม่ใช่ full suite
- `f1d26866`: เพิ่มการตรวจ pure criteria ของ historical receipts และ regression test การเปลี่ยนงบหลัง clarification
- `8b5abfb6`: combined revision ที่รวมการแก้ R7/R5 ข้างต้น ใช้สำหรับ full suite รอบใหม่ ผลจะบันทึกแยกจาก full suite เก่าที่ `b421bf6d`
- ชุด R7/verified-budget/read-only/semantic/derived: 108 ผ่าน 4.47 วินาที ก่อนเพิ่ม test R5 สุดท้าย
- ชุด receipt integrity รวม test R5 สุดท้าย: 21 ผ่าน 2.34 วินาที ตัวเลขซ้อนกับ 108 ห้ามบวกเป็นจำนวนรวม
- Ruff ผ่าน CI directory scope; Mypy `--platform linux` ผ่าน 277 source files
- ผล local ทั้งหมดไม่ใช่ตัวเลขทดสอบทางการของ main CI

## สิ่งที่แก้และเหตุผล

ก่อนแก้ การเปลี่ยน criterion ในแผนแล้วคำนวณ hashes ให้สอดคล้องกันอาจทำให้ประวัติรายงานว่าตรวจผ่านทั้งที่รายงานไม่ผ่าน contains/language ที่กำหนด Regression tests สองกรณียืนยันข้อบกพร่องนี้ด้วย DID NOT RAISE ก่อนแก้

ตอนอ่านประวัติ ระบบตรวจ contains, language และ json_object ซ้ำกับรายงานที่บันทึกไว้ใน dependency ของ verifier เฉพาะนั้น ไม่เรียก live verifier ที่อาจอ่านไฟล์ใหม่ ไม่เปลี่ยน receipt schema และไม่เรียกโมเดล language ยังคงเป็น heuristic อักขระเดิม ไม่ใช่การประเมินความเข้าใจภาษา

Hashes เป็นการผูกข้อมูลภายใน ไม่ใช่ลายเซ็นหรือการรับรองความจริงของผู้ขาย การทดสอบนี้ตรวจ internal consistency ไม่ได้อ้างว่าผู้ใช้ภายนอกสามารถเขียนฐานข้อมูลหรือปลอมแผนผ่าน API ได้

ประวัติ file_unchanged ที่ถูกต้องยังเปิดได้เมื่อ source เปลี่ยนหลังงานจบ เพราะประวัติอธิบายการตรวจในเวลานั้น ไม่ใช่ตรวจสภาพไฟล์ปัจจุบันอีกครั้ง

## R5 ที่พิสูจน์เพิ่ม

ทดสอบวงจรจริงบน SQLite/MCP โดยห้าม generation: ขอข้อมูลงบ → ตอบ 15,000 THB → execute แล้วไม่ผ่าน literal criterion → แก้เกณฑ์และถามงบใหม่ → ตอบ 10,000 THB → ยืนยันและ execute ใหม่

ยืนยันว่า receipts/report/status เดิมหายไปจาก active revision, คำตอบ version เก่าถูกปฏิเสธ, receipts เก่าใช้กับแผนใหม่ไม่ได้ และผลใหม่เป็นเกินงบ 2,500 THB จากราคาหลักฐาน 12,500 THB

นี่เป็นการพิสูจน์พฤติกรรมที่มีอยู่ ไม่ได้เพิ่ม API สำหรับแก้คำตอบในทุกสถานะ ยังไม่รองรับ selective invalidation ของ graph ทั่วไปหรือการ replay write effects

## Runtime

PostgreSQL และ Ollama เดิมหยุดด้วย exit 255 เวลาใกล้กัน โดย Docker รายงาน OOMKilled=false ยังไม่มี platform termination event ที่ชี้สาเหตุ จึงไม่สรุปว่าเป็น OOM, พื้นที่เต็ม หรือ proxy เพียงอย่างเดียว

รอบนี้เริ่ม containers เดิมและตรวจ Ollama tags ซึ่งยังไม่มีโมเดล ไม่ดาวน์โหลดโมเดลซ้ำ ไม่ลด sandbox/TLS/SSRF controls ไม่ล้าง model cache หรือฐานข้อมูล

## งานต่อและผู้รับผิดชอบ

1. Codex: ตรวจ full suite และ CI ตาม combined SHA; เก็บ failure แต่ละกรณีพร้อมเหตุผล ไม่ใช้ผลเก่ารับรอง SHA ใหม่
2. Claude/research: PR #214 ยังต้อง validate policy ที่ entry point และ reserve in-flight tokens รวม uncertain/crash cases; Codex review ด้วย fake provider ก่อน paid phase
3. ร่วมกัน: freeze SHA/model/provider/routing/settings/prompts/schema/policy และทุก role/retry/child; กำหนดวงเงินจริงและ provider-side cap ก่อน canary
4. Codex/backend: ขยาย R1 evidence metadata ให้แยก observation time, source claims, freshness policy และ conflict decision; ต้องมี schema/version และ oracle ก่อนเพิ่ม domain
5. Codex/backend: R5 ทั่วไปต้องมี dependency invalidation เมื่อ input เปลี่ยน, approval/version bindings และ no-replay guarantees; ไม่เปิดแก้ข้อมูลใน running contract โดยไม่มี state transition ที่กำหนดชัด
6. Claude/local/UI: Desk lifecycle E2E/video บน combined SHA เดียวกัน รวม setup, plan, clarification, confirmation, result, restart; ตรวจฟอนต์และ accessibility ของ revision นั้น
7. Model evaluation: แยก development/holdout ไทย/อังกฤษ วัด task success, false acceptance, clarification, latency และ cost per successful task หลัง free rehearsal ผ่าน
8. Self-install preview: clean installation, first task, update/uninstall/backup/rollback และคู่มือ keys/cost/privacy พร้อมผู้ทดสอบภายนอกติดตั้งเอง

## ขอบเขตที่ยังไม่พิสูจน์

RCT-7 ยังเป็น partial implementation: R1 ไม่พิสูจน์ความจริง/freshness/conflicts ทั่วไป; R2 ยังไม่มี capable-model holdout; R3/R4 ยังจำกัด trusted domains และการแตก necessary conditions; R5 ยังไม่มีการแก้หลายเจตนาและ selective invalidation ทั่วไป; R6 ยังขาด combined GUI lifecycle video; R7 ยังต้องเพิ่ม business verifiers และวัด false acceptance กับโมเดลจริง

การเปิดตัว self-install ไม่ต้องมี host กลางของ Delentia แต่ควรประกาศสถานะ experimental และความสามารถที่มีหลักฐานเฉพาะ revision เท่านั้น ไม่ยก scripted budget executor เป็นหลักฐานความเข้าใจของโมเดล
