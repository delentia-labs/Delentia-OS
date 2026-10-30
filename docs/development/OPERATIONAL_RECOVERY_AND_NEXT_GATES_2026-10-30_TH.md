# Job operational recovery และเกณฑ์ก่อน paid evaluation — 2026-10-30

## ขอบเขตรอบนี้

ต่อจาก PR #207 checkpoint `d9962cd3` บน branch `codex/job-operational-recovery-20261030` พัฒนา clock fencing, SQLite failure handling, upgrade/drain preflight และ functional capacity/cancel tests ไม่แก้ research/Desk, episode journal, resume หรือ idempotency ของ Claude ไม่เปิด paid API หรือ write workflow เพิ่ม

Code checkpoint คือ `ad70eea1` ผล full suite และ file hashes จะบันทึกใน evidence ประกอบเมื่อรันเสร็จ ตัวเลข local/cloud ไม่ใช่ public checkpoint ของ main

## Clock policy ที่เพิ่ม

- worker ปกติเทียบ wall clock กับ monotonic elapsed time หากต่างเกิน 2 วินาที หรือเวลาเป็น NaN/infinite ให้ fail closed ด้วย persistence-unavailable error
- fault ค้างตลอดอายุ worker แม้นาฬิกากลับมาปกติ ต้องหยุด worker ตรวจ host clock แล้วเริ่มใหม่ ไม่ปรับเวลาหรือฟื้น lease ให้เอง
- เก็บ `heartbeat_wall` คู่กับ lease renewal; observer ใหม่ที่พบ heartbeat อยู่ในอนาคตเกิน tolerance จะ interrupt งานเก่าและบันทึก audit พร้อม state ไม่ replay
- ตรวจ clock ผ่าน guard ของ contract receipt ด้วย จึงไม่เพียงป้องกัน job status สุดท้าย งานที่อ่านหลักฐานแล้วแต่ clock ผิดปกติไม่สามารถ commit receipt ต่อ
- API ของ worker ที่ clock fault ตอบ 503 ไม่รายงาน task success เมื่อ observer ใหม่กลับมาอ่านได้ต้องตรวจ durable state/receipts ต่อ
- injected wall clocks ใน tests ตรวจการถอยหลังเสมอ ถ้าต้องทดสอบ drift ให้ inject monotonic คู่กัน production defaults ตรวจทั้งสอง clock

นี่เป็นนโยบายตรวจ clock ของ worker ไม่ใช่ independent timestamp/witness ไม่แก้ปัญหา clock skew ของหลาย host; SQLite deployment นี้ไม่รับรอง distributed execution หลายเครื่อง Tolerance 2 วินาทีเป็นขอบเขต engineering ที่ต้องวัดบน target host ก่อน pilot

## DB/storage failures

JobService หยุด local runner หากบันทึก state/audit ไม่สำเร็จ ไม่คาดเดาสถานะ success และไม่ส่ง `on_done` สำหรับ completion ที่ commit ไม่สำเร็จ หาก DB ใช้ไม่ได้แม้ตอนบันทึก cancelled/failed จะเก็บ error ใน server log และทิ้ง durable projection ไว้จน healthy observer ตรวจ lease แล้ว interrupt

ตัวอย่าง crash window: runner คืนคำตอบแล้ว แต่ UPDATE answer เจอ SQLITE_FULL → answer/state/audit transaction rollback → job อาจยังแสดง running/pending ชั่วคราว → owner ไม่ heartbeat ต่อ → เมื่อ DB กลับมาและ lease หมด observer บันทึก interrupted ไม่ replay และไม่ประกาศว่าเคยสำเร็จ

readonly lifespan พยายาม persist cancel ตามเดิม ถ้าทำไม่ได้ยัง cancel local task เพื่อปิด service ได้ วิธีนี้หยุด thread/external effect ที่เริ่มไปแล้วไม่ได้ Callback delivery ยังคง best-effort; ไม่ใช่ transactional outbox หรือ exactly-once delivery

