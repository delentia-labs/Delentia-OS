# แผนหลังรอบ declared plans และ runtime readiness

สถานะรอบถัดมา: อ่าน [ผล criterion-derived plans/receipts และ dependency patches](RCT_DERIVED_PLANNING_RESULTS_2026-10-22_TH.md) และ [gates ล่าสุด](RCT_COMPLETION_NEXT_GATES_TH.md) ประกอบ รายการด้านล่างเก็บไว้ตาม checkpoint เดิม; follow-redirects1.16.1 มีแล้วและได้รับการอัปเดตทั้ง Action/SDK ในรอบใหม่ ไม่ได้อยู่ในสถานะรอแพตช์อีกต่อไป

22 ตุลาคม 2026. ใช้ร่วมกับ [แผนเดิม](CODEX_NEXT_LEVEL_PLAN_TH.md). รอบนี้เดินงาน B และบางส่วน D พร้อมปิด SSHfailure; ไม่ได้ประกาศว่ารอบ A–F เสร็จทั้งหมด.

## สิ่งที่ส่งมอบรอบนี้

- B: typeddeclaredcontext, reportedfacts/sources/unknowns/assumptions, componentDAG+criteriacoverage, initialcriticalinputwait, durableanswers/revisions และ CLI/APIplanordering
- B: compressedoutput→expand กลับครบไทย/ตัวเลข โดย namespace+currentepisodechecks; contract ยัง read-only
- Setup: preflight ที่ fail จริงและคำอธิบาย model/browser/DNS/SSH; แก้ containerCA โดยไม่ปิด TLS แต่ modelblob ยัง 403
- D: SSHisolation, ActionESMbuild+gatecases+bundledsmoke, GUIbuild ไม่พึ่ง GoogleFonts, auditorFDIAwording และ removedhistoricalclaim
- Securitytriage: productionnpm audit ของ GUI พบ 0; Action พบ 2high จาก follow-redirects; ปิด redirect ที่ APIcalls และทดสอบไม่ส่ง request/credential ไป destination แต่ยังไม่อ้าง dependencyalerts ปิดแล้ว

## ลำดับถัดไป

### 1. ทำ realintegrationhost ให้พร้อม

ผู้ดูแล environment เพิ่ม officialmodelblobdomain ใน network รายการเดิม, เตรียม DNS/publicpinnedegress และ Chromiumsandbox ที่ใช้ได้. เก็บ preflight ก่อน/หลัง, modelmanifest/digest, inference และ rerun กลุ่ม 13failure ที่ยังต้องรอ prerequisites ตามรายงานจริง. อย่าแทน model/crawler/browser ด้วย fixture แล้วอ้าง allgreen. ดู [วิธีแก้](RUNTIME_PREREQUISITES_AND_FAILURES_TH.md).

### 2. ขยาย B จาก declaredplan ไปสู่ semanticplanner

เก็บ goal-dependentfacts/relations/components/backwardprerequisites ที่ระบบสร้างเองโดยมี provenance และ uncertainty. แยก reportedfact จาก observed/verifiedsource, critical จาก optionalunknown และการขอคำยืนยันจากการให้ permission. ทำ Thai/Englishfixtures และ paraphrases ก่อน implementation. Acceptance: goal เปลี่ยนแต่ facts เดิม→componentplan เปลี่ยนถูกต้อง; everycriterion มี evidence/action/check; ไม่ยืม holdout มา debug. เพิ่ม contextrevision/migration/corruptiontests ก่อนเปิด default.

### 3. รอบ C: signed effects และ recovery

ออก state machine+crashmatrix ก่อนเปิด write: contract/planhash/version ต้องผูกกับ exactapprovedaction และ journalreceipt. ทดสอบ claimrace, policychange, erasure ระหว่างรัน, crash ก่อน/หลัง effect และ unknownoutcome. Reconcile กับ observableeffects ก่อน resumption; ห้าม resetrunning ตาม timeout. Read-onlyfence คงอยู่จนผ่าน. แยก initialwait/pendingapproval/mismatchwait/interrupted/unknownoutcome ทั้ง API และ UI.

