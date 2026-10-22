# ผลพัฒนา RCT-7: criterion-derived plans, receipts และ dependency patches

22 ตุลาคม 2026 — branch `codex/rct-derived-planning-and-receipts-20261022`, base `13c4860eb9672cc170ddc85758253f5872b74470`. อ่านคู่กับ [แผนงานถัดไป](RCT_COMPLETION_NEXT_GATES_TH.md) และ [รายละเอียดการใช้งาน](../concepts/rct-derived-plans.md).

## สถานะที่ยืนยันได้

Delentia เป็นระบบทดลองที่รันโค้ด เครื่องมืออ่านไฟล์ governance และ persistence ได้จริง มีเส้นทาง RCT-7 ที่ตรวจสอบพฤติกรรมได้บางส่วน รอบนี้เพิ่มการสร้างแผนจากเกณฑ์ผลลัพธ์โดยระบบเอง แก้ receipt race และอัปเดต dependency ที่มีแพตช์แล้ว แต่ **ยังไม่ใช่ semantic RCT-7 สมบูรณ์ ไม่ครบทุก entry point และยังไม่พร้อมประกาศ production/pilot**

เอกสารสถาปัตยกรรมเป็นเป้าหมายและแหล่งอ้างอิง ไม่ใช่หลักฐานว่าทุกส่วนถูก implement แล้ว รอบนี้อ้างสิ่งที่ตรวจจาก runtime/tests ไม่ตีความข้อความในไฟล์แนบเป็นคำสั่งให้ deploy/เผยแพร่หรือใช้ paid API คำสั่งของผู้ใช้ให้แก้โค้ดและ push บน branch Codex เป็นขอบเขตการทำงาน ไม่มี paid API ในรอบนี้

## สิ่งที่เปลี่ยน

### 1. สร้างแผนจาก acceptance criteria

เพิ่ม `derived_plan.py` และ CLI `--derive-plan`; HTTP ใช้ `planning_context: {"derive_from_criteria": true}` ระบบสร้าง reported goal, source reference ของแต่ละ criterion, preparation/check components และ dependency links เอง ไม่ต้องให้ผู้ใช้เขียน graph ทั้งหมด ไม่เรียกโมเดลตอนสร้างแผน

รองรับเฉพาะ predicates เดิม: contains, language th/en, json_object และ file_unchanged แผนมี `planning_origin: criterion_derived`, ruleset และ `semantic_completeness: false` ชัดเจน การเปลี่ยนเกณฑ์ภาษาเป็น JSON เปลี่ยนองค์ประกอบตามเกณฑ์ได้ แต่ยังไม่ใช่การเข้าใจความหมายของโจทย์แล้วแตกงานทุกประเภทเอง

Backward condition รวม transitive prerequisites แล้ว จึงเห็นขั้นเตรียมก่อน comparison ไม่แสดงเพียง node สุดท้าย เก็บ source ว่าข้อมูลมาจากผู้ใช้/criterion ไม่สร้าง observed fact หรือยืนยันว่า source เป็นจริง Unknowns ว่างใน mode นี้หมายถึงยังไม่ค้นหา unknowns อัตโนมัติ ไม่ได้หมายถึงไม่มีข้อมูลขาด

การ revise หลัง mismatch ของ derived contract สร้าง graph ใหม่ตาม goal/criteria ที่ยืนยัน เก็บ original intent และรักษา SHA-256 baseline ของไฟล์ที่ยังอยู่ในเกณฑ์เดิม CLI แสดงแผนก่อนทำงาน ส่วน HTTP คืน plan_ready ก่อนแล้วใช้ continuation อีกคำขอหนึ่ง ไม่เปลี่ยน default agent ให้ใช้ mode นี้โดยอัตโนมัติ

### 2. แก้ concurrent transition receipt

เดิม transition commit แล้ว append audit ก่อนเรียก get() คืนค่า ระหว่างนั้น caller อีกคนอาจ claim แผนต่อเป็น running ได้ ทำให้ caller แรกได้รับ running/version ของคนที่สองแทน receipt ของตัวเอง

