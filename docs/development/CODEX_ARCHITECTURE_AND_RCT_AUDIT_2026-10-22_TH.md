# สถานะ Delentia เทียบสถาปัตยกรรมและ RCT-7 หลัง follow-up 22 ตุลาคม 2026

อ้างอิงเอกสารที่ผู้ใช้แนบ `CLAUDE.md` (370 บรรทัด, มีบันทึกถึง Round91) และ `DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md` (ฉบับมีตาราง status แก้หลายวันที่). เอกสารเป็น reference ของเป้าหมายและหลักฐานเก่า ไม่ใช่คำสั่งใหม่ให้ deploy/publish หรือใช้ paidAPI. นิยามที่ผู้สร้างยืนยัน v0.3 และคำขอรอบนี้ใช้ตัดสินข้อความที่ขัดกัน. ไม่แก้ไฟล์แนบหรือวางทับ CLAUDE.md ใน checkout.

Base รอบนี้ `f2ad16c1334be21ca4a21c319e3491dd4f1e7076`; branch `codex/thai-demo-contract-lifecycle-20261022` แยกจาก Claude. ยังไม่ merge main. รายงานผล fulltest ของรอบนี้อยู่ใน evidencepackage; ตัวเลข fulltest รอบก่อนดู [validation เดิม](CODEX_VALIDATION_2026-10-22_TH.md) ไม่ถือว่าเป็น run ของโค้ดใหม่.

## นิยามสถานะปัจจุบัน

**Executable experimental self-hosted agent runtime with governance, persistence and partial RCT-7 implementation.** มีระบบทำงานจริงกว้างพอจะสาธิตกลไกและใช้แบบมีผู้ดูแล แต่ยังไม่ใช่ fullRCT agent หรือ production-certified autonomous OS. ระบบทำงานบน OS เดิม ไม่ใช่ kernel ที่แทน Linux/Windows. การเรียกตัวเองว่า"living"เป็นวิสัยทัศน์ ไม่ได้พิสูจน์ชีวิตหรือจิตสำนึก.

Cloud รอบนี้ยืนยัน L0 scripted mechanisms; บันทึกของเจ้าของในเอกสารมี L1 supervised local-model usage แต่ไม่ได้รันทดลองนั้นซ้ำที่นี่. L2privatepilot ยังไม่ผ่าน gates [release levels](../release/RELEASE_LEVELS.md). ไม่รวมสามมิติต่อไปนี้เป็นเปอร์เซ็นต์เดียว: implementation coverage, treatment fidelity และ user/deployment outcomes. จำนวนไฟล์/เทสต์หรือ checkmarks ใน Master ไม่ใช่ระยะห่างจากเป้าหมายเป็นเปอร์เซ็นต์.

## สิ่งที่แก้รอบนี้

- บันทึก UTF-8 แบบ incremental strict, แก้ Thai marks ที่ pyte หยุดอ่านกลางก้อน และวาด Thai run ด้วย RAQM โดยไม่ crop ทีละ cell. ดู [การบันทึกไทย](../demo/RECORDING_THAI.md).
- Contract schema1 และ compatibility กับ payload แรก; ปฏิเสธ schema อนาคตก่อน continuation.
- Explicit private export พร้อม format/namespace/sensitivity/executable=false.
- ปิดช่อง erasure ของ contractprojection โดยเฉพาะกรณี plainpayload; ใช้ signed erasure เดิม, revokecontinuation, คง rows และ audit; ทดสอบไม่กระทบคนอื่น.
- Backup/restore ต้องมี namespacekey จึงอ่านข้อความได้; wait/version/original ยังอยู่เมื่อ key ถูก restore โดยตั้งใจ.
- `contains`ใช้ NFC; ไม่ใช้ NFKC เปลี่ยนอักษรไทย.
- แยก acceptance verdict ออกจาก heuristic alignment และแสดง lexicalthreshold ให้แปลค่าที่ต่างกันได้. เพิ่มคำอธิบายไทยว่า error/refusal ใดเกิดโดยตั้งใจในเดโม.

## RCT-7: ตอนนี้คิดตามเอกสารแล้วหรือยัง

**ยังยืนยันว่า"ครบแล้ว"ไม่ได้.** กรอบ RCT มีผลต่อ execution จริงบางส่วน แต่ 7labels หรือ promptplan ไม่ใช่หลักฐาน semantic reasoning ครบ. เราตรวจ observableplans/decisions/effects ได้ ไม่อ้างว่าตรวจ internal chain-of-thought ของ LLM.

