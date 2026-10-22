# ผลทดสอบรอบแก้เดโมไทยและ contract lifecycle

22 ตุลาคม 2026 UTC. Branch `codex/thai-demo-contract-lifecycle-20261022`, base `f2ad16c1334be21ca4a21c319e3491dd4f1e7076`. ไม่ใช้ paid API ไม่ merge main ไม่ deploy/post/publish package. Final commit และ source SHA-256 อยู่ใน evidence manifest.

อ่าน [audit สถาปัตยกรรม/RCT](CODEX_ARCHITECTURE_AND_RCT_AUDIT_2026-10-22_TH.md), [แผนรอบถัดไป](CODEX_NEXT_LEVEL_PLAN_TH.md), [วิธีแก้การบันทึกไทย](../demo/RECORDING_THAI.md) และ [contract scope](../concepts/intent-contracts.md) ประกอบ.

## ผลที่รันจริงในรอบนี้

| ชุด | ผล / ขอบเขต |
|---|---|
| Full Python | **7,872 passed / 14 failed / 59 skipped / 1 xfailed**, 737.36 วินาที |
| Coverage ตามคำสั่ง | 90,042/98,786 statements ≈91.15%; รวม test modules ไม่ใช่ production-only coverage |
| Focused regression | **95 passed**, รวมอยู่ใน full suite ไม่บวกเป็น unique tests |
| Full-pipeline harness ที่เลือก | **21/21 cases, 134/134 checks**, local scripted HTTP model + real tools/persistence/signatures/notary/DAG/jury/external MCP; ใช้ `--no-subagents` จึงไม่อ้างกรณีที่ถูกเว้น |
| HTTP integration แยก process | ผ่าน prepare→wait→หยุด/เริ่ม server→clarify→revised plan→execute; source file ไม่เปลี่ยน |
| CLI export smoke | ผ่านกับ contract ที่สร้างจริงจากเดโม; non-executable schema1 envelope และ original intent อยู่ครบ |
| SDK JavaScript | **73 passed** |
| fdia-wasm / rct-edge | **32 / 37 passed**; รวม JavaScript142tests |
| Wheel | build แบบ isolated ผ่าน; ติดตั้งใน venv แยกจาก checkout แล้ว schema/persistence/export smoke และ CLI help ผ่าน; ไม่ publish |
| Lint / diff | changed Python files Ruff ผ่าน; git diff --check ผ่าน |
| Claim sync / docs | claim-sync ผ่าน; local links ของเอกสารหลัก10รายการไม่ขาด (ไม่รับรองทุก external link/anchor) |
| Thai recording | raw UTF-8 = transcript = cast, ไม่มี U+FFFD ทั้งสอง capture; price/vendor source text ครบ; ตรวจเฟรมไทยด้วยตาแล้ว |
| Video | MP42คลิปและ compilation **67.4วินาที**, ไม่มีเสียง, shaped terminal replay ที่เวลาจริง; scripted labelตลอด |

ตัวเลข full run รอบก่อนคือ7861/18failed ไม่เขียนทับประวัติ. รอบนี้ผ่านเพิ่ม11 = casesใหม่7และ4กรณีเดิมที่แก้สภาพแวดล้อม/claims testแล้ว; ไม่ใช้ความต่างนี้แทนการวัดคุณค่า RCT. Exploratory test runs ที่สะกดชื่อไฟล์ผิดหรือหยุดก่อนจบไม่ถือว่าเป็น completed validation; log `full-python.log` เป็น interrupted attempt ส่วนผลสมบูรณ์คือ `full-python-final.log`/XML.

คำสั่งหลัก (ใช้venvในcloud; PostgreSQL DSNเป็นloopback test container ผ่านenvironment):

