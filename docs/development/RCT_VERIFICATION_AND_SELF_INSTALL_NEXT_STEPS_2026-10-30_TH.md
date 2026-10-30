# RCT-7: verification integrity และแผนก่อน paid evaluation / open-source preview

วันที่ตรวจ: 2026-10-30 UTC ผู้รับผิดชอบ: Codex/cloud

เป้าหมายการเปิดตัวคือผู้ใช้ติดตั้ง Delentia บนเครื่องหรือ VPS ของตนเอง ไม่ใช่บริการให้ผู้ใช้เข้ามารันงานบน host กลางของ Delentia งานด้าน multi-tenant hosting จึงไม่ใช่เงื่อนไขเปิดตัวนี้ ส่วนการป้องกันข้อมูล การสำรองข้อมูล และค่าใช้จ่ายของ installation ยังต้องมีคู่มือและการทดสอบที่ตรงกับขอบเขตที่ประกาศ

## Revision และขอบเขต

- main ที่ตรวจ: `d1376d21f6dd88b3fa98a9263525859d27916c4b`
- ฐาน Codex: PR #212, `544f222a` (local-first onboarding)
- โค้ด RCT ใหม่: `918ca9de`, `796511d1`, `52dda3bb`, `b5af50ad`
- Combined revision สำหรับตรวจ: `b421bf6d183cb929c1bdcb3260e08718a445ccb5`
- รวม Claude #213 `4cb36a3` (bundled fonts) และ #214 `bce3c91` (budget guard) เพื่อทดสอบร่วม แต่ไม่ได้คัดการแก้ของ Claude เข้า PR โค้ด RCT ของ Codex

ตัวเลขในรายงานนี้เป็นผล cloud ของ revision ที่ระบุ ไม่ใช่ checkpoint ทางการบน main และไม่ควรนำไปแทนตัวเลขที่ `scripts/update_test_checkpoint.py` สรุปจาก CI ของ main ทุกการ merge/เปลี่ยน SHA ต้องตรวจหลักฐานของ revision นั้นใหม่

ไม่มีการเรียก paid API และไม่มีการประกาศ release milestone ในรอบนี้

## ข้อบกพร่องที่แก้จริง

### 1. Schema-valid output ไม่เพียงพอจะยืนยัน criterion

ก่อนแก้ handler สามารถคืน `satisfied: false` หรือคืน criterion คนละตัวแต่ยังผ่าน output schema ได้ scheduler จึงอาจนับ component ว่าเสร็จโดยไม่มี verdict ที่ยืนยัน criterion นั้น

เพิ่ม `CriterionVerification` และบังคับให้ verifier ที่ครอบคลุม criterion ส่ง output ของชนิดนี้ ผูกหนึ่ง verifier node กับหนึ่ง criterion ตรวจทั้ง raw output และ typed output ว่า `criterion_id` ตรงและ `satisfied is True` การใช้ `1` หรือข้อความ `"true"` ไม่ใช่ boolean true ที่ยอมรับได้ หากไม่ผ่านจะหยุดก่อน callback บันทึก completion และก่อนเผย output ให้ dependents

การตรวจนี้ยืนยันว่า handler ส่ง verdict ตรง contract ไม่ได้ทำให้ handler ที่เขียน oracle ผิดกลายเป็น oracle ที่ถูกต้อง

### 2. แผนและข้อมูลที่ตรวจแล้วต้องไม่เปลี่ยนผ่าน inspection references

ทำ snapshot ของ program, parameters และ answers ภายใน scheduler; registry เป็น read-only mapping; property ที่ใช้ดู plan/nodes/outputs/answers คืนสำเนา ป้องกัน caller แก้ nested values แล้วเปลี่ยน execution หลัง preflight เพิ่ม in-progress guard สำหรับ reentrant execution และไม่อนุญาต reset failure ผ่าน property แล้ว replay instance เดิม

ก่อนเริ่ม observation ตรวจ handler implementation และ literal parameter constraints ที่ทราบแล้ว ส่วน constraints ที่ต้องอาศัย upstream output ยังต้องตรวจเมื่อมี input จริง scheduler นี้ไม่ใช่ sandbox สำหรับ Python code ที่ application ลงทะเบียนเอง

### 3. Hash chain ที่ถูกต้องยังอาจบรรจุผลคำนวณผิด

เพิ่มการตรวจ receipt outputs ด้วย schema ของ fixed budget executor ตรวจ source path/hash binding และ criterion binding แล้วคำนวณซ้ำเฉพาะ pure arithmetic/copy handlers จากข้อมูลใน receipts เพื่อตรวจ totals, remainder และ composed report ไม่ execute tools หรือ effects ใหม่ขณะอ่านประวัติ

