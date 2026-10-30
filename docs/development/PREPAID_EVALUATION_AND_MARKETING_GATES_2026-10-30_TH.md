# ก่อนใช้ OpenRouter จริง และก่อนรับผู้ทดลอง — 30 ตุลาคม 2026

## ข้อสรุปสถานะ

Delentia มี runtime, governance, persistence, typed execution และ verifiers ที่รันได้จริงในงานที่กำหนดขอบเขต แต่ยังไม่ใช่ autonomous RCT-7 ทั่วไปหรือ production service การเชื่อม bounded contract กับ jobs รอบนี้ปิดช่องว่าง integration ส่วนหนึ่ง ไม่พิสูจน์ความสามารถของโมเดล.

มีสามการตัดสินใจที่ต้องแยกกัน: ทดลองโมเดลแบบควบคุมต้นทุน, เผยแพร่ technical preview, และเปิด host รับ named users การผ่านข้อแรกไม่ทำให้ผ่านอีกสองข้อโดยอัตโนมัติ ใช้ [release levels](../release/RELEASE_LEVELS.md) เดิม ไม่สร้างระดับใหม่หรือใช้เลข package version แทน maturity.

## 1. เกณฑ์ก่อน paid research call แรก

| งาน | หลักฐานก่อนเริ่ม | สถานะ/ผู้รับผิดชอบ |
| --- | --- | --- |
| Revision ที่จะวัด | SHA เดียวรวม dependencies, required checks มีผล, ตรวจ failure ที่เหลือและลงทะเบียนข้อจำกัด | #202–#205 ยังรอ review/CI; Codex |
| ขอบเขตงานที่ใช้โมเดลจริง | เลือก workflow ที่ต้อง generation ไม่ใช้ deterministic budget executor เป็นหลักฐานความสามารถโมเดล | เลือกกับ Architect/Claude; ใช้ของที่มี |
| การแยกข้อมูล | freeze development/holdout ก่อน tuning, gold labels/oracles อยู่นอก agent workspace, fixture/hash/version ตรวจซ้ำได้ | ใช้ research harness ของ Claude; ไม่อ่าน sealed labels เพื่อปรับ prompt |
| เส้นทางค่าใช้จ่าย | fake endpoint พิสูจน์ guard กับเส้นทางที่จะใช้จริง รวม main/judge/critic/chain/fallback/retry/stream หากเปิดใช้ | pre-API checklist เดิมมีหลักฐาน แต่ต้องยืนยันกับ configuration/revision ใหม่ |
| Budget และราคา | model ID, upstream provider/routing, ราคาที่ตรวจวันรัน, cap ต่อ call/run/ทั้ง experiment, token/step/retry limits, provider-side prepaid cap | ยังไม่มีการอนุมัติ paid model/วงเงินจริง ค่า default ในโค้ดไม่ใช่งบที่อนุมัติ |
| Fail closed | ไม่ทราบราคาไม่ dispatch, ไม่มี automatic paid fallback, timeout/crash คง reservation, restart ไม่เริ่ม run ID เดิมซ้ำ | ใช้ `research/daaes/budget_guard.py` และ `live_adapter.py`; Claude เป็นเจ้าของ runner |
| Raw outcomes | บันทึก code/policy/schema/prompt/settings/model hashes, request IDs, actual served model/provider ที่ทราบ, usage/cost/latency, failure taxonomy, oracle verdict | ต้องมีครบในรอบที่วัดจริง; redaction และ retention ต้องกำหนดก่อนส่งข้อมูล |
| Operator และ secrets | operator คนเดียวควบคุม canary, หยุดได้, key อ่านจาก secret store/environment, fixtures ไม่มีข้อมูลผู้ใช้จริง | ไม่ส่ง key ในแชท/PR/log; รอบนี้ไม่เรียก paid API |

`research/results_round103/pre_api_checklist_2026-10-26.md` เคยรายงาน 7 PASS และ “Ready for a paid call: True” จาก fake API และ scripted evidence ข้อความนั้นไม่ใช่การอนุมัติงบ ไม่ใช่ผล capable model และไม่รับรองทุก configuration ที่เปลี่ยนภายหลัง.

