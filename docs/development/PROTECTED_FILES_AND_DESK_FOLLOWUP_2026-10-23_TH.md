# Protected files, host และ Desk: checkpoint รอบต่อเนื่อง

อ้างอิง implementation `478b11a` ต่อจาก `704798d` บน PR #168. ผลในเอกสารนี้ผูกกับ branch และ host รอบนี้ ไม่ใช้แทน release gates ของ main หรือการรับรอง production.

## สิ่งที่เปลี่ยนจริง

`file_unchanged` เลิก resolve/check/read แยกขั้นตอน เปลี่ยนเป็น lexical path policy และ descriptor-relative acquisition โดยปฏิเสธ symlink ทุก relative component ด้วย O_NOFOLLOW. ยอมรับเฉพาะ regular file, อ่านเป็น chunks, จำกัด 64 MiB, ตรวจ size/mtime/ctime ก่อนและหลังอ่าน และปฏิเสธแพลตฟอร์มที่ไม่มี POSIX no-follow. การเปลี่ยนนี้ตั้งใจทำให้ protected-file contracts บนแพลตฟอร์มที่ไม่รองรับ fail closed; ไม่ fallback กลับไปอ่านแบบเดิม.

เพิ่ม 17 tests: เปรียบเทียบ bytes ที่เปลี่ยน, invalid paths 8 แบบ, leaf/directory symlinks, FIFO, missing/oversize file, สลับ directory ก่อนเปิด, สลับ directory หลังเปิดแล้วให้ descriptor ยึดต้นฉบับ และเปลี่ยน bytes ระหว่างอ่าน. Regression รวม contract/budget/scheduler/planner 142 passed. Ruff ผ่านทั้ง CI scope; Mypy CI-tools environment ผ่าน 260 source files.

ข้อจำกัด: digest เป็นการสังเกต bytes ไม่ใช่ atomic filesystem snapshot, vendor authenticity หรือ authorization ของผู้ใช้แต่ละคน. Workspace root และ ancestors ต้องอยู่ภายใต้ operator ที่เชื่อถือได้; ยังไม่ใช่หลักฐานรองรับ hostile multi-tenant filesystem หรือ hard-link provenance. การอ่าน MCP ทั่วไปที่ไม่ได้เลือก verified_read ต้อง review แยกต่างหาก.

## Host interruption และ model

ก่อนเริ่มรอบนี้ disk 32 GB ใช้ประมาณ 15 GB เหลือประมาณ 16 GB; RAM available ประมาณ 32 GB. Containers Ollama/PostgreSQL เดิมหยุด exit 255 หลัง runtime interruption. กู้ log การ pull ครั้งก่อนพบ proxyconnect `no route to host`; ไม่ได้ติดตั้งโมเดลสำเร็จ. ข้อผิดพลาด proxy อธิบาย download failure แต่ยังไม่พิสูจน์สาเหตุที่แพลตฟอร์มหยุด environment.

Refresh proxy ของ task-owned Ollama ผ่าน helper ที่ตรวจ bind mount/loopback, ไม่ snapshot/copy model, ตรวจ service แล้วลบ obsolete task containerเพื่อหลีกเลี่ยง VFS amplification. PostgreSQL เริ่มใหม่แล้ว. รอบนี้ไม่เริ่ม model pull ซ้ำระหว่าง full suite.

Artifact qwen2.5:7b = 4,683,073,952 bytes = ประมาณ 4.36 GiB. เกณฑ์ headroom 2×artifact+2 GiB = ประมาณ 10.72 GiB; free ก่อน pull รอบก่อนประมาณ 15.5 GiB เหลือส่วนเผื่อประมาณ 4.8 GiB. นี่เป็น planning guard ไม่ใช่ขอบเขตสูงสุดของการใช้ดิสก์หรือ storage ภายในแพลตฟอร์ม.

Native DNS ยัง gaierror. Chromium helper mode 4755 แต่ owner UID/GID 65534; unshare ถูกปฏิเสธเพราะ uid_map เป็น read-only. ต้องจัด host ที่รองรับ sandbox และ DNS จริง ไม่ใช้ --no-sandbox หรือปิด SSRF/DNS pinning. SSH config preflight ผ่าน ไม่ใช่หลักฐาน actual SSH connection.

เก็บ host samples แบบ bounded ทุก 10 วินาที: free bytes, MemAvailable, cgroup memory events, container status. ไม่มี environment variables, credentials หรือ signed download URLs. Samples พิสูจน์ช่วงที่เก็บเท่านั้น; ไม่มี platform termination logs จึงยังสรุป root cause ของทุก interruption ไม่ได้.

## Desk ที่เปิดทดสอบจริง และขอบเขตของ demo

GUI type-check, lint และ production build ผ่าน. เปิด static export บน loopback :3011 และ API แยกข้อมูล demo บน :8011. GET หน้า GUI, health, desk overview/sessions/models/tools ตอบ 200 ทั้ง 6 requests. เป็น actual HTTP smoke ไม่ใช่ browser interaction หรือ model success. ไม่มีผู้ใช้จริง/keys จาก operator state ใน demo workspace.