การเปลี่ยน source file หลังจบงานไม่ทำให้ status lookup อ่านไฟล์ใหม่หรือเขียนประวัติทับ ผลเก่ายังคงหมายถึง bytes ที่สังเกตในเวลานั้น ไม่ได้หมายถึงราคาปัจจุบันหรือความจริงของผู้ขาย

### 4. Public report ต้องตรงกับ execution history

ก่อนส่ง stored contract กลับ ตรวจว่า `execution_report` ตรงกับผล `compare_budget` ใน validated receipts และสถานะ `complete` มี receipts/report ครบ ป้องกัน API แสดง verified=true บน report คนละชุดกับที่ตรวจจริง มี HTTP negative test โดยสร้าง controlled internal inconsistency แล้วตรวจว่า status ไม่ส่ง verified result ออกมา

ไม่มีการเพิ่ม public import/write route เพื่อสร้าง inconsistency ในการทดสอบนี้ และไม่เปลี่ยน API/ความหมายของ JobService, episode journal, idempotency หรือ resume

### Compatibility ที่ต้อง review

Output shape ของ valid `verified_budget_v1` ยังเหมือนเดิม ไม่เพิ่ม executor version โดยไม่มีเหตุผล แต่ application ที่ลงทะเบียน custom criterion verifier ต้องใช้ output model ที่สืบทอด `CriterionVerification` และคืน criterion ID/boolean ที่ถูกต้อง verifier แบบเก่าที่ไม่มี contract นี้จะถูกปฏิเสธก่อนเริ่มงาน ประวัติที่มี hash ถูกแต่ semantic data ไม่สอดคล้องกันจะเปิดเป็น verified history ไม่ได้ ไม่มีการซ่อม/เขียนทับประวัติหรือ replay effects อัตโนมัติ

เส้นทาง verified reads นี้ยังต้องใช้ POSIX descriptor-relative/no-follow support; API ปฏิเสธด้วย 501 บน platform ที่ไม่รองรับ ผล Windows installer/Desk smoke ไม่ได้ยืนยันว่า budget verification นี้ทำงานแบบ native Windows ได้ ต้องประกาศ platform limitation หรือพิสูจน์ backend ที่รองรับก่อนเสนอ workflow นี้ให้ผู้ใช้ Windows

## หลักฐานและข้อจำกัดการทดสอบ

Focused regressions ของ stored receipts, HTTP status, governed budget และ read-only service: **99 ผ่าน** หลังการแก้ projection ส่วนสุดท้าย Ruff ผ่าน และ Mypy แบบ Linux ตาม CI scope ผ่าน **277 source files** (มี notes เกี่ยวกับฟังก์ชันที่ไม่มี type annotations; ไม่ได้หมายความว่าทุกบรรทัดถูกตรวจแบบ strict)

Full suite ของ combined SHA ข้างต้นจบที่ **9,165 passed / 10 failed / 45 skipped / 1 xfailed** ใช้เวลาประมาณ 10 นาที 31 วินาที: 9 failures ต้องใช้ Ollama model ที่ยังไม่มี และ 1 crawler failure เพราะ native DNS resolve ไม่ได้ รายละเอียดและ checksum อยู่ใน `rct-verification-20261030/summary.json` ไม่ใช้ผลนี้แทนผลของ revision ใหม่

Ollama ใน cloud ยังไม่มี model และ native DNS ของ cloud ยัง resolve ไม่ได้ นี่เป็นข้อจำกัดของ integration environment นี้ ไม่ใช่หลักฐานว่า core self-install เสีย และไม่ใช่เหตุให้ต้องสร้าง host กลางก่อน paid evaluation บนเครื่องอื่น ต้องเลือก provider/workflow/OS ที่จะวัดแล้วตรวจ prerequisites ของเครื่องนั้นจริง หากประกาศรองรับ Ollama/crawler ต้องมีผล integration ของเส้นทางเหล่านั้น ห้ามใช้การ skip แทนหลักฐานว่าปิด finding แล้ว

### A/B ของ execution integrity

Baseline คือ `544f222a`; treatment โค้ด `52dda3bb` (การแก้ missing-receipt admission เพิ่มภายหลังใน `b5af50ad`; ไม่เปลี่ยน A/B cases เดิม) ไม่มีการใช้โมเดล ทั้งสอง arm ใช้ cases และ expected outcomes เดียวกัน

