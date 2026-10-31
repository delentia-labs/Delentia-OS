# Citation acquisition และจำนวนรอบงานที่ยังเหลือ

Implementation 8523af2d; combined application d112bfcc; วันที่ 31 ตุลาคม 2026
Runtime ตอนแรก unavailable และ exec ใช้ไม่ได้ จากนั้นกลับมาและตรวจ workspace สะอาดก่อนแก้
ไม่ทราบสาเหตุ platform interruption จากหลักฐานนี้

## สิ่งที่พัฒนา

เพิ่ม citation_acquisition.py ใช้ current_bytes reader เดิม (POSIX descriptor-relative no-follow)
อ่านได้สูงสุด 16 ไฟล์ ไฟล์ละ 20 KB ตาม reader เดิม ไม่เพิ่ม parser หรือ file-read path ที่ข้าม security checks
ตรวจ allowlist, secret/traversal paths และ duplicate paths ก่อนอ่านไฟล์ใด ๆ
ตรวจ expected SHA256 กับ bytes ที่อ่านจริง แล้ว decode UTF-8 แบบ strict โดยไม่ normalize CRLF
ไม่รับ caller-supplied source text

Batch receipt ผูก actor/workspace/policy/catalog, contract ID/version/plan digest,
source identity/path/hash/byte length และ source bundle digest
เรียก receipt callback ก่อนคืน bundle; callback ล้มเหลวหรือ source หลัง ๆ ผิดจะไม่คืน partial bundle
ไม่มี automatic retry, dispatch หรือ write effect เพิ่ม

ขอบเขต: application ต้อง authenticate และกำหนด allowed_paths/current context เอง
callback ต้องต่อกับ durable persistence ที่เหมาะสมก่อนเปิด service; รอบนี้ยังไม่เชื่อม HTTP citation route
receipt hash ไม่ใช่ signature ไม่รับรอง authorship/truth/freshness หรือ atomic multi-file snapshot
ไม่มีการอ้างว่าทดสอบ directory-swap race ทุกกรณีแล้ว; ยังต้องทำ fault injection และ receipt recovery integration

## ผลตรวจ

- Tests ใหม่ 15 กรณี: real filesystem, unauthorized/traversal/secret/duplicate paths,
  changed bytes, invalid UTF-8, oversize, file/parent symlink, FIFO, callback failure, partial-batch refusal
- Source regressions 242 passed, 238 warnings, 6.34 วินาที
- Combined regressions 242 passed, 238 warnings, 6.37 วินาที (ชุดเดียวกัน ไม่บวก)
- Ruff passed; Linux Mypy source 284 files passed
- ไม่มี full suite ใหม่, real model, paid API, GUI video หรือ native first-run ในรอบนี้
- CI ของ checkpoint เก่า 3b4ca39c: CodeQL, lint/type, packaging/install, security checks ผ่าน
  Python 3.10–3.12 ยัง in_progress ตอนตรวจ; ไม่ใช้ผลนั้นรับรอง SHA ใหม่

## ต้องพัฒนาอีกกี่รอบ

ไม่สามารถรับประกันจำนวนรอบจนเข้าใจงานทุกชนิดได้ โดยยังไม่มี capable-model holdout
สำหรับขอบเขตที่ควรประกาศจริงคือ supervised use ใน 2–3 กลุ่มงาน และ self-install experimental preview:
ประมาณ 6–9 รอบงานที่มีเกณฑ์จบ โดยมี 6 กลุ่มหลักและเผื่อ 0–3 รอบแก้จากผลทดสอบ
นี่เป็น planning estimate ไม่ใช่วันส่งมอบ/วงเงิน/รับรองความสำเร็จ และไม่ใช่จำนวนแชทหรือ commits
หนึ่งรอบอาจมีหลาย PR; หาก evaluation ไม่ผ่านต้องปรับขอบเขตหรือเพิ่มรอบ

| รอบ | งาน | เกณฑ์จบ |
| --- | --- | --- |
| 1 | ปิด acquisition → persistence → public capability route | Auth/source/receipt/version bindings; cross-user, changed-file, callback crash, restart tests |
| 2 | เพิ่ม semantic verifier สำหรับ 2–3 workflow | Oracle จับ citation entailment/coverage, document fields/conflicts, table units/currency/rounding ตามขอบเขต; unsupported ไม่ fallback |
| 3 | Clarification และ selective invalidation | Material input เปลี่ยนแล้ว descendants/approval ถูก invalidate; historical results แยก revision; uncertain effects ไม่ replay |
| 4 | Budget/freeze และ exact-configuration rehearsal | NaN entry, token reservations, loopback freeze findings ปิด; concurrent/uncertain/crash tests; fake counters ตรง ledger |
| 5 | Capable-model canary และ holdout | Freeze code/model/settings/policy/roles; อนุมัติวงเงินก่อน paid; task success/false acceptance/clarification/latency/cost พร้อม raw outcomes |
| 6 | Self-install/Desk/release evidence | Native first-run, real-data lifecycle, restart/update/rollback/uninstall, video, external tester feedback และ claims ตรงหลักฐาน |

CI/review ต้องผ่านตลอดแต่ละรอบ ไม่ใช่รอทำครั้งเดียวท้ายโครงการ
งาน Claude ด้าน budget/research/native Desk สามารถขนานกับ Codex backend เพื่อลดเวลารอ
ไม่ต้องมี central Delentia host เพื่อเข้า phase เหล่านี้

## นิยามความพร้อม

- พร้อมตรวจโค้ดและทดลองเฉพาะขอบเขต: มี implementation/tests แล้ว แต่ยังต้องปิด CI/review
- พร้อม paid canary: จบ freeze/budget/rehearsal และมี model/provider/วงเงินจริง ไม่ต้องรอ general autonomy
- พร้อม self-install preview: มี first-task/install/demo evidence และ known limitations ตาม claims ที่เปิด
- general autonomous RCT-7: ยังไม่มีหลักฐานพอและไม่กำหนดจำนวนรอบตายตัว

จุดเสี่ยงที่ยังเหลือคือ semantic coverage, source authority, durable receipt integration/recovery,
ผลของ clarification ต่อแผน, model false acceptance และ usability บนเครื่องผู้ใช้จริง