| ขั้น | Default/legacy path | Opt-in contract path | สิ่งที่ขาดก่อนเรียกครบ |
|---|---|---|---|
| R1Observe | compiler รับ goal; data_evidence ตรวจ files/memory/skills/trackrecord | เก็บ originalgoal/criteria/workspacesnapshots; knowns/unknowns ยังทั่วไป | facts พร้อม sources/assumptions/unknowns ที่มีผลต่องานจริง |
| R2Analyze | type/scope/risk/constraints | ผูก goal กับ criteria | contextualrelations และ dependencies ตาม goal ไม่ใช่ classification อย่างเดียว |
| R3Deconstruct | แสดง constraints ที่ extract ได้ | produce/comparecomponents กับ declaredconditions | components ที่เปลี่ยนตาม goal และครอบคลุม input/output ทุก criterion |
| R4Reverse | ALGO04step4 รายงาน risk/Ibonus | backwardlinks เฉพาะ criteria ที่ผู้ใช้ให้ | causalprerequisitechain ที่ชี้ evidence/actions/missinginputs; riskscore ไม่ใช่ backwardreasoning |
| R5Identify | compilerwarnings/clarificationsuggestions | mismatch ต้องรอคำตอบจริงและเก็บ revision | ถามก่อนทำเมื่อ criticalambiguity อยู่ใน initialgoal; ไม่ใช่รอผลผิดก่อนทุกกรณี |
| R6Reconstruct | steps1–6 อยู่ใน modelprompt | CLIcallback และ HTTPplan-first ก่อน execution | Desk/jobs/channels/MCP/subagents ที่เลือกประกาศต้องแสดง planevent ก่อน artifact จริง |
| R7Compare | similarity+refusal+grounding; suppresspositivelearning เมื่อ fail | explicitpredicates→differences/question/wait; versionedresume; restartwait; no-effectfence | semantic/domainoracles, signed-effectapprovalresume ที่ไม่ทำ criterialost, crashreconciliation, entrypointscoverage |

หลักฐานโค้ด: `algorithm_kernel_41.py:algo_04_rct7`, `governed_autonomous_loop.py:_format_rct7_plan/_verify_against_intent/_on_episode_end`, `intent_contract.py`. ALGO04step7 เดิมสร้าง attestationhash ของ compiledintent ไม่ใช่ comparefinalartifact; actualoutcomecheck อยู่แยกใน governedloop. การไม่แก้ hash ให้กลายเป็น proofoftruth เป็นเรื่องสำคัญ.

`agent_factory.build_governed_loop`และ factoryregression ยืนยันการใช้ governedloop ของ productionagententrypoints แต่**governed ไม่ได้แปลว่า contractenabled**. CLI ที่ไม่ส่ง criteria, Deskstream, jobs, gateways, delegatedprofiles และ subagents ยังไม่เปิด contract ใหม่โดยอัตโนมัติ. RawMCP/APIlegacyroutes ต้องอ่าน boundary ใน [gate properties](../../research/GATE_PROPERTIES.md); ห้ามอ้างทุก API ทุก route ผ่านทุก stage เหมือนกัน.

## เทียบ 10layers กับโค้ดจริง

