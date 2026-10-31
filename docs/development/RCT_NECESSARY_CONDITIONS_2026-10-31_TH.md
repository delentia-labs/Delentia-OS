# RCT-7: เงื่อนไขจำเป็นและเส้นทางข้อมูล — 2026-10-31

## ขอบเขตและ revision

ฐานงาน c43d2ab9; implementation 52361024; main ที่ตรวจผ่าน GitHub API คือ 1ccc1c7c
CI ของ c43d2ab9 ที่ตรวจพบมี packaging checks queued ยังไม่ถือว่า revision ใหม่ผ่าน CI
เป้าหมาย release คือ open-source self-install ไม่ใช่ host กลาง ไม่เรียก paid API

## สิ่งที่เพิ่ม

intent_conditions.py ต่อจาก typed_intent และ component_execution เดิมโดยไม่เพิ่ม planner/provider ใหม่
application เป็นผู้กำหนด CriterionCapability ต่อทุก criterion รวมข้อห้าม และ NecessaryCondition ต่อ capability
condition ระบุ trusted producer handlers ที่ยอมรับ และ capability ระบุ verifier handlers ที่รองรับ
ทุก condition ต้องผ่าน; handler alternatives ภายใน condition เดียวเลือกอย่างใดอย่างหนึ่งได้

Validator ตรวจว่า producer อยู่บนเส้นทาง typed inputs ที่ไปถึง verifier จริง
การมี depends_on เฉย ๆ หรือให้ literal แทน observation ไม่พอ
ตรวจทั้งทางตรงและผ่าน transform หลายขั้น และไม่อาศัยลำดับรายการ nodes
ยังใช้ critical unknown gate, schema, registry และ criterion coverage เดิม
ไม่มีการ execute, ให้ approval, เรียกโมเดล หรือเปลี่ยน public JobService API
ไม่แก้ research, Desk, budget guard หรือ plan approval hooks ของ Claude

## หลักฐานทดสอบ

- Focused regressions: 172 passed, 220 warnings, 4.17 วินาที
- รวม tests ใหม่ 12 กรณี; จำนวนนี้รวม typed intent, component verification, semantic plan,
  intent contract, read-only evidence policy, verified budget และ historical receipt integrity
- Ruff: passed สำหรับ core, signedai, rct_control_plane, microservices
- Mypy --platform linux: passed, 281 source files; ยังมี notes ว่า untyped bodies ไม่ได้ตรวจทั้งหมด
- ไม่ได้รัน full suite ใหม่, real-model evaluation, A/B หรือ GUI E2E ในรอบนี้
- warnings ใน pytest ยังมี deprecated APIs; tests ผ่านไม่ได้แปลว่าปิด warnings แล้ว

## ข้อจำกัดที่ต้องไม่ขยายคำกล่าวอ้าง

เป็น opt-in structural validator ยังไม่เชื่อม service/Desk และไม่ได้พิสูจน์ semantic completeness
catalog เป็น trusted application input ต้องไม่รับจาก request/model มาเป็น authority โดยตรง
การมี dataflow หมายถึง handler รับข้อมูล ไม่รับรองว่า implementation ใช้ข้อมูลถูกต้อง
condition แบบนี้ยังไม่พิสูจน์ว่ามีเอกสารสองฉบับต่างกันจริง, freshness, source identity,
ความถูกต้องของ claim หรือการไม่ส่งอีเมล: แต่ละอย่างต้องมี domain/policy oracle แยก
การเลือก capability ให้ตรงเจตนาและการสร้าง necessary conditions จากโจทย์ใหม่ยังต้อง review
ไม่มี actor/workspace/version approval binding ใหม่ และยังไม่มี selective invalidation ทั่วไป

## งานต่อและเกณฑ์จบ

1. ปิด CI/review ของ adapter และ condition validator ตาม SHA จริง
2. ออกแบบ reviewed intent snapshot บน lifecycle เดิม ผูก actor/workspace/version/policy/catalog digest
   พร้อม tests stale confirmation, revoked access และเปลี่ยน intent หลังยืนยัน; ยังไม่เปิด generic execution
3. เพิ่ม capability catalog ที่มี version และ semantic oracles สำหรับ 2–3 workflow:
   สรุปพร้อม citation, เปรียบเทียบเอกสาร, วิเคราะห์ตาราง ต้องแยก supported/unsupported ให้ชัด
4. เพิ่ม input cardinality/source identity/semantic checks ตามงาน เช่น comparison ต้องใช้สองแหล่งที่กำหนด
5. สร้าง dependency invalidation preview แล้วเชื่อม durable CAS/approval rebinding เดิม
   unknown effects ต้อง reconcile ห้าม replay โดยเดา
6. แยก development/holdout ก่อน tuning: negation scope, implicit constraints, multi-intent,
   missing context และ unnecessary clarification; วัด completion และ false acceptance ร่วมกัน
7. Claude ปิด budget/freeze findings; Codex review ด้วย malformed/concurrent/uncertain/crash probes
   freeze code/model/settings/roles/retries/children แล้วซ้อม fake billing ทั้ง configuration
8. เมื่อระบุ model/provider และวงเงินแล้วจึง paid canary; ยังไม่มีการอนุมัติในรอบนี้
9. เชื่อม Desk lifecycle และ native first-run บน combined SHA พร้อมวิดีโอ คู่มือ keys/cost/privacy,
   update/rollback/uninstall และ known limitations ก่อน self-install preview

สถานะ: experimental local-first runtime มี typed proposal และ structural necessary-condition checks
ข้ามประเภทงาน แต่ยังไม่มีหลักฐานว่ารับงานทั่วไปแบบ autonomous ได้ครบถ้วน
