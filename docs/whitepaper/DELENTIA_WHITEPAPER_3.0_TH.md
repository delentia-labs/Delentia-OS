# Delentia Whitepaper 3.0: รันไทม์เอเจนต์ภายใต้รัฐธรรมนูญ (Constitutional Agent Runtime)

**ฉบับ:** 3.0 (2026-09-28) · **ผู้เขียน:** อิทธิฤทธิ์ แซ่โง้ว (The Architect), Delentia Labs
**ฉบับภาษาอังกฤษ:** [DELENTIA_WHITEPAPER_3.0_EN.md](DELENTIA_WHITEPAPER_3.0_EN.md)

> **วิธีอ่านเอกสารนี้** ตัวเลขทุกตัวมาจาก §9 (หลักฐาน) ซึ่งระบุคำสั่งที่ใช้วัดและวันที่วัด สิ่งที่ยังไม่ได้สร้าง
> จะเขียนกำกับว่า **ยังไม่สร้าง** และอยู่ใน §10 (Roadmap) whitepaper ฉบับก่อน (v2.x, "RCT Ecosystem", บทที่ 01–08)
> เก็บไว้เป็นประวัติเท่านั้น ถ้าเนื้อหาขัดกับฉบับนี้ ให้ถือฉบับนี้ §11 สรุปว่าเปลี่ยนอะไรบ้าง

---

## 1. ปัญหา

เอเจนต์ AI ทุกวันนี้ "ลงมือทำ" ได้แล้ว: อ่าน/เขียนไฟล์ รันคำสั่ง shell เรียก API ส่งข้อความ ผ่าน tool (เช่น MCP server)
ชั้นความปลอดภัยที่ใช้กันทั่วไปเป็นแค่ข้อความ: system prompt ที่ขอให้โมเดลระวัง หรือโมเดลตัวที่สองมาตัดสินตัวแรก
ทั้งสองแบบเป็นความน่าจะเป็น และอยู่ข้างในสิ่งที่มันควรจะควบคุม เอเจนต์ที่โดน prompt injection หรือแค่เข้าใจผิดก็ข้ามได้

จุดยืนของ Delentia คือ การตัดสินว่า *action นี้รันได้หรือไม่* ต้อง:

1. **แน่นอน (deterministic)**: คำขอเดิม นโยบายเดิม ได้คำตัดสินเดิมเสมอ
2. **อยู่นอกโมเดล**: บังคับด้วยโค้ด ณ จุดที่ tool call ถูกรันจริง ไม่ใช่ขอร้องใน prompt
3. **ยึดกับมนุษย์**: อำนาจสุดท้ายของ action เสี่ยงสูงคือคนที่การอนุมัติของเขาตรวจสอบด้วยการเข้ารหัสได้ ไม่ใช่ตัวเอเจนต์เอง
4. **บันทึกให้ตรวจย้อนได้**: โดยบุคคลอื่นที่ไม่ใช่เอเจนต์ที่ถูกตรวจ

## 2. FDIA: สมการรัฐธรรมนูญ

```
F = D^I × A
```

| สัญลักษณ์ | ชื่อ | ความหมายใน gate |
|---|---|---|
| **F** | Future (อนาคต) | ความชอบธรรมของ action: อนาคตนี้ควรเกิดขึ้นหรือไม่ |
| **D** | Data (ข้อมูล) | คุณภาพและความพอเพียงของข้อมูลเบื้องหลังคำขอ ปรับให้อยู่ใน [0, 1] |
| **I** | Intent (เจตนา) | ความแม่นยำของเจตนาที่ระบุ เพราะ D ≤ 1 ค่า I ที่สูงขึ้นทำให้ gate *เข้มขึ้น*: ข้อมูลคลุมเครือจะถูกลงโทษหนักขึ้นเมื่อเจตนาอ้างว่าแม่นยำ |
| **A** | Architect (สถาปนิก) | อำนาจของมนุษย์ **A = 0 คือไม่มีอนาคต** ไม่ว่า D และ I จะเป็นเท่าไร A ไม่ใช่ผลลัพธ์ของโมเดล แต่เป็นการตัดสินใจของมนุษย์ที่ตรวจสอบได้ |

### 2.1 กฎ 4 ข้อ (บังคับในโค้ด ทดสอบทั้งสองภาษา)