ตรวจ gateway ที่จะใช้ให้ครอบคลุม auxiliary models ด้วย การส่ง guarded provider ให้ main agent อย่างเดียวไม่พิสูจน์ว่าการสร้าง judge/critic/jury แยกทั้งหมดถูกคิดงบแล้ว หากยังตรวจไม่ครบให้ปิดเส้นทางที่ไม่ใช้ใน experiment อย่างชัดเจน; หาก policy บังคับใช้ต้องหยุดและแก้ integration ไม่ข้าม policy.

native DNS และ local Ollama ยังไม่พร้อมใน cloud ที่ตรวจรอบนี้ (`/api/tags` ว่าง; native resolver ไม่คืนผล) ต้องแก้ก่อนประเมิน workflow ที่ใช้ crawler/Ollama แต่ไม่จำเป็นต้องรอ local model เพื่อเริ่ม bounded OpenRouter experiment ผ่านเส้นทาง HTTPS ที่ตรวจแล้ว หากโจทย์นั้นไม่พึ่งสองอย่างนี้ ห้ามปิด SSRF/DNS pinning เพื่อให้ crawler ผ่าน.

GUI ไม่ใช่ prerequisite ของ headless model evaluation แต่ต้องผ่านเมื่อทดลอง workflow ผ่าน Desk ข้อกำหนด 72-hour soak/witness ของ shared pilot ไม่จำเป็นต้องใช้ปิดกั้น isolated research canary ที่ไม่มี external users.

## 2. ลำดับการทดลองและการคำนวณ

1. รัน free rehearsal ของ exact configuration และ fake billing/crash oracle ก่อน เปิด main model เพียงเส้นทางที่ลงทะเบียนไว้
2. เมื่อ Architect ระบุ model/provider/วงเงินแล้ว เริ่ม canary ทีละ run ด้วย fixtures ไม่มี write effects ตรวจ provider bill เทียบ ledger ก่อนเพิ่มจำนวน
3. freeze protocol แล้วรัน capability screen/batteries เดิม G-model ระบุ K.1.5 อย่างน้อย 90% ใน 5-goal และ 17-goal batteries ไม่เปลี่ยนเกณฑ์หลังเห็นผล
4. ทำ paired A/B โดย model/settings/fixtures/policy และขอบเขตเครื่องมือเท่ากัน ใช้ comparator และ ablation ที่ลงทะเบียนไว้ บันทึก order/seed และแยก developer tuning จาก holdout
5. ใช้ whole-workflow oracles ตรวจผล ไม่ใช้ความเห็นของ agent เองเป็น gold รายงาน failures และ missing results ทั้งหมด แยก infrastructure failures ออกจาก model mistakes

กำหนด `P_in`, `P_out` เป็น USD ต่อหนึ่งล้าน tokens และเพดานต่อ call เป็น `I_max`, `O_max`:

```text
C_call_max = (I_max × P_in + O_max × P_out) / 1,000,000
C_run_max  = ผลรวมเพดานของทุก role/call/retry ที่อนุญาตใน run
N_runs     = N_cases × N_arms × N_repeats
B_required = N_runs × C_run_max + reserve ที่กำหนด
N_afford   = floor((B_authorized - B_reserve) / C_run_max)
```

ตัวอย่างการนับจำนวนงานเท่านั้น: 22 cases × 2 arms × 3 repeats = 132 runs; หากอนุญาตสูงสุด 6 model calls/run จะมีเพดาน 792 calls ก่อนนับ auxiliary roles ที่ต้องกำหนดต่างหาก นี่ไม่ใช่จำนวนรันที่อนุมัติหรือการเสนอราคา ต้องใส่ราคาจริงและวงเงินจริงก่อนคำนวณ USD ไม่คาดเดาราคา OpenRouter.

รายงานสองแกนร่วมกัน:

| แกน | ตัวชี้วัด |
| --- | --- |
| คุณภาพผลลัพธ์ | task success, semantic correctness, false acceptance ของผลผิด, false refusal, oracle failures |
| คุณภาพกระบวนการ | ถามข้อมูลที่จำเป็น, confirmation-before-action, criterion coverage, authorization violations, recovery/receipt completeness |
| ประสิทธิภาพ | latency p50/p95, timeouts, tokens/เงินจริงต่อ task สำเร็จ, resource usage, infrastructure failure rate |

