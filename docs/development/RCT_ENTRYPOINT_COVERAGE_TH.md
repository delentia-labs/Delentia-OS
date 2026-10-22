# RCT contract coverage แยกตามช่องทาง

ตรวจ source ในรอบ 22 ตุลาคม 2026 ที่ branch `codex/rct-derived-planning-and-receipts-20261022`. ตารางนี้อ้างเฉพาะ explicit acceptance-contract workflow ไม่เหมารวม governance ที่แต่ละช่องทางมีอยู่แล้วเป็น semantic RCT-7

| ช่องทาง | จุดเรียกที่ตรวจ | Contract plan/wait/continue | ขอบเขตหลักฐาน |
|---|---|---|---|
| CLI agent | [cli.py](../../rct_control_plane/cli.py), agent_command | opt-in criteria + declared context หรือ derive-plan; plan callback ก่อนงาน | CLI regression และ scripted HTTP demo ใช้ tool/store จริง |
| CLI continue/show/export | [cli.py](../../rct_control_plane/cli.py), intent_contract_* | namespace/version, explicit answers/revision, inspection/export | lifecycle/CLI tests; export เป็น personal plaintext ไม่ใช่ execution token |
| HTTP run/continue/get | [api.py](../../rct_control_plane/api.py), run_governed_agent / continue_intent_contract | opt-in; API คืน plan_ready/wait ก่อน execution request ถัดไป | TestClient จริง ครอบคลุม derived/declaration, stale/replay; scripted model ไม่พิสูจน์ capable model |
| Desk stream | [desk_agent_stream.py](../../rct_control_plane/desk_agent_stream.py), agent_events._run | เรียก loop.run(goal,on_step=...) โดยไม่ส่ง criteria/context/on_plan | ยังไม่เปิด contract workflow ใน stream; step events เดิมไม่เท่ากับ visible plan event |
| HTTP background jobs | [api.py](../../rct_control_plane/api.py), _job_service.runner และ [jobs.py](../../rct_control_plane/jobs.py) | runner เดิมส่ง goal/on_step; ไม่มี contract request/continuation ใน job schema | ต้องเพิ่ม durable waiting state และ contract id ก่อนเปิด ไม่ปล่อยให้ wait ถูกสรุปเป็น completed |
| Scheduled cron | [cron_jobs.py](../../rct_control_plane/cron_jobs.py), run_job | loop.run(job.goal) | ยังไม่มี RCT contract input/clarification delivery loop ในเส้นทางนี้ |
| Incoming channels | [gateways/common.py](../../rct_control_plane/gateways/common.py), dispatch_governed | build_governed_loop(...).run(goal) | shared dispatch เดิมไม่ส่ง contract; ต้องออก continuation routing ตาม identity ก่อนเพิ่มแต่ละ channel |

การไม่ได้เปิด acceptance contracts ไม่ได้แปลว่า entry point นั้นไม่มี FDIA/policy/taint/governance; แปลว่าไม่ควรอ้างว่ามี initial-input wait, criterion plan และ mismatch continuation ตาม contract ใหม่ครบแล้ว

## ของเดิมที่ต้องใช้ต่อ ไม่สร้างทับ

[episode_journal.py](../../rct_control_plane/episode_journal.py) มี begin/intent-before-dispatch/result/end, sealed payload และการระบุ unknown outcome จริง [approvals.py](../../rct_control_plane/approvals.py), [approval_queue.py](../../rct_control_plane/approval_queue.py) และ [notary.py](../../rct_control_plane/notary.py) มี approval/signing mechanisms เดิม การกล่าวว่ายังขาด contract-aware signed effects ไม่ได้หมายถึง repository ไม่มี journal/ลายเซ็นเลย

งานรอบ C ต้องเชื่อมกลไกเหล่านี้กับ contract version/plan digest/exact action และพิสูจน์ crash matrix ไม่ทำเส้นทางใหม่ที่ลัด gate หรือ reset running ตาม timeout เพียงอย่างเดียว [governed loop](../../rct_control_plane/governed_autonomous_loop.py) ยังจำกัด contract tools เป็น read-only อยู่ จึงยังไม่มีหลักฐานว่า contract write effect recovery ผ่านแล้ว

## Gate ก่อนเปิดช่องทางเพิ่ม

ทดสอบต่อช่องทาง: plan-before-artifact/effect; missing critical input→wait→answer→new visible plan; mismatch→difference/question→wait; cross-namespace refusal; stale/replayed continuation; restart while waiting; cancel before dispatch; disconnect without accidental retry; read-only fence และ no positive learning เมื่อ mismatch

เริ่มจาก Desk stream หรือ jobs ที่เลือกหนึ่งช่องทางก่อน อย่าอ้าง coverage ของทุก channel จากการมี shared loop เพียงอย่างเดียว ใช้ [แผนงานถัดไป](RCT_COMPLETION_NEXT_GATES_TH.md) และ [ผลรอบนี้](RCT_DERIVED_PLANNING_RESULTS_2026-10-22_TH.md) ประกอบ