1. **A = 0 ⇒ F = 0** ไม่มี Architect ก็ไม่มี action เสี่ยงสูงใดผ่าน
2. **I ≤ 0 ⇒ F = 0** ไม่มีเจตนา ไม่มีอนาคต (ทางคณิตศาสตร์ `D^0 = 1` ซึ่งจะทำให้คำขอที่ไม่มีเจตนาผ่านเต็มที่ โค้ดปฏิเสธการตีความนี้)
3. **D ≤ 0 ⇒ F = 0** ไม่มีข้อมูล ไม่มีอนาคต
4. **A ต้องเป็นมนุษย์และตรวจสอบได้** token ของ Architect คือลายเซ็น Ed25519 ตรวจกับกุญแจสาธารณะที่ *ระบบที่ deploy* เชื่อถือ ไม่ใช่กุญแจที่ผู้เรียกส่งมาเอง

ค่าที่อยู่นอกโดเมนจะถูกปฏิเสธ (fail closed) เอนจินฝั่ง TypeScript (MCP tools และ Guard) กับฝั่ง Python (agent runtime)
ใช้ไฟล์สัญญาร่วมกัน 425 test vector (`contracts/fdia_vectors.v1.json` ตรึงด้วย SHA-256 ในทั้งสอง repo)
ตรงกัน 422 อีก 3 ตัวบันทึกความต่างที่รู้แล้วเรื่องการ clamp ค่าที่เกินช่วง

### 2.2 Architect token

```
dat1.<key_id>.<expires>.<signature>
ข้อความที่ลงลายเซ็น: delentia-architect-token:v1|key_id|action|sha256(payload)|expires
```

- ผูกกับ **action เดียว** และ **payload ที่ตรงกันทุกตัวอักษร** (ผ่าน hash) อายุไม่เกิน 24 ชั่วโมง
- กุญแจที่เชื่อถือมาจากการตั้งค่าของระบบเท่านั้น (`FDIA_ARCHITECT_KEYS_JSON` บน Workers, `~/.delentia/approvers.json` สำหรับ runtime)
  ถ้าไม่ได้ตั้งไว้เลย = ไม่มีอะไรได้รับอนุญาต
- action ที่ต้อง **ลงนามคู่ (dual sign-off)** ต้องใช้กุญแจที่เชื่อถือ 2 ดอกที่ต่างกัน
- กุญแจ Ed25519 ดอกเดียวลงนามได้ทั้งการอนุมัติใน runtime และ token นี้

### 2.3 เกณฑ์ของ gate

agent runtime จะบล็อก action เมื่อ F ต่ำกว่า `FDIA_GATE_THRESHOLD` (ค่าเริ่มต้น 0.5) และบอกโมเดลว่าเพราะอะไร
tool ที่เขียน แก้ไข หรือมีผลข้างเคียง จะรอมนุษย์อนุมัติเสมอ ไม่ว่า F จะเป็นเท่าไร

## 3. RCT-7: วิธีคิดของเอเจนต์

Reverse Component Thinking คิดย้อนจากผลลัพธ์ที่ต้องการ 7 ขั้น:
**สังเกต → วิเคราะห์ → แยกส่วน → คิดย้อนกลับ → ระบุเจตนาหลัก → ประกอบใหม่ → เทียบกับเจตนา**

- ใน agent runtime ขั้น 1–6 ถูกคำนวณสำหรับทุกเป้าหมายและใส่ใน prompt เป็นแผน ขั้นที่ 7 รันหลังจบ episode:
  semantic matcher เทียบสิ่งที่ทำไปกับเจตนาเดิม และบันทึกผล
- MCP tool สาธารณะ `rct_think` คืนโครงสร้าง 7 ขั้นเดียวกัน พร้อมคะแนนความสอดคล้องแบบ heuristic ที่คำนวณจากความครบถ้วนของคำขอ
  (spec: `RCT7_SCORING_SPEC.md` ใน MCP repo) **เป็น checklist ไม่ใช่ตัวตรวจจับ hallucination**

## 4. Constitutional Cycle (วงจรรัฐธรรมนูญ)

ทุก episode ของเอเจนต์ผ่าน 8 ขั้นโดยอัตโนมัติ ไม่ใช่เฉพาะตอนที่โมเดลเลือกเรียก tool

