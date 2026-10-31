# Capability อ้างอิงข้อความและเกณฑ์ phase ถัดไป

วันที่ 31 ตุลาคม 2026; เป้าหมาย open-source local-first/self-install ไม่ใช่ host กลาง
Implementation d6028b1b; combined application revision 139ac23f; main ที่ตรวจ b0110ef4
CI ของ checkpoint ก่อนหน้า 06230237 ยัง queued ตอนตรวจ ไม่ถือว่ารอบใหม่นี้ผ่าน CI
PR #219 ยัง HEAD 4c89d37a ไม่มี budget/freeze fix ใหม่ให้รับรอง

## สิ่งที่เพิ่ม

citation_verifier.py เพิ่ม oracle แบบ exact extractive citation และ capability/handler registry
ใช้ ComponentScheduler และ necessary-condition validator เดิม ไม่สร้าง execution engine อีกชุด
SourceBundle มี source identity, UTF-8 text และ hash; ExtractiveReport มีรายการข้อความคัดตรง
พร้อม start/end ซึ่งระบุเป็น UTF-8 byte offsets ข้าม Python/JavaScript ได้โดยไม่สับสนกับ UTF-16 indices
preserve whitespace, CRLF และ Unicode โดยไม่ normalize ก่อนตรวจ

ตรวจทุก extract ว่าตรงกับ source span จริง พร้อมตรวจ:

- source hash ไม่ตรงกับ text, source identities ซ้ำ, source ไม่รู้จัก
- missing/extra sources เมื่อเทียบ required_source_ids ที่ application กำหนด
- byte offsets ผิด, เกินขอบเขต, ข้อความว่าง หรือ duplicate extracts
- ทุก required source ต้องมี citation ที่ถูกต้อง
- schema ปฏิเสธ free-form summary ที่อยู่นอก extracts

registry ประกอบด้วย observed_texts_v1 (governed observation ไม่มี run function)
และ verify_extracts_v1 (pure verifier ไม่มี provider/file/tool side effects)
capability บังคับ typed input path จาก observed source ไป verifier
หาก verifier ให้ false scheduler ปฏิเสธและไม่ออก completion receipt ของ verifier

## ขอบเขตที่ห้ามขยายคำกล่าวอ้าง

verification_scope = exact_extractive_citations เท่านั้น
source hash ไม่ใช่ source authentication; source_id ยังต้องผูก acquisition receipts และ authorization
application ต้องกำหนด required identities เอง ห้ามให้ model ลดรายการเพื่อทำให้ผลผ่าน
ยังไม่เปิด HTTP route, ไม่ใช่ generic summary หรือ document-comparison workflow ที่เสร็จแล้ว

ข้อจำกัดที่มี test แสดง: คัด "100 THB" จาก "The amount is not 100 THB." ตรงกับ span จริง
แต่ไม่พิสูจน์ว่ายอดคือ 100 THB ดังนั้น oracle นี้ไม่ใช่ semantic entailment/claim truth judge
ไม่ประเมินความครบถ้วนของบทสรุป ความสำคัญของประโยค ความสด หรือความน่าเชื่อถือแหล่งข้อมูล
เอกสารสอง identity ที่มีเนื้อหาเดียวกันยังไม่พิสูจน์ว่าเป็น independent sources

## ผลทดสอบ

Tests ใหม่ 24 กรณี: hand-authored ไทย/อังกฤษ ไม่ใช่ model holdout
Source regression 227 passed, 238 warnings, 5.53 วินาที
Combined regression 227 passed, 238 warnings, 5.59 วินาที (ชุดเดียวกัน ไม่บวกยอด)
Ruff ผ่าน; Linux Mypy source 283 files ผ่านหลังแก้ชื่อ local variable ที่ทำให้ inferred type ขัดกัน
ไม่มี full suite ใหม่, browser E2E ใหม่, model A/B, paid calls หรือ video ในรอบนี้
ผล browser 112 page loads และ full suite ของรอบก่อนต้องอ้าง SHA เดิมของมัน

## ช่องว่างและงานถัดไปโดยมีเกณฑ์จบ

### 1. CI และ review

ต้องตรวจ SHA ที่ push จริง, review acquisition binding และขอบเขต verdict ก่อน merge
CI queued ไม่พิสูจน์ว่าโค้ดผ่านหรือระบุสาเหตุเป็น account limits ได้

### 2. ต่อ acquisition และ public capability schema

ให้ file authorization/no-follow acquisition เดิมสร้าง source bundle จาก bytes จริง
ผูก source identity/hash/receipt กับ contract/version/workspace/policy ไม่รับ text ที่ caller อ้างว่าอ่านแล้ว
public schema ต้องแยก proposed, reviewed, unsupported, execution outcome และ verification scope
เกณฑ์จบ: unknown source/receipt, cross-user path, stale source hash และ unsupported capability ถูกปฏิเสธก่อน execute

### 3. Semantic oracle ตาม workflow

- Extractive summary: เพิ่ม required topic/coverage ที่ผู้ใช้ review; citation integrity ไม่พอรับรองความครบ
- Document comparison: กำหนดสอง source identities, field mapping, conflicts และ missing values
- Table analysis: typed numbers/units/currency, rounding rules, tax/discount scope และ deterministic expected results
เกณฑ์จบ: oracle จับผลผิดที่ข้อความดูน่าเชื่อถือได้ และรายงาน unsupported semantics โดยไม่ fallback

### 4. Selective invalidation

ทำ durable input/plan revisions และ transitive invalidation; approval ต้อง rebind เมื่อ material input เปลี่ยน
ผลเก่าต้องคงเป็น historical snapshot ไม่ใช่ผลของ revision ใหม่
unknown external effect ต้อง reconcile ก่อน replay; pure DAG helper ไม่พอรับรอง recovery
เกณฑ์จบ: changed-input/stale-confirmation/crash-boundary tests บน persistence จริง

### 5. Free rehearsal ก่อน paid

Claude ปิด policy-entry NaN, in-flight token reservations และ #219 loopback exemption
ต้องมี concurrency/uncertainty/crash/restart evidence ไม่ใช่เพียง happy path
Freeze code/model/provider/routing/settings/prompts/schema/policy ทุก role/retry/child และ holdout
fake endpoint counters ต้องตรง ledger; malformed/over-budget requests ต้องไม่ dispatch
ยังต้องมี model/provider/วงเงินจริงที่กำหนดก่อน paid canary ไม่มีการอนุมัติค่าใช้จ่ายในรอบนี้

### 6. Model capability และ marketing

แยก development/holdout ก่อน tuning; baseline/RCT ใช้ model/data/budget เดียวกัน
วัด correctness, false acceptance, completion, clarification quality, latency และ cost
การถาม/ปฏิเสธทุกครั้งต้องไม่กลายเป็นวิธีทำคะแนนสูง
จากนั้นทดสอบ installation จริงและ Desk lifecycle พร้อม first task/restart/update/rollback/uninstall/video
เผยแพร่ experimental preview ด้วย claims ตาม evidence ไม่ใช้ deterministic tests แทนความสามารถโมเดล

สถานะ: experimental local-first runtime มี bounded HTTP review และ extractive citation oracle
ที่ต่อเข้ากับ scheduler ได้ แต่ยังไม่ครบ general-task RCT-7 และยังไม่ผ่าน paid/marketing gates ทั้งหมด
