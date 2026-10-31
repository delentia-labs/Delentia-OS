# RCT-7: historical verification และ clarification checkpoint

วันที่ 30 ตุลาคม 2026 (Asia/Bangkok) — เป้าหมายคือ open-source ที่ผู้ใช้ติดตั้งบนเครื่องหรือ VPS ของตนเอง ไม่มี paid API ในรอบนี้

## ผลล่าสุดและสถานะส่งมอบ

- **Full suite ของ 509aa705: 9,184 passed / 12 failed / 55 skipped / 1 xfailed, 961.98 วินาที**
- 12 failures: 9 missing Ollama model, 1 native DNS, 2 regex timing assertions ภายใต้ concurrent load (หนึ่งกรณีเป็น ratio ของ regex เก่าที่ใช้เป็น negative control อีกกรณีเกิน wall-clock 0.5 วินาที) ไม่แก้ตัวเลข threshold เพื่อให้ผ่าน
- Supplemental หลัง full suite: **52 passed / 0 failed / 0 skipped, 117.01 วินาที** ครอบคลุม PostgreSQL 7 tests ที่ระบุ DSN แล้ว, regex timing ทั้งสองไฟล์ และ browser-act ทั้งไฟล์ รวมสามกรณีที่ start browser ไม่สำเร็จใน full suite
- Parser regression และ fake-jury control ผ่านใน full suite ล่าสุด แต่ intermittent ReadError ของ fake-jury และ timing/browser sensitivity ต่อ concurrent load ยังต้องติดตาม ผล supplemental ไม่ลบ failures/skips จาก full suite
- **PR #218** เป็น draft ของ combined 509aa705 ไป main เพื่อรัน full CI; PR #215 ยังคงเป็น focused implementation review ที่ซ้อนบน #212
- main ล่าสุดที่ตรวจคือ **f3114596**: #213 และ #214 merge แล้ว; prospective merge กับ combined ให้ Git tree **0900f4c344716490ddefc725e0c45a7da51bac1e** เหมือนเดิมทุกไฟล์ จึงมีโค้ดของ main ล่าสุดในชุดที่ทดสอบแล้ว ไม่มีการ merge PR โดย Codex
- Claude เปิด #216 (W08/W10) และ #217 (Thai Desk/Delta log); ยังไม่รวมใน combined นี้ ไม่ได้แก้ไฟล์ทับงานสองชุดนั้น
- CI snapshot ของ #218: Lint & Type Check, Frontend (Node.js), Build/install/check/uninstall, CVE Scan (safety), Analyze(actions) ผ่าน; Python matrix และหลาย checks ยัง queued/in progress ไม่เรียกว่า CI ผ่านครบ และ CodeQL neutral ไม่แทน Analyze ทุกภาษา
- ไม่มี paid API หรือ GUI lifecycle video ใหม่ในรอบนี้; ผล local ไม่ใช่ตัวเลข checkpoint ทางการของ main


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

## Budget guard: ผลตรวจซ้ำบน combined 8b5abfb6

ใช้ `budget_followup_probe.py` กับ fake provider เท่านั้น ผลยังตรงกับ finding ที่ส่งไปแล้ว:

- `research/daaes/budget_guard.py` บริเวณ constructor ของ ExperimentLedger (บรรทัด 98–101): policy ที่สร้างโดยตรงไม่ได้ผ่าน validate เสมอไป เมื่อ USD fields เป็น NaN, before_call ยังรับ reservation 0.0000002 USD ได้
- บริเวณ `_before_call` (บรรทัด 215–223): cap input/output = 1 แต่สอง calls ที่อยู่ระหว่างทำงาน dispatch ได้ทั้งคู่ ก่อน settlement แรก ผลรวมทั้งสองฝั่งจบที่ 2 tokens
- Positive controls: max calls = 1 ปฏิเสธ call ที่สอง; negative/NaN price ถูกปฏิเสธ
- ไม่ได้กล่าวว่า positive USD reservation ทุกกรณีเสีย และไม่ได้เรียก provider จริง

เกณฑ์ปิด: validate ที่ public entry point และตอนโหลด durable policy, reserve tokens ของ in-flight/uncertain calls, settlement ไม่ปล่อย reservation ซ้ำ, restart ไม่ลืมรายการ uncertain; ต้องมี concurrency/crash/negative tests ในเลน Claude ก่อนใช้เงินจริง