| # | ขั้น | เกิดอะไรขึ้น | สถานะ |
|---|---|---|---|
| 1 | **GUARD** | CORD ตรวจทุกเป้าหมายก่อนเรียกโมเดล ถ้าพบสัญญาณร้ายแรง (prompt injection, payload ที่เข้ารหัส, ข้อความยาวเกิน) episode จบทันทีโดยไม่เรียกโมเดลและไม่รัน tool; D และ I ของ FDIA คำนวณจากเป้าหมายและบันทึก F ของเป้าหมายไว้ ส่วน FDIA gate ใช้กับทุก action ที่เสี่ยงในขั้นที่ 4 ซึ่งรู้ค่า A แล้ว | ✅ สร้างแล้ว (CORD อยู่ใน loop ตั้งแต่ 2026-09-30; ก่อนหน้านั้นมีแค่ 2 endpoint ของ API ที่ตรวจ) |
| 2 | **THINK** | RCT-7 ขั้น 1–6 เป็นแผนใน prompt; ดึงความจำและ skill ที่ผ่าน MEE มาให้อัตโนมัติ (ในฐานะข้อมูล ไม่ใช่คำสั่ง) | ✅ สร้างแล้ว |
| 3 | **ROUTE** | ALGO-21 ตัดสินว่า FAST (ความเสี่ยงต่ำ ขอบเขตแคบ: จำกัดจำนวนขั้น ตอบตรง) หรือ SLOW (ขั้นเต็ม คิดทีละขั้น); router ผิดพลาดให้ไป SLOW; ไม่ข้ามขั้นกำกับใดเลย | ✅ สร้างแล้ว (2026-09-29) |
| 4 | **ACT** | FDIA gate ทุกขั้น; tool ที่มีผลข้างเคียงรอการอนุมัติที่ลงลายเซ็นโดยมนุษย์ แล้ว episode ทำต่อได้ | ✅ สร้างแล้ว |
| 5 | **COMPRESS** | ผลลัพธ์ tool ที่เกิน ~2k token ถูกบีบด้วย Delta-Context และขยายกลับได้ | ✅ สร้างแล้ว |
| 6 | **VERIFY** | RCT-7 ขั้นที่ 7 เทียบกับเจตนาเดิม | ✅ สร้างแล้ว |
| 7 | **RECORD** | audit แบบ hash chain (ลงลายเซ็นเมื่อตั้งกุญแจ) และ RCTDB `experiment_runs` | ✅ สร้างแล้ว |
| 8 | **LEARN** | เฉพาะ episode ที่ผ่านการตรวจเท่านั้นที่สร้าง skill ได้ และต้องผ่าน MEE gate | ✅ สร้างแล้ว |

ทุกประตูเข้า (API, gateway ข้อความ 4 ช่องทาง, scheduler, MCP tool, profile และ subagent, terminal UI) สร้าง loop ผ่าน factory เดียวที่ควบคุมการกำกับ
มี test ที่จะล้มถ้ามีโมดูลใดสร้าง loop ที่ไม่ผ่านการกำกับ

## 5. ผลิตภัณฑ์ 3 ตัว

| ผลิตภัณฑ์ | คืออะไร | ใครเป็นคนคิด | บังคับใช้จริง? |
|---|---|---|---|
| **Delentia Guard** (`delentia-guard`) | proxy แบบ stdio คั่นหน้า MCP server ใดก็ได้ ทุก `tools/call` ถูกตรวจกับนโยบาย FDIA ก่อนถึง server; บีบ output ได้; ขออนุมัติมนุษย์สำหรับกฎ "ต้องให้คนตัดสิน"; audit log แบบ hash chain ลงลายเซ็น Ed25519 | เอเจนต์ของลูกค้าเอง | **ใช่** |
| **Delentia MCP tools** (`delentia-mcp`, Cloudflare Workers) | 6 tools: `evaluate_fdia`, `rct_think`, `compress_context`, `expand_context`, `orchestrate_swarm`, `configure_policy` | เอเจนต์ของลูกค้าเอง | ไม่ เป็นคำแนะนำ: เอเจนต์ต้องเลือกเรียกเอง |
| **Delentia-OS agent runtime** (Python) | เอเจนต์อัตโนมัติของ Delentia เอง: governed loop, daemon, scheduler, gateway, skill, ความจำ, sandbox, subagent, เลือกโมเดลได้ (Ollama หรือโมเดลใดก็ได้บน OpenRouter) | loop ของ Delentia กับโมเดลที่ผู้ดูแลเลือก | **ใช่** |