แก้ creation/transition ให้คืน frozen payload/state/version ของการเขียนครั้งนั้น โดยยังใช้ compare-and-swap ที่ฐานข้อมูล Caller ที่ถือ receipt เก่าต้องถูกปฏิเสธเมื่อพยายาม claim หลังคนอื่นรับงานแล้ว Tests ใช้ SQLite จริงและแทรกการ claim ของอีก caller ระหว่าง audit เพื่อพิสูจน์ลำดับนี้ ไม่ใช่เพียง assert ว่ามีฟิลด์ version

ยังไม่อ้าง atomicity ระหว่าง state commit กับ audit append: crash/audit failure หลัง commit อาจเหลือ running โดยไม่ส่ง receipt ให้ client และยังห้าม reset/retry ตาม timeout เรื่องนี้ต้องจัดการใน crash reconciliation ก่อนเปิด effects

### 3. Plan digest สำหรับ binding ในอนาคต

เพิ่ม plan_sha256 ของ canonical serialized plan และตรวจตอนอ่าน ถ้า plan bytes เปลี่ยนแต่ digest ไม่ตรงจะปฏิเสธ New transitions เพิ่ม digest ให้ contract เก่าที่ไม่มีฟิลด์นี้ได้ Digest รวม goal/criteria/workspace/baselines/graph ใช้เทียบว่าเป็นแผนเดียวกัน

Hash นี้ไม่ใช่ signature หรือ authorization ไม่ป้องกัน trusted writer ที่เขียนทั้ง hash และ plan ใหม่ ไม่ทำให้เกิด off-host witness และไม่เปิด write tools Contract path ยัง read-only เหมือนเดิม

### 4. ปิด dependency findings ที่มีแพตช์จริง

Registry รอบนี้มี follow-redirects 1.16.1 จึงอัปเดต lockfile ทั้ง GitHub Action และ TypeScript SDK จาก 1.16.0 โดยคง TLS/npm integrity checks และไม่เปลี่ยน package version ranges สร้าง Action dist/index.js ใหม่และ build SDK ใหม่

Action production audit ก่อนแก้มี 2 high; SDK production audit ก่อนแก้มี 1 high หลังแก้ทั้งสองเป็น 0 findings และ GUI production audit รอบนี้เป็น 0 เช่นกัน ผล audit เป็น snapshot ของแต่ละ package/registry ไม่ใช่การรับรองความปลอดภัยทั้งระบบหรือข้อสรุปว่า GitHub default-branch alerts ปิดทั้งหมดแล้ว

Action ยังปิด redirect ที่ call sites และทดสอบ bundled Node process จริงกับ synthetic HTTP backend: approve, reject, score ต่ำ, minimum NaN และ HTTP307 ข้าม origin ผล redirect ไม่มี request/credential ไป destination GitHub-hosted workflow/real API authentication/branch protection ยังไม่ได้ทดสอบในรอบนี้

## ผลทดสอบ

Final full Python: **7,900 passed / 13 failed / 59 skipped / 1 xfailed** ใช้เวลา **781.63 วินาที**; warnings 6,861; runner exit1 เพราะ failures ยังอยู่ Coverage **91.19%** (90553/99303 statements ตาม package roots ที่วัด รวม test modules ไม่ใช่ production-only coverage) ผ่าน floor72% แต่ไม่ได้ทำให้ suite เป็น all-green

Failures ที่เหลือเป็น integration 13กรณี: Ollama9, browser sandbox3 และ DNS/crawl1 preflight รอบนี้ยืนยัน model tags ว่าง, native DNS ล้มเหลว, Chromium sandbox abort; SSH config isolation ผ่าน ไม่มีการแทนโมเดลจริงด้วย fixture ลด sandbox/SSRF/TLS หรือเปลี่ยน failures เป็น skips ต้องแก้ prerequisites และ rerun จริงก่อนปิด failures เหล่านี้

เก็บ [machine-readable result และ hashes ของหลักฐาน](evidence/RCT_DERIVED_PLANNING_2026-10-22.json) พร้อมรายชื่อ failures เพื่อให้ตรวจย้อนกลับได้

