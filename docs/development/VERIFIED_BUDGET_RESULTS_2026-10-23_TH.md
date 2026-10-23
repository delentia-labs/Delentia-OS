# ผลพัฒนา RCT-7: verified budget execution และ component receipts

23ตุลาคม2026 — branch codex/rct-verified-budget-receipts-20261023 จาก base67bf57e1b0952d16b4878391b1be16ab34d62755. รอบนี้ปิดช่องว่างจาก “แผนอยู่ในcontext” ไปสู่ “อ่านหลักฐาน/คำนวณ/ตรวจผล/บันทึกการจบcomponentจริง” สำหรับ workflow เดียวที่ระบุขอบเขตชัดเจน ไม่ได้ประกาศ RCT-7ทั่วไปหรือproduction-ready

## ผลลัพธ์ที่ทำได้จริง

เพิ่ม verified_budget_v1: อ่าน quote JSONผ่าน governed MCP tool, ตรวจpinnedhashของobservedbytes, parse schemaเข้มงวด, เทียบยอดกับงบสกุลเดียวด้วยDecimal และออกcanonical JSONพร้อม receipts ที่ต้องเรียงตามdependencies ระบบไม่เรียกgeneration providerในเส้นทางนี้ ไม่ใช้ScriptedModelแทนการทำงานจริง

CLIจริงกับkernel/MCP/SQLiteจริงผ่านทั้ง:
- 12,500.10THB เทียบ15,000THB → within_budget=true, remaining=2499.90
- 15,000.01THB เทียบ15,000THB → within_budget=false, remaining=-0.01

ทั้งสองกรณีมีgeneration calls/prompt tokens/completion tokensเป็น0, receiptsครบ7componentตามcriteriaที่ใช้, original intentคงอยู่และไฟล์unchanged งานรายงานว่าเกินงบถือว่าตรวจสำเร็จได้ ไม่ใช่การอนุมัติซื้อ/โอน/เขียนข้อมูล

## กลไกที่เปลี่ยน

AutonomousLoopมี decision-source methodที่overrideได้ โดยdefaultยังเรียกproviderเหมือนเดิม Governed loopเลือกdeterministic driverเฉพาะrequestที่compileเป็นverified_budget_v1 ทุกtoolcallยังผ่านnormalguard/policy/gate/notary/journal/hooks การทดสอบpolicy refusalพิสูจน์ว่าdriverไม่ข้ามgate

เพิ่ม semantic_plan.quote_evidence={relative_path,sha256} แบบopt-in ต้องเป็นbudget taskและมีjson_object criterion ไม่เปลี่ยนdefault agentหรือเปิดwrite fence Quoteเป็นUTF-8 JSON≤20KB, schema_version integer1, totalเป็นdecimal string≤2ตำแหน่งและ≤1e15, currency THB/USD/EUR และtotal_is_final booleantrue Fieldเกิน/duplicate keys/nonfinite/ยอดไม่final/คนละสกุลเงินทำให้งานไม่ผ่าน ไม่มีFXหรือการเดาภาษี/เงื่อนไขที่ไม่ได้อยู่ในข้อมูล

Graphที่compileมาใช้handlersตามลำดับ inspect_sources→compare_budget→compose_answer→prepare/check ของcriteria:
- read/comparison receiptspersistในrunning claimก่อนคืนผลfinal
- completionต้องมีdependenciesและrequiredinputsครบ
- receiptsผูกcontract/namespace/claimversion/planhash มีoutputและhashchainพร้อมordinal
- storeตรวจความสอดคล้องของreceiptsตอนอ่าน
- finalcheckอ่านcurrent sourceด้วยPOSIX descriptor-relative no-follow reader ปฏิเสธsymlink/nonregular และตรวจhashอีกครั้ง
- acceptanceต้องมีรายงานตรงกับcanonical arithmeticและreceiptsครบทุกnode พร้อมผ่านcriteriaเดิม
- reviseล้างreceiptsเก่า ไม่รับมรดกcompletionจากแผนก่อน

Observed bytesไม่ใช่การรับรองvendor truthหรือความครบของข้อความ total_is_final. Receiptเป็นsealed local working record ไม่ใช่signature/off-host witness และไม่ป้องกันtrusted writerที่เขียนข้อมูล/hashใหม่ได้ทั้งชุด Source acquisitionยังใช้MCPread policyเดิม; final no-follow freshness checkไม่ได้รับรองว่าactual MCPreadทุกกรณีป้องกันhostile concurrent filesystem raceแล้ว ดู [activation gates](../release/ACTIVATION_GATES_2026-10-23_TH.md)

## Defectที่พบและแก้ก่อนยืนยันผล

ทดสอบเพิ่มพบว่าDecimalอย่างเดียวไม่พอ: หากapplicationส่วนอื่นตั้งambient precision=2, 15000−12500.10อาจได้2500.00 จึงแก้ใช้local Context precision40ที่แยกจากambient settings และเพิ่มregressionพิสูจน์ผล2499.90กับการไม่เปลี่ยนcontextของcaller

