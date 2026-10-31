# Acquisition provenance และงานถัดไป

## การแก้รอบนี้

verified_budget ตรวจ observations ใน evidence requirement ให้ตรงกับ path/hash ของ source ที่ governed read อ่านจริง ก่อน publish observation receipt หรือเรียก dependent computation หาก requirement อ้างอีกไฟล์/อีก hash จะหยุด ไม่อนุมานว่า executor อ่านแหล่งเพิ่มเติมแล้ว

validate_receipts ใช้การตรวจเดียวกันกับ historical observation จึงไม่รับประวัติที่ rehash ให้สอดคล้องแต่ผูก requirement กับ source ที่ไม่เคยอ่าน PublicContract เพิ่ม acquisition_links เชื่อม observation_id, receipt_sha256, tool_result_sha256, source_sha256 และ source_locator; ก่อน execute ยังไม่มี links

ขอบเขตคือ acquisition identity ภายใน workflow เดียว Receipts เป็น local hash-linked state ไม่ใช่ signature/independent witness และไม่รับรอง source authorship หรือ semantic truth ค่า claimed date ยังเป็นข้อมูลที่แหล่งอ้าง

## ตรวจสอบ

Ruff CI scope ผ่าน; Linux Mypy ผ่าน 279 source files ชุดทดสอบครอบคลุม HTTP links, requirement/source mismatch ก่อน computation, rehashed historical mismatch และ regression ของ read-only/contract/budget เดิม ผลชุดสุดท้ายบันทึกใน PR ตาม SHA ไม่ใช้ผลเก่ารับรอง revision ใหม่ ไม่มี full suite หรือ capable-model evaluation ใหม่ในรอบนี้

CI baseline cfc22b94 ยัง queued หลายรายการ ณ ตอนตรวจ ไม่ถือว่า green งาน Claude #217/#219/#220 ยัง head เดิมและไม่ได้แก้ทับในรอบนี้ ไม่มี paid API/merge/release

## แผนต่อ

1. ปิด CI/review ของ provenance ใหม่ รวมการตรวจ public schema กับ Desk ก่อนใช้ links ใน UI
2. Source identity: เลือก domain และ authority ที่จะเชื่อถือ กำหนด signature/identity verification ที่ตรวจได้ แยก source-provided timestamp ออกจาก observed_at และ verification time
3. Typed intent: model adapter เดิมสร้าง material criteria/constraints/unknowns พร้อม provenance; hard refusal/clarification สำหรับ unsupported/ambiguous inputs ไม่เพิ่ม planner ซ้ำอีกชุด
4. Coverage: criterion → necessary inputs → handler → receipt → semantic verifier พร้อม negative cases ที่ DAG ครบแต่ intent ไม่ครบ
5. Correction: invalidation closure และ approval version เมื่อข้อมูลเปลี่ยน; read-only ก่อน external writes, reconcile uncertain effects ก่อน replay
6. Domain oracle: ภาษี/ส่วนลด/rounding/currency และ citation support; ไม่ใช้ format/language checks แทน business correctness
7. Claude ปิด budget policy-entry/token reservations และ loopback freeze exemption ใน #219; freeze model/provider/settings/roles/retries/children/holdout แล้วซ้อม fake billing/recovery
8. Review #217 และใช้ #220 ทำ native first-run/Desk lifecycle E2E/video; ระบุ combined SHA และ known limitations ก่อน self-install preview

สถานะ: runtime ทดลอง local-first ที่มี read-only contract evidence gate และ acquisition links ทำงานจริงใน workflow งบ แต่ยังไม่ครบ general RCT-7/source authentication/semantic conflict handling/model holdout ไม่ควรให้เปอร์เซ็นต์ความสมบูรณ์รวมจากจำนวน tests