| ชุด | Baseline | Treatment | สิ่งที่วัด |
|---|---:|---:|---|
| Framework targeted cases | 2/11 ถูกตาม oracle | 11/11 | verdict binding, literal admission, snapshot mutation, reentry และ sticky failure |
| Budget receipt consistency | 1/7 ถูกตาม oracle | 7/7 | valid positive control และ well-hashed history ที่มีผล/source/criterion ไม่สอดคล้องกัน |

จำนวนนี้เป็น authored regression cases ไม่ใช่ holdout อิสระ ไม่ใช่เปอร์เซ็นต์ความสมบูรณ์ RCT-7 และไม่ใช่คะแนนความเข้าใจของ capable model กรณี reentry ตรวจจำนวน handler invocations ไม่ได้อ้างว่า baseline รายงานสำเร็จสองครั้ง

Microbenchmark เป็น single-node CPU path 1,000 samples ต่อ arm เวลาอยู่ระดับไมโครวินาที ตรวจ raw JSON สำหรับ median/p95 ไม่ใช้สรุป task latency หรือ speedup เพราะมี noise และการรันต่างช่วงเวลา ผล correctness สำคัญกว่าความต่างเวลาใน probe นี้

สคริปต์ทำซ้ำอยู่ใน directory หลักฐานข้างเอกสาร ใช้ `PYTHONPATH` ชี้ checkout ของ arm จาก working directory ที่อยู่นอกทั้งสอง repo และใช้ Python environment เดียวกัน เช่น:

```sh
cd /tmp
PYTHONPATH=/absolute/path/to/checkout /path/to/python \
  /absolute/path/to/framework_ab.py --arm baseline --out /tmp/framework-baseline.json
PYTHONPATH=/absolute/path/to/checkout /path/to/python \
  /absolute/path/to/receipt_ab.py --arm baseline --out /tmp/receipt-baseline.json
```

### Fonts และ self-install evidence

Claude #213 ผ่าน Frontend, clean-wheel package check และ lint/security jobs ที่ตรวจจาก GitHub ส่วน Python matrices ยังต้องรอผลครบ ณ เวลาบันทึก ไม่มีการแก้ GUI ซ้ำในเลน Codex

ใน cloud: ติดตั้ง dependencies ก่อน แล้ว build static Desk สำเร็จใน container ที่ใช้ `--network none`; นี่ไม่ใช่การอ้างว่า npm install ทำงาน offline ได้ Browser ตรวจโหลด font faces ไทย/อังกฤษ 17 combinations จาก local resources และไม่พบ external font requests ใน probe นั้น

Accessibility: 112 page loads = 28 pages × ไทย/อังกฤษ × 375/1280 px ไม่พบ axe violations หรือ sideways scroll บนเส้นทางที่ script ตรวจ นี่เป็น API-unavailable page sweep ไม่ใช่ end-to-end contract lifecycle หรือการรับรอง accessibility ทุก interaction

Wheel ที่รวม static Desk ผ่าน fresh-environment installation contract ทั้ง imports, CLI/doctor, scripted demo, health/models API, cross-process memory และ package-directory read-only รวม 6 กลุ่ม Demo แบบ scripted พิสูจน์ installation plumbing ไม่ได้พิสูจน์ความสามารถโมเดล

ตรวจ HTTP budget workflow เพิ่มจาก installed wheel โดยใช้ application modules ใน site-packages จริง: plan → confirm → arithmetic/verdict → เปิด app/factory ใหม่แล้ว status ยัง verified รวม anonymous access และ missing-receipt refusal ผ่านครบ การเปิด application ใหม่ใน process เดียวไม่ใช่ kill/restart crash test

ยังไม่มีวิดีโอ workflow จริงใหม่ที่แสดง capable model ตั้งแต่ setup จน result/restart ในรอบนี้

## สถานะ RCT-7 ตามการออกแบบ