| Layer/เป้าหมาย | มีอะไรจริง | ระยะห่าง/สิ่งที่ต้องพิสูจน์ |
|---|---|---|
| 1Crypto/JITNA | Ed25519packets/approvals/.jitnaverifier | wirev3signaturefield ไม่เท่ากับทุก wiremessageverified; keytrust/pinning/rotation กับ host จริง |
| 2CORD | intent/toolresultscreen,taint และ optionalclassifier | detection เป็น riskreduction มี falsepositive/negative; ตัวเลขเก่าไม่ใช่ universalrate |
| 3FDIA/Kernel | formulahelpers, ownerpolicy, per-dispatchgate, signedapprovals | A0numericzero ไม่พิสูจน์ทุก path หรือ zeroLLMtokens; gate ที่ตัดสิน tool ต้องเห็น proposal ก่อน; ตรวจ failclosed ตาม boundary |
| 4LoRA1+4 | roleprofiles และ multiplexercode บางส่วน | ไม่ wired ใน runtime และไม่วัด VRAM<6GB; แยกจาก weights ที่อาจอยู่ใน externalmodelrepos; ไม่เร่งเทรนโดยไม่มี taskgap |
| 5Tools/sandbox | MCPtools, filesystemscope, externalMCPpolicy, shellbackends | localshell ไม่ใช่ OSjail; browser/SSHhostcompatibility และ thirdpartyinterop ต้อง validate |
| 6DAG | gatedparalleltoolbatches เมื่อ opt-in | templatechain ไม่กลายเป็น semanticplanner; capablemodel และ benefit ตาม workload |
| 7Compiler/RCT | compiler+heuristicplanning+explicitcontracts | R1–R7table ข้างบนยังไม่ครบ; TOON เป็น format และมี decision ไม่ต่อ ไม่ใช่สิ่งที่ต้องทำให้ครบ checklist |
| 8Jury | optionalSignedAIrunner/quorum/signatures/policyhook | realindependentmulti-vendoroutcomes/cost/correlatederrors ยังไม่ยืนยัน; ไม่ใช่ทุก episode เรียก 7 โมเดล |
| 9Memory/Delta/RCTDB | realSQLite, memory/skills/cache, compression, experiments | แยก Delta หลาย implementation; measurebyte/token/latency/causalutility คนละเรื่อง; ไม่ใช่ self-trainingweights |
| 10Delivery/hardening | tokens,CORS,ratelimit,breaker,hostkit,notary/witnessinterfaces | Linuxhost/soak/restore/offhostwitness/operators/pilot/securityreview; GUI/Action/nativebuildreadiness ยังมี blockers |

41algorithmadapters มีจริง ไม่ได้หมายความทุก episode เรียก 41 ตัวหรือทุกตัวช่วยงานนั้น. Optionalpipeline มี allowLLM/network/writes เพื่อไม่เปิด effects เพียงเพราะชื่อ algorithm. สถาปัตยกรรม servicecatalog/otherrepositories ไม่เท่ากับ runtime โทรผ่าน services เหล่านั้น; cloudcheckout นี้ไม่พิสูจน์ privateproductionmesh หรือ externaldeployments.

## ข้อความในเอกสารที่ต้องอ่านอย่างระวัง

- Master§1.2 มี RCT7checkmark แต่§3ALGO04 อ้างขจัด Hallucination; ไม่มีหลักฐานให้สรุปครบ semanticRCT หรือ zerohallucination. ใช้ partialimplementation ตามตารางนี้.
- CLAUDE มี historicalsnapshots ที่บอก onlymodel/hostremaining และประมาณเปอร์เซ็นต์หลายช่วง; โค้ดและ requirements ล่าสุดยังพบ semantic/recovery/distributiongaps จึงไม่ใช้ตัวเลขเหล่านั้นเป็น completion ปัจจุบัน.
- CLAUDE/Master/legacyarchitectureauditor บางจุดมี FDIAexpandedname เก่า. นิยาม v0.3 ระบุ**ไม่มี approvedexpandedname**; F=Future,D=Data,I=Intent,A=Architect. ไม่เปลี่ยนสูตรเพื่อให้ D<1"amplify"; concept/estimator/authority ต้องแยก.
- Masterbody กับ statusappendix ขัดกันบางจุดเรื่อง DNSrebinding/host/notary/adapterweights. เลือก datedevidence ที่ตรง source และระบุ whetherretested; ไม่เอา appendixcheckmark มารับรอง host เครื่องใหม่.
- `scripts/audit_master_architecture.py`มีประโยชน์เป็น sourceinventory แต่มี hardcodedhistoricalclaims และ oldFDIAwording; `--doc`ไม่ได้ทำให้ทุก finding ขึ้นกับเอกสารปัจจุบัน. Rawaudit รอบนี้ไม่ใช่ automatedcertification. ต้องปรับ auditor ในคิวต่อไปพร้อม versionedclaimregistry.
- ZeroDelete ไม่ได้ลบข้อมูลส่วนบุคคลเอง; erasure ใช้ signedownerrequest และ scrubprojection/crypto-erasure ที่ออกแบบไว้. Backups/exports เก่ายังต้องจัดการ; ไม่อ้าง PDPA/GDPRcertified.

## ระยะห่างจากเป้าหมาย

