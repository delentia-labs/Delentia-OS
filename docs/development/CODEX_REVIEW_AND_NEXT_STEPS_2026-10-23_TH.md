# ขอบเขต review และแผนพัฒนาถัดไปของ Codex

23 ตุลาคม 2026 — branch `codex/rct-verified-budget-receipts-20261023` สืบต่อจาก `67bf57e` ไม่ merge main และไม่รวมการพัฒนาของ Claude ที่ไม่ได้อยู่ใน ancestry นี้ Git push ไม่เท่ากับ deploy หรืออนุมัติ production

## งานสะสมที่ต้อง review เมื่อเทียบกับ main

ก่อน commit รอบ verified-budget branch มี 11 commits ที่ไม่อยู่ใน origin/main ซึ่งตรวจได้ถึง `19d5fe8`:

| Commit | ขอบเขต |
|---|---|
| 775548f | ปรับ public information ตามนิยาม v0.3 ที่ผู้สร้างยืนยัน |
| 4140318 | คืน workspace/environment หลัง research harness จบ |
| f0429bd | ปรับขอบเขต demo สองภาษาและแนวทางบันทึก |
| 41776ef | merge งาน public-information เข้าสาย research cleanup |
| b010da5 | durable explicit intent contracts และหลักฐานทดสอบ |
| f2ad16c | บันทึก dependency review gate ที่เคยรายงานระหว่าง push |
| 2fc16e8 | รักษาข้อความไทยใน demo และแก้ lifecycle ของ intent contract |
| 1b1be31 | declared RCT plans, runtime readiness และ build hardening |
| 13c4860 | เอกสาร Action runtime ให้ตรงกับ Node 24 artifact ที่ตรวจ |
| 4044f1f | derive criterion plans และ stable contract receipts |
| 67bf57e | bounded Thai/English semantic planner และ critical-input waits |

รอบใหม่เพิ่ม pinned-quote executor, exact Decimal arithmetic, dependency-enforced component receipts, source freshness check, cancellation/replay/namespace tests และ activation assessment ดู [ผลรอบล่าสุด](VERIFIED_BUDGET_RESULTS_2026-10-23_TH.md) และ [machine-readable evidence](evidence/VERIFIED_BUDGET_2026-10-23.json)

การเปรียบเทียบกับ main รวม Action bundle ที่ build แล้วจึงมี diff ใหญ่ ควร review source/package/runtime changes คู่กับ generated artifact อย่าสรุปว่า generated diff ทั้งหมดเป็น logic ที่เขียนใหม่ในรอบล่าสุด ผล merge-tree ไม่พบ conflict แต่ยังไม่มีผลทดสอบต้นไม้ที่รวม dependency commits ใหม่จาก main

ไม่เพิ่ม API keys, operator databases, namespace keys, model weights หรือ private demo state เข้า Git และไม่ใช้ paid API

## ลำดับพัฒนาและเกณฑ์จบ

### 1. ทำ integration host ให้ทำซ้ำได้

- ตรวจ GitHub dependency alerts บน default branch ใหม่: push วันที่ 23 ตุลาคมรายงาน 47 รายการ (7 critical / 25 high / 15 moderate) ต้องทำ inventory แยก manifest/version/reachability/fix และรันทดสอบหลังแก้ ตัวเลขนี้เป็น server summary ของ default branch ไม่ใช่ audit ของ branch นี้ และไม่ถูกปิดด้วยผล npm audit เฉพาะ GUI/Action/SDK ก่อนหน้า

- แก้ proxy route ของ Ollama container แล้วตรวจ official model digest, tags และ inference จริง ก่อนรัน model integration ทั้ง 9 กรณี การ probe HTTP 206 อย่างเดียวไม่ถือว่าติดตั้งสำเร็จ
- ทำ browser sandbox ให้ใช้ได้บน target host โดยรักษา sandbox ตรวจ user namespace/SUID helper ตามข้อจำกัด host แล้วรัน TC027 ทั้ง 3 กรณีและ browser tests ที่ถูก skip
- แก้ native DNS/egress ให้ web-crawl tool ใช้ได้โดยรักษา SSRF และ DNS-pinning policy การ curl ผ่าน proxy ไม่ใช่หลักฐานของ native resolver
- เลือก revision ที่รวม main ผ่าน review แล้วรัน full suite เก็บ command, exit code, failures, skips และ dependency versions; ไม่เปลี่ยน failures เป็น skips เพื่อให้เขียว

เกณฑ์จบ: required integrations ผ่านบน host ที่ระบุ และ skip ทุกตัวมี owner/เหตุผล/ผลต่อ release ชัดเจน

### 2. ปิดขอบเขตบริการ read-only รุ่นแรก

- เพิ่ม server-enforced verified-budget profile: allowlist routes/tools/executor versions, ปฏิเสธ unknown schema และไม่ fallback ไป general agent
- กำหนด versioned request/result/error/status contracts; แยก legacy heuristic, typed verification และ model capability metrics
- แก้ receipt timestamp/canonical encoding ข้ามภาษา พร้อม compatibility/migration tests
- เพิ่ม authentication, per-user workspace/file authorization และทดสอบสองผู้ใช้พร้อมกันโดยไม่สลับ global workspace ต่อ request
- harden actual MCP source acquisition ต่อ symlink/resolve-read races; final hash check ไม่ทดแทนการป้องกันข้อมูลรั่วขณะอ่าน

เกณฑ์จบ: negative route/schema/identity/path/race tests ผ่าน ไม่มี write surface หรือ generic fallback ใน profile และ UI อธิบาย scope ของผลตรวจตรงกับ API

