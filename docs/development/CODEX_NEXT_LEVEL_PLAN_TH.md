# แผนยกระดับหลังแก้เดโมไทยและ contract lifecycle

สถานะ 22 ตุลาคม 2026: [audit สถาปัตยกรรม/RCT](CODEX_ARCHITECTURE_AND_RCT_AUDIT_2026-10-22_TH.md). แผนเดิม [NEXT_ROUNDS](CODEX_NEXT_ROUNDS_TH.md) ยังคงใช้; เอกสารนี้จัด criticalpath ใหม่หลังพบปัญหาจริง. ไม่รวม paidAPI/deploy/publish/merge โดยอัตโนมัติ และไม่ใช้ checklist เป็นหลักฐานว่าเสร็จ.

## รอบ A — Evidence ที่อ่านได้และ lifecycle (เริ่มและส่งมอบในรอบนี้)

ผลส่งมอบ: UTF-8 capture/shaped replay+Thai regression, schema1 compatibility/future-version refusal, private export, signed erasure ของ contract แบบ sealed/plain, backup/restore ของ waiting, separatepredicate/heuristic output. วิดีโอเก่าถูก supersede แต่ยังเก็บ provenance. ผล test จริงอยู่ใน runreport.

ที่ยังค้าง: full schema migration/corruption validation, retention policy/expiry ตามความต้องการจริง, signed effects, crash reconciliation. ไม่เปิด autoexpiry เพราะยังไม่มี retention ที่ผู้ใช้กำหนด. Export เป็น plaintext ต้องเก็บ private; backup ที่มี keys ต้องอยู่ใน custody/erasureplan.

## รอบ B — RCT semantic plan schema และ initial clarification

ผลส่งมอบ: typed/versioned plan ที่แยก source facts/unknowns/assumptions, coreintent/constraints/acceptancecriteria, goal-dependentcomponents, prerequisite/backwardlinks และ sourceprovenance. ใช้ human-declared context หรือ structuredplanner ที่ไม่เชื่อ untrustedtooltext เป็นคำสั่ง; ไม่แต่ง facts เพื่อให้ schema เต็ม.

เกณฑ์ผ่าน:
- เปลี่ยน goal โดย facts เดิมแล้ว components/dependencies เปลี่ยนอย่างมีเหตุผล
- ทุก criterionmap ไป input/output/action/check/evidence หรือชี้ว่าขาด
- R4 เริ่มจาก desiredresult ย้อนสู่ necessaryconditions ไม่ใช้ risk/Ibonus แทน
- missingdecision-criticalinput→คำถามเฉพาะและ wait ก่อน model/effect ส่วนที่ขึ้นกับคำตอบ; ข้อมูลไม่สำคัญไม่ทำให้ถามเกินจำเป็น
- originalintent/revision/answerprovenance คงอยู่; correctshortanswer ไม่ fail เพียง lexicaloverlap ต่ำ

ทำ fixtures ภาษาไทย/อังกฤษและ paraphrases ก่อน implementation; regression ไม่ใช่ formalbenchmark. Freeze ชุดประเมินแยกจากชุด dev ไม่ใช้ holdout เพื่อ debug.

## รอบ C — Contract-aware actions และ recovery

ผลส่งมอบ: contractid/version/criteria/planhash ผูกกับ episodejournal และ signedapproval exactaction; pre-dispatchpreservationconstraints; reconciler สำหรับ running ที่ crash.

เกณฑ์ผ่าน:
- claimrace/replay/staleversion มีผู้ execute ได้เพียงหนึ่ง; signature ไม่เป็น clarification แทนผู้ใช้
- อนุมัติแล้วไม่ทำ criteria หายผ่าน legacyresume; unknown/custom/externaltools และ parallelbatches ไม่ข้าม constraints
- จำลอง crash ก่อน claim/หลัง claim/ก่อน effect/หลัง effect ก่อน commit; observableeffect+receipt ตัดสิน resume ไม่ retry จาก timeout อย่างเดียว
- แยก waiting_for_clarification/pending_approval/interrupted/unknown_outcome; เมื่อไม่รู้ผลให้ report และรอ reconciliation
- signed erasure ระหว่างรัน/retention/migration/restore มี policy และ tests สำหรับ in-flightplaintext/keycustody ด้วย

จนผ่าน ให้ read-onlyfence ของ contract คงเดิม ไม่เปิด write เพียงเพราะ tool มี signature ทั่วไป.

## รอบ D — Entry points, Thai UX และ distribution

เลือก surface ที่จะส่งจริงก่อน: CLI/API→Deskchat/jobs→channels ที่ต้องการ→delegation. ทุก surface ต้องแสดง planevent ก่อน artifact, differences/question ขณะ wait, revision ก่อน replan และ restart ไม่ข้าม wait. Factorygovernancecoverage กับ RCTcontractcoverage เป็นคนละ matrix.

