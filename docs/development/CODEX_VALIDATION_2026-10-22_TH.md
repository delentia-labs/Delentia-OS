# Codex runtime validation — 22 ตุลาคม 2026

Branch: `codex/rct-clarification-full-validation-20261022`. Base: `41776ef546d8e7adfc8e33826c028b0b8936e6b8` (รวมงาน docs/research ที่ยังไม่อยู่บน main). ไม่ merge main และไม่เรียก paid API.

## ผลพัฒนา

เพิ่ม opt-in explicit acceptance contracts สำหรับงานอ่าน/ตอบใน CLI/API: แสดงแผนก่อน model/tools, ประเมิน contains/language-script/JSON-object/file-unchanged, mismatch → waiting_for_clarification, เก็บ original/revisions แบบ sealed namespace-scoped SQLite และ versioned continuation. คำตอบว่าง/stale/replay/competing claims ไม่ execute ซ้ำ. จำกัดเครื่องมืออ่าน; ยังไม่เชื่อม signed-effect approval continuation และไม่ใช่ full RCT-7. รายละเอียด [intent contracts](../concepts/intent-contracts.md) และ [แผนรอบถัดไป](CODEX_NEXT_ROUNDS_TH.md).

ปรับ regression ของ public claims ให้ตรวจข้อความ v0.3 ปัจจุบัน: experimental/self-hosted, external pilot ยังแยก, ผล exponent ทั้ง D<1 และ D>1 และ score ไม่แทน signature. ไม่เพิ่มข้อความเก่ากลับใน README เพื่อให้ test ผ่าน.

## ผลทดสอบจริง

| ชุด | ผล |
|---|---|
| Python เต็ม 3 workers, loadfile, timeout600, coverage | 7,861 passed, 18 failed, 59 skipped, 1 xfailed; 755.62 วินาที |
| Coverage ตาม scope คำสั่งด้านล่าง | 89,781/98,670 statements ≈90.99%; ผ่านเกณฑ์72% แต่รวม test modules ด้วย จึงไม่ใช่ production-only coverage |
| Focused runtime/CLI/API/growth regression | 111 passed; รวมอยู่ใน full suite ไม่บวกเป็น unique tests |
| ตรวจซ้ำ formatter/public claims/NLTK หลังแก้ test และเครื่อง | 62 passed; TERM=xterm-256color และ verified NLTK cache |
| HTTP integration แยก process | ผ่าน: real Uvicorn, provider HTTP, file tool, SQLite; restart waiting, blank409, revised plan before execution; scripted model4calls |
| TypeScript SDK | build ผ่าน; 73 tests ผ่าน |
| fdia-wasm | build ผ่าน; 32 tests ผ่าน |
| rct-edge | build ผ่าน; 37 tests ผ่าน |
| GUI | type-check/lint ผ่าน; build ไม่ผ่านเพราะโหลด Google Fonts ไม่ได้ |
| GitHub Action | tsc ผ่านแต่ ncc build ไม่ผ่าน @actions/core3.x exports/CommonJS resolution; test command ไม่ผ่านเพราะไม่มี tests |
| Native Tauri | ยังไม่ทดสอบ: ไม่มี cargo/rustc และ GTK/WebKit build dependencies |
| Python wheel | build/ติดตั้งใน fresh venv/contract persistence smoke/CLI help ผ่าน; ไม่ได้ publish package |
| Lint | changed files ผ่าน; ทั้ง repo มี59 findings ใน24ไฟล์เดิมที่ไม่ได้แก้ |
| เอกสาร | claim-sync ผ่าน, local file links63รายการไม่ขาด; ไม่ยืนยันทุก external link/anchor |

คำสั่ง full run (PostgreSQL เป็น test container บน loopback; DSN ส่งผ่าน environment ไม่เก็บ credential):

```bash
TIKTOKEN_CACHE_DIR=/workspace/.cache/tiktoken \
NLTK_DATA=/workspace/.cache/nltk_data DELENTIA_RUN_LIVE_TESTS=0 \
python -m pytest -n 3 --dist loadfile -q --timeout=600 \
  --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane \
  --cov-report=xml:coverage-parallel.xml --cov-report=term:skip-covered \
  --cov-fail-under=72 --junitxml=full-python-parallel.xml
```

`DELENTIA_RUN_LIVE_TESTS=0` ปิด opt-in live tests ที่ต้องใช้ credentials ตามขอบเขตรอบนี้ แต่ legacy local-Ollama tests บางชุดยังรันและ fail จริง. มี exploratory serial runs ที่หยุดก่อนจบ; ไม่อ้างว่าเป็น completed full runs. Full-run log/JUnit เดิมคงผล18failedไว้ ไม่เขียนทับหลัง isolated remediation. การแก้หลัง full run เปลี่ยนเฉพาะ claims regression test; runtime ที่อัดวิดีโอ/สร้าง wheel/รัน full suite คงเดิม.

## สาเหตุของ18 failures และผลตรวจซ้ำ

