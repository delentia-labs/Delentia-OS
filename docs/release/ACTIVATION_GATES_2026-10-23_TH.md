# เกณฑ์ออกจาก experimental runtime ไปสู่การรับงานจริง

อัปเดตต่อเนื่อง: ดู [protected files/host/Desk checkpoint](../development/PROTECTED_FILES_AND_DESK_FOLLOWUP_2026-10-23_TH.md) และ [typed scheduler results](../development/RCT_FRAMEWORK_AND_RUNTIME_RECOVERY_2026-10-23_TH.md). ตารางด้านล่างเป็น baseline เก่า: ตอนนี้มี generic scheduler substrate และ no-follow actual MCP acquisition สำหรับ verified_read แล้ว แต่ general planner, server profile, recovery และ pilot gates ยังไม่ปิด.

ประเมิน23ตุลาคม2026เฉพาะ code/evidence รอบ verified-budget จาก base67bf57e. ใช้ [release levels เดิม](RELEASE_LEVELS.md) เป็นหลัก ไม่ยกระดับทั้งโครงการด้วยจำนวน tests หรือผล workflow เดียว สถานะ metในเอกสารเก่าผูกกับ checkpoint/hostเดิม ไม่ใช่หลักฐานว่า branch/host/profileใหม่นี้ผ่านแล้ว

## เป้าหมายแรกที่มีขอบเขตชัดเจน

รับงาน “อ่าน JSON ที่ผู้ใช้ระบุว่าเป็นยอดสุดท้าย เปรียบเทียบกับงบสกุลเดียว และส่งรายงานตรวจสอบพร้อมหลักฐาน” แบบ read-only บน POSIX workspace ที่ operatorควบคุม ไม่ต้องรอโมเดลทั่วไปเพื่อคำนวณงานนี้ การที่โหมดนี้ไม่ใช้generationไม่ได้ทำให้ G-model หรือ L2 ของ generic agent ผ่านโดยอัตโนมัติ

Local CLI/workflow ทำงานจริงแล้วตาม [ผลทดสอบ](../development/VERIFIED_BUDGET_RESULTS_2026-10-23_TH.md). การเปิดบริการรับไฟล์จากคนนอกยังต้องมี release profile ที่ serverบังคับจริง ไม่พึ่ง clientเลือกsemantic_planถูกต้อง

## Gate matrix สำหรับรุ่นรับงานจำกัดขอบเขต

| Gate | ของที่มี/ตรวจแล้ว | สิ่งที่ยังต้องปิด | หลักฐานก่อนเปิด |
|---|---|---|---|
| Task contract | strict JSON/amount/currency/size/hash; positive budget; waitและcanonical result | versioned public request/result/error contract; unsupported requests/executor versionsต้องไม่fallbackไปagentทั่วไป | schema/fuzz/migration tests และเอกสารข้อจำกัดที่ตรงกับruntime |
| Execution | fixed dependency-enforced receipts; actual governed read; exact arithmetic; all-node acceptance | generic schedulerยังไม่มี; must exposeเฉพาะhandlerที่reviewed; test quota/time/cancel edgesของprofile | per-node observations/results และ negative testsที่ปิดdependent workได้จริง |
| Server profile | CLI/HTTP opt-inใช้งานได้ | monolithยังรับ generic agent/jobs/routesอื่นได้ ต้องมี server-enforced allowlist/no fallback/no write routesของprofile | route/method/identity/payload mutation tests; เปิดเฉพาะsurfaceที่ผ่าน |
| Identity/data isolation | token identity/namespace contractsและsecret-path mechanismsเดิม; cross-namespace regressionผ่าน | per-user file authorizationและserver-selected workspace; ไม่ใช้global REPO_ROOTสลับต่อrequest; แยกstate/keysจากdemo | two-user concurrent file/contract tests, revocation, export/erasure และworkspace escape tests |
| Filesystem | expected hashและfinal descriptor-relative no-follow check; symlink/FIFO refusalที่final checker | review/harden actual MCP source read against resolve/read racesก่อนเปิดuntrusted concurrent writers | actual-source TOCTOU/symlink/race tests บนtargetfilesystem; readresultต้องไม่เปิดเผยข้อมูลนอกscopeแม้งานถูกปฏิเสธ |
| Evidence meaning | observed bytes, scope flagในdocument, final snapshotและexact report | vendor authenticity/freshness beyondlocal snapshot, forged/conflicting documents, taxes/exclusions และsource reconciliation | กำหนดว่าใครรับรองtotal_is_final; signed/observedsourcepolicyตามworkflowจริง ห้ามอ้างuniversal truth |
| Receipt/recovery | sealed hash-linked partial receipts; version claim; replay refused; cancellation checkpoint | full process-crash matrix, job terminal states, reconciliation, acknowledgement failures, duplicate requests/delivery | real-process kill/restart testsทุกboundary; observable outcome; no blind reset/retry |
| Verification/UI | semantic/acceptance verdictsตรงกับtyped workflow | legacy intent heuristicอาจfalseแม้arithmeticถูก ต้องแสดงmethod/scopeและnormalizepublic response; zero-generation runsไม่ปนmodel scores | UI/API consumer tests; no false “model success/learning” attribution; operatorมองเห็นcause/wait/status |
| Build/release | wheelสร้างและติดตั้งจากนอกcheckout; source-byte integrity | versioned release/image, pinned runtime deps, targetOS fresh install/upgrade/rollback และCIของexactcommit | reproducible artifact+checksums+dependency review ไม่ใช้หมายเลข2.3.1เพียงอย่างเดียว |
| Operator storage | writable DELENTIA_HOME mode0700และsealing/SQLite probe; startupdraft saved | review/save/Publish configและfresh-taskrestoreยังไม่verified; backup retention/key policy | restart/restoreจากoff-hostcopyและoperator runbookที่ผู้อื่นทำตามได้ |
| Capacity/reliability | input20KB, bounded numbers, loop/time budgetsเดิม; no-generation task | rate/concurrency/queue/disk limits, resource isolation, latency/SLO/errorbudget/alerting | workloadที่กำหนดและวัดจริง; testsตามโหลด/ไฟล์เสีย/ดิสก์เต็ม/DB lock; ไม่ใช้เวลารันsuiteเป็นlatency |
| Pilot operations | audit/notary/witness/backup toolsเดิมมีอยู่ | Linux host72h, separate-user notary, scheduledoff-hostwitness, restore/rollback drill, owner/operator stopและoutsidefeedbackของprofileนี้ | timestamped operational evidenceและincident reviewจากhost/ผู้ใช้จริง |

