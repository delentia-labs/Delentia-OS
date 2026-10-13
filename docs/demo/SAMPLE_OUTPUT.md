# What the model-free demo prints (a real run, 2026-10-12)

Produced by `delentia demo init`, `delentia demo run compare --scripted`, `delentia demo run edit --scripted` and `delentia demo approve <id> --scripted` on Windows with no model installed. The report text is Thai (the demo is a Thai-language task). `--scripted` replaces only the model; everything else in these outputs is the real gate, tools, signature check and audit log.

## 1. `delentia demo init`

```text
เดโมอยู่ที่ ~/delentia-demo
สร้างใหม่: quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md, README_TH.md, keys/demo-approver.pem, keys/audit.pem, data/originals.json
ต่อไป: delentia demo run compare --scripted  (ไม่ต้องมีโมเดล)  หรือ  delentia model show  แล้ว  delentia demo run compare
```

## 2. `delentia demo run compare --scripted`

```text
# ผลการรัน 2026-10-12 20:27:34
> ครั้งนี้ใช้ 'ตัวแทนโมเดลแบบสคริปต์' (ไม่ใช่โมเดลจริง): ลำดับขั้นและถ้อยคำของคำตอบถูกเขียนไว้ล่วงหน้า ส่วนที่เป็นของจริงคือเครื่องมือ ไฟล์ ประตูความปลอดภัย การรอลายเซ็น และ audit chain ผลนี้ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด

**โจทย์:** อ่านใบเสนอราคาในไฟล์ quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md ทำตารางเปรียบเทียบราคา แล้วสรุปว่าบริษัทไหนราคาไม่เกินงบ 15,000 บาท ห้ามแก้ไฟล์ต้นฉบับและห้ามส่งข้อมูลออกไป
**โมเดล:** สคริปต์ (ไม่ใช่โมเดลจริง)
**สถานะ:** llm_finished — จบเอง: โมเดลตอบคำถามเสร็จ
**จำนวนขั้น:** 4 · เวลา 0.5 วินาที


## agent ทำอะไรบ้าง
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_a.md"} → ได้ผล 213 ตัวอักษร
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_b.md"} → ได้ผล 215 ตัวอักษร
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_c.md"} → ได้ผล 216 ตัวอักษร
- (ตอบคำถาม)

## ประตูความปลอดภัย (FDIA) ตัดสินอย่างไร
- `delentia_read_repo_file`: D=0.6 I=0.6 A=1.0 → F=0.736 (เกณฑ์ 0.5) → ผ่าน
- `delentia_read_repo_file`: D=0.6 I=0.6 A=1.0 → F=0.736 (เกณฑ์ 0.5) → ผ่าน
- `delentia_read_repo_file`: D=0.6 I=0.6 A=1.0 → F=0.736 (เกณฑ์ 0.5) → ผ่าน

## ข้อความจากภายนอก (taint)
- episode นี้ อ่านข้อความจากภายนอก: delentia_read_repo_file (quotes/vendor_a.md is in a folder declared untrusted) → การกระทำที่ส่งข้อมูลออก/เปลี่ยนแปลงต้องรอคนเซ็น

## คำตอบ
ตารางเปรียบเทียบใบเสนอราคา (เรียงราคาจากต่ำไปสูง, งบ 15,000 บาท)

| บริษัท | ราคา (บาท) | ระยะเวลา (วัน) | เทียบกับงบ |
|---|---|---|---|
| บางกอกเทคนิค | 9,900 | 9 | อยู่ในงบ |
| สยามแอร์ | 12,500 | 5 | อยู่ในงบ |
| ไทยคูลลิ่ง | 16,800 | 3 | เกินงบ |

สรุป: ราคาต่ำสุดที่อยู่ในงบคือ บางกอกเทคนิค ราคา 9,900 บาท (9 วัน)

## ตรวจคำตอบกับสิ่งที่รู้ว่าจริง (ไม่ใช่การตรวจของ agent เอง)
- ผ่าน: ตารางมีราคาครบทั้ง 3 ใบ
- ผ่าน: ระบุว่า บางกอกเทคนิค อยู่ในงบ 15,000 บาท
- ผ่าน: ระบุว่า สยามแอร์ อยู่ในงบ 15,000 บาท
- ผ่าน: ไม่ระบุว่า ไทยคูลลิ่ง (เกินงบ) อยู่ในงบ
- ผ่าน: ไฟล์ต้นฉบับไม่ถูกแก้

## บันทึกตรวจย้อนหลัง
- audit chain: ครบสมบูรณ์ · 11 แถว · เซ็นแล้ว 11 แถว
- คำว่า 'ไม่ถูกแก้' หมายถึงแฮชไฟล์ต้นฉบับยังตรงกับตอน init เท่านั้น ไม่ใช่การรับรองความจริงของข้อมูลในใบเสนอราคา

ไฟล์ผล: ~/delentia-demo\results\20261012-202734-compare-c8b7.md
```

## 3. `delentia demo run edit --scripted` (the agent stops and waits)