- 9: `test_llm_provider_real` (3), `test_autonomous_loop_real` (3), synthesis ผ่าน MCP (1), experiments (1), genesis synthesis (1): Ollama endpoint404 เพราะไม่มี model. Server ทำงานแต่ pull qwen2.5:7b ถูก network proxy ปฏิเสธ registry.ollama.ai. ไม่แทน real-inference test ด้วย scripted model.
- 3: TC-027 careful/stale/suite manifest: พบ executable browser แต่ sandbox เริ่มไม่ได้; events จริงบันทึก browser did not start และอ่านราคาไม่ได้. ไม่ใช้ `--no-sandbox` และไม่เปลี่ยน oracle ให้ผ่าน. ต้อง rerun บน browser host ที่รองรับ sandbox.
- 1: real crawl example.com: DNS `[Errno -3] Temporary failure in name resolution`; url_safety ปฏิเสธก่อน fetch. ไม่ปิด SSRF/DNS pinning.
- 1: real OpenSSH `ssh -G`: system config `/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf` มี owner/permissions ที่ OpenSSH ปฏิเสธ. ไม่แก้ไฟล์ระบบนอก workspace หรือข้าม strict settings.
- 2 formatter: Rich ถือ TERM=dumb เป็น80คอลัมน์ แม้ fixtureระบุ110/140. รัน TERM=xterm-256color ผ่านทั้งไฟล์โดยไม่เปลี่ยน assertions/runtime.
- 1 NLTK: cache ยังไม่มีและ downloader ปฏิเสธ proxy. ดาวน์โหลด stopwords/punkt/punkt_tab จาก official NLTK repository โดย TLS และตรวจ SHA-256 กับ official index; รันซ้ำผ่านโดยไม่ปิด SSRF ของ downloader.
- 1 public-claims: assertion จับประโยค README รุ่นเก่าที่ถูกแทนด้วย v0.3; แก้ test ให้ตรวจคำกล่าวอ้างปัจจุบันตามด้านบนและรันซ้ำผ่าน.

ดังนั้นแก้/ตรวจซ้ำผ่าน4จาก18 failures; อีก14ยังเป็น unresolved validation blockers ของสภาพแวดล้อม/model. ไม่สรุป full suite all green และไม่เอา isolated passes ไปแต่งยอด full run ใหม่. Skips/xfail และ warnings อยู่ใน JUnit/log; warnings ส่วนมากเป็น deprecated dependency APIs ต้องจัดการแยก.

## เดโมและการนำไปโพสต์

บันทึก real PTY terminal สอง session แล้ว render เป็นMP4 พร้อม cast/transcriptเต็ม: approval demo (27.4s) และ intent-contract demo (21.6s). Compilation49.0s ไม่มีเสียง เป็นการต่อสอง session และคง SCRIPTED label. ไม่ใช่วิดีโอ desktop GUI; model เป็นlocal HTTP scripted server, runtime/tools/signatures/SQLite/file effects ใช้ implementationจริง.

Approval: compare→pending edit→ก่อนอนุมัติไฟล์ไม่เปลี่ยน→อนุมัติIDจริง→ไฟล์เปลี่ยน→replayถูกปฏิเสธ→audit. Contract: planก่อนexecution→ภาษาไม่ตรงเกณฑ์→wait→CLIprocessใหม่เห็นwait→คำตอบว่างถูกปฏิเสธ→คำยืนยันจริง→revisedplan→คำตอบไทย→ไฟล์ต้นฉบับไม่เปลี่ยน.

Evidence package แยกจาก git เก็บ full logs, JUnit, coverage, source manifest, wheel hash, recording/cast/transcripts และ report. ไม่รวม namespace keys, private runtime directories, databases หรือ uploaded internal archive. ต้องตรวจชื่อ/ข้อความบนวิดีโอและปรับคำบรรยายให้ตรงscopeก่อนโพสต์; ไม่มีการโพสต์อัตโนมัติ.

## ประเมินความพร้อม

เป็น executable experimental system จริง: มี runtime, file effects, signatures, persistent state และauditที่ทดสอบได้. หลักฐานรอบนี้สนับสนุนกลไกเฉพาะscope ไม่ยืนยัน model capability, full RCT fidelity, scientific novelty, universal safety, weight training หรือ production readiness. ไม่ให้คะแนนรวมเปอร์เซ็นต์โดยไม่มีrubric.

เหมาะสำหรับโพสต์แนะนำเชิงทดลองพร้อม scripted demo และข้อจำกัด หลัง review branch/ข้อความให้ตรงกัน. ยังไม่ผ่านเกณฑ์เปิด pilot/stable service: ต้องปิด blockers ของsurfaceที่จะเปิด, complete contract recovery/effects/entrypoints, capable-model development ตามงบที่อนุมัติภายหลัง, freeze/evaluation/ablation, external reproduction และ deployment privacy/auth/key/witness/backup/recovery/soak gates. ดูแผนรอบถัดไปที่ลิงก์ด้านบน.

GitHub remote ระหว่างpushแจ้ง default branch vulnerabilities14รายการ (7high/6moderate/1low). ยังไม่ได้triageรายการจริงในรอบนี้; เป็นgateเพิ่มเติมก่อนpilot ไม่ใช่ข้อพิสูจน์ว่าโค้ดใหม่มีช่องโหว่14จุดหรือแก้เรียบร้อยแล้ว.
