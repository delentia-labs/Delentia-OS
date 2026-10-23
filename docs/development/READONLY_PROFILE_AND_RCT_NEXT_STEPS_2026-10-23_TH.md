# Read-only profile checkpoint และแผน RCT-7

## ผลงานและขอบเขตจริง

เพิ่ม opt-in API profile ผ่าน `DELENTIA_READONLY_POLICY` ซึ่งต้องชี้ไฟล์ JSON ของ operator ตั้งค่าก่อนเริ่ม process ไม่ใช่ข้อมูลที่ผู้ใช้ส่งมากับ request ตัวอย่าง (ไม่รวม token):

```json
{
  "schema_version": "1",
  "workspace_id": "review",
  "workspace_root": "/absolute/trusted/workspace",
  "actor_files": {"alice": ["quotes/alice.json"]}
}
```

root ต้องตรงกับ `mcp_server.REPO_ROOT` ของ process; ใช้ API tokens รายบุคคลเดิม และปฏิเสธ shared identity การอนุญาตไฟล์เป็น exact relative path ไม่ใช่ glob ผู้ใช้แก้ namespace, goal, tools, criteria, planning context หรือ executor เองไม่ได้ ไม่สลับ global workspace ระหว่าง requests

profile เปิดเพียง GET `/health` และ POST `/v1/agent/readonly/budget` ปิด route อื่นรวม generic run, MCP, jobs, continuation, docs, WebSocket และ OPTIONS ขณะนี้จึงยังต่อ Desk ที่ต้องใช้ cross-origin ไม่ได้ การรันแบบไม่ตั้ง policy ยังคง behavior เดิม profile ไม่ได้ถูกเปิดใช้กับ operator server ที่มีอยู่โดยอัตโนมัติ

request v1:

```json
{
  "schema_version": "1",
  "executor_version": "verified_budget_v1",
  "workspace_id": "review",
  "budget": "15000 THB",
  "evidence": {"relative_path": "quotes/alice.json", "sha256": "<64 lowercase hex>"}
}
```

response มี envelope version และระบุขอบเขต document bytes/same-currency arithmetic แต่ `result` ภายในยังเป็น contract format เดิม ไม่ใช่ public contract schema ที่สมบูรณ์ Error schemas ของ auth/validation ยังต้องรวมให้เป็น version เดียวกัน

**endpoint รอบนี้หยุดที่ `plan_ready` เพื่อแสดงแผนก่อนทำงาน ไม่มี source read หรือ completion receipts ผ่าน endpoint นี้** HTTP 200 ไม่ได้หมายความว่าตรวจงบสำเร็จ ไม่เพิ่ม dummy on_plan callback เพื่อข้ามการแสดงแผน การเปิด continuation ต้องผูก contract กับ service profile/actor/workspace/policy version และยืนยันแผนก่อน จึงยังปิด legacy continuation ทั้งหมดใน profile

แยก lifespan ไม่เริ่ม general scheduler, gateway pollers, cron delivery หรือ model warmup ขณะใช้ profile คำว่า read-only หมายถึงไม่เปิด workspace/external write tools; การสร้าง contract ยังเขียน state ลง SQLite ไม่ได้แปลว่าไม่มี disk writes

ข้อจำกัด: trusted operator/OS, single workspace ต่อ process, exact path authorization ไม่ใช่ inode isolation จาก hard links หรือการแก้ root โดย operator ไม่ใช่ multi-tenant OS sandbox และยังไม่มี public pilot

## การตรวจสอบ

ชุดใหม่ 25 กรณีร่วมกับ verified-budget และ API auth รวม **79 ผ่าน** (ชุดทับซ้อนกับหลักฐานเก่า ไม่นำไปบวก full-suite): ตรวจ auth จริง, schema/version, path/actor/workspace denial, websocket/route denial, startup policy fail-closed, application wiring/lifespan, persisted plan และ verified-budget execution เดิมผ่าน SQLite/ไฟล์จริง

Ruff ตรวจ core/signedai/rct_control_plane/microservices; Mypy ตรวจขอบเขต CI (261 source files). หลักฐาน log/XML อยู่ `/workspace/delentia-readonly-profile-evidence/` ผลเต็มดู log ล่าสุด ไม่ได้รัน full Python suite, model evaluation, A/B ใหม่ หรือ GUI demo รอบนี้

ทดสอบเริ่มแรกคาด semantic success ผิด: API ต้องส่ง plan ก่อน จากนั้นคาด waiting_for_input ผิดอีกครั้ง: เมื่อข้อมูลครบคือ plan_ready แก้ test ให้ตรวจ protocol จริง ไม่เปลี่ยน runtime ให้ข้าม gate

ตรวจพื้นที่ host รอบนี้เห็นประมาณ 30 GiB available; `getent hosts example.com` exit 2 ยังไม่ resolve ไม่ใช้พื้นที่เดิม 8 GiB อธิบาย host ปัจจุบัน ยังไม่ตรวจยืนยัน model digest/inference ใหม่ และไม่ใช้ paid API

## ช่องว่าง RCT-7 และเกณฑ์ปิด