Full runก่อนแก้ถูกinterruptอย่างชัดเจน หลัง5517passed/29skippedใน252.51วินาที exit2 เป็นpartial run ไม่ใช่completed suiteและไม่บวกจำนวนกับรอบสุดท้าย เก็บinterrupted artifactsและprecision-defect evidenceไว้ หลังแก้focusedผ่านและจึงfreeze runtimeรันfullใหม่

## ผลทดสอบสุดท้าย

Final full Python: **7,975passed /13failed /59skipped /1xfailed**, **716.22วินาที**; warnings6,913; runner exit1เพราะfailuresยังอยู่ Coverage **91.24%** (91151/99906; รวมtest modules ไม่ใช่production-only coverage). 13failedเป็นnode idsเดิมทั้งหมด: local model9/browser sandbox3/DNS1 ไม่เปลี่ยนfailuresเป็นskipsหรือแทนโมเดลจริงด้วยfixtureเพื่อให้suiteเขียว เวลาsuiteไม่ใช่latencyของคำขอหนึ่งงาน

[Machine-readable result พร้อมfailures/skipped reasonsและraw evidence hashes](evidence/VERIFIED_BUDGET_2026-10-23.json)

Focused suite **290passed** รวมverified-budgetใหม่32กรณีและregressions semantic/contracts/governed/gate properties/CLI/API/streaming/callbacks จำนวนนี้ซ้อนกับfull suite

กรณีใหม่ครอบคลุมexact boundary/zero/over-budget/decimal arithmetic, invalid/truncated/duplicate/nonfinite JSON, hash/currency/scope mismatch, inferred budget wait, source changeหลังobserve, cancellationหลังdurablepartialreceipt, dependency/answer/receipt tamper, replan clearing, path/secret guards, final symlink/FIFO rejection, policy refusal, HTTP replay/namespace, ambient Decimal contextและunsupported platform refusal

Pipeline --no-subagents ผ่าน21/21cases134/134checks ไม่รันoptional subagent cases RuffตามCI scopeและauthored diff checkผ่าน Wheelติดตั้งในvalidation venvแล้วรันproduction CLIจาก/tmp importsite-packagesจริง ตรวจreport2499.90,5receiptsและfileunchangedผ่าน Version2.3.1เป็นlocal reviewartifact ต้องอ้างexactcommitประกอบ ไม่มีpackagepublication/native desktop/deployed-hostvalidationหรือJSchangesในรอบนี้

## ข้อสังเกตเรื่องผลตรวจที่ต้องแสดงให้ถูก

### การตรวจซ้ำก่อน commit/push

หลัง environment กลับมาเข้าถึงได้ ตรวจ verified-budget tests ซ้ำ: **32 passed / 68 warnings ใน 2.00 วินาที** ไม่ใช่การรัน full suite ใหม่ ผล full suite ด้านบนยังเป็นรอบก่อนดาวน์โหลดโมเดล

ตรวจ official model CDN ได้ HTTP 206 ใน probe แต่การ pull `qwen2.5:7b` ที่เริ่มภายหลัง **ไม่สำเร็จ**: proxy connection ไป CDN ขึ้น `no route to host`; ผล `/api/tags` ที่เก็บท้าย pull ยังไม่มีโมเดล ไม่ได้ปิด model integration failures 9 กรณี ไม่ปิด TLS verification และไม่ใช้ paid API หลักฐาน local: `model-cdn-probe.json`, `ollama-pull.json`, `publication-recheck.log` ใน evidence directory; ไม่เผย signed URL หรือ private state

ก่อนเผย branch พบ origin/main เพิ่ม dependency commits 3 รายการถึง `19d5fe8230f5f32691ae6a410085707219dd20a1` การตรวจ `git merge-tree` ไม่พบ conflict แต่ยังไม่ได้ merge/rebase หรือทดสอบต้นไม้รวม จึงไม่ถือว่าผล full suite นี้เป็นผลทดสอบ current main

semantic_verification/acceptance_verificationผ่านในCLIจริง แต่legacy intent_verificationยังaligned=falseสำหรับรายงานตัวเลขที่คำนวณขึ้นใหม่ Heuristicเดิมไม่ใช่arithmetic oracle และถูกเก็บแยกไว้ ไม่เปลี่ยนให้trueเพื่อแต่งภาพว่าgeneral intent fidelityผ่านแล้ว

ก่อนเปิดprofileสาธารณะต้องมีpublic response/UIที่บอกmethod/scopeชัดเจน และแยกoperational executionออกจากmodel scores: zero-generation runsไม่ใช่หลักฐานว่าตัวโมเดลตอบถูก/ผิดหรือมีcapabilityเพิ่ม Generic stopped_reasonชื่อllm_finishedยังเป็นcompatibility enum แม้executorนี้ไม่เรียกgenerationให้ดูexecutorและcostประกอบ

## Cloud setupที่แก้เพิ่ม

