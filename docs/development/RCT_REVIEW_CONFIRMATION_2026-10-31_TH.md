# Typed intent review/confirmation และทางไป self-install preview

วันที่ 31 ตุลาคม 2026 — เป้าหมายยังเป็น open-source ติดตั้งบนเครื่องหรือ VPS ของผู้ใช้

## Revision และขอบเขต

Implementation 5d90b8c3, combined revision 11e65b9f รวม necessary-condition validation รอบก่อนด้วย
main ที่ตรวจคือ 1ccc1c7c; Claude PR #217/#219/#220 ยังมี SHA เดิมที่ตรวจรอบก่อน
ไม่แก้ research, Desk, plan approval hooks, JobService API หรือ resume semantics

## สิ่งที่พัฒนา

เพิ่ม intent_review.py และ optional keyword ใน IntentContractStore.create/claim เดิม
Review snapshot อยู่ใน plan จึงรวมใน plan digest และ persistence ที่มีอยู่
ผูก proposal กับ goal quotes, criterion IDs, actor/namespace และ workspace
ผูกคำยืนยันกับ contract ID, version, plan digest และเทียบ current binding ของ application
กับ actor/workspace/policy/catalog digest ที่บันทึกไว้ ไม่สร้าง lifecycle หรือ store อีกชุด

ก่อนเปลี่ยนเป็น running ต้องยืนยันครบ การเปลี่ยน policy/catalog หรือไม่ส่ง binding ถูกปฏิเสธ
CAS เดิมรับประกันว่าการยืนยันพร้อมกันสองครั้งมีผู้ชนะเพียงหนึ่งครั้ง
คำยืนยันเก่าใช้กับ plan/version/contract อื่นไม่ได้
การแก้โจทย์ของ typed-review contract ต้องสร้าง reviewed contract ใหม่ในระยะนี้
จึงไม่ปล่อย replan ลบ review requirement แล้วอาศัย approval เดิม

## ข้อจำกัดสำคัญ

นี่เป็น backend gate แบบ opt-in ยังไม่มี HTTP/Desk route สำหรับ typed intent ใหม่
current binding ต้องมาจาก service ที่ authenticate และตรวจสิทธิ์ปัจจุบันเอง
ห้ามนำ binding ที่ request ส่งมาใช้เป็นหลักฐาน authorization
ไม่มีการตรวจสิทธิ์ภายนอกใน module นี้ จึงไม่อ้างว่า HTTP revocation flow ใหม่เสร็จแล้ว
การเทียบ criterion IDs ไม่พิสูจน์ว่าข้อความเจตนากับ legacy verifier มีความหมายตรงกัน
ต้องมี reviewed capability mapping และ semantic oracle ก่อนเปิด general task execution
unknowns ต้อง resolve ก่อนแนบ review ในเวอร์ชันนี้ ยังไม่มี selective invalidation ทั่วไป
catalog digest เป็น caller-supplied binding ยังไม่มี versioned catalog deployment pipeline

## การตรวจสอบ

- Source regression: 201 passed, 220 warnings, 4.51 วินาที
- Combined regression: 312 passed, 244 warnings, 27.52 วินาที
- สองชุดซ้อนกัน ไม่บวกเป็นยอดรวม; tests ใหม่ของ review gate 21 กรณี
- Ruff ผ่าน; Linux Mypy ผ่าน 282 source files (ยังมีข้อจำกัด untyped function bodies)
- ทดสอบ SQLite reopen, snapshot mutation, wrong actor/root/policy/catalog,
  missing confirmation, stale version/digest, boolean schema/version, concurrent claim,
  replan bypass, existing read-only service, Desk events, jobs และ idempotency
- โมเดลจริง, paid dispatch และ GUI video ไม่ได้รัน

## CI ที่ตรวจ

Package check run 41164750645 ของ 169d9541 ยัง queued
Jobs 124429791380 และ 124429791505 ไม่มี runner_name ขณะตรวจ
หลักฐานนี้บอกว่ายังไม่เริ่มบน runner ไม่พิสูจน์สาเหตุว่า billing/quota/approval เป็นปัญหา
ต้องตรวจ CI ของ SHA ใหม่หลัง push และ review ก่อน merge

## Budget findings สำหรับประสาน Claude

ทำซ้ำบน combined 11e65b9f โดย fake provider ไม่มี network dispatch:

- research/daaes/budget_guard.py:99 constructor ไม่ validate policy;
  policy ที่ USD fields เป็น NaN ยังผ่าน before_call
- บรรทัด 215 ตรวจเฉพาะ settled input/output tokens ไม่มี reservation ของ in-flight tokens;
  cap input/output อย่างละ 1 แต่สอง concurrent calls dispatch และ settle อย่างละ 2 tokens
- Positive controls: call-count cap 1 ปฏิเสธคำขอที่สอง; negative/NaN prices ถูกปฏิเสธ

วิธีทำซ้ำจาก repo root:

```bash
PYTHONPATH=. python docs/development/rct-verification-20261030/budget_followup_probe.py
```

ต้องใช้ dependency environment ของ repo; เรียก script โดยไม่มี repo root ใน import path
จะเกิด ModuleNotFoundError ก่อน probe ทำงาน ไม่ใช่หลักฐาน budget behavior
ข้อเสนอ: validate policy ทุก public entry, reserve tokens แบบ per-call identity,
settle/reconcile แบบ idempotent, เก็บ uncertain reservations และพิสูจน์ crash/restart
ยังไม่แก้ไฟล์เลน Claude ในรอบนี้

