# Typed intent สำหรับงานทั่วไป: implementation และขอบเขตหลักฐาน

## เป้าหมาย

ชั้นวิเคราะห์ควรใช้ร่วมกันข้ามประเภทงานได้ ส่วนการลงมือและพิสูจน์ผลต้องใช้ trusted capabilities/verifiers ที่เหมาะกับงาน ไม่มี schema หรือ test suite จำกัดชุดใดพิสูจน์ความเข้าใจงานทุกชนิดได้

## Implementation

เพิ่ม typed_intent.py ใช้ injected LLMProvider.complete เดิมหนึ่งครั้ง ไม่มี default provider, automatic retry/repair หรือ fallback โดย caller ต้องส่ง provider ที่ตั้งค่า/ควบคุมงบไว้แล้ว ไม่ได้เปิด HTTP route หรือเรียกโมเดลอัตโนมัติใน workflow ปัจจุบัน

IntentProposal v1 แยก material_criteria, constraints, unknowns; obligations มี required/prohibited polarity และ source_quotes ที่ต้องเป็นข้อความจริงในโจทย์ รองรับโจทย์ Unicode ไทย/อังกฤษ ตรวจ duplicate IDs, unknown fields/versions, JSON duplicate keys/non-finite และขนาด goal/output

GroundedIntent ผูก goal SHA-256 และคืน needs_review หรือ needs_clarification เสมอ grants_execution=False; schema-valid และ exact source quotes ไม่พิสูจน์ semantic correctness หรือครบทุกเจตนา โมเดลยังอาจตีความผิดแม้ quote ถูก ต้องมี review/oracle/holdout

validate_intent_program ใช้ component_execution.validate_program เดิม ไม่สร้าง scheduler อีกชุด บังคับ coverage ของทั้ง material criteria และ constraints รวมข้อห้าม ต้องมี trusted verifier สำหรับทุก ID critical unknown ที่ยังไม่มีคำตอบปฏิเสธก่อน validation; answers ต้องผูก ID ที่มีอยู่ โปรแกรมที่ graph ถูกแต่ตก constraint จะไม่ผ่าน

ไม่ได้เพิ่ม trusted handlers ใหม่หรือทำให้ unsupported task execute ได้เอง และยังไม่ทำ selective invalidation/replay

## Tests

Adapter/coverage + scheduler: 33 passed ใน 0.70 วินาที รวม scripted Thai negation, English multi-intent, invented quote, duplicate IDs, unsupported schema, injected tool fields, missing prohibition coverage, critical clarification และ no retry/no dispatch on invalid goal

Expanded regression: 159 passed / 220 warnings ใน 4.19 วินาที รวม semantic plan, legacy contract, HTTP evidence policy, verified budget และ receipt integrity จำนวนสองชุดซ้อนกันไม่บวกกัน Ruff CI scope ผ่าน; Linux Mypy ผ่าน 280 source files; strict MkDocs ตรวจเพิ่มเติมก่อน commit

ไม่มี paid model, inference จริง, capable-model holdout หรือ local full suite ใหม่ ผลนี้พิสูจน์ protocol/validation ไม่ใช่ความสามารถภาษาไทย/อังกฤษของโมเดล และ CI ใหม่ต้องตรวจตาม SHA หลัง push

## การประเมินความพร้อม

- ข้าม domain ได้ในชั้น proposal schema และ structural coverage แต่ยังไม่เปิด general task execution ผ่าน UI/API
- R1 มี evidence gate/acquisition provenance; source authentication และ semantic fact support ยังขาด
- R2 มี adapter proposal แต่ความครบของการเข้าใจโจทย์ยังต้องวัดจริง
- R3/R4 ตรวจ coverage เทียบ proposal ได้ แต่ถ้า proposal ตกเจตนาตั้งแต่แรกต้องใช้ independent oracle จับ
- R5 critical questions ต้องตอบก่อนตรวจโปรแกรม; selective invalidation ของ executed graph ยังขาด
- R6 Desk lifecycle และ R7 business verifiers หลาย domain ยังเป็นงานต่อ

## แผนต่อที่มีเกณฑ์จบ

1. Review adapter และ CI จาก SHA ใหม่ จากนั้นทดลอง development fixtures ผ่านโมเดลฟรีบน host ที่พร้อม ระบุ model/digest/settings/code; ไม่เปลี่ยน holdout หลังเห็นผล
2. เพิ่ม intent review/confirmation binding actor/version/workspace และเก็บ model provenance โดยใช้ lifecycle เดิม ก่อนเปิดรับ proposal จาก HTTP/Desk
3. เพิ่ม oracle cases สำหรับ implicit constraints, negation scope, conflicting intents, missing context, irrelevant questions และ unsupported operations; A/B ใช้โมเดล/ข้อมูล/งบเดียวกัน วัด task/process quality แยกกัน
4. เพิ่ม necessary-condition representation กับ trusted capability catalog; ทำเส้นทาง criterion → inputs → handler → receipt → verifier และปฏิเสธ unsupported domains
5. ทำ downstream invalidation และ approval rebinding ก่อน reuse outputs; uncertain effects reconcile ก่อน replay
6. Claude ปิด budget-entry/token findings และ #219 loopback freeze exemption; role/retry/child ทุกเส้นต้องอยู่ใน free rehearsal ก่อนอนุมัติงบ
7. เลือก 2–3 task families สำหรับ supervised evaluation เช่น document summary/citation, comparison, table analysis พร้อม native first-run และ Desk E2E/video หลัง review #217/#220

สถานะยังเป็น experimental local-first runtime มี proposal/coverage layer ที่ใช้ข้าม domain ได้ แต่ยังไม่รับรอง general autonomous RCT-7 ไม่ merge/release หรือเรียก paid API ในรอบนี้
