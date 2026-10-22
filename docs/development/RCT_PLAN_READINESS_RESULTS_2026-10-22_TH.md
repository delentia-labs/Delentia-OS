# ผลงานรอบ RCT declared plans และ runtime readiness

22 ตุลาคม 2026 UTC. Base `2fc16e8a7dd425d78debb6ebbff4c05e1d65b041`; branch `codex/rct-plan-and-runtime-readiness-20261022`. Final commit/source hashes อยู่ใน run manifest. ไม่มี paid API, merge main, deploy, package publish หรือโพสต์อัตโนมัติ.

## สถานะที่นิยามได้จากหลักฐาน

เป็น **executable experimental self-hosted agent runtime with governance and partial RCT-7**. รอบนี้เพิ่ม declared planning context ที่มีโครงสร้างและรอข้อมูลสำคัญก่อนทำงาน โดยผู้ใช้เป็นผู้ประกาศ facts/unknowns/components. ยังไม่ใช่ระบบที่สร้าง semantic decomposition ถูกต้องเองจากทุกโจทย์ และยังไม่ครบ RCT-7 ทุก entry point. โค้ดพร้อมพัฒนาและสาธิตกลไกต่อ แต่เครื่อง cloud นี้ยังขาด prerequisites ของ real-model/browser/network integration และยังไม่ผ่าน L2 pilot.

ดู [declared plans](../concepts/rct-declared-plans.md), [วิธีแก้ prerequisites](RUNTIME_PREREQUISITES_AND_FAILURES_TH.md) และ [แผนรอบถัดไป](READINESS_NEXT_ROUNDS_TH.md).

## สิ่งที่พัฒนาและตรวจแล้ว

- โครงสร้าง facts พร้อม source, unknowns/critical/answers, assumptions และ component graph; validate typed schema, unique ids, references, cycles และ coverage ของทุก criterion. Plan graph เป็นสิ่งที่ผู้ใช้ประกาศ ไม่ใช่ผลวิจัยความสามารถ reasoning ของโมเดล.
- Critical unknown ทำให้เกิด durable `waiting_for_input` ก่อน model/tool. คำตอบต้องตรง unknown ids; คำว่า looks good ไม่แก้ missing budget. คำตอบและ original intent คงอยู่ข้าม restart และ API คืน revised plan ก่อน execution อีก request.
- CLI รับ `--planning-context-file` และ `--answers-file`; API รับ `planning_context`/`answers`. Default/legacy path คงเดิม.
- Expand output ที่ถูกบีบอัดได้ใน contract หลังตรวจ namespace ownership และ id ที่ออกใน episode ปัจจุบัน. อื่นคน/episodeเก่าถูกบล็อกก่อน dispatch. ทดสอบ real MCP recovery ของข้อความไทยและราคา โดยไฟล์เดิมไม่เปลี่ยน. Raw owner MCP เป็นอีก trust boundary ไม่ได้กล่าวว่า API ทุก path ใช้ข้อกำหนดเดียวกัน.
- VERIFY รับ confirmed unknown answers ที่โมเดลเห็นใน plan ด้วย แก้ false rejection ของงบ15,000ที่ผู้ใช้ตอบจริง; ตัวเลข99,999ที่โมเดลแต่งยังไม่กลายเป็นหลักฐาน. Predicates กับ heuristic verification ยังคงแยกกัน ไม่รับรอง semantic truth.
- SSH ใช้ `-F os.devnull` เพื่อไม่รับ ambient config/ProxyCommand/identities; real OpenSSH strict-settings test ผ่าน โดยไม่แก้ `/etc` หรือเชื่อมต่อ SSH server จริง.
- Action build แก้ ESM resolution ของ @actions/core ด้วย ESNext/Bundler, `tsc --noEmit` + ncc, committed bundled artifact, policy gate tests และ fail-closed score/threshold validation. ปิด HTTP redirects ที่จุดเรียก API และ packaged process test ยืนยันว่าไม่ส่ง request/bearerไป redirect destination.
- GUI ใช้ installed-font stacks แทน build-time Google Fonts fetch; web static export, lint, type-check และ HTTP static assets ผ่าน. Font appearance ขึ้นกับฟอนต์ในเครื่อง; ไม่ได้ทำ browser-render/native Tauri validation.
- Architecture auditor แก้ FDIAเป็นนิยามv0.3ที่ไม่มีapprovedexpandedname และไม่รายงาน Layer2 range ที่ลบไปแล้วซ้ำ. ยังเป็น heuristic source inventory ไม่ใช่ certification.
- เพิ่ม `scripts/runtime_readiness.py` ตรวจ local model, optional local inference, DNS, browser sandbox และ OpenSSH ก่อนเสียเวลารัน full integration. ไม่เปลี่ยน failed tests เป็น skipped หรือ scripted passes.

