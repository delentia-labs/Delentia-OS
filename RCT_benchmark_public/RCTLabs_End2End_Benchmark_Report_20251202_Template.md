---
title: RCTLabs End-to-End Benchmark Report
role: rctlabs_end2end_benchmark_report
version: v1.0
report_date: 2025-12-02
status: template
depends_on:
  - RCTLabs_End2End_Benchmark_Design_v1.md
  - RCTLabs_End2End_Benchmark_Cases_v1.jsonl
---

# RCTLabs End-to-End Benchmark Report (Template)

> **Note:**  
> เอกสารนี้เป็น template สำหรับรายงานผล RCTLabs benchmark ในแต่ละรอบ
> แนะนำให้ทำสำเนาเป็น `RCTLabs_End2End_Benchmark_Report_YYYYMMDD.md`
> แล้วเติมตัวเลข/ข้อค้นพบจากผลรันจริง


---

## 1. Run Summary

- วันที่รัน benchmark: `YYYY-MM-DD`
- เวอร์ชัน spec: `RCTLabs_End2End_Benchmark_Design_v1` (หรืออื่น)
- จำนวนเคสทั้งหมด: `N`
- Modes ที่รัน:
  - [ ] llm_only
  - [ ] rctlabs_rct

**TL;DR:**

- โดยรวม RCTLabs (rctlabs_rct) ดีกว่า baseline LLM-only แค่ไหน?
- จุดเด่น/จุดอ่อนที่ชัดเจนในรอบนี้คืออะไร?


---

## 2. Configuration

### 2.1 Runtime & Model

- RCTLabs API base URL: `RCTLABS_API_BASE_URL`
- Model / provider:
- Prompting strategy version:
- Integration กับ Kernel / Memory: (สั้น ๆ)


### 2.2 Dataset

- Cases file: `RCTLabs_End2End_Benchmark_Cases_v1.jsonl`
- Distribution ของ scenario_type:

  | Scenario Type       | Count |
  |---------------------|-------|
  | repo_overview       |       |
  | architecture_plan   |       |
  | reading_synthesis   |       |


---

## 3. Metrics Overview

ใส่ตาราง per mode:

| Mode         | Avg Quality | Avg Usefulness | Avg Latency (ms) | Notes          |
|--------------|-------------|----------------|------------------|----------------|
| llm_only     |             |                |                  | baseline       |
| rctlabs_rct  |             |                |                  | full RCT stack |


---

## 4. Per-Scenario Analysis

### 4.1 Repo Overview (lab-001, ...)

- ตัวเลขสำคัญ: avg quality/usefulness ต่อ scenario_type
- ข้อสังเกต:
  - RCTLabs ช่วยให้เห็นโครง repo ชัดขึ้นไหม?
  - ยังมีโฟลเดอร์สำคัญที่ถูกละเลยหรือไม่?

### 4.2 Architecture Plan (lab-002, ...)

- คุณภาพของ D-Day plan / architecture
- ประเด็นที่ดี: การจับ dependency, risk, phase ถูกต้อง
- ประเด็นที่ต้องปรับ: แผนคร่าวไป, ไม่ผูกกับ RCT ecosystem จริง

### 4.3 Reading & Synthesis (lab-003, ...)

- ความสามารถในการเล่า story / narrative ของ RCT
- ความถูกต้องของการเชื่อม FDIA / RCT-7 / Constitution / Ecosystem


---

## 5. Case Studies

### 5.1 เคสที่ RCTLabs ชนะ LLM-only ชัดเจน

- ID: `lab-00X`
- Task: `scenario_type=...`
- เปรียบเทียบ:
  - llm_only → ขาดอะไร?
  - rctlabs_rct → เพิ่ม context / structure / plan อย่างไร?
- บทเรียน: ควรเน้นปรับ prompt/pipeline แบบนี้ต่อ


### 5.2 เคสที่ RCTLabs ยังไม่ดีเท่าที่ควร

- ID: `lab-00Y`
- ปัญหา: เช่น useful น้อย, สับสน context, ไม่เจาะจงกับ repo จริง
- แนวทางแก้ไข: ปรับ UX, เพิ่ม hint metadata, เป็นต้น


---

## 6. Implications for RCTLabs Product Design

- สิ่งที่ design ปัจจุบันทำได้ดี (onboarding, architecture planning ฯลฯ)
- สิ่งที่ควรปรับ (เช่น การถาม back, multi-turn, filter context)
- ไอเดีย feature ใหม่ที่เกิดจากผล benchmark รอบนี้


---

## 7. Limitations

- จำนวน scenario ยังน้อยและโฟกัสแค่กลุ่มแรก
- ยังอาศัย LLM evaluator เป็นหลัก (human eval น้อย)
- config ของ Kernel/Memory อาจยังไม่ tuned


---

## 8. Action Items & Next Steps

- [ ] เพิ่ม scenario ใหม่ (เช่น research, experiment design)
- [ ] เพิ่ม human eval สำหรับเคสสำคัญ
- [ ] ปรับ RCTLabs API/pipeline ตามข้อค้นพบ
- [ ] ผูก benchmark นี้เข้ากับ SignedAI เพื่อมี audit trail และ governance
