# ทำไม integration failures ทั้ง 13 กรณียังไม่ผ่าน และแก้อย่างไร

ตรวจ 22 ตุลาคม 2026. ใช้ source/test names และ full-run evidence จาก checkpoint `4044f1f` ประกอบ preflight สดของรอบ bounded semantic planner. ผล full-run ล่าสุดของรอบนี้อยู่ใน [รายงาน](BOUNDED_SEMANTIC_PLANNER_RESULTS_TH.md). ปัญหาพื้นฐานมีสามกลุ่ม แต่แต่ละ test ตรวจ capability ต่างกัน จึงยังต้อง rerun ทุกกรณีหลังแก้ prerequisites ไม่ใช่ปิด test เพียงเพราะ service เปิด port ได้

## รายการไม่ผ่านทั้งหมด

ชื่อไฟล์ในตารางอยู่ใต้ `rct_control_plane/tests/`; class/method ที่ซ้ำกันให้ดู node id ครบจาก machine-readable evidence

| # | Test | เหตุที่ยังไม่ผ่าน | วิธีปิดและหลักฐานที่ต้องได้ |
|---|---|---|---|
| 1 | test_llm_provider_real.py::test_ollama_provider_real_completion | POST local Ollama /api/generate ได้ HTTP404 เพราะโมเดลที่ test ต้องใช้ไม่มี; /api/tags ว่าง | O1: ติดตั้งโมเดลจริงและให้ completion ตอบข้อความจริง |
| 2 | test_llm_provider_real.py::test_quota_tracker_blocks_the_real_call_after_limit_reached | call แรกที่ควรสำเร็จเพื่อสร้างการใช้ quota ล้มเหลวก่อน จึงยังไปพิสูจน์การ block หลังชน limit ไม่ได้ | O1 แล้วทดสอบทั้ง successful call และ call ที่ quota ต้องปฏิเสธ; ไม่แก้ quota ให้ผ่านโดยไม่เรียกโมเดล |
| 3 | test_llm_provider_real.py::test_autonomous_loop_accepts_injected_provider | provider ที่ inject ยังต้องเรียกโมเดลจริงและได้404 ไม่ใช่การไม่รับ dependency injection | O1 แล้วพิสูจน์ว่า loop ใช้ injected provider และได้ decision จริง |
| 4 | test_autonomous_loop_real.py::test_decide_next_action_returns_well_formed_decision | ไม่มี response โมเดลให้ parse เป็น action; HTTP404 เกิดก่อนตรวจโครงสร้าง decision | O1 แล้วตรวจ schema/decision จากโมเดลจริง ไม่แทนด้วย scripted decision |
| 5 | test_autonomous_loop_real.py::test_autonomous_loop_real_tool_call_end_to_end | loop จบ llm_error แทน llm_finished/max_iterations_reached/parse_error ที่ test ยอมรับ | O1 แล้วตรวจ tool-call/history/result ของเส้นทางจริง |
| 6 | test_autonomous_loop_real.py::test_autonomous_loop_pauses_for_approval_on_medium_risk_command | ไม่มี model-generated action เข้ามาถึง approval path จึงได้ llm_error แทน pending_approval | O1 แล้วพิสูจน์ว่าหยุดก่อน effect และได้ pending approval จริง; ห้ามทำให้ llm_error นับเป็นอนุมัติ |
| 7 | test_experiments_real.py::test_compare_experiment_runs_reflects_real_benchmark_score_delta | real benchmark ใช้โมเดลจริงแต่เรียกไม่ได้ จึงไม่มีค่าจาก run จริงให้เปรียบเทียบ | O1 แล้วรัน benchmark/comparison ซ้ำ บันทึก model/settings/provenance ไม่สร้าง score แทน |
| 8 | test_genesis_synthesis_real.py::test_synthesizes_and_verifies_a_real_simple_function | synthesis ไม่มีโมเดลสร้าง candidate จึงไม่ถึงขั้น verify function จริง | O1 แล้วตรวจ candidate และ sandbox verification; service ready อย่างเดียวไม่รับประกันว่าทักษะ synthesis จะผ่าน |
| 9 | test_mcp_server_round32_new_tools_real.py::TestKernelCapabilityWrappers::test_synthesize_function_real_deterministic_case | MCP ห่อความล้มเหลวจาก synthesis เป็น UnexpectedToolError; สายงานนี้พึ่งโมเดลที่ยังไม่มี | O1 แล้วตรวจผ่าน MCP จริงด้วย ไม่ใช้ผล unit test ของ wrapper มาแทน |
| 10 | test_daaes_tc027_round85_real.py::test_a_careful_agent_that_looks_again_reports_the_current_price_and_the_browser_reaches_nothing_else | Chromium abort ก่อนอ่านหน้าจริง เพราะ setuid helper ใช้งานไม่ได้ จึงไม่มี observations ปัจจุบันให้ agent reread | B1 แล้วพิสูจน์ว่าอ่านหน้าที่เปลี่ยนราคาได้ และ browser ไม่ออกนอกขอบเขตที่กำหนด |
| 11 | test_daaes_tc027_round85_real.py::test_an_agent_that_answers_from_the_first_look_is_stale_and_the_oracle_knows_what_the_page_shows_now | test ตั้งใจให้ stale agent ไม่ผ่าน แต่ oracle ต้องเห็นราคาเก่า120/ปัจจุบัน95 จริง เมื่อ browser เริ่มไม่ได้จึงไม่สร้างหลักฐานนี้ได้ | B1; ต้องได้ expected stale failure ตาม oracle ไม่ใช่นับ browser crash เป็น stale detection ที่สำเร็จ |
| 12 | test_daaes_tc027_round85_real.py::test_the_case_runs_through_the_suite_runner_with_a_manifest | runner สร้างผล/manifest ได้บางส่วน แต่ case browser ที่อยู่ข้างในยังไม่ผ่าน | B1 แล้วตรวจ case result, manifest และ constraints พร้อมกัน ไม่แก้ manifest ให้บอกว่าผ่าน |
| 13 | test_mcp_server_round31_new_tools_real.py::TestWebCrawlTool::test_crawl_real_url | host resolve example.com ไม่ได้; tool ไม่ได้ success payload ที่มี status_code จึงเกิด KeyError ที่ assertion status_code==200 | D1 แล้วต้องได้ HTTP200 และ URL จาก crawler จริง การปรับข้อความ error ให้อ่านง่ายขึ้นไม่ใช่การแก้ DNS/การผ่าน success test |