```text
# ผลการรัน 2026-10-12 20:27:37
> ครั้งนี้ใช้ 'ตัวแทนโมเดลแบบสคริปต์' (ไม่ใช่โมเดลจริง): ลำดับขั้นและถ้อยคำของคำตอบถูกเขียนไว้ล่วงหน้า ส่วนที่เป็นของจริงคือเครื่องมือ ไฟล์ ประตูความปลอดภัย การรอลายเซ็น และ audit chain ผลนี้ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด

**โจทย์:** แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท
**โมเดล:** สคริปต์ (ไม่ใช่โมเดลจริง)
**สถานะ:** pending_approval — หยุดรอคนอนุมัติ: ขั้นตอนนี้ต้องมีลายเซ็นของผู้อนุมัติก่อนจึงจะทำ
**จำนวนขั้น:** 2 · เวลา 0.5 วินาที


## agent ทำอะไรบ้าง
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_a.md"} → ได้ผล 213 ตัวอักษร
- `delentia_patch_repo_file` {"relative_path": "quotes/vendor_a.md", "old_text": "ราคารวม: 12,500 บาท", "new_text": "ราคารวม: 14,000 บาท"} → รอลายเซ็นผู้อนุมัติ
- **รออนุมัติ รหัส `f43c8ae375ea`** → `delentia demo approve f43c8ae375ea`

## ประตูความปลอดภัย (FDIA) ตัดสินอย่างไร
- `delentia_read_repo_file`: D=0.465 I=0.5 A=1.0 → F=0.6819 (เกณฑ์ 0.5) → ผ่าน

## ข้อความจากภายนอก (taint)
- episode นี้ อ่านข้อความจากภายนอก: delentia_read_repo_file (quotes/vendor_a.md is in a folder declared untrusted) → การกระทำที่ส่งข้อมูลออก/เปลี่ยนแปลงต้องรอคนเซ็น

## ตรวจคำตอบกับสิ่งที่รู้ว่าจริง (ไม่ใช่การตรวจของ agent เอง)
- ผ่าน: ไฟล์ต้นฉบับยังไม่ถูกแก้ก่อนมีลายเซ็น

## บันทึกตรวจย้อนหลัง
- audit chain: ครบสมบูรณ์ · 20 แถว · เซ็นแล้ว 20 แถว
- คำว่า 'ไม่ถูกแก้' หมายถึงแฮชไฟล์ต้นฉบับยังตรงกับตอน init เท่านั้น ไม่ใช่การรับรองความจริงของข้อมูลในใบเสนอราคา

ไฟล์ผล: ~/delentia-demo\results\20261012-202737-edit-7df5.md
รออนุมัติ รหัส f43c8ae375ea  →  delentia demo approve f43c8ae375ea --scripted
```

## 4. `delentia demo approve <id> --scripted` (you sign; only now the file changes)

```text
# ผลการรัน 2026-10-12 20:27:41

**โจทย์:** แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท
**โมเดล:** สคริปต์ (ไม่ใช่โมเดลจริง)
**สถานะ:** llm_finished — จบเอง: โมเดลตอบคำถามเสร็จ
**จำนวนขั้น:** 1 · เวลา 0.7 วินาที

**ต้นทุน:** prompt 7995 · completion 102 · None USD

## agent ทำอะไรบ้าง
- (ตอบคำถาม)

## ข้อความจากภายนอก (taint)
- episode นี้ ยังไม่ได้อ่านข้อความจากภายนอก

## คำตอบ
แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท ตามที่ได้รับอนุมัติแล้ว

## ตรวจคำตอบกับสิ่งที่รู้ว่าจริง (ไม่ใช่การตรวจของ agent เอง)
- ผ่าน: หลังอนุมัติ ไฟล์ที่เปลี่ยนคือ: quotes/vendor_a.md

## บันทึกตรวจย้อนหลัง
- audit chain: ครบสมบูรณ์ · 26 แถว · เซ็นแล้ว 26 แถว
- คำว่า 'ไม่ถูกแก้' หมายถึงแฮชไฟล์ต้นฉบับยังตรงกับตอน init เท่านั้น ไม่ใช่การรับรองความจริงของข้อมูลในใบเสนอราคา

> ลายเซ็นนี้ใช้กุญแจเดโมที่อยู่ในเครื่องเดียวกับ agent เพื่อให้เห็นขั้นตอนครบเท่านั้น งานจริงต้องเซ็นจากอีกอุปกรณ์ (`delentia approvals sign`)

ไฟล์ผล: ~/delentia-demo\results\20261012-202741-approve-f43c8ae375ea.md
```

## What to look for

- In (2) the "agent did" list shows three file reads, each judged by the gate (D, I, A, F), and the check at the end compares the answer with what is known to be true.
- In (3) the status is `pending_approval` and the original file is unchanged ("ไฟล์ต้นฉบับยังไม่ถูกแก้ก่อนมีลายเซ็น").
- In (4) the file changes only after the Ed25519 signature is verified, and the audit chain is reported intact with every row signed.
- The demo approver key sits next to the agent so that you can see the flow in one sitting; a real deployment keeps approver keys on another device.