| ขั้น | สิ่งที่มีและเพิ่มรอบนี้ | สิ่งที่ยังขาดก่อนอ้างว่าใช้ทั่วไปได้ |
|---|---|---|
| R1 Observe | bounded evidence acquisition, pinned bytes/hash และ source binding | freshness, trust ของ source, conflicting sources และ provenance ที่มีความหมาย |
| R2 Analyze | typed contract/criteria และ domain-specific planning | ambiguity, negation, paraphrases และ multi-intent ไทย/อังกฤษบน holdout |
| R3 Deconstruct | typed DAG/registry, dependencies และ preflight constraints | trusted handlers หลาย domain และการตรวจว่างานที่แตกครอบคลุมเจตนาจริง |
| R4 Reverse reasoning | criterion → verifier → typed inputs → evidence/receipt ตรวจย้อนใน budget workflow ได้แน่นขึ้น | necessary-condition reasoning ที่โมเดลสร้างเองและถูก oracle ตรวจในโจทย์ใหม่ |
| R5 Core intent | versioned intent/clarification ที่มีอยู่เดิม; scheduler ไม่รับการแก้ snapshot แทน continuation | การถามที่เปลี่ยนคำตอบจริง, invalidation ข้ามหลายผลลัพธ์ และคุณภาพการ resolve multi-intent |
| R6 Reconstruct | tests ยืนยัน plan-first แล้ว confirm ก่อน governed reads | Desk lifecycle E2E บน combined SHA รวม identity/reconnect/cancel/restart |
| R7 Compare | strict criterion verdict, arithmetic/dataflow receipt verification และ public-report binding | semantic verifiers หลาย domain, model false acceptance และการหยุด/ถามเมื่อหลักฐานไม่พอ |

คำนิยามปัจจุบัน: **runtime ทดลองที่ติดตั้งใช้งานในเครื่องได้ มี governed execution และตรวจผลเฉพาะ domain ได้จริง พร้อมกลไก RCT-7 บางส่วนที่บังคับด้วยโค้ด** ยังไม่ใช่ autonomous RCT-7 ทั่วไป ไม่มีเหตุผลให้สรุปเปอร์เซ็นต์ความสมบูรณ์ทั้งโครงการจากจำนวน tests หรือจากการมี graph/receipts

## Budget guard: findings ที่ต้องส่งต่อ Claude

Probe บน #214 `bce3c91` ยืนยันว่าราคาติดลบ/NaN และ in-flight call-count cap เดิมถูกปฏิเสธแล้ว แต่ยังมีสองกรณี:

1. `ExperimentLedger` รับ `BudgetPolicy` โดยไม่เรียก validate ที่ entry point เส้นทาง live adapter/provider บางเส้นทางก็ไม่ validate; policy ที่ USD fields เป็น NaN ทำให้ comparison ไม่ปฏิเสธ `before_call` การมี helper `.validate()` อย่างเดียวไม่พอ ต้องบังคับก่อน ledger/run/provider ใช้งาน
2. การเช็ก input/output token caps ใช้ completed totals เมื่อมีสอง in-flight calls ที่ cap input/output อย่างละ 1 และ call cap 3 ทั้งสอง fake calls ยัง dispatch ได้ แล้ว settle รวมอย่างละ 2 ต้อง reserve outstanding token allowances ควบคู่ money/calls และกำหนด uncertain-call behavior ให้ชัด

นี่ไม่ได้แปลว่า positive-price monetary reservation ทั้งหมดถูกข้ามได้ Probe ใช้ fake provider เท่านั้น ส่ง reproduction และผลไว้ใน review comment ของ #214 แล้ว Codex ไม่แก้ `research/daaes/budget_guard.py` ซ้ำ

## แผนรอบถัดไปและเกณฑ์จบ

### รอบ A: รวม revision และปิด budget admission

- Claude ปิดสอง findings ด้วย invalid-policy, concurrent-token และ uncertain/crash cases ผ่าน entry points จริง
- Review #212–#214 และ dependencies ของ backend แล้วเลือก combined SHA ที่ผ่าน checks ครบ
- PR RCT นี้เป็น stacked draft บน #212; หลัง dependencies รวม main ให้ retarget main และ push commit ใหม่เพื่อรัน CI เต็ม ห้ามอาศัย checkmarks ของ SHA เก่า
- เกณฑ์จบ: ไม่มี budget admission gap ที่ทราบ, source และ installed artifact มีหลักฐานผูก SHA/checksum ชัด

### รอบ B: freeze paid protocol โดยยังไม่ dispatch

- เลือก workflow ที่จำเป็นต้องสร้างคำตอบด้วยโมเดลจริง พร้อม whole-workflow oracle; deterministic budget executor ไม่ใช่ตัวแทน model ability
- แยก development/holdout ก่อนปรับ prompts/planner; ครอบคลุมไทย/อังกฤษ, negation, ambiguity, multi-intent, conflicting evidence, stale evidence และ changed inputs
- Pin code, provider/model/routing, settings, prompts, schema/policy, ทุก main/judge/critic/child/retry role
- กำหนด USD รวม/ต่อ run, token/call caps, reserve และ provider-side spending cap โดยเจ้าของ ยังไม่มีการอนุมัติวงเงินในรอบนี้
- ซ้อม exact configuration ด้วย fake endpoint เทียบ ledger กับ fake bill รวม concurrency, uncertainty และ crash/restart
- เกณฑ์จบ: manifest ที่ executable และ reproducible; draft manifest ต้องปฏิเสธ paid dispatch

