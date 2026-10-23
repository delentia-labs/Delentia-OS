# Typed RCT execution และการกู้ runtime รอบ 23 ตุลาคม 2026

อ้าง implementation checkpoint `d806599` บน PR #168 เวลาในคำอธิบายใช้ Asia/Bangkok; raw container timestamps เป็น UTC ผลแต่ละชุดมี scope ของตนเอง ไม่ใช่การประกาศ RCT-7 ทั่วไปหรือ pilot-ready

## ปัญหา runtime ที่ตรวจพบจริง

หลัง reconnect รอบล่าสุด filesystem ขนาดประมาณ 32 GB ใช้เต็ม 100% เหลือ **69,242,880 bytes** ขณะที่ RAM ที่รายงานว่างมากกว่า 32 GB และ current cgroup memory.events รายงาน oom/oom_kill=0 ข้อมูลนี้เป็น snapshot ของ instance ปัจจุบัน ไม่พิสูจน์ว่า instance ก่อนหน้าไม่เคย OOM

Ollama และ PostgreSQL หยุดด้วย exit 255, OOMKilled=false เวลา 2026-10-23T05:06:25Z ทั้งสอง container ต่างกันน้อยกว่า 1 ms (12:06:25 เวลาไทย) ร่วมกับ exec-server transport closed / environment unavailable แสดงว่าการขัดข้องกระทบ runtime หลายบริการ ไม่ใช่เพียง HTTP timeout ของโมเดล แต่ไม่มี platform lifecycle log ที่ระบุสาเหตุการตัดเครื่อง จึงยังไม่ระบุว่าดิสก์เต็มเป็นสาเหตุของทุกเหตุการณ์ก่อนหน้า

พบ model blob ที่ยังไม่เสร็จ ขนาด logical 4,683,073,952 bytes ทั้งใน workspace cache และ task-owned container สำรอง การคัดลอก/เก็บสำรองระหว่างแก้ proxy เพิ่มพื้นที่ที่ใช้ เป็นส่วนที่ workflow ของ Codex ต้องปรับปรุง ไม่ควรทำ snapshot/container backup ที่รวม model download ซ้ำหลายชุด

### การคืนพื้นที่และข้อจำกัด

ลบเฉพาะ `sha256-2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730-partial*` ใน `/workspace/.cache/ollama-models/blobs` ซึ่งเป็น incomplete download และลบ container ของงาน `codex-delentia-ollama-20261022-before-persistent-models` ที่หยุดอยู่และเก็บสำเนาซ้ำ เก็บ source, test evidence, PostgreSQL และ container สำรองก่อน proxy refresh ไว้ ไม่ใช้ docker system prune หรือการลบ workspace แบบกว้าง

พื้นที่ว่างหลัง cleanup **16,625,254,400 bytes** (ประมาณ 15.48 GiB; df แสดง 16G) เก็บ before/after ใน `/workspace/delentia-rct-framework-evidence/disk-recovery.json` ตัวเลขพื้นที่คืนเป็นผลรวม filesystem จริง ไม่อ้าง attribution ต่อไฟล์/ชั้น snapshot ที่ไม่มีหลักฐานแยก

หยุด model pull ในรอบตรวจ full suite นี้ ต้องใช้ model storage เพียงชุดเดียว ตรวจ allocated size/free space ก่อน pull และไม่ snapshot model partial ลง image อีก การดาวน์โหลดรอบใหม่ควรมีพื้นที่เผื่ออย่างน้อย 2 เท่า artifact บวกพื้นที่ build/test 2 GiB และติดตามระหว่างรัน เงื่อนไขนี้เป็น operational guard ไม่รับประกันพื้นที่ที่ platform ใช้ทำ snapshot ภายนอก

### Proxy, DNS และการ restart

ตรวจพบ proxy IP เปลี่ยนหลัง environment restore ขณะที่ Ollama container เก็บ IP เดิม การ restart container เดิมอย่างเดียวไม่แก้ค่า environment ของ daemon ต้องเปรียบเทียบ route ตอน startup และ refresh configuration โดยรักษา CA/TLS verification พร้อม persistent model cache ห้ามตีความ sparse/partial blob ว่าเป็นโมเดลพร้อมใช้