### 3. ยกระดับ planner และหลักฐาน

- สร้าง frozen Thai/English development/holdout cases สำหรับ paraphrase, ambiguity, multi-intent, negation, conflicting constraints และ out-of-scope requests
- ระบุ provenance/uncertainty ของทุก derived field พร้อม invalidation เมื่อแก้โจทย์/หลักฐาน
- เพิ่ม source identity, observation time, freshness policy และ conflict resolution ตามงานจริง แยก user assertion ออกจาก verified observation
- พัฒนา typed handler registry กับ dependency scheduler; แผนจากโมเดลต้องไม่เพิ่ม authority และ dependent node ต้องไม่จบหาก prerequisite ไม่ผ่าน

เกณฑ์จบ: รายงานผลแยกตามภาษา/ชนิดโจทย์/false acceptance โดยใช้ holdout ที่ไม่ปรับตามคำตอบ และทุก component ที่ประกาศว่าจบมี receipt จาก handler จริง

### 4. เพิ่ม domain semantic verifiers

- ขยาย numeric oracle ตาม use case: currencies, rounding, taxes, discounts, totals และเงื่อนไขที่ต้องถามเพิ่ม แทนการเดาจากข้อความ
- เพิ่ม source-to-claim checks และ contradiction tests; verifier ต้องปฏิเสธข้อสรุปที่หลักฐานรองรับไม่พอ
- เก็บ semantic verdict แยกจาก JSON/language/contains checks และทดสอบค่าชายขอบ/ข้อมูลผิด/การเปลี่ยน source

เกณฑ์จบ: มี independent expected results สำหรับ domain ที่เปิดใช้ และไม่มีการอ้างความถูกต้องเกิน field/assumption ที่ตรวจจริง

### 5. Effects, journal และ recovery ก่อนเปิด write tools

- ผูก approval/signature กับ contract id/version, plan/action digest, actor, workspace, policy, expiry และ nonce
- กำหนด idempotency/reconciliation ตาม tool จริง พร้อม job terminal states และ duplicate-delivery handling
- ทำ real-process kill/restart matrix ก่อน effect, หลัง effect ก่อน receipt, หลัง receipt ก่อน acknowledgement และกรณี DB/network/disk failure
- recovery ต้องแยก not-started/applied/unknown และห้าม replay external effect โดยเดา

เกณฑ์จบ: signed request ที่แก้ข้อมูล/หมดอายุ/replay ถูกปฏิเสธ และมีหลักฐาน crash reconciliation ทุก boundary ของ tool ที่จะเปิด ไม่ประกาศ exactly-once โดยไม่มีหลักฐานจากปลายทาง

### 6. ขยาย Desk/jobs/channels ทีละช่องทาง

- ทำ plan-before-action, persistent clarification, continuation, cancel และ progress/receipt views ให้ตรงกัน
- ทดสอบ disconnect/reconnect, namespace isolation, duplicate requests และ process restart แยกตาม surface
- บังคับ verified profile และ effect policy ที่ server ทุกเส้นทาง

เกณฑ์จบ: แต่ละช่องทางมี end-to-end evidence ของตัวเอง ไม่อนุมานความพร้อมจาก shared loop เพียงอย่างเดียว

### 7. Capable-model evaluation

- เริ่มจากโมเดล local ที่ติดตั้งและตรวจ digest แล้ว; รอบนี้ยังไม่ใช้ paid API
- freeze model/settings/code/schema/policy/evaluation protocol แล้วแยก development ออกจาก holdout
- วัด task success, unsafe acceptance, clarification quality, Thai/English fidelity, latency และ resource usage
- แยกผล deterministic executor ที่ generation calls เป็นศูนย์ออกจาก model accuracy

เกณฑ์จบ: ผลรันซ้ำตรวจสอบได้พร้อม raw outcomes และข้อจำกัด ไม่ใช้ demo เดียวแทนความสามารถทั่วไป

### 8. Release operations และ supervised pilot

- สร้าง versioned artifact/image และทดสอบ fresh install/upgrade/rollback บน host เป้าหมาย
- ทดสอบ quota/concurrency/queue, DB lock, disk full, retention, monitoring และ operator stop
- backup พร้อม key policy; restore จาก off-host copy จริง; แยก notary/witness และตรวจ evidence continuity
- ทำ soak 72 ชั่วโมงตาม release gates แล้วจึง outside supervised pilot พร้อม incident/feedback log และเจ้าของการปฏิบัติการ

เกณฑ์จบ: ผ่าน [activation gates](../release/ACTIVATION_GATES_2026-10-23_TH.md) ของ profile/surface ที่จะเปิด และประเมินตาม [release levels](../release/RELEASE_LEVELS.md) เดิม การเปิด PR รอบนี้ไม่ใช่การอนุมัติ deploy/publish/pilot

## ลำดับ review ที่แนะนำ

1. ตรวจ contract authority, namespace/CAS lifecycle และ fail-closed paths
2. ตรวจ exact arithmetic, actual source acquisition และ receipt integrity
3. ตรวจ regression/CLI/wheel evidence และ failures ที่ยังค้าง
4. ตรวจ Action/SDK dependencies, generated bundle และ Thai demo/public claims ของงานสะสม
5. เลือกวิธีรวม main และรัน required CI ของ revision รวมก่อน merge

สถานะ: experimental governed runtime พร้อม verified read-only workflow เฉพาะงาน ยังไม่ใช่ RCT-7 ทั่วไปที่พร้อมรับงานเองหรือ production/pilot-ready