## ผลทดสอบรอบสุดท้าย

| ชุด | ผลจริง / ขอบเขต |
|---|---|
| Full Python release | **7,888 passed / 13 failed / 59 skipped / 1 xfailed**, 748.12 วินาที (12นาที28วินาที), exit1 |
| Coverage ตามคำสั่ง | 90,351/99,102 statements ≈91.17%; รวม test modules ไม่ใช่ production-only coverage |
| Focused regressions รวม gate properties | **261 passed**, ไม่บวกซ้ำเป็น unique full tests |
| Pipeline harness | **21/21 cases, 134/134 checks**; --no-subagents จึงไม่อ้าง cases ที่เว้น |
| HTTP initial-plan integration | ผ่าน real Uvicorn restart, SQLite, file tools; waitก่อนmodel, answers→visibleplan, executionและgroundingตรงconfirmedbudget; scripted model2calls |
| TypeScript SDK / WASM / Edge / Action | **73 / 32 / 37 / 11 passed** รวม153tests |
| Action artifact | tsc/ncc buildผ่าน, node syntaxผ่าน, bundled process5casesผ่านรวมredirectdestinationrequests0; syntheticloopbackpolicybackend ไม่ใช่GitHub-hostedexecution |
| GUI web | build/staticexport/type-check/lintผ่าน; HTTPตรวจ4pagesและstylesheet; ไม่ใช่browserrender/nativeTauri |
| Wheel | buildและติดตั้งในvenvแยกจากcheckoutผ่าน; enrichedplan/initialwait/answers smokeผ่าน; ไม่publish |
| Lint | changedfilesและCI scope core/signedai/rct_control_plane/microservicesผ่าน; authored-source diffผ่าน; generatedbundlewhitespaceเก็บตามbuild |
| Docs / claims | local linksตรวจ19รายการไม่ขาดก่อนเพิ่มรายงานนี้, claim-syncผ่าน; historicalcheckpointไม่ถูกเขียนทับ |
| Preflight real integration | SSHผ่าน; localmodel/browser/DNSยังไม่พร้อม จึงready=false/exit1ตามจริง |
| Demo recording | releaseclip26.2วินาที; rawUTF-8=transcript=cast, ไม่มีU+FFFD, ตรวจThai frameจริง; SCRIPTED+user-declaredplan label |

13failuresที่เหลือคือ9localOllama model,3browser sandbox,1publicDNS/crawl. ชื่อcaseและtracebackอยู่ในfull-python-release.log/JUnit. SSHfailureเดิมปิดแล้ว; statuscompatibilityregressionจากรอบแรกไม่อยู่ในผลrelease. ไม่มีfailureใหม่ในส่วนที่แก้เหลืออยู่ในrunนี้ แต่ยังไม่ใช่fullsuite allgreen และไม่ยืนยันsurfacesที่ยังblocked.

```bash
TERM=xterm-256color RCT_LLM_PROVIDER=regex \
TIKTOKEN_CACHE_DIR=/workspace/.cache/tiktoken \
NLTK_DATA=/workspace/.cache/nltk_data DELENTIA_RUN_LIVE_TESTS=0 \
python -m pytest -n 3 --dist loadfile -q --timeout=600 \
  --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane \
  --cov-report=xml:coverage-release.xml --cov-report=term:skip-covered \
  --cov-fail-under=72 --junitxml=full-python-release.xml
```

PostgreSQL DSNส่งผ่านenvironmentของloopbacktestcontainer. Warnings6,855ส่วนใหญ่เกี่ยวกับdeprecatedAPIs ต้องแยกmaintenanceออกจากผลpass/fail. NativeTauriRust/GTK/WebKitยังไม่รัน; บันทึกownerhost/72hsoak/witness/externalpilotยังไม่เกิดในcloudรอบนี้.

## เหตุใด prerequisites ยังไม่ครบ

1. **Ollama**: แก้ CA trust ภายใน task-owned containerด้วยpublicCAที่platformเชื่อถืออยู่แล้วและคงTLSverification. หลังแก้ trust, official blob CDN ยังถูกproxyปฏิเสธ403. Sparsepartialมีlogicalsize4.68GBแต่Completed0ทุกpart ไม่ใช่weightsที่ใช้ได้. ต้องเพิ่ม exact CDN hostname ในรายการnetworkเดิมและตรวจความพร้อม/พื้นที่/manifesthashใหม่. Registry manifestอย่างเดียวไม่พอ.
2. **Browser**: setuid sandbox helper ถูกremapเป็นnobody; usernamespace sandboxก็ใช้ไม่ได้. ต้องปรับbaseimage/host/runtimeให้sandboxใช้งานได้ ไม่ใช้--no-sandbox/privileged/ปิดseccompเพื่อแต่งผล.
3. **Public crawl**: hostDNSล้มเหลวและproxyfetch403. ต้องมีDNS+permittedegressที่รักษาDNSpinning/SSRFcontrols. Proxy-onlyHTTPไม่ใช่หลักฐานว่าcrawlertransportพร้อม.

