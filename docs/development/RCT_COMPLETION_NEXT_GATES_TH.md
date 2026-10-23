# แผนพัฒนา RCT-7 หลัง criterion-derived plans และ atomic receipts

Checkpoint23ตุลาคม: มี [verified read-only budget workflow และcomponent receipts](VERIFIED_BUDGET_RESULTS_2026-10-23_TH.md) ที่รันจริงโดยไม่ใช้generationแล้วในขอบเขตจำกัด ดู [activation gatesล่าสุด](../release/ACTIVATION_GATES_2026-10-23_TH.md) ก่อนขยายไปรับงานจากคนนอก ไม่ได้ปิดgeneral semantic/effects/operations gatesทั้งหมด

Checkpoint ถัดมา: เพิ่ม bounded Thai/English summary/budget task planner และ reported-source provenance แล้ว พร้อมเตรียม network draft โดยรักษารายการเดิม ดู [ผลและลำดับงานล่าสุด](BOUNDED_SEMANTIC_PLANNER_RESULTS_TH.md) และ [failure catalog13กรณี](INTEGRATION_FAILURE_CATALOG_TH.md). รายการ semantic/effect/pilot gates ด้านล่างยังไม่ถือว่าปิดทั้งหมด

22 ตุลาคม 2026. ใช้ต่อจาก [แผน readiness](READINESS_NEXT_ROUNDS_TH.md). รายการด้านล่างเป็นงานที่ต้องทำและเกณฑ์รับงาน ไม่ใช่รายการที่ผ่านแล้ว การผ่าน unit tests หรือการมีชื่อ R1–R7 ไม่ทำให้ semantic RCT-7 สมบูรณ์

## A — ปิดข้อจำกัดเครื่อง integration

1. เพิ่ม official model blob host `dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com` ใน allowlist เดิม โดยรักษา registry และโดเมนที่ใช้อยู่ ไม่แทนรายการที่อ่านไม่ได้ทั้งหมด ตรวจ manifest/digest, พื้นที่ว่าง และการดาวน์โหลดจริงโดยคง TLS verification
2. ติดตั้ง `qwen2.5:7b` จริง ทดสอบ local inference และบันทึกชื่อ/digest/settings/เวลา ไม่ตั้ง alias ให้ fixture หรือโมเดลอื่นผ่านข้อกำหนดเดิม โมเดลตอบได้หนึ่งครั้งยังไม่รับประกัน integration tests ผ่าน
3. ใช้ host/base image ที่ Chromium sandbox ทำงานได้: root-owned helper mode 4755 หรือ user namespaces ที่อนุญาตจริง ไม่ใช้ `--no-sandbox` หรือ privileged workaround
4. ทำ native DNS และ public egress ให้ crawler ที่ pin IP ใช้งานได้ การ curl ผ่าน proxy สำเร็จไม่เท่ากับผ่าน DNS-pinned crawler ห้ามลด SSRF checks
5. เก็บ preflight ก่อน/หลัง รัน integration ที่ล้มเหลวจริง แล้ว full suite อีกครั้ง ไม่มีการเปลี่ยน failures เป็น skips เพื่อให้รายงานเขียว

แยก inventory ของ skipped integrations ด้วย: browser/Hermes, external real services, speech/media weights/dependencies และ Windows-only checks ต้องมี host/fixtures/CI ที่เหมาะสม ส่วน paid-live tests9กรณียังคงไม่เปิดตามคำสั่งผู้ใช้ การผ่าน suite ส่วนที่รันไม่ได้พิสูจน์ส่วนที่ skipped หรือ expected-failure

ผู้ดูแล environment ต้องแก้สาม capability นี้ก่อนปิดรอบ A รายละเอียดเดิมอยู่ใน [runtime prerequisites](RUNTIME_PREREQUISITES_AND_FAILURES_TH.md). Draft startup ที่บันทึกไว้เป็น configuration สำหรับ review/Publish ไม่ใช่หลักฐานว่าเครื่องปัจจุบันหรือเครื่องใหม่พร้อมแล้ว

## B — semantic planner ที่ตรวจสอบได้

รอบนี้มี compiler จาก explicit predicates เท่านั้น ขั้นถัดไปต้องออกแบบ planner ที่แยก observed evidence, reported facts, inferred relations, assumptions และ critical unknowns โดยเก็บ source locator/digest และชนิด provenance ที่ไม่เลื่อน reported เป็น verified เพียงเพราะโมเดลพูดซ้ำ

ทำ development fixtures ภาษาไทย/อังกฤษพร้อม paraphrases สำหรับสรุป เทียบทางเลือก วางแผนงบ และตรวจเอกสาร เก็บคู่ same facts/different goal และ same goal/missing critical input ให้ oracle ระบุองค์ประกอบ เงื่อนไขย้อนกลับ และคำถามที่ต้องรอ เตรียม holdout แยกก่อนปรับ planner; ห้ามใช้ผล holdout ไล่แก้ implementation แล้วอ้างเป็นการประเมินอิสระ

Planner ควรคืน proposal ตาม schema ที่ตรวจได้ พร้อม uncertainty/source references; schema validation ไม่รับรองความจริง ตรวจ evidence acquisition และ dependency closure ก่อนเริ่มงาน ห้ามให้ข้อความในเอกสาร/โมเดลเพิ่มสิทธิ์เครื่องมือ ต้องมี plan revision ที่เปลี่ยน context/criteria ได้อย่างชัดเจน เก็บ original intent และ version/digest ทุกครั้ง ทดสอบ corrupted payload, legacy migration, erasure และ conflicting revisions