## ขอบเขต configuration freeze

ยังไม่มี model/provider/routing และวงเงินที่อนุมัติ จึงยัง freeze การทดลองแบบ paid ไม่ได้ `research/daaes/run_manifest.py` เป็นหลักฐานบันทึกเงื่อนไข ไม่ใช่ spending authorization และการ validate field presence ไม่แทน budget enforcement

ใช้ manifest/ledger/harness เดิมร่วมกับ Claude เพิ่มข้อมูลที่จำเป็น ได้แก่ full commit SHA, role ทั้ง main/judge/critic/children, model revision ที่ provider รายงาน, temperature/seed/token limit, prompt/schema/policy hashes, retries/fallback, development/holdout split ที่ล็อกก่อน tuning, budget ต่อ run/ทั้งรอบ และ provider-side cap หาก provider ไม่เปิดเผย model revision ต้องบันทึกข้อจำกัดนั้น

Free rehearsal ต้องทดสอบเส้นทางที่เปิดจริงทุก role ผ่าน fake endpoint และเทียบจำนวน dispatch/usage/reservation/settlement หลัง timeout หรือ restart กับ ledger ก่อน paid canary จาก installation จริง

## Finding เพิ่มเติมจาก full suite: command substitution scanner

full suite บน 8b5abfb6 พบ `test_adversarial_inputs_stay_fast[substitutions-tick]` ล้ม การตรวจโค้ดพบ `command.find("$(", pos)` ค้น suffix เดิมซ้ำหลัง backtick แต่ละคู่ เป็นงานค้นหาที่โตแบบ quadratic เมื่อไม่พบ dollar opener หรือ opener อยู่ท้ายข้อความ

แก้ใน `4bbe5d09`: จำ dollar opener ถัดไปและจำผลว่าไม่มี opener แทนการค้นซ้ำ เมื่อ cursor ผ่าน opener จึงค้นใหม่ รักษาผล parser เดิม ชุด safe_text 19 tests ผ่าน รวม randomized equivalence กับ regex เดิมและสอง deterministic search-work bounds ใหม่

input 6,000 ตัวอักษรเคยทำงานค้นหา suffix รวม 6,003,000 ตัวอักษร เกิน bound 12,000 ที่ regression กำหนด การวัดครั้งเดียวระหว่าง host ยังรัน suite: 60,001/120,001/240,001 ตัวอักษร ก่อนแก้ 0.995/3.721/15.118 วินาที หลังแก้ 0.038/0.078/0.159 วินาที ตัวเลขนี้ไม่ใช่ benchmark ทั้งระบบหรือผลโมเดล และมี load อื่นร่วมอยู่

Ruff และ Linux Mypy ผ่านหลังแก้ ไม่แตะ plan approval hooks, JobService, research หรือ Desk ของ Claude

## Installed package และผล failure ที่ต้องติดตาม

combined 509aa705 สร้าง wheel ใหม่ SHA-256 `ef166827277d181078b4e9d5650d3ec9ca40d8e874f08fb850fde7e53c480b70` มีฟอนต์ woff2 17 ไฟล์ ตรวจ hashes ของ component_execution, verified_budget, budget_execution, intent_contract และ safe_text ตรงกันทั้ง source/wheel/installed site-packages

ติดตั้งทับ wheel เดิมใน virtualenv ที่แยกไว้แล้ว; pip check ผ่าน (ไม่ใช่หลักฐาน fresh OS install ใหม่) HTTP workflow ผ่าน plan-before-execute, confirmation, arithmetic, reopen app/status, anonymous refusal, missing-receipt refusal และ installed pure-criterion rejection การ reopen นี้ไม่ใช่ OS kill/restart test และไม่มี capable model

Full suite แรก 8b5abfb6: 9,185 passed / 12 failed / 52 skipped / 1 xfailed ใน 907.46 วินาที 12 failures คือโมเดล 9, native DNS 1, safe_text 1, fake-jury 1 ไม่แทนผล revision 509aa705