## O1 — โมเดล Ollama จริง

ลำดับตรวจ: local service → TLS trust ใน container → official manifest/blob access → model installed → actual inference → capability tests. Host นี้มี service แต่ tags ว่าง รอบก่อนแก้ CA trust แล้วโดยใช้ public trust anchors ของ platformและคง TLS verification; blob download ยังถูก proxy ปฏิเสธที่ official redirect CDN

รอบนี้อ่าน saved configuration ได้เป็นครั้งแรก จึงบันทึกเพิ่ม `dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com` และ `example.com` ใน custom allowlist โดยรักษา5รายการเดิมและ package-manager presets ไว้ พร้อมปรับ startup wording ที่ล้าสมัย ผล tool ยืนยัน status=saved และ requires_publish=true. นี่เป็น draft persistence ไม่ใช่ runtime propagation

ผู้ดูแลต้อง review/save และ Publish ใน environment settings ก่อนตรวจใหม่ เมื่อ network พร้อมให้ pull `qwen2.5:7b` จริงจาก official registry ตรวจ digest/พื้นที่ว่าง/หน่วยความจำและ persistent storage แล้วเรียก local inference ห้ามปิด TLS, เปลี่ยน checksum, เปลี่ยนชื่อโมเดลอื่นเป็น7b หรือถือ sparse partial blob เป็น download ที่เสร็จแล้ว ดู [รายละเอียดเดิม](RUNTIME_PREREQUISITES_AND_FAILURES_TH.md)

เมื่อ inference สำเร็จจึง rerun tests1–9 เพราะ model installed ไม่ได้พิสูจน์ parsing, tool choice, approval, synthesis หรือ benchmark quality ถ้ายังไม่ผ่านต้องแยก model capability, timeout, prompt/schema และ repository defect ตามผลจริงต่อไป

## B1 — Chromium sandbox ที่ทำงานจริง

Preflight สดยัง abort ด้วยข้อความ helper ต้อง owned by root และ mode4755. Host นี้ helper ถูก remap ownership และการลอง user-namespace fallback รอบก่อนก็ไม่มี sandbox ที่ใช้ได้ ต้องแก้ compatible host/base image หรือ runtime policy ที่ platform รองรับ การติดตั้ง executable เพิ่มอย่างเดียวไม่ได้แก้ root cause

หลังแก้ให้ sandboxed Chromium เปิด about:blank สำเร็จ จากนั้นรัน TC027 ทั้งสามกรณีและ browser cases ที่ถูก skip ห้ามใช้ --no-sandbox, privileged workaround หรือ screenshot fixture เพื่อประกาศว่าผ่าน real-browser integration

## D1 — Native DNS และ public pinned egress

Preflight สดยังได้ gaierror จาก socket.getaddrinfo('example.com',443). การเพิ่ม example.com ใน draft ช่วยประกาศ egress ที่ต้องใช้ แต่ยังไม่พิสูจน์ว่า native DNS ของ host หรือ direct validated-IP connection ใช้งานได้ ต้องตรวจทั้ง resolver และ public connection ที่ crawler pin ไว้

การ curl ผ่าน proxy อย่างเดียวไม่เท่ากับผ่าน crawler และห้ามอนุญาต private IP/ถอด DNS pinning/ลด SSRF guard เพื่อให้ test เขียว ถ้า platform รองรับเพียง proxy ต้องออกแบบ trusted proxy transport ที่รักษา destination validation อย่างถูกต้องและมี security regression tests แยกก่อนใช้งาน

## สิ่งที่ไม่ใช่ failed แต่ยังไม่ได้ยืนยัน

Checkpoint เดิมมี59 skipped: browser16, Hermes10, paid-live9, real services4, Windows Job Objects3 และ speech/media/weights/dependencies/other-checkout/collection cases ที่เหลือ; เหตุผลรอบล่าสุดเก็บตามผลจริงใน evidence. Paid-live9ยังไม่เปิดตามคำสั่งผู้ใช้ Windows-only checks ต้องใช้ Windows CI และบริการเสริมต้องมี host/model/dependencies ของตัวเอง

1 xfailed เป็น image generation ที่ขาด diffusion extras/model weights ไม่ใช่ผลสร้างภาพจริงที่ผ่าน. SSH config failure เดิมปิดแล้วด้วย isolated -F config และ real ssh -G check ผ่าน แต่ไม่ได้พิสูจน์การเชื่อมต่อ SSH server จริงทุกแห่ง

ดังนั้น “ไม่มี repository regression ในชุดที่รันผ่าน” และ “integration ทั้งหมดพร้อม” เป็นคนละข้อสรุป รอบนี้ยังไม่ใช้ข้อหลัง