ทดสอบ actual Memory API ใน demo namespace แยก: บันทึกข้อความไทย `น้ำ กำลัง งบประมาณ 15,000.00 บาท`, อ่านกลับตรงทุกตัวอักษร แล้ว revoke และยืนยันว่าไม่อยู่ใน active list. ไม่ใช้ model generation. ผลนี้ไม่ยืนยันการ render ภาษาไทยใน browser.

Browser launch ยังล้มเหลวที่ sandbox จึงยังไม่มีภาพหน้าจอ/วิดีโอและยังไม่ได้คลิกใช้งาน end-to-end. ห้ามนำผล HTTP หรือ build ไปเรียกว่า GUI E2E ผ่าน.

ตรวจ source `desk_agent_stream.agent_events`: loop.run ส่ง goal/on_step แต่ยังไม่ส่ง acceptance criteria/planning context/on_plan/contract continuation. Summary ยังใช้ intent_verification เดิม. ดังนั้นการต่อ shared loop ไม่ได้ทำให้ Desk ได้ typed RCT contract lifecycle ครบโดยอัตโนมัติ.

Build เตือนว่า `headers()` ใน Next config ไม่ถูกใช้โดย static export อัตโนมัติ. ก่อนให้บริการเว็บต้องตั้งและทดสอบ security headers ที่ static host/reverse proxy จริง; npm build ผ่านไม่ยืนยัน deployment headers.

แผน demo หลัง host พร้อม:

1. ใช้ workspace/identity ใหม่ มีข้อมูลสังเคราะห์ไทยและอังกฤษ ระบุ SHA, model/digest และโหมด generation ให้เห็นในบันทึก.
2. Settings → เชื่อม gateway → ตรวจ Status/Models; ทดสอบ API down และ reconnect ว่าไม่แสดง success ค้าง.
3. Chat → ส่งงาน read-only ที่รองรับ → เห็น plan ก่อนผล → ถามงบ/สกุลเงินที่ขาด → ตอบ clarification ของ contract/version เดิม.
4. ตรวจผลตรงงบและเกินงบ รวมกรณี source hash เปลี่ยน, currency ขัดกัน, unsupported request; ทุกกรณีต้องมี verdict และเหตุผลตรงกับ verifier.
5. Sessions → ตรวจ components/receipts/criteria; cancel, refresh, reconnect และ restart ต้องไม่ทำให้ waiting กลายเป็น completed.
6. บันทึก browser video จริงพร้อม console/network errors, test results และ manifest/checksum; ตรวจภาษาไทย/font/line wrapping และซ่อน credentials ก่อนเผยแพร่. รีวิวผลก่อนโพสต์; รอบนี้ไม่มีการเผยแพร่ภายนอก.

## ระยะห่างจากเป้าหมายและลำดับพัฒนา

ไม่แปลงจำนวน tests ผ่านเป็นเปอร์เซ็นต์ความสมบูรณ์ของ RCT-7: งานแต่ละ gate มีน้ำหนักและความเสี่ยงต่างกัน และผ่าน scheduler ไม่เท่ากับเข้าใจโจทย์ทั่วไป.

| Milestone | มีแล้ว | งานที่ต้องปิดและหลักฐานจบ |
|---|---|---|
| M0 Security baseline | Protected-file acquisition + negative/race tests; push checkpoint | CodeQL Python ของ SHA ใหม่ต้องจบพร้อมตรวจ annotations; inventory dependencies และ combined-main revision ยังต้องตรวจ |
| M1 Stable integration host | service recovery, headroom guard, preflight, bounded telemetry | DNS/browser ผ่าน, official model download/digest/inference และ integration 9+3+1 กรณีผ่าน; ไม่ใช้ skipped แทน passed |
| M2 Scoped service | typed budget executor, dependency scheduler, completion receipts | server-enforced allowlist/versioned schemas, actor-selected workspace, concurrent two-user authorization; no fallback/write path |
| M3 Durable read-only jobs | contract version/CAS และ local receipt mechanisms | idempotency/status/cancel/continuation; real process kill ก่อนอ่าน/หลังอ่าน/หลังpersist, DB lock/disk full; no false completion |
| M4 RCT semantics | trusted budget compiler และ structured dependency execution | Thai/English ambiguity, negation, paraphrase, multi-intent, evidence conflicts; criterion→handler→receipt→verifier trace, selective invalidation |
| M5 Model evidence | execution A/B harness | แยก dev/holdout ก่อน tuning; pin model/settings/code/protocol; raw capability outcomes แยก infra/model failure และไม่รวม zero-generation เป็น model success; ไม่ใช้ paid API |
| M6 Desk contract lifecycle | GUI build/API smoke และ governed chat | versioned plan/wait/difference/receipt events + UI; actor/version continuation; E2E browser/video และ reconnect/restart tests |
| M7 Writes | existing approval/notary/journal building blocks | หนึ่ง workflow: signature bind contract/version/plan/action/actor/workspace/policy/nonce/expiry; reconcile ทุก crash boundary ก่อนเปิด |
| M8 Supervised pilot | release-level/operator design เดิม | exact artifact clean install/upgrade/rollback, separate notary user, off-host restore, independent witness, 72h soak, outside reviewer |