ระบุ denominators, ขนาดตัวอย่าง, uncertainty/ช่วงความเชื่อมั่น และ raw outcomes ห้ามสรุปว่า zero failures เท่ากับความเสี่ยงศูนย์ ด้วย rule-of-three แบบประมาณ การไม่พบ failure ใน 30 independent trials ยังให้ขอบบน 95% ราว 10%; ต้องประมาณ 300 trials ที่ไม่มี failure จึงอยู่ราว 1% ภายใต้สมมติฐาน independence กรณี correlated trials ต้องใช้วิธีเหมาะสมกว่านี้.

## 3. ก่อน technical preview และ marketing/recruitment

เผยแพร่ L0 mechanism evidence ได้เมื่ออธิบายขอบเขตตรงกับสิ่งที่รัน การชวนคนติดตั้งหรือเชื่อมข้อมูลจริงต้องมี package/installer ที่ตรวจ revision นั้นแล้ว, คู่มือ setup/rollback/limitations, privacy/retention/erasure และช่องทางแจ้งปัญหา ไม่ใช้คำว่า production หรือ autonomous general RCT-7.

Claude ควรทดสอบ Desk บน combined SHA ที่รวม backend จริง: ไทย/อังกฤษ, accessibility, identity change, reconnect, cancel, restart, plan/clarification/confirmation/differences/receipts และบันทึกวิดีโอใหม่ วิดีโอต้องบอกชัดว่าส่วนใด scripted/model-free และส่วนใดมาจากโมเดลจริง CI GUI failure ที่ exit 2 ยังต้องใช้ log/artifact หาสาเหตุก่อนสรุปว่าเป็น WCAG defect.

ตัวเลขสาธารณะต้องมาจาก CI ของ main ผ่าน `scripts/update_test_checkpoint.py` ไม่ยกยอด cloud suite ของ branch นี้เป็น canonical checkpoint ไม่แก้ generated readiness snapshot ด้วยมือ และไม่แก้ public claims ของ Claude โดยไม่ประสานงาน.

หาก marketing หมายถึงรับรายชื่อผู้สนใจ technical preview ให้ระบุว่ายังไม่เปิด shared autonomous service หากหมายถึงรับคนเข้ารันงานบน host จริง ต้องผ่าน L2 gates ในส่วนถัดไปก่อน.

## 4. ก่อน supervised private pilot

| งาน | เกณฑ์จบ |
| --- | --- |
| Combined workflow | มี E2E รับงาน → แผน → ถาม/ตอบเมื่อจำเป็น → confirm → execute → verdict/receipts → restart/status จาก revision เดียว |
| Worker operation | load/concurrency/queue/DB-lock/disk-full/clock-jump tests; stop/drain worker รุ่นเก่าก่อน upgrade; ไม่ replay unknown outcomes |
| Privacy | retention ของ request tombstones/job mappings/audits, erase และผลต่อ old backups ลงทะเบียนพร้อม operator procedure |
| Restore | off-host encrypted backup และ restore จริง ตรวจ keys, permissions, audit continuity และ erasure reconciliation |
| Witness/notary | witness อีกเครื่องตรวจ signed head ที่สด; notary user แยกจาก agent บน host ที่จะเปิดจริง |
| Soak/incident | 72 ชั่วโมงจริงบน target host, metrics/alerts, stop/rollback/incident drills และ outside review |
| People/model | capable-model evidence ตามเกณฑ์เดิม, named users จำนวนน้อย, owner supervision, ขอบเขตข้อมูลและ workflow ที่ตกลงกัน |

notary คนละ account บน Windows ของ Architect เป็นหลักฐานของเครื่องนั้น ไม่รับรอง Linux host หรือเครื่องที่จะเปิดใหม่ การมี RFC3161 code ไม่เท่ากับมี scheduled independent witness ที่ตรวจจริง.

## 5. ช่องว่าง RCT-7 ที่ยังต้องวิจัย/พัฒนา