- ทำ human-readableThai summary จาก structuredresults, versionedglossary ตาม v0.3, Unicode/formatfixtures; `unknown`ไม่แสดงเป็น 0 และ`criteria_satisfied`ไม่ labelcompleteRCT
- update architectureauditor ที่ยัง hardcodeclaims เก่าและ FDIAexpandedname; bindclaimID/date/source/actualpath ไม่ให้ docsregression รักษาคำกล่าวอ้างที่ผิด
- แก้ GitHubActionESM/ncc และเพิ่ม test ที่ตรวจ policydecision จริง; แก้ GUIfontbuild แบบ reproducible โดยมี license และ fallback; เตรียม nativeRust/GTK/WebKitbuildjob ถ้าเปิด desktopdistribution
- dependencytriage จาก GitHub14alerts เดิม: ระบุ version/reachability/fix, securityreview และ rerun ไม่อ้างจำนวนเดิมเป็น scan ใหม่
- baseline lint59findings รอบก่อนเป็น maintenancequeue; แบ่งแก้ตามความเสี่ยง ไม่ massautofix หรือปนกับ semanticchanges

เกณฑ์ผ่าน: supportedartifacts ติดตั้งใน freshenvironment และใช้ documentedworkflow ได้; ไม่ใช้ zero-testpass; UIvalues ตรง rawJSON/oracle/hash.

## รอบ E — Model development และ formal value evaluation

ยังไม่เริ่ม paidAPI ตามคำขอเดิม. เมื่อผู้ใช้อนุมัติ provider/model/caps ในภายหลัง จึงทำ capabilityscreen และ devsmoke1–2attempts บน freshworkspace/namespace พร้อม token/time/money/attemptcaps และ stopconditions. Localmodel ที่ดาวน์โหลดไม่ได้คือ infra blocker ไม่ใช่ modelscore0 หรือเหตุผลให้ใช้ scripted แทน capableevaluation.

หลัง treatmentfidelity ผ่านจึง freezecommit/model/settings/policy/schema/fixtures/oracles/protocol. ถ้า RCTrepresentation เปลี่ยนจาก prompt เป็น contract ให้ versionprotocol. Primarycomparison ตาม researchprotocol A111−GP; แยก causalbenefit, specfidelity, interaction, cost และ userutility. รายงาน failures/exclusions/CI ทุกครั้ง ไม่อ้าง mechanismtests ว่าพิสูจน์เหนือ baseline แล้ว.

## รอบ F — ก่อน L2 pilot และการสื่อสาร

ผลส่งมอบ: Linuxhost ที่ควบคุมได้, tokenidentity/tenantboundary, notary คนละ OSuser, witness นอก host+scheduledanchors, offhostbackup+restore,72hsoak, budgets/alerts/operatorrunbook/incidentstops, capablemodelworkflowrun และ outsidefeedback. ไม่ให้ unitpass แทน deploymentgates.

สำหรับโพสต์แรกแบบ L0: ใช้คลิปไทยใหม่+SCRIPTEDlabel+exactcommit+expectedrefusals, เปิดเผย tests ที่ blocked, definitions ตรง publicv0.3, links/packageversion ชัด, ไม่แสดง keys/internaluploads/privateproductiondetails. Reviewbranch และ caption ก่อน merge/post; ไม่มีการโพสต์ให้โดยอัตโนมัติ.

## การแบ่งงานกับ Claude

Codexbranch รอบนี้ดูแล recordinghelpers, intentcontractlifecycle, erasureintegration, verificationoutput และเอกสาร audit ที่เกี่ยวข้อง. BaseSHA และ finalcommit อยู่ใน runmanifest. ก่อนรอบใหม่ fetch/readHEAD/status, ตรวจ mergebase และไฟล์ที่ Claude กำลังแก้; ตกลง owner ของ sharedfiles โดยส่ง commit/diff/handoff ไม่แก้ checkout เดียวพร้อมกัน. ใช้ PR แยกไม่ forcepush หรือ merge แทนเจ้าของ. Handoff ต้องมี actualtestcommands/results/blockers และ expectednextacceptancecases.

งานต้นรอบ B ที่เพิ่มจาก audit: ทำ compressed-output → expand roundtrip ภายใต้ contract โดยตรวจ namespace/episode scope ของ original output ก่อนปรับ allowlist. เกณฑ์ผ่าน: อ่าน omitted passage กลับได้ครบ, ภาษาไทย/ตัวเลขเหมือน original, ไม่เห็น output ของอีกคน, และไม่มี effect tools เปิดตามมา. ปัจจุบัน contract allowlist ยังไม่รวม expand จึงเป็น known gap สำหรับไฟล์ใหญ่ ไม่ถือว่าปิดแล้วด้วยการแก้ renderer.