Guard ออกก่อน เพราะบังคับนโยบายกับเอเจนต์ที่คนใช้อยู่แล้วได้ทันที

## 6. สถาปัตยกรรม: 10 ชั้น ตามที่สร้างจริง

whitepaper ฉบับก่อนอธิบาย 10 ชั้น ยังเป็นแผนที่ที่มีประโยชน์ แต่หลายชั้นถูกเขียนเหมือนสร้างเสร็จแล้วทั้งที่เป็นแผน ตารางนี้คือบันทึกที่แก้แล้ว

| ชั้น | คำอธิบายเดิม | ที่สร้างจริง (2026-09-28) | การตัดสินใจ |
|---|---|---|---|
| L1 OS primitives | เข้าถึงฮาร์ดแวร์ตรง แยก process ระดับ OS | sandbox ระดับ process (`local` และ `docker`) พร้อมจัดระดับความเสี่ยงคำสั่ง | แก้เอกสาร: Delentia เป็น runtime บน OS ไม่ใช่ OS |
| L2 Kernel services | จัดการ VRAM, สลับ LoRA < 12 ms | `lora_multiplexer.py` จัดการ slot ของ adapter (มี mock สำรอง); SLM ไม่ได้ต่อกับ runtime; 12 ms ไม่เคยวัด | แก้เอกสาร; SLM เป็นส่วนเสริมนอกเส้นทางหลัก |
| L3 Algorithm kernel | 41 อัลกอริทึม + FDIA | ✅ 41/41 มี logic จริง; 24 ตัวรันอัตโนมัติจาก kernel ที่เหลือเรียกผ่าน tool หรือ router | คงไว้ |
| L4 RCTDB | 8 มิติ บน Qdrant + Neo4j + PostgreSQL | ค่าเริ่มต้นคือ SQLite (ตาราง RCTDB, audit แบบ hash chain, experiment runs); มี backend PostgreSQL + pgvector; Qdrant ใช้ใน vector search (ALGO-16); Neo4j ใช้ใน graph traversal (ALGO-17) เมื่อตั้ง server ไว้ | แก้เอกสารเป็น "SQLite เป็นค่าเริ่มต้น มี backend เสริม" ช่องว่างในโค้ด: audit hash chain มีแค่บน SQLite ต้องทำให้ PostgreSQL เท่ากันก่อน deploy หลายเครื่อง |
| L5 SignedAI | ฉันทามติหลายโมเดล ≥ 75% | logic ฉันทามติและการเลือก tier อยู่ใน `signedai/core`; ยังไม่มี HTTP API; รายชื่อโมเดลในเอกสารเก่าล้าสมัย | แก้เอกสาร; API wrapper อยู่ใน backlog |
| L6 JITNA | แพ็กเก็ต I, D, Δ, A, R, M | ✅ แพ็กเก็ตลงลายเซ็น Ed25519 (v2), streaming (v3) | คงไว้ |
| L7 FloatingAI & Delta | บีบความจำ 91.5% | "Delta" 3 ชิ้นที่ต่างกัน (ดู §7) | ตั้งชื่อใหม่และแยกกัน |
| L8 Regional language adapter | เลือกโมเดลตาม locale และที่ตั้งข้อมูล (PDPA/GDPR) | มี endpoint ตรวจความเสี่ยง PDPA และรายการ adapter กฎหมายไทย; ไม่มีชั้นที่เลือกโมเดลตาม locale หรือที่ตั้งข้อมูล | แก้เอกสาร; สร้างเมื่อมีลูกค้าต้องการ |
| L9 Universal adapter | REST / GraphQL / WebSocket / gRPC | MCP คือพื้นผิวเชื่อมต่อ (6 remote tools, 34 runtime tools, Guard สำหรับ MCP server ใดก็ได้); มี adapter SDK แต่เงียบ | นิยาม L9 ใหม่เป็น "MCP + Guard" |
| L10 Enterprise hardening | JWT RS256, RBAC, circuit breaker | ✅ `enterprise_hardening.py`, API auth ด้วย bearer token, allowlist ผู้ส่งแบบ fail-closed บน gateway | คงไว้ |