Gate: โจทย์เปลี่ยนแล้วองค์ประกอบเปลี่ยนตามเหตุผลจริง, ทุกเกณฑ์มี action/evidence/check, ข้อมูลสำคัญหายต้องถามและรอ, ไม่มีแหล่งข้อมูลแต่ง และแผนไม่เพิ่มสิทธิ์ ผ่านทั้ง scripted structural tests และ capable local-model evaluation ก่อนขยาย default รอบนี้ยังไม่มี paid API

## C — signed effects และ crash reconciliation

ต้องมี reviewed state machine ก่อนเปิด write fence ผูก approval กับ contract id/version, plan digest, namespace/actor, workspace, exact tool+canonical args, policy version, nonce และ validity ลงลายเซ็นจริง ไม่ใช้ `plan_sha256` เป็นสิทธิ์แทนลายเซ็น

Journal ต้องแยก reserved, dispatching, effect observed, verification และ outcome unknown พร้อม idempotency key ตาม capability ของแต่ละ tool ไม่อ้าง exactly-once สำหรับ external effect ที่ไม่มี primitive รองรับ

| จุด crash/race | ผลที่ต้องพิสูจน์ |
|---|---|
| ก่อน reservation | ไม่มี effect; คำขอเดิมยังต้องผ่าน policy/version |
| หลัง reservation ก่อน dispatch | reconciliation พิสูจน์ว่ายังไม่เกิด effect ก่อน retry |
| หลังส่งคำสั่งก่อนรับ response | outcome unknown; ห้ามเดาว่าไม่เกิดหรือยิงซ้ำ |
| effect เกิดแล้วแต่ receipt ไม่ครบ | สังเกต effect ด้วยหลักฐานที่ผูกกับคำขอนั้นก่อนบันทึกผล |
| policy/plan/version เปลี่ยนหลังเซ็น | signature เก่าใช้ไม่ได้กับคำขอใหม่ |
| erasure/cancel ระหว่างรัน | ไม่ใช้ข้อความที่ถูกลบเพื่อเริ่มงานใหม่ และรายงานข้อจำกัดของ effect ที่เกิดแล้ว |
| สอง caller claim พร้อมกัน | ผู้ชนะเดียว; receipt ของแต่ละ caller ไม่รับสถานะของอีกคน |

รอบนี้แก้เฉพาะ receipt race และเพิ่ม plan binding material แล้ว ยังไม่มี signed effect token หรือ reconciliation ที่ผ่าน crash matrix จึงคง contract tools เป็น read-only

## D — ขยายช่องทางทีละช่องทาง

ทำ coverage matrix CLI, HTTP run/continue, Desk stream, jobs และ channels ก่อนต่อเพิ่ม แต่ละช่องทางต้องมี plan event ก่อน artifact/effect, initial-input wait, mismatch wait, continuation ผูก namespace/version, restart/cancel และ stale/replay tests ชัดเจน Job ที่รอผู้ใช้ต้องมี durable wait state ไม่กลายเป็น completed หรือวนเรียกโมเดลเอง

ตรวจจุดเรียกจริงแล้วใน [entry-point coverage](RCT_ENTRYPOINT_COVERAGE_TH.md). กลไก approval/notary/journal เดิมมีอยู่จริง ต้องต่อเข้ากับ contract โดยรักษา gates เดิม ไม่สร้าง bypass หรืออ้างว่า shared loop ทำให้แต่ละ surface รองรับ contract โดยอัตโนมัติ

Action รอบนี้อัปเดต follow-redirects 1.16.1 และสร้าง bundle ใหม่ ต้องติดตาม production audit/lockfile/bundle ต่อไป 0 findings ของ package นี้ไม่เท่ากับ GitHub alerts ทุก branch หายแล้ว GitHub-hosted workflow/real API auth/branch protection ยังต้องทดสอบบนระบบนั้น และ native Tauri ยังต้อง Rust/GTK/WebKit/fresh install

## E — capable model และการประเมิน

เมื่อ local model พร้อม ให้ capability screen โดยไม่ใช้ paid API ก่อน เก็บ provider/model/digest/prompt/temperature/budgets/seed หากรองรับ และ policy/schema/commit สำหรับ reproducibility ถ้าจะใช้ paid API ภายหลังต้องได้รับขอบเขตที่ผู้ใช้กำหนดก่อน

Freeze development artifacts และ protocol ก่อน formal comparison ตาม research protocol เดิม วัดแยก structural validity, intent fidelity, critical question recall, evidence provenance, tool violations, latency/cost และ recovery ไม่แปลงจำนวน unit tests เป็น semantic accuracy หรือ causal benefit

## F — ก่อน pilot และโพสต์แรก

Production/pilot ต้องมี host isolation, separate-user notary, off-host witness ที่รันตามกำหนด, backup/restore ที่พิสูจน์ได้, budgets/alerts/operator stop, soak 72 ชั่วโมง และ outside feedback จริง การเขียนแผนไม่ได้ทำให้ gates เหล่านี้ผ่าน

โพสต์ L0 ควรใช้ demo ที่ระบุ SCRIPTED model และ criterion-derived/user-declared planning ตามกรณี พร้อม commit/คำสั่ง/ผลที่ตรวจได้ เปิดเผย blockers ไม่อ้าง complete RCT-7, production-ready, zero hallucination หรือการรับรอง compliance ไม่มีการโพสต์/merge/deploy อัตโนมัติในงานนี้

## การประสาน Codex / Claude

รอบนี้ใช้ branch `codex/rct-derived-planning-and-receipts-20261022` จาก `13c4860eb9672cc170ddc85758253f5872b74470` ไม่ force push หรือ merge main ส่ง commit/diff/test artifacts ให้ review ก่อนแก้ shared files: intent_contract.py, rct_plan.py, cli.py และ Action lockfile/bundle แยกตัวผู้พัฒนาออกจาก model/config ที่ใช้ประเมินเสมอ