Tests ใช้ write lock จาก SQLite อีก connection และ real SQLITE_FULL จาก `PRAGMA max_page_count` ไม่ได้เติมดิสก์ cloud จริง การทดสอบนี้ยังไม่แทน kernel ENOSPC, filesystem I/O failure, corruption หรือ target-host load benchmark

## Upgrade/drain ขั้นตอนที่ตรวจได้

1. ปิด admission และหยุด/disable service managers ของ worker รุ่นเก่า อย่าปล่อยให้ restart รุ่นเก่าได้ระหว่าง deploy
2. รอ terminal หรือขอ cancel งานที่ยังมี owner เก็บสถานะและ receipts ของ interrupted/unknown outcomes; ห้าม reset/replay โดยเดา
3. หลังหยุด worker เก่า ใช้ artifact ของ revision ใหม่ตรวจ snapshot แบบ read-only:

```bash
python -m rct_control_plane.job_preflight --database /path/to/agentic.db --require-drained
```

4. Exit 0 หมายถึง snapshot นี้ไม่มี live jobs/unknown statuses และ quick_check ผ่าน; exit 1 หมายถึงยังไม่ drained/ไม่ผ่าน; exit 2 หมายถึง inspect ไม่ได้ ไม่มีการ migrate หรือสร้าง DB จากคำสั่งนี้
5. backup และตรวจ restore ตามขั้นตอน operator แล้วเริ่มรุ่นใหม่ runtime จะปฏิเสธ startup หากพบ live owner ที่ยังไม่มี heartbeat field ของ clock fencing ไม่เปลี่ยนผลของงานเก่าให้เอง
6. ตรวจ health/auth/status/receipts แล้ว smoke workflow ใหม่ก่อนเปิด admission อีกครั้ง

Preflight ไม่ล็อก admission ระยะยาว worker เก่าที่ไม่รู้จัก protocol สามารถเริ่มงานหลัง snapshot ได้ จึงต้องหยุด/disable ก่อนตรวจจริง Startup guard ไม่ใช่เครื่องมือ kill/drain process อัตโนมัติ และไม่ได้รับรอง rolling upgrade ระหว่าง worker รุ่นเก่ากับใหม่

รายงานเป็น aggregate counts ไม่มี goal/answer/actor names บอกจำนวน request mappings/job mappings/owner rows ที่มี แต่ `retention_policy_verified=false` เสมอ การนับแถวไม่พิสูจน์ว่า erasure สมบูรณ์

## Retention/erasure ที่ยังต้องปิด

| ข้อมูล | พฤติกรรมที่มี | งานที่ยังต้องตัดสิน/พิสูจน์ |
| --- | --- | --- |
| request keys/tombstones | คง hashed identity/key linkage เพื่อไม่คืน authority ของ request ที่ erased | กำหนด retry horizon และ epoch/version ก่อนทำ TTL; ห้ามลบทิ้งจน request เก่ากลายเป็นงานใหม่ได้ |
| contract payload | erasure scrub payload และเพิ่ม version เพื่อปฏิเสธ continuation เก่า | race tests ระหว่าง erasure กับงานทุกประเภท โดยเฉพาะ generic jobs ที่ไม่ได้ใช้ contract |
| job goal/answer และ mappings | มี namespaced scrub บางส่วน; metadata mappings/owners ยังอยู่ | กำหนดอายุ, export/access, legal/operational reason และผลต่อ pending jobs/notifications |
| audits | ต้องคง chain continuity; ข้อความบางส่วนใช้ per-person encryption | ตรวจ inventory, key destruction และ legacy plaintext บนข้อมูลจริง |
| old backups | อาจมี ciphertext/key/text ก่อน erasure | off-host restore พร้อม erasure reconciliation และ operator procedure ที่ทดลองจริง |

รอบนี้ไม่เพิ่ม automatic deletion และไม่กำหนด retention อายุแทน Architect ก่อนมี policy ที่อนุมัติ ให้ใช้ isolated synthetic fixtures สำหรับ model research และห้ามใช้ metadata counts อ้างว่า personal data ถูกลบทั้งหมดแล้ว ก่อน erasure/upgrade บน host ควร drain งานที่เกี่ยวข้องและตรวจ state จริง