**ตอบคำถามที่ถามซ้ำบ่อย: ต้องแก้ whitepaper หรือแก้โค้ด?** ส่วนใหญ่แก้ whitepaper
โค้ดทำสิ่งที่ agent runtime ต้องมีในระยะนี้ครบแล้ว ข้อความเดิมอธิบายโครงสร้างที่ใหญ่กว่าที่ผู้ใช้ปัจจุบันต้องการ (ฐานข้อมูล 3 ตัว, ชั้น OS, การเลือกเส้นทางตามภูมิภาค)
การแก้โค้ดมีเหตุผลเฉพาะจุดที่ปิดช่องว่างจริง: audit chain บน PostgreSQL (ก่อนรันมากกว่า 1 เครื่อง), HTTP API ของ SignedAI,
และการเลือกโมเดลตามภูมิภาคเมื่อมีลูกค้าขอ

## 7. ความจำและ Delta ทั้งสาม

| ชื่อในเอกสารนี้ | โค้ด | ทำอะไร | วัดได้ |
|---|---|---|---|
| **Delta-Context** | TS `compress_context` / `expand_context`; Python `delta_v2.py` (port ที่ได้ผลตรงกันทุก byte); Guard `--compress` | ย่อ output ขนาดใหญ่ของ tool โดยเก็บบรรทัดที่เป็นความล้มเหลวไว้ และขยายส่วนที่เหลือกลับได้ | ลด token ~70–75% บนโค้ดและ log จริง (โหมด aggressive); Guard: ~66% บน log build + test จริง |
| **Delta-Memory** | `core/delta_engine/memory_delta.py` | เก็บสถานะเอเจนต์เป็นส่วนต่างแทน snapshot เต็ม | 91.5% บนการจำลอง 20 เอเจนต์ × 100 tick (ขนาด byte แบบประมาณ) |
| **DeltaBlock** | `algo_25_delta_block.py` | log ส่วนต่าง และบีบประวัติบทสนทนา | – |

ความจำอัตโนมัติ: ความจำที่เกี่ยวข้องถูกดึงเข้า prompt ตอนเริ่มทุก episode โดยติดป้ายว่าเป็นข้อมูล
skill เรียนรู้ได้เฉพาะจาก episode ที่ผ่านการตรวจ ผ่าน MEE gate

## 8. Audit และการดูแลกุญแจ

ลายเซ็นพิสูจน์ว่าใครเขียนบันทึกและบันทึกไม่ถูกแก้ แต่ไม่ได้พิสูจน์ว่าบันทึกเป็นความจริง และไม่พิสูจน์อะไรเลยถ้าเอเจนต์ที่ถูกตรวจถือกุญแจเอง
Delentia จึงอธิบาย audit trail ตามผู้โจมตีที่แต่ละระดับป้องกันได้

| ระดับ | เพิ่มอะไร | สถานะ |
|---|---|---|
| A0 | ลงลายเซ็นตัวเองในโปรเซสด้วยกุญแจชั่วคราว | เลิกใช้แล้ว |
| A1 | กุญแจระยะยาวอยู่นอกเส้นทางที่ tool เข้าถึง; ทุกแถวถูก chain และลงลายเซ็น; `delentia audit-chain verify` | ✅ Runtime (เมื่อตั้ง `DELENTIA_AUDIT_SIGNING_KEY`) |
| A2 | ลงลายเซ็นในโปรเซสแยก ณ จุดคอขวดที่เห็น tool call จริง | ✅ **Guard สำหรับเส้นทาง MCP**: กุญแจอยู่ในโปรเซส Guard; call ที่อ้างถึงกุญแจหรือ log ถูกปฏิเสธ ✅ **Runtime (Round 50)**: `delentia notary serve` ถือกุญแจในโปรเซสของตัวเอง; governed loop บันทึกทุก tool call (hash ของ argument, ผลลัพธ์ และการตัดสินของ FDIA) ก่อนรัน และปฏิเสธ call ถ้า notary บันทึกไม่ได้ (เมื่อตั้ง `DELENTIA_NOTARY_URL`) ควรรัน notary ด้วย OS user อื่น; ตัว gate ยังรันในโปรเซสของ agent |
| A3 | เผยแพร่ head ของ chain ไปยังพยานภายนอก | 🟡 พยานออนไลน์แล้ว (fdia Worker `/v1/audit/anchor` แบบเพิ่มได้อย่างเดียว; rollback/fork ถูกเก็บเป็นหลักฐาน) `delentia-guard anchor`, `delentia audit-chain anchor` และ `delentia notary anchor` ฝากได้เมื่อสั่ง; **ยังไม่มีการตั้งเวลาอัตโนมัติ** |
| A4 | กุญแจใน HSM/KMS, หมุนกุญแจ, WORM storage, ตรวจสอบโดยบุคคลภายนอก | **ยังไม่สร้าง**; ทำเมื่อลูกค้าต้องการ |