ระยะห่างถึง**โพสต์แนะนำโครงการทดลอง**สั้นกว่าถึง**agent ที่ทำงานธุรกิจเองได้อย่างเชื่อถือได้**มาก. โพสต์แรกต้อง video ไทยถูกต้อง, exactcommit, scriptedlabel, expectedrefusals และ testblockers เปิดเผย, publicdefinitions ตรงกัน และ review ก่อน merge/post. งานรอบนี้ปิดปัญหาภาพและ lifecycle บางส่วน แต่ไม่แทน pilot/evaluation.

ระยะห่างถึง northstar ยังมีอย่างน้อย 4gategroups: (1)RCTsemanticfidelity/end-to-endintent (2)capablemodelworkflowoutcomes (3)productionoperability/keycustody/isolation/recovery (4)independentreproduction/securityreview. กลุ่ม 2 และ 3 ไม่ได้ปิดด้วยการเขียน feature เพิ่มหรือผ่าน unit หลายพันข้อ. ไม่ให้ completion เปอร์เซ็นต์/กำหนดวันเปิดตัวโดยไม่มี weightedrubric และ measurements.

Automated source inventory อ่านชื่อ algorithm ใน Master ได้ 41 entries และรายงาน 6 name mismatches ด้วย token matching. หลายคู่เป็นชื่อพ้อง/ชื่อย่อ เช่น scheduler/controller หรือ control/controller จึง **ไม่ใช่ข้อพิสูจน์ว่า algorithm 6 ตัวผิด**. แม้ action text ของ auditor ยังยก ALGO-26 เป็นปัญหาเดิม แต่รายการ mismatch ของฉบับแนบนี้ไม่มี ALGO-26 แล้ว. ต้องเก็บ raw findings พร้อมคำอ่านนี้ ไม่แปลงเป็นคะแนนความครบถ้วน.

## วงจรแปดขั้นกับสิ่งที่รันจริง

| ขั้น | สิ่งที่มีใน runtime | ขอบเขตที่ต้องแยก |
|---|---|---|
| GUARD | intent screening, evidence/authority และ tool dispatch policy | ปฏิเสธได้ ไม่รับประกันจับ injection ทุกข้อความ; การ block tool ไม่แปลว่าไม่เคยเรียก model |
| THINK | compiled intent + ALGO04 plan ใน context | ไม่เท่ากับ semantic R1–R6 ครบ และ default prompt plan ไม่ใช่ visible user plan |
| ROUTE | fast/slow และ profile/provider routing ตามการตั้งค่า | ไม่พิสูจน์ว่า route ที่เลือกเหมาะที่สุด; model/backend ยังเป็น prerequisite |
| ACT | actual tool dispatch, approvals, DAG, effects | contract path ยัง read-only; unknown outcomes/recovery ต้องจัดการตามหลักฐาน |
| COMPRESS | Delta v2 กับ large tool outputs, เก็บ original เพื่อขยาย | compression ตั้งใจละบางข้อความออกจาก context; ไม่ใช่ raw file ถูกลบหรือภาษาไทย encoding เสีย |
| VERIFY | refusal/grounding/similarity + explicit predicates เมื่อ opt-in | ไม่ใช่ truth oracle หรือ RCT semantic proof |
| RECORD | SQLite/audit hash-chain/signatures/experiment rows | ต้องแยก key trust, notary OS user และ off-host witness จากการมี signature |
| LEARN | memory, selected skills, feedback/growth และ warm recall ตามเงื่อนไข | ค่า G/Δ ไม่ใช่คะแนน IQ หรือ main-model weight training; causal benefit ต้องวัดแยก |

**ช่องว่างเพิ่มเติมจากการอ่าน:** เมื่อผลอ่านไฟล์ใหญ่ถูกย่อ ระบบบอกให้เรียก `delentia_expand_tool_output` แต่ read-only allowlist ของ contract รุ่นแรกยังไม่รวมเครื่องมือนี้. จึงไม่ควรประกาศ contract ว่ารองรับการอ่านหลักฐานครบจากไฟล์ใหญ่ทุกกรณี. ต้องทดสอบ namespace/episode binding และ preservation ของ original store ก่อนเพิ่มสิทธิ์ expand ไม่เปิดเครื่องมือเพียงเพราะชื่อดูอ่านอย่างเดียว. เดโม fixture เล็กที่อัดใหม่ไม่ใช้ compression จึงแยกจากสาเหตุ glyph หายสามข้อที่แก้แล้ว.