```bash
TERM=xterm-256color TIKTOKEN_CACHE_DIR=/workspace/.cache/tiktoken \
NLTK_DATA=/workspace/.cache/nltk_data DELENTIA_RUN_LIVE_TESTS=0 \
python -m pytest -n 3 --dist loadfile -q --timeout=600 \
  --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane \
  --cov-report=xml:coverage-final.xml --cov-report=term:skip-covered \
  --cov-fail-under=72 --junitxml=full-python-final.xml

python scripts/full_pipeline_cases.py --no-subagents --keep --json pipeline.json
```

## 14 failures ที่ยังปิดไม่ได้ในเครื่องนี้

- **9 local-model tests**: Ollama endpointตอบ404เพราะไม่มีโมเดล; model pullเคยถูกproxyปฏิเสธ. ครอบคลุมprovider3, autonomous loop3, MCP synthesis1, experiments1, genesis1. ไม่เปลี่ยนเป็นscripted inferenceเพื่อให้ผ่าน.
- **3 browser TC027 tests**: พบbrowser binaryแต่sandboxเริ่มไม่ได้; จึงอ่านราคาไม่ได้. ไม่เปิด `--no-sandbox` หรือเปลี่ยนoracle.
- **1 crawl**: example.com DNSล้มเหลว; url_safetyปฏิเสธก่อนfetch. ไม่ปิดSSRF/pinning.
- **1 SSH config**: OpenSSHปฏิเสธowner/permissionsของsysteminclude. ไม่แก้ไฟล์ระบบหรือข้ามstrictsettings.

ชื่อcase/tracebacksจริงอยู่ในJUnit/logและfailureinventory. Full command exit1ตามจริง จึงไม่อ้าง all green. Skipped/xfail/warningsแยกไว้; warnings6837ส่วนใหญ่เกี่ยวกับdeprecated APIs. Checksที่ผ่านไม่ได้ทำให้surfaceที่blockedได้รับการรับรอง.

## สิ่งที่ยังไม่รันใหม่/ไม่ผ่านจากรอบก่อน

GUItypecheck/lintเคยผ่าน แต่productionbuildติดGoogleFonts network; GitHubAction ncc/@actions/core export resolutionและtestที่ไม่มีcasesยังไม่แก้; nativeTauriยังไม่มีtoolchain. รอบนี้ไม่แก้distributionเหล่านี้และไม่อ้างว่าผ่านbuildใหม่. Repository-wide lint59findingsและGitHubdependency14alertsเป็นคิวจากรอบก่อน ไม่ใช่scanใหม่หรือสิ่งที่แก้แล้ว.

## คุณภาพและสถานะ

การแก้รอบนี้มี regression ที่ทำซ้ำข้อบกพร่องจริง: byte splitsทุกตำแหน่ง, Thai marksที่pyteเคยตัดข้อความถัดมา, canonical text, unsupported schema, namespace export, signed erasureแบบsealed/plainโดยคงอีกคนไว้, backup/restoreที่ต้องมีkey. ผลสนับสนุนการแก้เฉพาะscopeนี้และไม่พบtestfailureใหม่ในส่วนที่เปลี่ยน. ยังไม่ใช่semanticRCT7ครบหรือproductionassurance.

หลักฐานที่ยังต้องสร้าง: goal-dependent facts/components/backward prerequisites, initial ambiguity wait, signed effect/recovery, ทุกentrypoint, capable-model outcomes/comparisons, realhost/witness/restore/soak และoutside reproduction. ยังมีknown gapของcontractกับcompressed-output expansionตามaudit. ห้ามใช้คลิปไทยเก่า; คลิปใหม่แสดงกลไกได้ แต่ยังต้องreviewcaption/publicdefinitionsก่อนโพสต์.

บันทึก cloud `start_skill` ฉบับใหม่แล้ว: TERM/NLTK/cache, tests, optionalservices และThai recording prerequisites. เป็นsaved draftที่ต้องreview/saveในenvironment settingsแล้วPublishตามUI; การsaveไม่เปลี่ยนruntimeหรือยืนยันfresh-task restoration.