## Paid evaluation: สิ่งที่ทำได้และ blockers

เลือก W03 เป็น candidate สำหรับ **canary plumbing แรก**: ให้โมเดลอ่าน simulated product page สองรอบที่ราคาเปลี่ยน ตรวจ source citation, freshness และ unauthorized outbound attempts ด้วย whole-workflow oracle เดิม ใช้ RecordingWorld จึงไม่พึ่ง native DNS ของ cloud และไม่มีข้อมูลผู้ใช้จริง วิธีนี้วัดการทำงานของโมเดลบน controlled world ไม่ใช่ real-web deployment หรือ semantic RCT-7 ครบทุก domain

Manifest draft อยู่ที่ `evidence/FIRST_MODEL_CANARY_DRAFT_2026-10-30.json` ยังห้าม dispatch paid call จน model/provider/pricing/budget/roles และ exact configuration ผ่าน review/fake rehearsal ครบ การเลือก W03 ไม่เปลี่ยนเกณฑ์ capability/holdout เดิม

ส่ง findings budget guard ให้ Claude แล้ว: https://github.com/delentia-labs/Delentia-OS/pull/206#issuecomment-6515998534

- negative/NaN prices admitted ต้องตรวจ finite/nonnegative ก่อน dispatch/persist
- in-flight calls ไม่ถูกนับใน call cap ต้อง atomic reserve call/token slots และ settle-once รวม uncertain calls หลัง crash
- W12 children ต้องคิดงบแยก process ครบ parent meter เพียงตัวเดียวไม่เห็นค่าใช้จ่ายทั้งหมด

ยังไม่แก้ research code ของ Claude, ยังไม่ถือว่าปิดสอง findings และไม่เพิ่ม default models/keys/budget การตั้ง default USD ใน code หรือ dry-run estimate ไม่ใช่ authorization

Claude มี PR #209 สำหรับ holdout set 4: 60 requests และ labeling/runner hooks ตาม PR description ยังไม่มี real-model run ใน PR นั้น รอบนี้อ่านเฉพาะ metadata ไม่เปิด sealed gold labels ต้องให้ Architect label/seal และ pin final combined code/prompt/protocol ก่อน holdout

## แผนส่งต่อและเกณฑ์จบ

| ลำดับ | งาน | ผู้รับผิดชอบ/เกณฑ์จบ |
| --- | --- | --- |
| 1 | ปิด budget guard findings | Claude; invalid inputs/concurrent/timeout/crash/restart tests และ fake endpoint counter ตรง ledger |
| 2 | ปิด combined revision | Codex + review โดย Architect; #202/#203/#205 CI ผ่านแล้ว ณ เวลาตรวจ แต่ #204/#207/PR นี้ต้อง retarget main และ push validation commit หลัง dependencies merge |
| 3 | Freeze canary manifest | Codex/Claude/Architect; SHA/model/provider/routing/settings/prompts/policy/schema/prices/caps/roles ระบุครบ |
| 4 | Free rehearsal exact configuration | Claude research lane; ทุก call path ถูก guard, raw outcomes/config hashes พร้อม; ไม่อ่าน holdout gold ระหว่าง tuning |
| 5 | Paid canary | หลัง Architect กำหนดวงเงินจริง; ทีละ run เทียบ provider billing กับ ledger และเก็บ unknown/reserved outcomes |
| 6 | Capability + holdout/A-B | แยก task correctness/false acceptance จาก clarification/confirmation/recovery; latency/cost/infra failures พร้อม denominators |
| 7 | Desk E2E/video | Claude/local; แก้ GUI axe step failure จาก artifact แล้วทดสอบไทย/อังกฤษ/identity/reconnect/cancel/restart บน combined SHA |
| 8 | External pilot | target-host load/clock/DB/upgrade drills, retention policy, off-host restore, scheduled independent witness, notary แยก user, soak 72h และ outside review |

ยังไม่เปิด generic write workflow และไม่รับรอง production/autonomous general RCT-7 สิ่งที่พิสูจน์รอบนี้คือ clock/DB failure behavior ของ background runtime ภายใต้ scenarios ที่ระบุ
