# บันทึกการพัฒนาและแชท — 31 ตุลาคม 2026

บันทึกนี้เก็บคำขอรอบปัจจุบันและสรุปการตัดสินใจ/ผลตรวจ ไม่ใช่ transcript ทุกข้อความย้อนหลังแบบคำต่อคำ ไม่มีการ export raw chat ฉบับเต็มจากแอปในรอบนี้

## คำขอผู้ใช้ในรอบนี้

> เริ่มต้นการเก็บงานทุกอย่างต่อตามแผนงานทั้งหมดที่วางไว้ และพัฒนาทุกอย่างต่อตามองค์ประกอบที่ยังขาดหาย
>
> พร้อมทำการทดสอบเทส ทุกอย่างเชิงลึกโดยละเอียด
>
> และทำการ commit and push ทุกอย่างรวมทั้งแชทขึ้น github repo หลังทำการตรวจสอบทั้งหมดแล้วเสร็จโดยละเอียด พร้อมทำการอธิบายผลลัพท์

บริบทที่ยึดต่อ: เป้าหมาย open-source self-install บนเครื่อง/VPS ผู้ใช้, ไม่ใช้ paid API จนมี model/provider และวงเงินอนุมัติ, Claude รับ research/Desk/local ส่วน Codex รับ backend/contracts/verifiers ไม่แก้ branch ของอีกฝ่าย

## Baseline ที่ตรวจจาก GitHub

main f31145964183abae46dd516e978ec3f51c5b856a ยังเป็น baseline ล่าสุดที่ตรวจ ผล check-runs ของ combined 509aa705eaae7838f872b3d5b91ded68cb5dcad7 ผ่านครบ 19 รายการที่ API รายงาน รวม Python 3.10/3.11/3.12, CodeQL, frontend/Rust, package checks และ security workflows นี่เป็น CI ของ PR #218 ไม่ใช่ผลของโค้ดใหม่ในรอบนี้ และไม่ใช้แทน checkpoint ทางการของ main

Claude เปิด PR #219 paid-run-freeze โดยแก้ research/paid_run_freeze.py, orchestrator/rehearsal และ tests จึงไม่พัฒนา freeze implementation อีกชุด ส่วน #216/#217 ยังเป็นงาน research/Desk ของ Claude

## R1 ที่พัฒนา

เพิ่ม rct_control_plane/evidence_assessment.py เป็น pure opt-in API ไม่มี I/O หรือ provider dispatch:

- observe คำนวณ SHA-256 จาก bytes ที่ caller ส่ง พร้อม locator และเวลาสังเกตที่มี timezone
- SourceClaim อ้างถึง observation ผ่าน identity แยก subject/key/value และ claimed_at
- assess_evidence ตรวจ identity ซ้ำ, dangling observation references, inventory bounds และ policy อายุที่เป็น integer แบบไม่รับ bool/NaN
- claimed date ไม่มีค่า = unknown; เก่าเกิน policy = stale; ใหม่กว่าเวลาที่อ่าน = future; ในช่วง = current รวม exact boundary
- ค่า literal ต่างกันใน subject/key เดียวกัน = disagreement พร้อม claim IDs ทั้งสองทิศทาง; คนละ subject ไม่รวมเป็น conflict
- truth_verified เป็น False เสมอ ไม่มีการอนุมานความเป็นอิสระ/authority จาก path หรือ hash
- current หมายถึงวันที่ที่ source กล่าวอ้างอยู่ใน policy ไม่ใช่พิสูจน์ว่า source date ถูกต้อง; needs_review=False ไม่ใช่สิทธิ์ execute หรือ approval

ยังไม่เชื่อม module นี้เข้ากับ active contract verdict ไม่ใช่การปิด R1 ทั้งขั้น การเชื่อมต้องกำหนด policy/version และ public schema ร่วมกับผู้ใช้ API ก่อน

## การทดสอบรอบนี้

118 passed / 204 warnings ใน 4.10 วินาที จาก evidence assessment ใหม่ร่วมกับ receipt semantic integrity, verified budget และ read-only service; Ruff ผ่าน; Linux Mypy ผ่าน 278 source files

ไม่ได้รัน local full suite ใหม่ในรอบนี้ ผล full suite 9,184 passed / 12 failed / 55 skipped / 1 xfailed ของ 509aa705 ยังคงเป็นหลักฐาน revision เดิมเท่านั้น CI ใหม่ต้องรอหลัง push

## งานต่อและเกณฑ์จบ

1. ตรวจ CI ของ revision ใหม่ และ review R1 API ก่อนเชื่อมเข้ากับ contract schema; เวลา/TTL และการหยุดเมื่อ evidence ไม่พอต้องมี policy ชัด
2. Claude ปิด policy-entry validation และ in-flight token reservations ที่ยังเป็น budget findings; review #219 พร้อม main/judge/children/retries ที่เปิดจริง
3. รวม #216/#217 หลัง review แล้วให้ Claude ทำ Desk lifecycle E2E/video บน combined SHA เดียวกัน
4. R1 เพิ่ม source identity/authentication policy และ semantic conflict handling; วันที่ที่ source อ้างกับ observation time ต้องแสดงแยกกัน
5. R2/R3/R4 ประเมิน intent/criterion coverage และ necessary conditions ด้วย development/holdout ที่ล็อกก่อน tuning ไม่เพิ่ม planner ซ้ำ
6. R5 ออกแบบ versioned correction และ selective downstream invalidation ทั่วไป พร้อม no-replay ของ effects; รอบก่อนพิสูจน์เฉพาะ workflow งบ
7. R7 เพิ่ม domain verifier ตาม business oracle ทีละประเภท; วัด false acceptance กับโมเดลจริงหลัง free rehearsal ผ่าน
8. Paid phase ต้องมี model/provider/routing, settings, role inventory, budget/caps และ provider-side limits ที่อนุมัติก่อน canary
9. Marketing self-install preview ต้องมี first-run evidence บน OS ที่ประกาศ, known failures, keys/cost/privacy/update/rollback/uninstall และ demo ที่ตรงกับข้ออ้าง

สถานะ: runtime ทดลอง local-first ที่มี verified execution เฉพาะ domain เพิ่ม R1 assessment foundation ในรอบนี้ ยังไม่รับรอง autonomous RCT-7 ทั่วไป ไม่มี paid calls, release หรือ merge โดย Codex

Combined ใหม่ a55457a0f6414a44c8e0bce9bfd3260bed9b9023 ทดสอบชุดเดิมซ้ำผ่าน 118 cases / 204 warnings ใน 4.08 วินาที; push แล้วทั้ง implementation b044e683 และ combined นี้ ผล CI ใหม่ยังต้องรอ ไม่ใช้ผลเขียวของ 509aa705 รับรอง revision ใหม่