### 4. Entry points และ distribution

ขยาย planevents/clarification/continuation ไป Desk/jobs/channels ที่เลือกทีละ surface พร้อม matrix การครอบคลุม. GUIwebbuild ผ่านไม่เท่ากับ nativeTauri; เตรียม Rust/GTK/WebKitCI และ freshinstall ก่อนเปิด desktop. Action มี bundledlocalexecution แล้วแต่ยังต้อง validateGitHub-hostedworkflow/branchprotection/realAPIauth; pendinghumanapproval ปัจจุบันเป็น warning ไม่ใช่การเซ็นอนุมัติให้เกิด effect. เพิ่ม response-schema/inputvalidation และ reviewpolicyboundary ก่อนอ้าง mergeassurance.

รอ patchedfollow-redirectsversion ที่ registry มีจริงและ updatelockfile แบบ reviewed แล้ว rebuildbundle; npm audit รอบนี้ให้ fixAvailable=false. ตรวจ reachability และ otherconsumers ด้วย ไม่ถือว่า maxRedirects0 แก้ library ทั่ว repository. GitHubdefaultbranch14alerts จากรอบก่อนยังต้องแยกรายการจริง ไม่เอา 2npmfindings ไปบวก/ลบจาก 14 โดยไม่ mapadvisories.

### 5. Model development, freeze, evaluation

ยังไม่ใช้ paidAPI. เมื่อผู้ใช้กำหนด provider/model/caps ภายหลังจึง capabilityscreen และ devsmoke1–2attempts. Freezecommit/model/settings/policy/plan-schema/fixtures/oracle/protocol ก่อน formalcomparison ตาม A111−GP. Declaredcontext เป็น treatmentinput ที่ต้องตรงกันทุก arm; เปลี่ยน semantics ต้อง versionprotocol. ScriptedHTTP และ unitpass ไม่ใช่ modelability หรือ causalbenefit.

### 6. L2pilot และโพสต์แรก

Pilot ต้อง capablemodel, Linuxhost/72hsoak, separate-usernotary, offhostscheduledwitness, backuprestore, budgets/alerts/operatorstops และ outsidefeedback. ยังไม่ผ่านด้วย build/testcount อย่างเดียว. โพสต์ L0 ทำได้หลัง reviewsource/caption/definitions และเปิดเผย blockers; labelSCRIPTED และ declaredplanning ให้ชัด ไม่อ้าง completeRCT7/stable/compliance/zerohallucination. ไม่มี auto-post/deploy/merge.

## แบ่งงาน

Codexbranch `codex/rct-plan-and-runtime-readiness-20261022`, base `2fc16e8a7dd425d78debb6ebbff4c05e1d65b041`. Sharedfiles คือ governedloop/contract/API/CLI/sandbox และ distributionfiles ใน diff; ต้องส่ง commit/test/evidencehandoff ก่อน Claude แก้ไฟล์เดียวกัน. Fetch/readstatus และ mergebase ทุกรอบ ไม่ forcepush หรือแก้ checkout เดียวพร้อมกัน. Runtime และ model/config/evaluationprovenance ต้องเก็บแยกจากชื่อผู้ช่วยที่เขียนโค้ด.

ผลส่งมอบสุดท้ายและตัวเลขที่รันจริงอยู่ใน [รายงานรอบนี้](RCT_PLAN_READINESS_RESULTS_2026-10-22_TH.md). เพิ่ม regression หลังพบว่าคำตอบงบจากผู้ใช้ยังไม่ถึง VERIFY; ตอนนี้ confirmed unknown answers ใช้เป็น evidence ได้ ขณะที่ตัวเลขที่โมเดลแต่งยังถูกปฏิเสธ. ยังไม่ยกระดับ heuristic check เป็น semantic truth oracle.