ลำดับ critical path: M0 → M1 → M5 → M8; พัฒนา M2/M3/M4/M6 ได้ระหว่างเตรียม host โดยยังไม่อ้าง model/GUI production readiness. M7 ต้องรอ contract/recovery bindings ที่พิสูจน์แล้ว. เป้าหมายรับงานแรกควรเป็น read-only workflow จำกัดขอบเขตและมีผู้ดูแล.

72-hour soak มีระยะเวลาขั้นต่ำจริง 72 ชั่วโมงหลัง host/config/artifact คงที่; full suite หรือการรันสั้นไม่สามารถนับแทน. ยังไม่ให้วันเปิด pilot จน blockers ของ host/model/identity/recovery ปิด.

## ผลรอบนี้

CodeQL checkpoint `478b11a`: Analyze Python/Rust/JavaScript/Actions และ aggregate CodeQL success; aggregate annotations = 0. เดิมเคยมี 3 high path findings ใน intent_contract.py. นี่เป็นหลักฐานผล PR check ของ SHA นี้ ไม่ใช่การรับรองว่า repository ไม่มี vulnerabilities; code-scanning inventory API ยัง 403. GitHub default-branch push summary ยังรายงาน 47 dependency alerts ซึ่งไม่ใช่ผล audit branch นี้.

A/B รันใหม่ 72 generated cases (24 canonical, 24 reordered, 24 invalid evidence), 3 timing repetitions ต่อ arm. Baseline `26139b0` vs current scheduler: canonical 24/24 ทั้งคู่; reordered 0/24 → 24/24; invalid evidence ปฏิเสธถูก 24/24 ทั้งคู่. Canonical median 0.948399 → 1.627826 ms (เพิ่มประมาณ 0.679 ms หรือ 71.6%). Timing วัดขณะมีงานทดสอบอื่นบน host จึงไม่ใช่ controlled production benchmark. Repeated timing ไม่ใช่ independent samples และ template cases ไม่ใช่ semantic holdout.

Dependency audit รอบนี้พบ GUI Next.js 16.3.8 มี 1 critical package (advisories 3 รายการ: GHSA-2464-fhr4-w9xw, GHSA-p3m5-59mp-jv5r, GHSA-673q-mjm6-r5xr). ตรวจ candidate แยกก่อน แล้ว pin Next.js และ eslint-config-next 16.4.2 พร้อม lockfile ใน commit `90fe749`. npm ci, type-check, lint, production build ผ่าน; static HTTP หลัง upgrade ตอบ 200. Production npm audit หลังแก้ GUI 0 findings และ Action 0 findings. ไม่ใช้ผลนี้อ้างว่า default branch 47 alerts ปิดทั้งหมด และไม่เท่ากับ full dev-dependency/Python inventory.

Python full suite รัน runtime source ของ `478b11a`; ระหว่างรันมีเฉพาะ docs และ GUI dependency update, ไม่มีการแก้ Python source/tests. ผลสุดท้าย **8,018 passed / 15 failed / 59 skipped / 1 xfailed**, 6,915 warnings, 715.35 วินาที (11m55), exit 1. รอบนี้ไม่ได้เก็บ coverage ใหม่.

Failures: 9 missing-model (Ollama generate HTTP 404 และ downstream llm_error), 3 Chromium sandbox (TC027 ไม่ได้ observed page), 1 native DNS crawler (ไม่เกิด success result จึงไม่มี status_code), 2 regex performance (0.604 และประมาณ 0.525 วินาที เกิน budget 0.5s). รายชื่อครบใน JSON evidence. ห้ามตีความ 59 skipped/1 xfailed ว่าเป็น integration ที่ผ่าน.

รัน regex audit สองกรณีแยกหลัง full suite: 2 passed, 15.13s โดยไม่เปลี่ยน source/threshold. แสดงความไวต่อสภาพแวดล้อมและภาระงาน แต่ไม่พิสูจน์สาเหตุเดียว; full-suite failures ยังคง 15. ขั้นถัดไปแยก controlled performance lane เก็บ CPU/time distributions และวิเคราะห์ matcher ก่อนเปลี่ยน algorithm หรือ test budget; ไม่เพิ่ม threshold เพื่อซ่อนปัญหา.

ข้อมูลผลและ SHA-256 ของ raw evidence อยู่ใน [JSON](evidence/PROTECTED_FILES_AND_DESK_2026-10-23.json). ไม่รวม private demo DB/operator keys/model weights ในชุดเผยแพร่. ผล CI ของ commit หลัง dependency/docs update ต้องตรวจแยกจาก CodeQL ที่ผ่านบน 478b11a; ไม่มีการ merge หรือประกาศ pilot-ready.
