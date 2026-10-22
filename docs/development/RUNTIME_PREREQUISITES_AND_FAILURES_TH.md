# แก้ prerequisites ของ full integration tests อย่างไร

ตรวจ 22 ตุลาคม 2026 บน cloud นี้. ใช้ `python scripts/runtime_readiness.py --json /tmp/readiness.json` ก่อนรันชุดใหญ่. Exit1 หมายถึงยังไม่พร้อมสำหรับ integration ทั้งชุด ไม่ได้หมายความว่าพัฒนา unit/scripted workflows ต่อไม่ได้. Preflight ไม่แก้ assertions ไม่ skip tests และไม่แทน full suite.

## 1. Ollama: แยก service, trust, model files และ inference

รอบก่อน 9tests ไม่ผ่านเพราะไม่มี `qwen2.5:7b`. รอบนี้อ่าน error body จริงพบ TLS `x509: certificate signed by unknown authority` ภายใน container แม้ host อ่าน registry manifest ได้.

สิ่งที่แก้แล้ว: คัดลอก **public CA anchors ที่ platform เชื่อถืออยู่แล้ว** จาก `/usr/local/share/ca-certificates/` ไปยัง task-owned Ollama container, รัน `update-ca-certificates`, restart container และตรวจ `/api/tags` ก่อน pull ใหม่. SHA-256 ของ CA อยู่ใน evidence. ไม่ใช้ insecure TLS/แก้ checksum/คัดลอก private key.

หลังแก้ trust โหลด manifest ได้และเริ่มสร้าง partial blob แต่ **download ยังถูก proxy ปฏิเสธ Forbidden ที่ official blob redirect**:

- `registry.ollama.ai`
- `dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com`

ต้องเพิ่ม domain ที่จำเป็นใน **รายการ network เดิมของ Environment Settings** แล้ว save ให้ runtime ได้รับการเปลี่ยนแปลง ก่อนลอง pull อีกครั้ง. ตอนนี้อ่าน allowlist ทั้งหมดจาก tool ไม่ได้จึงไม่ได้เขียนทับรายการด้วยค่าที่เดา. โดเมน redirect อาจเปลี่ยนตาม registry; ตรวจ hostname จาก response โดยไม่เผย signed URL query. Container ต้องใช้ supportedproxy/trust เส้นทางเดียวกันด้วย.

```bash
curl --fail http://127.0.0.1:11434/api/tags
# ใช้เฉพาะ local service ของงาน; ไม่มี paid API
curl --fail http://127.0.0.1:11434/api/pull \
  -H 'Content-Type: application/json' \
  -d '{"name":"qwen2.5:7b","stream":false}'
python scripts/runtime_readiness.py --inference --json /tmp/readiness.json
```

Model blob มีขนาดประมาณ 4.68GB; ต้องเผื่อ disk และ RAM สำหรับโหลดจริง. Partial file ที่แสดง logicalsize4.68GB อาจเป็น sparsefile ที่ Completed=0 ทุก part ไม่ใช่ download สำเร็จ. ใช้ persistent model storage เมื่อเตรียม host ใหม่ ไม่ลบ container ที่มี model โดยไม่สำรอง. เก็บ manifest/model digest และให้ Ollama ตรวจ SHA-256 จนจบ. ไม่ใช้โมเดลเล็กอีกตัวหรือ scriptedserver แทนชื่อ qwen2.5:7b เพื่อแต่งผลผ่าน.

เมื่อพร้อมให้รัน provider, autonomous-loop, synthesis, experiments และ genesis tests จริง. Model ตอบผิด/เลือก tool ไม่ได้หลังโหลดสำเร็จเป็น model/application outcome ที่ต้องวิเคราะห์ใหม่ ไม่รับประกันว่าแค่เปิด network แล้ว 9tests จะผ่านแน่นอน. ยังไม่มี paidAPI หรือ capable-model evaluation ในรอบนี้.

## 2. Chromium sandbox

Executable มีจริง แต่ helper `/usr/lib/chromium/chrome-sandbox` ใน instance นี้ถูก remapowner เป็น nobody. Chromium ต้องการ root-owned4755. ลองใช้ user-namespace sandbox โดยไม่เปิด `--no-sandbox` แล้วก็รายงาน No usable sandbox.