fake-jury control คาด accuracy 0.5 แต่ได้ 0.467 โดย unsafe_passed ยังตรง expected 15 (เป็น negative control ที่จงใจให้ scripted jurors ตอบผิด ไม่ใช่โมเดลจริง) รันแยกทั้งไฟล์ผ่าน 8 tests; diagnostic fake-only 10 รอบได้ผลตาม expected ทุกครั้ง แต่พบ voter ReadError รวม 3 ครั้งซึ่งถูกนับเป็น abstain ข้อมูลนี้แสดงว่าทางเชื่อมต่อ fixture ยังมีความไม่แน่นอน แต่ยังไม่พิสูจน์ root cause ของ failure แรก ต้องเก็บไว้เป็น unresolved intermittent finding ไม่ใช้ rerun ผ่านลบผลเดิม

52 skips ของ suite แรกมี 7 PostgreSQL tests เพราะไม่ได้ตั้ง DELENTIA_TEST_PG_DSN ใน invocation นั้น ต้องตรวจเพิ่มโดยระบุ DSN ของฐานข้อมูลทดสอบ ไม่อ้างว่า container running เท่ากับ tests ผ่าน ที่เหลือส่วนใหญ่เป็น paid/live services, optional voice/video/weights, Windows-only และ Hermes ที่ไม่ได้ติดตั้ง

## รายละเอียดรอบพัฒนาถัดไปของ RCT-7

| รอบ | ขอบเขต implementation ที่เสนอ | Negative tests / เกณฑ์จบ |
| --- | --- | --- |
| R1 evidence assessment | Schema แยก observed bytes/hash, claimed facts, observed_at, claimed source date, source identity และ freshness policy; ระบุสถานะ unknown/stale/conflicting อย่างตรงไปตรงมา | ไม่มี source date ต้องไม่ถูกจัดว่า fresh; วันที่อนาคต/clock skew ต้องมี policy; สองแหล่งขัดกันต้องถามหรือแสดง conflict; hash ตรงไม่ลบ conflict |
| R2 intent evaluation | ใช้ planner เดิมและชุด holdout ไทย/อังกฤษที่ล็อกก่อน tuning เพิ่ม labels สำหรับ negation, ambiguity, multi-intent และคำตอบที่ต้องถาม | รายงาน task quality และ process quality แยกกัน; ไม่ให้ clarification ทุกครั้งเป็นทางลัดทำคะแนน; แยก infrastructure errors จาก model errors |
| R3/R4 semantic coverage | ระบุ domain handler/verifier ที่รองรับและเส้นทางย้อนจาก material criterion → necessary inputs → handler → receipt → verifier | ปฏิเสธ criterion ที่ไม่มี semantic verifier; DAG สมบูรณ์แต่ไม่ครอบคลุมเจตนาต้องไม่ผ่าน; unsupported domain ต้องแสดงขอบเขต |
| R5 versioned correction | ออกแบบ transition สำหรับ correction จากสถานะที่อนุญาต ระบุ downstream invalidation และ approval ที่ต้องขอใหม่ตาม binding | stale actor/version, เปลี่ยนข้อมูลขณะ running, dependent result เก่า, restart ระหว่าง invalidation; write effect ต้อง reconcile ไม่ replay |
| R6 Desk lifecycle | Claude ต่อ UI กับ schema backend ที่ตกลงร่วมกัน แล้วเลือก combined SHA เดียว | identity change, reconnect, cancel, restart, clarification และ receipts ผ่าน E2E พร้อมวิดีโอจริง ไม่ใช้ HTTP-only probe แทน |
| R7 domain verifier ถัดไป | เลือก domain เดียวก่อน เช่น ใบเสนอราคาที่มีภาษี/ส่วนลดและเงื่อนไข กำหนด ground truth/oracle และหน่วย/สกุลเงิน/rounding | ข้อมูลขาด, tax รวม/ไม่รวม, currency mismatch, contradictory total และหลักฐาน stale ต้องไม่ถูกยอมรับเงียบ ๆ |

ต้องแยก task completion จาก business outcome เสมอ: งาน “เปรียบเทียบงบ” สามารถทำสำเร็จโดยได้คำตอบว่าเกินงบ แต่คำว่า verified ต้องระบุว่าตรวจ arithmetic/criteria ใด ไม่สื่อว่าซื้อได้หรือข้อมูลผู้ขายจริงทั้งหมด

การรวมงาน: Codex รับ backend/contracts/verifiers และ tests; Claude รับ research budget/evaluation กับ Desk/local first-run; shared API/event schema ต้องตกลงก่อนเปลี่ยน และยังไม่แตะ plan approval hooks หรือ JobService semantics โดยไม่มีการประสาน