ยังต้องพิสูจน์การเข้าใจ paraphrase/negation/ambiguity/multi-intent, การถามเฉพาะข้อมูลที่มีผล, การ invalidate dependent outputs เมื่อข้อมูลเปลี่ยน, provenance/freshness/conflicting evidence และ semantic verifiers หลาย domain การมี graph/receipt/hash ช่วยตรวจ execution แต่ hash ไม่พิสูจน์ความจริงหรือความหมายของเอกสาร.

bounded budget workflow เป็นหนึ่ง domain การเปิด signed write workflow ต้องมี approval binding กับ contract/version/action/policy/actor/workspace/nonce/expiry และ crash reconciliation ของผลปลายทาง ไม่อนุมานความพร้อมจาก read-only recovery.

ไม่สามารถให้เปอร์เซ็นต์ความสำเร็จทั้งโครงการอย่างมีหลักฐานได้ เพราะยังไม่มีน้ำหนักเป้าหมายและ capable-model holdout ของ revision นี้ ให้ติดตามแต่ละ gate และข้อบกพร่องที่ปิดได้แทน.

## 6. แผนงานร่วมกับ Claude

| ลำดับ | Codex/cloud | Claude/local | เกณฑ์ส่งต่อ |
| --- | --- | --- | --- |
| A | Review #202–#205 และ bounded jobs PR, retarget stacked PR เมื่อ dependencies merge แล้ว push validation commit | ตรวจ GUI logs และ dependency PR ของตน | SHA และ CI ชัดเจน; ไม่ merge/force-push branch อีกฝ่าย |
| B | Backend lifecycle/authorization/audit/DB-failure tests | Desk lifecycle/accessibility/reconnect/video | รันกับ combined SHA เดียว; ส่ง schema ที่คง version |
| C | เสนอ budget-path audit findings/oracle requirements โดยไม่แก้ research runner ซ้ำ | exact live configuration, fake API rehearsal, model/provider pinning | main และ auxiliary calls อยู่ใต้ guard เดียวกันหรือถูกปิดโดย protocol |
| D | ตรวจ raw outcomes และ verifier coverage | live/holdout runners บน host ที่พร้อม | Architect อนุมัติ model/provider/งบก่อน paid call |
| E | Recovery/retention/load และ pilot checklist | Windows install, host/model/browser และ demo | independent operational evidence ก่อนรับ external users |

ข้อมูลที่ยังต้องได้รับก่อนจ่ายเงินจริงคือ model ID และ provider/routing ที่อนุญาต, วงเงินรวมสูงสุดและ reserve, workflow/roles ที่จะเปิด, รวมถึง combined SHA/GUI evidence จาก Claude ไม่ต้องส่ง token, API key หรือ `.env`.

## อัปเดตระหว่างรอบนี้

GitHub main ขยับเป็น `368537d5` หลัง merge dependency PR #200/#201 (NLTK/msgpack) และ branch Codex รวมการเปลี่ยนแปลงแล้ว Claude เปิด PR #206 (`85281fba`) สำหรับ W12 live runner; ไฟล์ที่ประกาศใน PR ไม่ซ้อนกับ PR #207 ของ Codex ยังไม่ถือว่ารวม W12 นี้เข้ากับ backend ใหม่หรือรันทดสอบ combined W12 แล้ว

W12 ใช้ children แยก OS processes ตาม PR #206 จึงต้องตรวจ shared token/cost cap และ provider-side limit ของทั้ง parent และ children ก่อน paid run ไม่อนุมานว่า parent budget guard เห็นค่าใช้จ่าย children ทั้งหมด ไม่เปลี่ยน runner ของ Claude ใน PR นี้

GitHub push banner รายงาน 4 low vulnerabilities บน default branch ณ รอบนี้ แต่ Dependabot inventory API ตอบ 403 (`Resource not accessible by integration`) จึงยังแจกแจง package/version/fix จาก API ไม่ได้ ต้องให้ผู้มีสิทธิ์ตรวจ inventory ก่อนปิด security finding ห้ามใช้ตัวเลข 47 รายการในรายงานเก่าเป็นยอดปัจจุบัน หรืออ้างว่าปัจจุบันไม่มีช่องโหว่จากผล scan ที่ผ่านบางชุด