GitHub API ผ่าน proxy ใช้ได้ แต่ native resolver ของ api.github.com/example.com ยัง gaierror ผลสองอย่างนี้ไม่ขัดกัน: proxy เป็นผู้เชื่อมต่อปลายทางให้ HTTP ส่วน native DNS ของ crawler เป็นอีก prerequisite ห้ามปิด SSRF/DNS pinning เพื่อให้ test ผ่าน

browser sandbox ยังต้อง compatible host: helper ownership/mode และ user namespace ที่ใช้ได้ ไม่ใช้ --no-sandbox เพื่อลด failures ส่วน model inference/capability ยังไม่ผ่าน เพราะ tags ล่าสุดที่ตรวจยังไม่มีโมเดลที่พร้อมใช้

## Implementation ที่ส่งขึ้น branch

- `component_execution.py`: typed IR, trusted handler registry, DAG/reference/typed-edge checks, criterion verifier coverage, bounded dependency scheduler และ sticky failures
- `budget_execution.py`: trusted compiler/handlers นำ source observation → exact arithmetic → report → criterion verification มาใช้ framework เดียวกัน
- `intent_contract.py`: execution program รวมอยู่ใน plan digest ของแผนใหม่ ตรวจ unsupported executor/version และ program mismatch; เก็บ compatibility ของ sealed budget plans เดิมที่ยังไม่มี IR
- `verified_budget.py`: ใช้ scheduler แทน completion loop ที่อาศัย serialization order; ยังคง receipt bindings, final source freshness และ read-only governed dispatch
- `mcp_server.py`: opt-in verified_read ใช้ descriptor-relative no-follow ตอนอ่านจริง ปฏิเสธ symlink/nonregular/secret/oversize และไม่คืน content ใน refusal
- `semantic_plan.py` / `governed_autonomous_loop.py`: แก้ narrowing/type errors และตรวจ durable contract/store ก่อนเขียน partial state ไม่ suppress errors เพื่อให้ mypy ผ่าน

Generic DAG execution substrate ไม่ใช่ generic semantic planner การสร้าง runtime programs ยังผ่าน trusted budget compiler; registry ไม่รับ callable/code จาก request General task handlers, independent domain oracles, server-enforced profile/tenant isolation, signed effects, process recovery และ channels ยังเป็นงานค้าง Whole-contract replan ยัง invalidate receipts ทั้งชุด ไม่ได้เพิ่ม incremental invalidation/recovery โดยอัตโนมัติ

## Validation และ A/B

Focused regression ก่อน fixture lint cleanup: **192 passed** ใน 5.73 วินาที ชุด checkpoint หลัง cleanup: **60 passed** ใน 2.75 วินาที (ซ้อนกับชุดแรก) Ruff 0.15.21 ตาม CI pin ผ่าน ส่วน Mypy 2.3.0 แบบ `--no-site-packages` ผ่าน 260 source files หลังแก้ 21 errors ในสองไฟล์ การใช้ flag นี้กัน dependency stubs ของ application ที่ไม่อยู่ใน CI tools-only job; ต่อมาตรวจ GitHub CI ของ d806599 ได้ว่า **Lint & Type Check ผ่านจริง** ส่วน jobs อื่นต้องดูแยกตามสถานะ

Scripted pipeline ผ่าน **21/21 cases และ 134/134 checks** (ไม่รัน optional subprocess cases); ผลนี้ไม่ใช่ capable-model evaluation

Actual CLI/kernel/MCP/SQLite ผ่าน within-budget และ over-budget กรณีละ 7 receipts, generation calls=0 และ source unchanged A/B ด้านล่างเป็น microbenchmark แยกต่างหาก ไม่มี governed dispatch/persistence ใน timing loop