### รอบ C: paid canary และ capable-model holdout

- เริ่มทีละ run หลังมีขอบเขต/งบ ตรวจ usage/bill เทียบ ledger และเก็บ raw outcomes
- ใช้ installation จริงทำงานที่ไม่ใช่ `--scripted` แล้วตรวจ result ตาม oracle ก่อนขยาย battery
- รายงาน task success, false acceptance, clarification quality, latency, usage และต้นทุนต่อ task สำเร็จ แยก infra failures ออกจาก model mistakes และแยก development ออกจาก holdout
- เกณฑ์จบ: ข้ออ้างทุกข้อมี raw evidence ไม่ตีความ zero-generation execution เป็น model success

### รอบ D: Desk และ first-run สำหรับ open-source preview

- Claude รับผิดชอบ UI/Windows/local model/launcher และ GUI E2E; Codex รับ backend/verifier/evaluation integration ตาม schema ที่ตกลง
- ใช้ combined SHA เดียวกันทดสอบ setup → task → plan → clarification/confirmation ที่รองรับ → execute → verdict/receipts → restart/status รวม identity/reconnect/cancel
- บันทึกวิดีโอจริงและข้อผิดพลาด; ตรวจ Thai text/layout/labels กับการใช้งานจริง ไม่ใช้ font-load proof แทนความครบของคำศัพท์
- ให้ผู้ทดลองอิสระติดตั้งตามคู่มือบน OS ที่ประกาศ รองรับ update/rollback/uninstall และอธิบาย keys, costs, local paths, privacy/backup และ feedback
- Linux evidence, Windows CI/manual first-run และ native macOS evidence ต้องแยกกัน ไม่ขยายการรับรองข้าม OS
- เกณฑ์จบ: คนที่ไม่ได้สร้างระบบทำ first task ได้และทราบขอบเขต experimental preview

### รอบ E: ขยาย RCT-7 ทีละ domain

- เพิ่ม trusted handler/verifier ของ domain ถัดไปจากข้อมูล failure ของ holdout ไม่สร้าง planner อีกชุดโดยไม่มีเหตุผล
- ทุก material criterion ต้อง trace ถึง necessary inputs, handler, evidence, receipt และ semantic verifier
- ทดสอบ changing answers → invalidation, conflicting evidence → stop/clarify, และการไม่อ้าง verified เกินขอบเขต oracle
- Write workflow เปิดทีละประเภทหลังพิสูจน์ approval/action/version bindings และ actual-effect crash reconciliation
- เกณฑ์จบ: มี E2E และ negative cases ของแต่ละ domain/surface ไม่ใช้ shared-loop coverage แทน surface evidence

Restore/witness/notary separation/soak ยังคงเป็นงานตามขอบเขต workflow ที่อ้างว่าจะทนทาน แต่การสร้าง host กลางหรือ multi-tenant service ไม่ใช่เงื่อนไขสำหรับ open-source self-install preview นี้

## Recovery checkpoint เพิ่มเติม

หลัง runtime กลับมา ตรวจ main ได้ `61cdea9c093b5f0cf597f162b66b0f277fe18b5f` ซึ่งเพิ่ม #209 holdout sheet และ #211 W09 runner; ผล full suite ข้างต้นยังเป็นของ combined SHA เดิม ไม่ครอบคลุม main ใหม่นี้

Ollama/PostgreSQL หยุดพร้อมกันที่ 2026-10-30 08:29:45 UTC ด้วย exit 255 และ Docker รายงาน OOMKilled=false ทั้งคู่ จึงยังสรุปสาเหตุ platform interruption ไม่ได้ หลัง refresh proxy แล้ว pull เริ่มรับ blob ได้จริง แต่ค้างที่ cache ประมาณ 330 MB ก่อนเครื่องหยุด ยังไม่มีหลักฐาน model completion/digest/inference; ไม่เริ่ม pull ใหม่โดยไม่ตรวจ cache/process และ headroom ก่อน

Package checks ของ PR #215 ที่ code SHA `b5af50ad` ผ่านทั้ง clean-wheel และ optional-extras jobs แต่ stacked PR นี้ยังต้อง retarget main หลัง dependencies พร้อมแล้วรัน CI เต็มตาม revision ใหม่