ชุดเฉพาะส่วนที่แก้ผ่าน **48 tests** รวม tests ใหม่ 12 กรณีและของเดิม 36 กรณี: predicate-dependent plans/provenance/backward closure, revisions/baselines, creation/transition race receipts, digest mismatch, strict marker 3 variants, API plan-before-model/replay, CLI flags และ maximum criteria graph รวมทั้ง lifecycle/Thai/expansion เดิม จำนวนนี้ซ้อนกับ full suite จึงห้ามนำไปบวกเป็นจำนวน tests ไม่ซ้ำ

Full ครั้งแรกของรอบนี้จบครบที่ 7,898 passed /15 failed /59 skipped /1 xfailed ใน768.29วินาที พบ splash tests อีก2กรณีนอกเหนือจาก integration เดิม แยกรันแล้ว reproduce ได้: `TERM=dumb` ทำให้ Rich คืน80x25เมื่อกำหนดเฉพาะwidth จึงแก้ helperของ tests ให้ pin height40ด้วย เพื่อทดสอบ virtual console ตาม width ที่ระบุจริง คง assertions ทุกข้อและไม่แก้ application rendering หลังแก้ targeted รวม splash ผ่าน **97 tests** (48 contract/planning +49 formatter/DSL) แล้วจึงรัน full ใหม่ ผลเก็บแยก initial/final ไม่ลบประวัติที่ล้มเหลว

Skipped cases ไม่ใช่ passed: รอบ initial มี browserที่เริ่มไม่ได้16, Hermesไม่ติดตั้ง10, paid-live9ที่ตั้งใจไม่เปิดตามคำสั่งผู้ใช้, external real services4, Windows Job Objects3 และ speech/media/model weights/optional dependencies/checkoutอื่นที่ขาด รายการเหตุผลครบเก็บใน machine-readable result รอบสุดท้าย กรณี expected-failure เป็น image generation ที่ต้อง diffusion extras และ model weights การรัน Pythonทั้งsuiteจึงไม่ใช่การยืนยัน optional integrations ทุกชนิด

Pipeline ผ่าน **21/21 cases, 134/134 checks** ด้วย `--no-subagents --keep` ไม่ได้รันกรณี subagents และไม่อ้างครบทุก optional pipeline case

JavaScript ผ่าน **153 tests**: SDK73, FDIA package32, Edge37, Action11 รัน SDK ซ้ำหลังเปลี่ยน lockfileแล้ว Action build และ SDK build ผ่าน Ruff ตาม CI scope core/signedai/rct_control_plane/microservices ผ่าน และ authored diff whitespace check ผ่าน Generated Action bundle เป็น upstream-generated bytes ไม่ได้ปรับ whitespace ทั้ง bundle ด้วยมือ

สร้าง wheel ในเครื่องและติดตั้งลง validation venv แล้วทดสอบจาก `/tmp` ยืนยัน import จาก site-packages จริง ทดสอบ derived graph/digest/SQLite round-trip/claim ผ่าน Wheel ยังใช้ project version2.3.1 จึงต้องอ้าง exact source commit ประกอบ ไม่ได้ publish package หรือ native desktop build

## RCT-7 เทียบกับเป้าหมาย

| ขั้น | สิ่งที่มีตอนนี้ | สิ่งที่ยังต้องพัฒนา/พิสูจน์ |
|---|---|---|
| R1 Observe | reported facts/sources/unknowns/assumptions ใน declared mode; derived mode อ้าง goal/criteria | แยก observed/verified/inferred evidence และค้นหา critical unknowns เอง |
| R2 Analyze | constraints และกราฟความสัมพันธ์ที่ประกาศ/สร้างตาม predicates | semantic relations/context ที่ถูกต้องตามโจทย์ทั่วไป |
| R3 Deconstruct | typed graph, coverage/cycle/dangling checks และ compiler ตามเกณฑ์ | สร้าง goal-dependent semantic components จาก facts เดิมแต่โจทย์ต่างกัน |
| R4 Reverse | backward criterion links พร้อม prerequisite closure | เงื่อนไขจำเป็นด้านเนื้อหา/หลักฐาน ไม่ใช่เพียง check รูปแบบ |
| R5 Core intent | critical questions ที่ประกาศไว้ทำให้ durable wait ก่อนโมเดล/tools; confirmed answers/revisions | ค้นพบ ambiguity/criticality เองและครอบคลุมทุก entry point |
| R6 Reconstruct | แผนเห็นได้ก่อนทำงานใน CLI/HTTP contract path | Desk/jobs/channels และ event ordering ที่ผ่าน matrix |
| R7 Compare | deterministic predicates + heuristic grounding/intent; mismatch wait/resume ที่คง original | semantic/effect oracle ที่น่าเชื่อถือและ signed effects/crash reconciliation |

