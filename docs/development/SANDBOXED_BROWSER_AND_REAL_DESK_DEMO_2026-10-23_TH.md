# Sandboxed browser และ Desk demo ที่รันจริง

รอบต่อจาก `971903c`; implementation checkpoints `8a822cd` และ `9b25199`. ผลและ hashes อยู่ใน [JSON evidence](evidence/SANDBOXED_BROWSER_AND_DESK_2026-10-23.json). เป้าหมายที่ปิดได้ในรอบนี้คือ browser runner สำหรับการทดสอบและ demo Settings/Memory พร้อมแก้ defects ที่พบจากการใช้งานจริง ไม่ใช่การปิดแผนทั้งหมด 8 ข้อหรือเปิด pilot.

## วิธีแก้ browser ที่พิสูจน์แล้ว

Shell เดิมอยู่ใน user namespace ที่ map UID เดียว; Chromium helper มี owner 65534 และ host unshare ถูกปฏิเสธ. ไม่แก้ด้วย --no-sandbox, privileged container หรือปิด TLS. ตรวจ Docker แบบ non-root พบว่า default seccomp ปฏิเสธ user namespace แต่ [profile ของ Playwright](https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json) อนุญาต syscall ที่ browser sandbox ต้องใช้และยังมี defaultAction SCMP_ACT_ERRNO.

ใช้ browser image แยกบน Debian 13, Chromium 154.0.8037.57, Playwright 1.56.0, UID 1000. `chrome://sandbox` รายงาน Layer 1 Namespace, PID namespaces Yes, Network namespaces Yes, Seccomp-BPF Yes, TSYNC Yes และ “You are adequately sandboxed”. Yama LSM protection รายงาน No; ไม่อ้างว่ามีการป้องกันทุกประเภทหรือเทียบเท่า production host ที่ผ่าน review.

Image `delentia-browser:playwright-1.56.0`: `sha256:efa697fa03944f7359f5b4c203d2050bd862320999752a550914b92c5566f9a9`, logical size 1,096,174,947 bytes. Seccomp file SHA-256 `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`.

APT ใน container ล้มเหลวจาก TLS/proxy; จึงนำเฉพาะ Chromium/fonts/ELF dependencies ที่ติดตั้งอยู่บน host Debian รุ่นเดียวกันเข้าระบบ offline และติดตั้ง pinned Playwright wheels แบบ no-index. เก็บ runtime hashes; ไม่ snapshot ทั้ง host ไม่ mount source/private state หรือ Docker socket เข้า browser. Build ครั้งหนึ่งเริ่มก่อน archive เสร็จและถูกปฏิเสธว่า incomplete; build ที่ใช้งานจริงทำหลัง archive ปิดครบแล้วและผ่าน functional sandbox checks.

Adapter `/workspace/.delentia-cloud/chromium-container` ส่งต่อ caller arguments เดิมครบ รวม proxy fence และ DNS pin. ใช้ task-named --rm containers, parent-death watchdog และ timeout 90s เพื่อไม่ทิ้ง browser เมื่อ caller ถูก kill. Host networking ใช้เข้าถึง local integration fixtures; adapter นี้เป็น test-host configuration ไม่ใช่ multi-tenant deployment boundary.

การใช้งานบน workspace ที่เตรียมแล้ว:

```bash
cd /workspace/Delentia-OS
source /workspace/.delentia-cloud/activate-delentia.sh
export DELENTIA_BROWSER_PATH=/workspace/.delentia-cloud/chromium-container
/workspace/.venvs/delentia/bin/python scripts/runtime_readiness.py
/workspace/.venvs/delentia/bin/python -m pytest -q \
  rct_control_plane/tests/test_daaes_tc027_round85_real.py \
  rct_control_plane/tests/test_browser_round58_real.py \
  rct_control_plane/tests/test_browser_act_round62_real.py
```

ตรวจ image/adapter/profile และพื้นที่ก่อนเสมอ. ถ้าไม่อยู่หรือ sandbox ไม่ผ่าน ให้หยุดส่วน browser ไม่ fallback เป็น unsandboxed. Startup instructions บันทึกใน cloud configuration draft แล้ว; ยังไม่ Publish และยังไม่ได้พิสูจน์ fresh-task restoration.

## ผลทดสอบ

| ขอบเขต | ผล |
|---|---|
| TC027 dynamic browser workflow | 5 passed, 87.57s รวม 3 กรณีที่เคยติด sandbox; decoy requests และ unexpected paths ยังถูกตรวจ |
| Browser read/action regressions | 67 passed, 164.33s |
| Static export route/header regression | 1 passed, 1.19s |
| GUI type-check, lint, production build | ผ่านหลังแก้ source สุดท้าย |
| Ruff CI scope และ scripts ใหม่ | ผ่าน |
| Real GUI Settings/Memory | 6 checkpoints ผ่าน, JavaScript page errors 0 |
| Delayed old-gateway response regression | ผ่าน: request เก่าถูกทำให้ล้มเหลวแบบควบคุม ส่วน gateway ใหม่เป็น API จริง |
| Runtime readiness พร้อม adapter | browser และ SSH config ผ่าน; model และ native DNS ไม่ผ่าน |