## ลำดับถัดไปพร้อมเกณฑ์จบ

1. ปิด review/CI ของ combined revision ก่อนเพิ่ม surface ใหม่
2. เชื่อม authenticated typed-review service: status/review/confirm โดย current binding มาจาก
   server policy; negative HTTP tests cross-user, revoked access, stale plan/catalog/version
3. สร้าง catalog version และ reviewed mapping จาก intent ไป semantic verifiers สำหรับ
   summary+citation, document comparison, table analysis; unsupported ต้องไม่มี fallback
4. เพิ่ม source/cardinality/conflict checks พร้อม oracle; receipt/hash ยังไม่ใช่ truth
5. Selective invalidation ต้องผูก plan/input revisions, transitive dependencies และ approval;
   unknown effects ต้อง reconcile ก่อน replay ไม่ใช้ pure graph helper แทน durable recovery
6. แยก development/holdout ก่อน tuning; pin model/digest/settings/prompts/policy/roles;
   วัด task correctness/completion, false acceptance, clarification, latency และ cost
7. ปิด budget/freeze findings และ fake billing rehearsal ก่อนกำหนดวงเงินจริง/paid canary
8. Desk lifecycle E2E บน revision เดียวกันพร้อม native first-run, restart, update/rollback,
   uninstall, keys/cost/privacy และวิดีโอ ก่อนชวนผู้ใช้ self-install preview

สถานะยังเป็น experimental local-first runtime ไม่ใช่ general autonomous agent ที่รับงานทุกชนิด

## Freeze review เพิ่มเติม

อ่าน PR #219 SHA 4c89d37a อีกครั้ง: research/paid_run_freeze.py:208–219 ยัง return []
เมื่อ base URL เป็น loopback และ force=False โดยไม่ตรวจ freeze file
loopback อาจเป็น gateway ที่ forward ไป paid provider จึงใช้ URL อย่างเดียวรับรองว่าไม่มีค่าใช้จ่ายไม่ได้
ข้อเสนอคือ require freeze เป็น default รวม local gateway และให้ fake-only harness
มีการยืนยันชนิด provider/egress isolation ชัดเจน แทนการ exempt ด้วย hostname
นี่เป็น static review ของเส้นทางเดิม ไม่ได้ทดลองเรียก provider จริงหรืออ้างว่ามีค่าใช้จ่ายเกิดขึ้น

## Full suite ของ combined 11e65b9f

รันจริงด้วย pytest -n 3 --dist loadfile --timeout=600:
**9,262 passed / 13 failed / 68 skipped / 1 xfailed**, 9,239 warnings, 612.93 วินาที
ผลนี้เป็น local evidence ไม่ใช่ตัวเลขประชาสัมพันธ์จาก CI ของ main
รายการ failure IDs และ SHA256 ของ raw XML/log อยู่ใน intent-review-full-summary.json

13 failures แบ่งเป็น:

- 9 model-backed tests: Ollama ไม่รับการเชื่อมต่อขณะ full suite (ConnectError รวม tool wrapper)
- 3 TC-027 browser workflows: events ระบุ browser did not start; ไม่มี price reads
- 1 real URL crawler: result ไม่มี status_code; native DNS example.com ล้มเหลว

ตรวจ browser เพิ่มพบ activation ไม่ได้ตั้ง DELENTIA_BROWSER_PATH จึงเลือก /usr/bin/chromium
runner เดิม /workspace/.delentia-cloud/chromium-container เปิด sandbox และ dump about:blank ได้
เพิ่ม export ให้ task-local activation ใช้ runner นี้แล้ว โดยไม่ใช้ --no-sandbox และไม่ปิด URL fences
การเปลี่ยน activation เป็น host-only configuration ไม่ใช่ portable product change

เริ่ม task-owned Ollama/PostgreSQL containers เดิมที่ stopped หลัง full suite จบ
Ollama ตอบ api/tags แต่ models=[] จึงยังทำ inference ไม่ได้ ไม่เริ่ม pull หรือดาวน์โหลดใหม่
PostgreSQL supplemental audit-chain tests ผ่าน 7 กรณีใน 0.94 วินาที

Skips สำคัญใน full suite: browser startup 16, PostgreSQL DSN 7, paid live 9,
Hermes 10 รวม optional audio/media/Windows/live-service/weights ที่ไม่มีใน host นี้
skips ไม่ใช่ passes และ supplemental runs ไม่ลบ failure/skip ของ full suite เดิม

หลังแก้ host activation: browser supplemental **72 passed, 34 warnings, 176.02 วินาที**
รวม TC-027 ทั้ง 5 กรณี, browser act และ browser governance tests ไม่มี skip ในชุดนี้
crawler probe ยืนยัน error: refused: example.com does not resolve, refused_by=url_safety
จึงต้องแก้ native resolver/egress โดยรักษา SSRF/DNS-pinning ก่อนรัน crawler integration ใหม่
Strict MkDocs ผ่านหลังบันทึกรายงาน; ไม่มี paid calls, ไม่มี merge เข้า main หรือ release