จึงยังตอบว่า “ระบบคิดตาม RCT-7 ครบถ้วนสมบูรณ์แล้ว” ไม่ได้ สิ่งที่รันจริงในโค้ดเป็นของจริง แต่ระดับการยืนยันต้องผูกกับ workflow ที่ทดสอบ การมี tests หลายพันกรณีไม่ใช่เปอร์เซ็นต์ความครบของสถาปัตยกรรมหรือความแม่นยำ semantic

## Demo และหลักฐาน

บันทึก CLI จริงที่อ่านไฟล์สังเคราะห์ราคา **12,500 บาท น้ำ กำลัง** ผ่าน tool จริงและ SQLite โดยใช้ local scripted HTTP model สอง calls แสดง plan ก่อนงาน แล้วตรวจเกณฑ์และไฟล์เดิมไม่เปลี่ยน ไม่มี paid API ไม่ใช่ real-model capability benchmark

วิดีโอเป็น Unicode-shaped terminal replay จาก PTY และ timestamps จริง ไม่มีเสียง ไม่ใช่ desktop screen capture ตรวจ raw UTF-8, transcript และ cast ตรงกัน ไม่มี U+FFFD และมีคำไทย/ตัวเลขที่กำหนดครบ ตรวจภาพไทยประกอบแล้ว การผ่าน script check ไม่ได้ประเมินคุณภาพภาษาไทยโดย semantic evaluator

หลักฐานอยู่ใน `/workspace/delentia-rct-completion-evidence`: full-python.log/XML คือ initial completed run; full-python-final.log/XML คือ final completed run; targeted-final.log/XML รวม97 tests; pipeline.log, JS logs, audit ก่อน/หลัง, preflight, wheel smoke, demo-result.json, cast/transcript/raw PTY และ derived-plan-demo.mp4 ชุดแชร์ใช้ allowlist ไม่รวม databases, namespace keys, model config ส่วนตัว หรือ uploaded internal source documents

## งานที่ยังขาดก่อนเผยแพร่

1. Integration host: โมเดลจริง, Chromium sandbox, native DNS/public pinned egress แล้ว rerun failures โดยไม่ลด checks
2. Semantic planner/provenance/critical unknown discovery และ context revision/migration ที่ผ่าน Thai/English development/holdout protocol
3. Contract-aware signed effects พร้อม journal/crash reconciliation ก่อนเปิด write tools
4. แผน/clarification/continuation ใน Desk/jobs/channels พร้อม namespace/cancel/restart tests ตาม [coverage ของจุดเรียกจริง](RCT_ENTRYPOINT_COVERAGE_TH.md)
5. Capable local-model development และ formal evaluation ที่ freeze model/settings/commit/protocol; paid API ยังไม่ได้รับอนุญาต
6. Host/notary/witness/backup-restore/soak/outside pilot และ review claims/captions ก่อนโพสต์

ดูรายละเอียดและ acceptance gates ใน [แผนรอบถัดไป](RCT_COMPLETION_NEXT_GATES_TH.md) ระยะห่างจาก architecture ยังเป็นงานด้าน semantics, effects/recovery และ operations ที่มีสาระสำคัญ จึงไม่ควรตีเป็นเปอร์เซ็นต์จากจำนวนไฟล์หรือจำนวน tests สถานะที่เหมาะสมยังเป็น **experimental governed runtime with partial RCT-7 and bounded criterion-derived planning**

ไม่มีการ merge main, deploy, publish package, เปิด public service หรือโพสต์ภายนอก การบันทึก Git ใช้ branch Codex แยกจากงานของ Claude และต้องตรวจ remote SHA หลัง push