| Cohort | A: baseline 26139b0 | B: typed scheduler | ข้อสรุป |
|---|---|---|---|
| canonical order | correct 24/24; median 1.065 ms | correct 24/24; median 1.932 ms | ผลถูกเท่ากัน แต่มี validation/scheduling overhead |
| reversed serialization, dependencies unchanged | correct 0/24; median 0.313 ms | correct 24/24; median 1.992 ms | B ทำงานตาม dependencies; A ล้มเหลวเร็ว ไม่ใช่ทำงานสำเร็จเร็วกว่า |
| invalid evidence | correctly rejected 24/24; median 0.030 ms | correctly rejected 24/24; median 0.253 ms | ทั้งสองปฏิเสธข้อมูลผิดในชุดนี้ |

ใช้ 72 generated cases, TH/EN goal templates, 3 currencies และ integer-cent expected values แต่ละ arm วัดซ้ำ 3 ครั้งและสลับลำดับ A/B การวัดซ้ำไม่ใช่ independent sample ชุด reordered เป็น structural stress ที่กำหนดไว้ ไม่ใช่ holdout ไม่อ้าง general RCT accuracy, language understanding, model capability, production latency หรือ unattended reliability จากตัวเลขนี้ รันซ้ำได้ด้วย `scripts/evaluate_component_scheduler.py --output /tmp/component-ab.json`

Tests ใหม่ตรวจ DAG/fan-in/order permutations, invalid nodes/ports/phases/criteria, failure callback, typed output refusal, unknown inputs, source acquisition race และ governed reordered graph ส่วน real-process crash matrix และ independent-model comparison ยังไม่ได้เพิ่มครบ

Full suite ของ implementation checkpoint: **8,002 passed / 14 failed / 59 skipped / 1 xfailed**, 810.37 วินาที, exit 1; coverage 91.26% รวม test modules. Failure node ids ตรงกับรอบก่อน: False. ดู [ผล machine-readable และ A/B raw outcomes](evidence/RCT_FRAMEWORK_2026-10-23.json).

## วิธีลดการหยุดงานซ้ำ

1. เปิด session แล้วตรวจ Git status, free disk, memory events และ service routes ก่อนโหลดโมเดล
2. แก้ lint/focused regressions แล้ว commit/push checkpoint ก่อนงานที่ใช้เวลานาน
3. ใช้ persistent model directory หนึ่งชุด ไม่มี snapshot/download copies หลายชุด และไม่รัน model pull ระหว่าง full test โดยไม่มี capacity plan
4. หลัง restore ให้ restart services และตรวจ readiness จริง; proxy IP/DNS/settings ต้องตรวจใหม่ ไม่เชื่อแค่ saved draft
5. เก็บ tests/exit codes/resource evidence เป็นไฟล์ต่อเนื่อง ถ้า transport หายให้นับงานนั้นว่ายังไม่ยืนยันจนตรวจผลได้
6. หากยัง unavailable หลังคืนพื้นที่ ต้องใช้ platform lifecycle/storage/termination logs เพื่อแยก host recycle, snapshot/Publish หรือ service failure; application logs อย่างเดียวสรุป root cause ส่วนนั้นไม่ได้

สถานะ: typed execution framework ทำงานได้ในขอบเขตที่ทดสอบและมี A/B structural evidence แล้ว แต่ integration host และ release gates ยังไม่ครบ ไม่มี paid API, main merge, deployment หรือ outside pilot ในรอบนี้


## Findings ที่ไม่ใช่สาเหตุ transport หลุด แต่ยังขวาง release

GitHub check annotations ของ baseline 26139b0 ระบุ CodeQL 3 high alerts: uncontrolled data used in path expression ใน intent_contract.py ที่ _file/_digest (lines 54, 63, 65 ของ baseline) ไม่ใช่ CodeQL analysis failure ต้อง review path validation/actual acquisition และรอผล head ปัจจุบันก่อนปิด finding; ไม่ dismiss หรือถือว่า false positive จาก Bandit high-severity=0 เพียงอย่างเดียว

Dependency alerts 47 รายการเป็น default-branch summary อีกชุดหนึ่ง การอ่าน Dependabot inventory ถูกปฏิเสธ Resource not accessible by integration จึงยังไม่ยืนยัน package/reachability inventory ครบ การมี GitHub push/PR permission ไม่เท่ากับสิทธิ์ security inventory