Real-model testsอาจมีmodel/application failuresใหม่หลังdownloadสำเร็จได้ จึงไม่สัญญาว่าเปิดnetworkแล้วทุกข้อจะผ่านทันที. Rerunกลุ่มที่affectedก่อนfullอีกครั้งเมื่อstateเปลี่ยนจริง. คำสั่งและขั้นตอนอยู่ในเอกสารprerequisites.

## Dependency triage

รัน production `npm audit --omit=dev` จริง: GUI0findings; Action2highจากfollow-redirects (GHSA-q3jh-wrc6-jgq8 และ GHSA-8r9p-f939-6h3c), auditให้fixAvailable=false. Mitigatecallsiteด้วยmaxRedirects0และทดสอบtrafficจริง; **ยังไม่อ้างว่าลบdependencyadvisoriesแล้ว**. ต้องรอ/เลือกpatchedversionที่มีจริง ตรวจreachabilityของconsumerอื่นและrebuildlock/bundleต่อ. ไม่บวก/ลบตัวเลขนี้กับGitHubdefaultbranch14alertsจากรอบก่อนโดยยังไม่ได้mapรายการเดียวกัน.

## คุณภาพและระยะห่างจากเป้าหมาย

กลไกใหม่มีtestsที่ตรวจพฤติกรรมจริงและกรณีปฏิเสธ ไม่ใช่แค่schemaมีfieldหรือสคริปต์พิมพ์PASS. ผลสนับสนุนdeclaredcontext/clarification/ownership/dataflow/packagingในscopeที่วัด. ยังไม่ยืนยันcapablemodel, userutility, causalbenefit, fullRCT, multi-dayautonomyหรือproductionsecurity. RCT R1/R3/R4/R5ก้าวหน้าด้านobservablestructureสำหรับdeclaredplans; semanticderivation, fullrevision, effects/recoveryและbroaderentrypointsยังค้าง.

รอบA–Fไม่ได้เสร็จทั้งหมด: รอบBทำส่วนdeclaredcontext/initialwait/expansion; รอบDทำบางdistribution/auditor/triage; รอบCยังคงread-onlyfence, รอบEยังไม่ใช้paidmodel และรอบFยังไม่มี72hhost/outsidepilot. ไม่แปลงจำนวนfeatures/testsเป็นcompletionเปอร์เซ็นต์.

## Provenance และข้อจำกัดของการตรวจ

Full runรอบแรกพบ13infra failuresบวก1compatibility regression: output-scope refusalใช้ชื่อสถานะใหม่ในlegacyroute. แก้ให้legacyคงfdia_blockedและcontractคงสถานะของcontract โดยทุกกรณียังบล็อกก่อนeffect. จากการตรวจเดโมพบconfirmedinputไม่ถึงVERIFYและแก้อีกครั้ง; full runระหว่างนั้นถูกinterruptและไม่ถือว่าจบ. ผลreleaseใช้runtimeหลังแก้ทั้งสองจุด. เก็บinitial/interruptedlogsแยก ไม่เขียนผลเก่าให้เป็นpass.

Generated Action bundleมีupstreamwhitespaceในruntime/vendor code จึงเก็บbytesที่buildได้และตรวจauthored-source diffแยก; ไม่trimstringsของvendorเพื่อให้diffcheckสวย. Source Ruff/CI scopeและpackagechecksต้องอ่านแยกจากgeneratedartifact. Lockfilesและdependencyversionsไม่เปลี่ยน; Actionpackage scriptเปลี่ยนเพื่อtypecheckโดยไม่ทิ้งunbundledoutput.

Static GUI HTTP smokeไม่ใช่browserrender; bundledActionใช้syntheticloopbackbackendไม่ใช่GitHub-hostedexecution; pipeline --no-subagentsเว้นกรณีsubagents. Wheelเป็นlocalreviewbuild2.3.1ไม่ได้publish และpackageversionไม่แทนexactcommit. Scriptedmodelไม่ใช่capablemodelและไม่มีpaidcalls.

Cloud start_skillฉบับใหม่บันทึกแล้วพร้อมpreflight, CAtrust, knownblockersและstartupchecks. Saved draftไม่ใช่runtimeupdate/publication/freshrestore; review/saveและPublishผ่านEnvironment Settingsเป็นคนละขั้น. ไม่เขียนทับallowlistที่อ่านรายการเดิมไม่ได้.
