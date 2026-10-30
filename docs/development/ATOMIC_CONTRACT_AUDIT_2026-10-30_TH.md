# Atomic contract audit และ erased request tombstones

Patch นี้ต่อจาก PR #203 บนฐาน 02ab828a ไม่แตะ jobs/plan approval หรือสร้าง outbox ซ้ำกับ primitive ที่มีอยู่แล้ว

## Transaction boundary ที่แก้

ก่อนแก้ contract/request mapping commit ก่อน append_audit หาก process ตายระหว่างนั้นจะมี state โดยไม่มี audit entry ของ transition

หลังแก้ใช้ `ControlPlanePersistence._append_audit(conn, ...)` ซึ่งบันทึก audit_trail และ audit_chain ด้วย connection เดียวกับ contract transaction:

- create: contract + optional request mapping + audit trail/hash chain commit หรือ rollback พร้อมกัน
- transition: CAS state/version update + audit trail/hash chain commit หรือ rollback พร้อมกัน
- duplicate request: lookup state เดิม ไม่สร้าง audit ซ้ำและไม่ execute
- failed audit write: ไม่ advance version และไม่ claim สิทธิ์ execute; HTTP confirm ตอบ unavailable โดยไม่มี evidence read

เป็น guarantee ของ SQLite transactions ใน persistence นี้ ไม่ใช่ independent witness, external notary delivery หรือ PostgreSQL portability certification ไม่แก้ช่องว่างประวัติที่เกิดก่อน upgrade ด้วยการแต่ง audit ย้อนหลัง

## Erasure และ retention

`request_sha256` ถูกเพิ่มในคอลัมน์ scrub ของ erasure เดิม จึงล้าง fingerprint ของ request พร้อม payload ของ contract แต่เก็บ namespace, hashed request key และ contract ID เป็น replay tombstone เมื่อข้อความ intent ถูกลบ/อ่านไม่ได้ retry key เดิมตอบ conflict แทน 500 หรือสร้าง intent เดิมกลับ

ไม่มี plaintext request_id/goal ในตาราง key และไม่มี automatic key eviction/TTL การเก็บ tombstone ถาวรใน DB นี้เป็นนโยบายป้องกัน replay ไม่ใช่คำอ้างว่าลบ metadata ทั้งหมด การทำ off-host backup erasure check และตัดสิน metadata retention ระยะยาวยังต้องทำก่อน pilot

สิทธิ์เข้าถึง policy/file/actor ยังตรวจทุก HTTP operation เหมือน #203 การลบ fingerprint ไม่มอบ authority ใหม่ และการสร้างเจตนาใหม่ต้องใช้ request_id ใหม่หลังผ่านการอนุญาต ไม่เปิด write tools

## หลักฐาน

178 regression tests ผ่านใน 4.52s: atomic audit rollback, idempotent HTTP, concurrent/kill create, contract versions, verified-budget receipts, memory erasure และ audit chain ไม่มี model generation

Tests ใหม่พิสูจน์ว่า audit fault ระหว่าง claim ไม่อ่าน source, state/version เดิมยังอยู่และ confirm ใหม่สำเร็จเมื่อ DB กลับมา รวมทั้ง erase→retry ผ่าน HTTP ต้องเป็น conflict/no resurrection ตาราง tombstone ไม่ถูกนับว่ายังมี request fingerprint หลัง scrub

Kill test ของ #203 เปลี่ยน marker หลัง commit ไปที่การ return จาก create เพราะ audit อยู่ใน transaction แล้ว และตรวจว่ามี audit intent entry เดียวทั้งก่อน-insert kill และหลัง-commit kill

Ruff ผ่าน และ Mypy --platform linux ของ intent_contract.py/memory_erasure.py ผ่าน Full combined result บันทึกแยกในรายงาน jobs integration ไม่รวมยอด suite ที่ทับซ้อนกัน ไม่อ้างว่าเป็น canonical CI main checkpoint

## Merge/handoff

PR นี้มี dependency #203 ให้ review diff เทียบ branch นั้นก่อน เมื่อ #203 merge แล้ว retarget PR นี้ไป main และ push commit validation ใหม่ตามข้อตกลง Claude เพื่อเรียก full CI ห้าม merge เพียงเพราะ focused tests ผ่าน

Claude ยังถือ plan approval/P6/P15 และ research/Desk Codexเปลี่ยน memory_erasure.py เพียงคอลัมน์ request_sha256 ที่ scrub เพิ่ม ไม่มีการเปลี่ยน protocol ลายเซ็น erasure หรือ namespace authorization