จนกว่า A3 จะเสร็จ Delentia จะไม่เรียก log ของตัวเองว่า "tamper-proof" หรือ "immutable"
ข้อมูลส่วนบุคคลไม่อยู่บน chain (chain เก็บแค่ hash) จึงลบข้อมูลตามสิทธิ PDPA ได้โดยไม่ทำให้ chain เสีย

## 9. หลักฐาน

### 9.1 ที่วัดได้จริง (ทำซ้ำได้)

| ข้อความ | ค่า | วิธีทำซ้ำ | วันที่ |
|---|---|---|---|
| ชุดทดสอบ runtime | ผ่าน 3,922; ไม่ผ่าน 1 (test แบบ live ของ OpenRouter ที่ต้องใช้ key เครือข่าย) | `pytest` ใน Delentia-OS | 2026-09-28 |
| ชุดทดสอบ MCP + Guard | ผ่าน 288 ไม่ผ่าน 0 (295 เมื่อต่อ private services) | `npm ci && npm run build && npm run test:all` ใน `delentia-mcp/ecosystem` | 2026-09-28 |
| สัญญา FDIA | 422 จาก 425 vector ตรงกันระหว่าง TypeScript กับ Python; อีก 3 เป็นความต่างเรื่อง clamp ที่บันทึกไว้ | contract test ในทั้งสอง repo | 2026-09-28 |
| Delta-Context | token ลดลง ~70–75% (aggressive); เก็บบรรทัดคำตอบได้ 100% เมื่อถามด้วยคำเดียวกับต้นฉบับ และ ~60% เมื่อถามแบบถอดความ; โหมดปกติ ~6–12% | `benchmarks/compression-real/` ใน `delentia-mcp/ecosystem` | Round 46 |
| การบีบของ Guard | เล็กลง ~66% บน log build + test จริง โดยยังเก็บ test ที่ล้มไว้ | `delentia-mcp/ecosystem/docs/GUARD.md` | 2026-09 |
| Delta-Memory | 91.5% บนการจำลอง 20 × 100 | `python scripts/benchmark_fdia_delta.py --json` | 2026-09-28 |
| การประเมิน FDIA (Python) | 2.37 µs ต่อครั้ง บน CPU โน้ตบุ๊ก 1 เครื่อง | สคริปต์เดียวกัน | 2026-09-28 |
| การดึงความจำ (SQLite ในหน่วยความจำ) | p95 0.021 ms | สคริปต์เดียวกัน | 2026-09-28 |
| การคัดกรอง CORD | 100 pattern ~48 µs ต่อครั้ง; ชุดตัวอย่างของสคริปต์เองได้อัตราตรวจจับ 50% จึงไม่อ้างอัตราตรวจจับ | สคริปต์เดียวกัน | 2026-09-28 |
| การเลือก tool ของโมเดล (K.1.5) | qwen2.5:7b บน CPU: เลือก tool ถูก 0/17; พฤติกรรมการกำกับและการปฏิเสธ 100% | `scripts/k1_5_formal_acceptance.py` | Round 45 |

ผล K.1.5 คือเหตุผลที่ runtime ให้ผู้ดูแลเลือกโมเดลได้: การกำกับบังคับด้วยโค้ด และยังได้ผลแม้โมเดลจะเลือก tool ไม่ได้

### 9.2 ข้อความที่ถอนออก