Startup instructions เพิ่ม disk/proxy/model-cache guards ลง cloud configuration draft สำเร็จ แต่ยัง requires_publish=true; ไม่ Publish ระหว่าง full suite การบันทึก draft ไม่ใช่การเปลี่ยน runtime และไม่ใช่การแก้ platform lifecycle service


## ผลตรวจเพิ่มเติมหลัง full suite และการค้นพบ VFS

Full run มี 14 failures: model integrations เดิม 9, browser sandbox 3, native DNS 1 และเพิ่ม regex timing test อีก 1 (`test_regex_audit_round72_real::test_no_pattern_the_runtime_builds_or_writes_is_slow_on_hostile_text`) ซึ่งวัด DSLParser.PARAMETER_PATTERN ได้ 0.5781 วินาที รันกรณีนี้แยกหลัง suite จบ **ผ่าน 1 test ใน 14.05 วินาที** แต่ไม่เปลี่ยนผล full run ให้เป็น 13 failures และไม่แก้ threshold เพื่อให้ผ่าน เป็นหลักฐานว่าผลไวต่อสภาพการรัน/ไม่เกิดซ้ำในการตรวจแยก ยังไม่พิสูจน์สาเหตุ timing ที่แน่นอน

CI ของ d806599: Lint & Type Check ผ่าน ส่วน Python 3.12 หยุดในขั้น Wait for Ollama and pull the real default model ด้วย exit 22; Run tests ถูก skipped จึงไม่ใช่ผล pytest ของ CI เครื่องนั้น ยังไม่ทราบว่า HTTP error เกิดตอน pull หรือ warm-up จาก annotations อย่างเดียว CodeQL ยังมี path alerts 3 high เดิม

หลัง full run จบ refresh container โดยไม่ดาวน์โหลดโมเดลกลับทำให้ free disk ลดจากประมาณ 16.6 GB เหลือ 6.53 GB จึงตรวจ Docker และพบ storage driver **vfs** พร้อม Ollama image ~5.02 GB VFS เก็บสำเนา filesystem ต่อ container; ตัวเลข writable-size 2.37 KB ไม่สะท้อน storage จริงทั้งหมด เมื่อรวม rollback containers หลายตัวจึงใช้พื้นที่มาก สอดคล้องกับ disk-full ที่พบและอธิบายว่าทำไมการสร้าง container ใหม่กินพื้นที่แม้ไม่มี model download

หลังยืนยัน replacement service แล้ว ลบเฉพาะ stopped task containers `before-proxy-refresh` และ `stale-route-1792733286` คืนพื้นที่จาก **6,528,532,480 เป็น 16,614,531,072 bytes** ไม่ลบ PostgreSQL/source/evidence และไม่ทำ global prune ดู vfs-recovery.json ใน evidence directory

ตอนจบ proxy route ของ container ตรงกับ runtime, local Ollama /api/tags ตอบ HTTP 200 (models=0) และ registry manifest จากใน container ตอบ **HTTP 200 พร้อม TLS/hostname verification** ผ่าน openssl ไม่ปิด verification และไม่เริ่มดาวน์โหลด blob ใหม่ curl ไม่มีใน image จึงใช้ openssl ที่มีอยู่โดยรักษาการตรวจ certificate

Helper `/workspace/.delentia-cloud/refresh_ollama_proxy.py` ใช้ existing image/cache, ตรวจพื้นที่เผื่อก่อน recreate, ตรวจ HTTP readiness แล้วลบ obsolete task container เพื่อไม่สะสมสำเนา VFS; no-change invocation ผ่าน การเปลี่ยน startup draft ยังไม่ได้ Publish และการ restore/fresh-task validation เป็นงานแยก

การรัน full suite จนจบหลัง cleanup เป็นหลักฐานว่าทำงานต่อได้ตลอดรอบนี้ ไม่ใช่ 72h soak หรือข้อพิสูจน์ว่า platform lifecycle interruptions ทุกครั้งถูกแก้แล้ว หากยังเกิดอีกหลังมี headroom ต้องตรวจ termination/storage/snapshot logs ของ platform ต่อ