1. ความเข้าใจ intent: semantic planner เป็น bounded rules; ต้องมีไทย/อังกฤษ paraphrase, negation, multi-intent, ambiguity, unknown intent และ holdout ที่แยกก่อน tuning วัด task success/false acceptance/clarification ไม่ใช้ executor tests เป็น model capability
2. หลักฐาน: hash ยืนยัน bytes ไม่ยืนยัน vendor truth/freshness/conflicting sources ต้องมี source provenance, retrieval time, expiry และ conflict rules พร้อม negative cases
3. Backward reasoning: ต้องพิสูจน์ criterion → necessary conditions → handler → receipt → verifier ครบทุก material criterion ไม่ใช่ข้อความ backward chain อย่างเดียว
4. Clarification: ต้องถามข้อมูลที่เปลี่ยนผลจริง ผูกคำตอบกับ actor/version และ invalidate outputs ที่พึ่งข้อมูลนั้น พร้อมตรวจ replay/stale answers
5. Execution: typed graph/scheduler ทำงานได้ใน domain งบ แต่ต้องเพิ่ม trusted domain handlers และ input/output/verifier contracts ทีละ domain ไม่ให้โมเดลลงทะเบียน executable code
6. Verification: ตรวจ Decimal/currency/final-total ได้เฉพาะ schema ที่รองรับ ภาษาหรือ JSON ถูกต้องไม่รับรองภาษี เงื่อนไขธุรกิจ หรือข้อสรุปทั่วไป
7. Recovery/effects: completion callback ไม่เท่ากับ durable per-node commit; ต้องพิสูจน์ interrupted jobs และ signed write reconciliation ก่อนเปิด writes
8. Channels/operations: Desk, background jobs และช่องทางอื่นต้องมี E2E แยก; backup/witness/soak/outside review ยังไม่ครบ

ไม่มี denominator ที่ตกลงกันสำหรับคำนวณเปอร์เซ็นต์ RCT-7 สมบูรณ์ จึงใช้ acceptance gates แทนเปอร์เซ็นต์จากจำนวน tests

## ลำดับพัฒนาถัดไป

### A: ปิด public service contract ก่อนเปิด execution
- ทำ request/result/error/receipt schema พร้อม canonical encoding ข้ามภาษา
- persist service profile ID + policy version + actor + workspace + executor binding ใน contract
- เพิ่ม authorized get/confirm endpoint; ปฏิเสธ contract จาก generic routes, actor อื่น, old versions และ policy ที่เพิกถอนสิทธิ์
- คืน plan ก่อนอ่านจริง; confirm ต้องอ้าง version/digest ที่ผู้ใช้เห็น ไม่มี fallback
- เกณฑ์จบ: real HTTP two-phase test อ่านได้เฉพาะไฟล์ของ actor, complete receipts, stale/cross-actor/revoked cases ไม่ dispatch tool

### B: Jobs/recovery
- ออกแบบ job/contract state machine, idempotency key ที่ผูก actor+request hash, lookup/cancel/continuation
- ทดสอบ kill ก่อนอ่าน หลังอ่านก่อน receipt หลัง persist ก่อนตอบ และรอคำตอบ; DB lock/disk full ต้องไม่รายงาน success
- ไม่ replay incomplete operation โดยเดาว่าครั้งก่อนล้มเหลว; มีสถานะ reconciliation-required ที่แสดงผู้ใช้ได้

### C: Desk lifecycle
- แสดง plan, await-confirmation, clarification, differences, receipts และ verifier scope
- จำกัด CORS เฉพาะ origin ที่ operator อนุญาต; public health ไม่ใช่ผล auth success
- แยก token identity, workspace/session, clear stale UI state; reconnect/cancel/restart E2E
- บันทึกวิดีโอจากการคลิกจริงใหม่ แยกจาก Settings/Memory demo เดิม

### D: Host + capability (ทำคู่กับ A–C ได้)
- ตรวจ storage/model cache/container ปัจจุบันก่อน pull, TLS/digest/inference และ 9 model integration cases
- แก้ native DNS โดยไม่ลด SSRF/DNS-pinning; ยืนยัน browser sandbox runner อีกครั้งหลัง restore
- pin model/settings/code/schema/policy; raw Thai/English holdout outcomes, false acceptance, p50/p95 latency, RAM/disk และ infrastructure failure labels
- เปรียบเทียบ baseline/new planner ด้วยข้อมูลเดียวกัน ห้ามสรุป causal gain จาก scheduler order stress test เดิม

### E: Write workflow และ operational pilot
- เลือก workflow เดียว ผูก signature กับ contract/version/plan/action/policy/actor/workspace/nonce/expiry
- crash ก่อน dispatch, หลัง effect ก่อน persist, หลัง persist ก่อน acknowledge ต้อง reconcile ปลายทางได้
- clean install/upgrade/rollback, off-host restore จริง, independent witness, notary แยก user, load/limits, soak 72h และ outside review

สถานะ: runtime ทดลองที่มีตัวตรวจเฉพาะงานและ execution framework จริง เพิ่ม API boundary สำหรับการวางแผนแบบจำกัดสิทธิ์แล้ว แต่ยังไม่ใช่บริการ read-only end-to-end ที่ครบ lifecycle และยังไม่รับรอง autonomous RCT-7 หรือ production/pilot readiness