ตารางนี้เป็น acceptance backlog ไม่ใช่การรับรองว่าทุก findingเป็นexploitที่reproduceแล้ว จุด resolve/read race เป็นขอบเขตที่เห็นจากsourceและต้องทดสอบ/hardenก่อนเปิดให้ผู้เขียนไฟล์ที่ไม่ไว้ใจกันใช้งานร่วมกัน Final hash mismatchป้องกันการยอมรับผลที่ไม่ตรงpin แต่ไม่ใช่การรับรองความลับของทุกreadresult

Public schemaยังต้องกำหนดcanonical encodingข้ามภาษา: monetary valuesเป็นdecimal stringsอยู่แล้ว แต่recorded_nsของreceiptเป็นPython integerที่ใหญ่กว่าJavaScript safe-integer range ต้องใช้exact-integer codecหรือออกschema migrationที่ระบุชัดก่อนให้clientคำนวณhashใหม่ และต้องแยกcompatibilityenum llm_finished/legacyheuristicออกจากdeterministic task verdict ไม่ใช้zero-generation operational recordsเป็นmodel accuracy scores

## ก้าวต่อไปสำหรับ RCT-7 ทั่วไป

1. R1/R2: observed-source identity/freshness/conflict resolution และ general ambiguity/multi-intent handling พร้อม provenance/uncertaintyที่วัดได้
2. R3/R4/R6: typed handler registry, input/output schemas, dependency schedulerและcompletion receiptsสำหรับtaskอื่น โดยแผนจากโมเดลไม่เพิ่มauthority
3. R5/R7: field-level context revisions/invalidation, semantic/numeric/domain verifiers, clarified waitsและverified corrections ไม่ใช้contains/script checksเป็นtruth oracle
4. Effects: contract id/version, plan/action/policy/workspace/actor bindings, nonce/expiryและactual signature ผ่านapproval/notary/journalเดิม; idempotency/reconciliationตามtoolcapabilityก่อนเปิดwrite fence
5. Model: capable local modelและThai/English development/holdout evaluationที่freeze provider/model/digest/settings/code/schema/policy/protocol; paidAPIยังไม่เปิด
6. Surfaces: Desk/jobs/cron/channelsทีละsurfaceพร้อมplan-before-effects, persistentwait, namespace/replay/cancel/disconnect/restart tests ไม่เหมารวมจากsharedloop
7. Operations: ผ่านgatesของsurfaceที่จะเปิดตามrelease levelsเดิม แล้วL2supervisedpilotและL3designpartnerตามoperatorcontract L4ยังไม่อยู่ในแผนเดิม

## การประกาศ/โพสต์ที่สอดคล้องกับหลักฐาน

รอบนี้กล่าวได้ว่า “มี workflow ตรวจยอด JSON แบบอ่านอย่างเดียวที่รันจริงผ่าน kernel/MCP/SQLite โดยไม่ใช้generation model พร้อม source hash, Decimal และcomponent receipts” ต้องระบุschema/สกุลเงิน/OS/ขนาดไฟล์ที่รองรับ และแยกdocument assertionออกจากexternal truth

ยังกล่าวไม่ได้ว่า RCT-7ครบทุกโจทย์, agentทำงานเองได้ทุกช่องทาง, production/pilotพร้อม, ภาษี/FX/การซื้อถูกอนุมัติแล้ว หรือมีgeneral-model accuracyจากdemoนี้ ไม่มีการmerge main/deploy/publish/postหรือเริ่มoutsidepilotอัตโนมัติในงานนี้