การแก้ต้องอยู่ที่ **base image/host/platform runtime**: ติดตั้ง Chromium+sandbox package จากแหล่งที่เชื่อถือและ owner/mode ถูกต้อง หรือใช้ host ที่อนุญาต usernamespace sandbox พร้อม seccomp ตามปกติ. การแก้ owner ใน host จริงต้องทำโดยผู้ดูแล image; ใน workspace ที่จำกัดนี้ยังทำให้พร้อมไม่ได้. ไม่ใช้ `--no-sandbox`, privilegedcontainer หรือปิด seccomp เพื่อให้ test ผ่าน.

ตรวจด้วย preflight แล้วรัน `test_daaes_tc027_round85_real.py` บน host ที่ browser เริ่มได้. Oracle ต้องอ่านราคาผ่าน browser จริง มี decoyrequests เป็น 0 และตรวจ stale/currentprice เดิมครบ. การเปลี่ยนเป็น HTTPclient หรือ skip เงียบไม่ใช่การแก้ 3tests นี้.

## 3. DNS และ crawler egress

`socket.getaddrinfo('example.com',443)` ล้มเหลว และ proxy fetch ก็ถูก 403. Crawler ตรวจ publicaddresses และ pin ปลายทางตอน connect เพื่อกัน SSRF/DNSrebinding จึงไม่ได้ใช้ proxy ที่ resolve ให้แทนแบบไม่มีการผูก IP.

ต้องมี host DNS ที่ใช้ได้ และ network path ที่อนุญาต publicHTTPS ตามขอบเขตของ crawler. การเพิ่ม example.com ใน allowlist อย่างเดียวอาจยังไม่ทำให้ DNS/directpinnedtransport ทำงานใน proxy-onlyenvironment. ถ้าจำเป็นต้องใช้ proxy ต้องออกแบบ trusted egress boundary ที่รักษา equivalentSSRF/pinningcontrols และทดสอบ redirect/rebinding ใหม่ก่อน ไม่ตั้ง `DELENTIA_CRAWL_ALLOW_PRIVATE=1` เป็นทางแก้ทั่วไป.

เมื่อ DNS/egress พร้อมให้รัน realcrawltest และ securityregressions ของ url_safety. ถ้าใช้ localHTTPfixture ใน unit tests ต้องระบุว่าเป็น fixture แยกจาก publicnetworkintegration.

## 4. OpenSSH: แก้ที่โค้ดแล้ว

ปัญหาเดิมคือ ambientsystemconfig มี owner/permissions ที่ OpenSSH ปฏิเสธ. Backend กำหนด connectionoptions เองอยู่แล้ว จึงเพิ่ม `-F os.devnull` ให้ไม่รับ user/systemconfig ที่อาจเพิ่ม ProxyCommand/hostrewrite/identities ด้วย. คง StrictHostKeyChecking, pinnedknown_hosts, BatchMode, noforwarding และ noagent เหมือนเดิม.

Real `ssh -G` test ผ่านแล้ว โดยไม่แตะ `/etc/ssh` และไม่ได้เปิด SSHconnection จริง. Host alias/ProxyJump จาก config จะไม่ถูกนำมาใช้; ต้องระบุ target/port/key/known_hosts ผ่าน supportedsettings โดยตรง. การใช้ SSHserver จริงยังต้องมี configuredhost และทดสอบแยก.

## วิธีพัฒนาต่อโดยไม่เสียเวลารอสิ่งเดิม

1. รัน preflight และเก็บ status ก่อนทุก full-integrationcycle
2. แก้โค้ดแล้วรัน focusedregressions ที่เกี่ยวข้อง; local scriptedHTTP/MCP/SQLite/signature/harness ตรวจ plumbing ได้โดยไม่ใช้ paidAPI
3. รัน build/type/lint ของ distribution ที่แก้ และตรวจติดตั้ง wheel จากนอก checkout
4. รัน fullsuite หนึ่งรอบบน frozenruntime เพื่อเก็บผลจริง เมื่อแก้ prerequisite แล้วจึง rerun กลุ่มที่ affected และ full อีกครั้ง
5. แยก pass/fail/skip/xfail/unrun/infra-exclusion; อย่าบวก targetedrerun เป็น uniquefulltests หรือเรียก allgreen เพราะซ่อน integrationfailures

คำแนะนำ startup และ knownblockers บันทึกใน cloudconfigurationdraft แล้ว. Review/save และ Publish ผ่าน Environment Settings เป็นคนละขั้นกับการบันทึก draft; ยังไม่ยืนยัน fresh-taskrestore หรือ hostreadiness.