73 pytest cases ในสามกลุ่มข้างต้นเป็น targeted runs ไม่ใช่ full Python suite รอบใหม่. ผล full เดิมยังเป็น 8,018 passed / 15 failed / 59 skipped / 1 xfailed บน runtime checkpoint เดิม ห้ามลบ 3 browser failures จากรายงานเดิมแล้วเรียกว่า full suite ใหม่ผ่าน.

## Bugs ที่พบจาก browser จริงและแก้แล้ว

1. Settings แสดง `Reachable: undefined` เพราะ health response ไม่มี service field → ใช้ชื่อ Delentia API เมื่อไม่มีชื่อ และแปล controls/status ที่ใช้ใน flow เป็นไทย.
2. Sidebar แสดง API offline ค้างหลังเปลี่ยน gateway → dispatch connection-change event, เคลียร์ข้อมูล connection เก่า และ reload consumers ทันที.
3. Request เก่าที่เสร็จช้าสามารถทับผลใหม่ → useDeskData ใช้ request version ปฏิเสธ stale completion/error; browser regression ทดสอบ delayed old failure โดยแยกจาก recording ที่ใช้ API จริงทั้งหมด.
4. Memory history แสดงว่ายังไม่มี event หลังบันทึก → mutation revision ทำให้ history และ log status refresh หลัง remember/replace/pin/revoke สำเร็จ.
5. Static demo server แสดง directory listing เมื่อ route มีทั้ง settings.html และ settings/ → utility ใหม่ให้ HTML precedence, ปฏิเสธ directory listing และส่ง X-Frame-Options/X-Content-Type-Options จริง. เป็น local review server ไม่ใช่ public/authenticated deployment service.

ภาษาไทยในภาพที่ตรวจอ่านได้ครบ ทั้ง น้ำ, กำลัง, งบประมาณ และเลข 15,000.00. ยังมีศัพท์/labels ภาษาอังกฤษในหน้าอื่นและ domain labels บางส่วน ไม่อ้างว่าทุกหน้า localized ครบ.

## Demo และการทำซ้ำ

วิดีโอ `DELENTIA_DESK_REAL_GUI_DEMO_2026-10-23.mp4` ยาว 20.9s เป็น actual browser frames ที่เก็บตามเวลาแล้ว encode ด้วย host ffmpeg, ไม่ใช่ animation/mock response. Capture cadence ประมาณ 0.5s บวก screenshot overhead; output encode 20fps โดยซ้ำเฟรมตามเวลา ไม่ใช่ native 20fps capture. มีป้าย REAL GUI / SYNTHETIC DATA / NO MODEL GENERATION.

Playwright bundled ffmpeg ดาวน์โหลดจาก CDN ไม่ได้ (403 Domain forbidden); จึงไม่อ้างว่า recorder package ติดตั้งสำเร็จ. ใช้ ffmpeg ที่มีบน host โดยไม่เปลี่ยน TLS/checksum. เก็บ raw frame timestamps และ hashes เพื่อทวน provenance.

Flow ที่บันทึก:

1. Settings ตรวจ gateway ที่ไม่มี service และแสดงการเชื่อมต่อล้มเหลว.
2. บันทึก gateway ของ API แยกสำหรับ demo และตรวจชื่อ/สถานะที่ถูกต้อง รวม sidebar.
3. เพิ่มข้อความไทยสังเคราะห์ผ่าน UI จริง และตรวจ memory/history event ที่ API บันทึกจริง.
4. Reload หน้าแล้วข้อมูลยังอยู่.
5. Revoke พร้อมเหตุผลผ่าน UI; ข้อมูลหายจาก active list.
6. เปิดรายการ revoked และเห็นหลักฐานว่าเป็น soft revocation ไม่ใช่การลบ bytes.

ใช้ private demo data root ใหม่ mode 0700 แยกจาก operator keys/DB. ไม่มี model generation, paid API หรือข้อความจากลูกค้าจริง. Event chain ที่เห็นเป็น local audit; ไม่ใช่ independent witness หรือหลักฐานว่าทุก event anchored แล้ว. ไม่มีการเผยแพร่วิดีโอภายนอก.

Scripts ใน repository:

- `scripts/serve_desk_static.py --port 3022`: serve apps/gui/out บน loopback.
- `scripts/record_desk_browser_demo.py`: ต้องติดตั้ง Playwright และใช้ sandboxed Chromium; กำหนด DELENTIA_DEMO_BASE_URL, DELENTIA_DEMO_API_URL, DELENTIA_DEMO_OUTPUT และ optional DELENTIA_DEMO_CHROMIUM. ใช้เฉพาะ API demo บน loopback เพราะจะสร้าง/revoke ความจำสังเคราะห์.
- `scripts/check_desk_gateway_race.py`: controlled failure regression แยกจาก demo, ใช้ local fixture ports 3021/8021.
- `scripts/encode_desk_capture.py <capture-directory> <output.mp4>`: รับเฉพาะ completed capture ที่ผ่านและไม่มี page errors.

ตัวอย่างการรัน recorder บน runner ที่เตรียมไว้ (ต้อง start API แยกที่ 8023 และ static server 3022 ก่อน):

```bash
docker run --rm --user 1000:1000 --network host --shm-size=1g \
  --security-opt seccomp=/workspace/delentia-browser-host-evidence/seccomp-profile.json \
  -e DELENTIA_DEMO_BASE_URL=http://127.0.0.1:3022 \
  -e DELENTIA_DEMO_API_URL=http://127.0.0.1:8023 \
  -v /workspace/Delentia-OS/scripts/record_desk_browser_demo.py:/runner.py:ro \
  -v /workspace/delentia-browser-host-evidence/recording-final:/out \
  delentia-browser:playwright-1.56.0 python /runner.py
```

ใช้ output directory ใหม่สำหรับ public capture เท่านั้น. รอบนี้ให้ directory นี้ writable เพื่อรองรับ UID mapping ที่ต่างกัน และ mount เฉพาะ directory นี้; ไม่เก็บ secrets/DB ใน directory นี้. บน host ถาวรควรจัด ownership/ACL ให้ runner เขียนได้โดยไม่เปิดสิทธิ์กว้าง. ห้ามใช้ operator data directory แทน. ไม่ mount ทั้ง workspace เข้า browser.

## ระยะห่างและงานถัดไปตามแผน 8 ข้อ

| งาน | สถานะหลังรอบนี้ | เกณฑ์จบถัดไป |
|---|---|---|
| Integration host | Browser runner ผ่าน; native host Chromium เดิมไม่ถูกแก้; DNS/model ยังติด | DNS จริงพร้อม SSRF pinning; storage โมเดลแยกมี headroom, official digest/inference และ 9 tests ผ่าน |
| Server read-only profile | ยังไม่ได้ implement ในรอบนี้ | server-selected actor/workspace, versioned schemas, route/tool/executor allowlist, unknown versions/no fallback, concurrent two-user isolation tests |
| Jobs/recovery | ยังไม่ปิด | idempotency/status/cancel/continuation และ real kill/restart ทุก boundary; incomplete receipts ไม่ completed |
| Desk contract lifecycle | Settings/Memory demo และ refresh defects ปิดตามขอบเขตทดสอบ | plan/wait/clarification/difference/receipt events, actor/version continuation, reconnect/restart/cancel E2E; chat ปัจจุบันยังไม่ได้ส่ง contract inputs ครบ |
| Semantic planner/verifiers | ไม่มีการเปลี่ยน semantics รอบนี้ | ambiguity/negation/multi-intent/conflicts, criterion→handler→receipt→verifier coverage และ invalidation |
| Capable-model evaluation | ยังไม่ได้รัน | dev/holdout แยกก่อน tuning, pin model/settings/protocol; task success/false acceptance/latency ไม่รวม no-generation demo |
| Signed write workflow | ไม่เปิดเพิ่ม | bind approvals ทุก field และ crash reconciliation ของ workflow เดียวก่อนเปิด |
| Operational gates | ยังไม่ปิด | clean install/rollback, off-host restore, separate notary user, independent witness, soak จริง 72h และ outside review |

หลังเตรียม browser พื้นที่เหลือประมาณ 8 GB; guard โมเดลเดิมต้องอย่างน้อย 2×4,683,073,952 bytes+2GiB ≈10.72GiB. จึงไม่ pull ซ้ำบนพื้นที่นี้ ไม่ใช้ snapshot/สำเนา weights เพิ่ม และไม่ prune Docker ทั้งระบบ. แนะนำ storage/host ที่มีพื้นที่จริงเพิ่มก่อน model work.

งานพัฒนาที่ควรทำระหว่างรอ host/model: server read-only profile ก่อน แล้ว stable public contract schema → jobs/recovery → Desk contract lifecycle. Demo ที่มีใช้สื่อสาร “UI และการเก็บ/เพิกถอนความจำที่ทำงานจริง” ได้ แต่ใช้เป็นหลักฐานว่า RCT-7 เข้าใจโจทย์ทั่วไปหรือพร้อมทำงานธุรกิจเองไม่ได้.