| ข้อความเดิม | เหตุผลที่ถอน |
|---|---|
| "hallucination 0%", "hallucination drift 0.00%" | ไม่เคยวัด |
| "hallucination 0.3% เทียบอุตสาหกรรม 12–15%" | dataset และชุด benchmark ที่อ้างถึงไม่มีอยู่ใน repo ใด ทำซ้ำไม่ได้ |
| ความเสถียร 99.98%, 259.2 ล้าน request | ไม่มี load test |
| 4,849 tests | แทนที่ด้วยตัวเลขใน §9.1 |
| "Zero-knowledge proof ของคะแนน FDIA" | `zk_fdia.py` เป็น hash commitment; ผู้ตรวจยืนยันไม่ได้ว่า F ที่ปิดผนึกเท่ากับ D^I × A ให้เรียกว่า commitment |
| audit "tamper-proof" / "immutable" | ดู §8; ยังไม่ได้จนกว่าจะถึง A3 |
| baseline "LLM ไม่มีการป้องกัน" หลุด 94.7% | ไม่ได้รัน LLM จริง ค่าถูก hardcode |
| บีบ 74.2% / 85% | 74% เป็นเป้าขั้นต่ำตอนออกแบบ 85% ไม่มีที่มา; ดู Delta-Context ใน §9.1 |
| สลับ LoRA < 12 ms | ไม่เคยวัด |
| "AI OS ที่ยึดเจตนาเป็นแห่งแรกของโลก" | พิสูจน์ไม่ได้; Delentia เป็น runtime ไม่ใช่ OS |
| SignedAI บน GPT-4 Turbo / Claude 3.5 | ชื่อโมเดลล้าสมัย; ตอนนี้ผู้ดูแลเป็นคนเลือกโมเดล |

## 10. Roadmap (ยังไม่สร้าง)

1. **ฝาก head แบบ A3**: เผยแพร่ head ของ chain ทั้ง Guard และ runtime ไปยังพยานภายนอกตามรอบเวลา
2. **Host**: รัน runtime แบบสาธารณะ (แผน: Oracle Always Free + Cloudflare Tunnel, บังคับ token) แล้วเปิดสะพาน FDIA จาก Workers ไป Python
3. **โมเดลที่ขับ loop ได้**: เผยแพร่ชุดโมเดลอ้างอิงเล็ก ๆ ที่ผ่าน K.1.5
4. **audit chain บน PostgreSQL** และ **HTTP API ของ SignedAI**
5. **Design partner** ของ Guard ก่อนเพิ่มอัลกอริทึม sandbox backend หรือช่องทางใหม่

## 11. เปลี่ยนอะไรจาก v2.x

- ใหม่: Constitutional Cycle, governed runtime, Delentia Guard, Architect token แบบ Ed25519, กฎ FDIA 4 ข้อ, สัญญา FDIA ข้ามภาษา, ระดับ audit A0–A4
- แก้ไข: ความหมายของแต่ละตัวใน FDIA, สถานะ 10 ชั้น, Delta ทั้งสาม, และตัวเลขทุกตัว (§9)
- แหล่งเดียว: ไฟล์นี้และฉบับภาษาอังกฤษ เอกสารเก่ายังอยู่ใน `docs/whitepapers/` และ `whitepapers/` เพื่อเป็นประวัติ

## ภาคผนวก A. รายการวัตถุของระบบ

| กลุ่ม | วัตถุ | สถานะ |
|---|---|---|
| ปรัชญา | FDIA, RCT-7, The Architect, Architect veto | ใช้ในโค้ด |
| โปรโตคอล | JITNA (RFC-001), TOON | JITNA อยู่ในโค้ด; TOON อยู่แค่ใน dataset |
| ความจำ | RCTDB, AgentMemory, SkillLibrary, experiment runs, Vault-1068 client | อยู่ในโค้ด (class ของ Vault client ชื่อ `RCTDBClient` ชวนสับสน) |
| ความปลอดภัย | CORD, FDIA gate, ZK-FDIA commitment, approvals, Architect token, API auth, audit chain, Guard | อยู่ในโค้ด |
| การคิด | 41 อัลกอริทึม, Kernel 9 Tiers, Intent Loop, ALGO-21 router, MEE | อยู่ในโค้ด; Intent Loop 2 ตัวยังไม่รวมกัน; ALGO-21 ทำงานใน loop แล้ว (ROUTE) |
| ฉันทามติ | SignedAI, HexaCore (9 บทบาท) | logic อยู่ในโค้ด ยังไม่มี API |
| โมเดล | 1+4 pillars (Router, Guardian, Executor, Scribe), delentia-slm | อยู่บน Hugging Face; ไม่ได้ต่อกับ runtime |
| ผลิตภัณฑ์ | Guard, 6 MCP tools, runtime (34 MCP tools), เว็บไซต์ | ใช้งานจริงหรืออยู่ในโค้ด |