พบว่าDELENTIA_HOMEไม่ได้ตั้งและdefault /home/agentเขียนไม่ได้ จัดทำ /workspace/.delentia-cloud/activate-delentia.sh และoperator directory mode0700 แยกจากdemo โดยไม่เปลี่ยนHOME ใช้ephemeral probeใต้operator directoryทดสอบnamespace sealing+SQLite round-tripแล้วลบเฉพาะprobeของงานนี้

บันทึกstart_skillและsuggested DELENTIA_HOME=/workspace/.delentia-cloud/operator ลงenvironment draftสำเร็จ requires_publish=true ไม่เปลี่ยนnetwork/installscript/repository membershipและไม่เพิ่มsecret การsourcehelperทดสอบในเครื่องไม่ใช่การPublish/fresh-taskrestore ต้องreview/saveและPublishผ่านsettingsก่อนอ้างว่าsnapshotใหม่พร้อมแล้ว ไม่รวมoperator state/keysในชุดหลักฐาน

Preflightสดยังmodeltagsว่าง/browser sandbox abort/native DNS gaierror; SSH config isolationผ่าน เส้นทางdeterministicใหม่นี้ทำงานได้โดยไม่พึ่งสามcapabilitiesดังกล่าว แต่ไม่ทำให้full integration13กรณีหรือG-model/G-hostของโครงการผ่าน ดู [failure catalogเดิม](INTEGRATION_FAILURE_CATALOG_TH.md)

## RCT-7หลังพัฒนา

| ขั้น | หลักฐานที่เพิ่ม | สิ่งที่ยังต้องทำ |
|---|---|---|
| R1 Observe | pinned observed JSONbytesและreceiptเชื่อมactual toolresult; finalsnapshot | authenticity/recencyภายนอกworkspace, conflicting sources, immutable observation recordsทั่วไป |
| R2 Analyze | typedfinal total, confirmedbudget, explicitcurrency/scope constraints | generalambiguity/multi-intent/paraphrases, taxes/exclusionsและdomainอื่น |
| R3 Deconstruct | fixedtask graphมีhandlerและcompletionจริง | typedhandler registryและgeneric scheduler ไม่ใช่graphในpromptสำหรับtaskอื่น |
| R4 Reverse | read→compare→report→criteria prerequisitesถูกบังคับก่อนcomplete | ค้นหาnecessaryconditionsทั่วไปจากโจทย์จริงและvalidateความเพียงพอ |
| R5 Core intent | missingbudget wait+amount/currencyvalidation; mismatchwait | conversational clarificationทั่วไป/context reuseและfield-level revision/invalidation |
| R6 Reconstruct | CLI/APIplanก่อนงาน, per-node durablepartialreceipts | Desk/jobs/channels, strict serverprofile, cancel/disconnect/jobterminal/restart UX |
| R7 Compare | exactDecimal, strictreportequality, currenthash, fullreceiptsetและcriteria | semanticoraclesด้านอื่น, external effects/reconciliation, scope-consistentpublicverdict/metrics |

การจำลองcancelหลังreadยืนยันpartialstateอยู่จริงและrefuse automaticrestart แต่ไม่ใช่full real-process crash/recovery matrix Contractที่runningยังไม่ถูกreset/replayด้วยtimeout และwrite toolsยังปิดอยู่ ไม่อ้างexactly-onceของexternal effect

## จะออกจากคำว่าexperimentalไปทำงานจริงได้อย่างไร

เป้าหมายที่ใกล้และตรวจรับได้คือread-only quote-verification serviceที่รับschemaจำกัดและอธิบายassumptionsชัดเจน โค้ดlocalworkflowรันได้แล้ว แต่การเปิดให้คนนอกต้องปิดgatesเพิ่มเติม: server-enforced profile/no fallback, identity+file/workspace isolation, source-read race hardening, versioned response/errors, quota/rate/queue/resource bounds, idempotentrequest/status/delivery, recovery/restart, reproducible releaseและoperator monitoring/backup/restore

ขั้นต่อไปสำหรับagentทั่วไปยังต้องcapable model+frozenThai/Englishevaluation, general task/evidence handlers, independent semanticverifiers, contract-aware signed effects/crashreconciliation, channelsและLinuxhost/witness/notary/72hsoak/outsidepilot ตาม [activation assessmentแบบละเอียด](../release/ACTIVATION_GATES_2026-10-23_TH.md) ซึ่งแยกของเดิมที่มีอยู่กับหลักฐานที่ยังไม่ผ่านของรุ่นนี้

สถานะที่ยืนยัน: **experimental governed runtime ที่มี deterministic read-only verified workflow และdependency-enforced component receiptsในขอบเขตหนึ่ง** ยังไม่ใช่RCT-7ครบทุกโจทย์หรือproduction/pilot-ready ไม่มีmerge main/deploy/publish/post/outsidecontactในการพัฒนารอบนี้

ดู [schema/พฤติกรรม](../concepts/verified-budget-executor.md). Evidenceอยู่ /workspace/delentia-verified-budget-evidence มีfull/targeted/Pipeline logs, actual CLI results, wheel proof, operator-home probe, preflightและsource hashes โดยexcludeprivate databases/keys/demo stateจากชุดแชร์
