# Evidence run: the scripted demo from a fresh install (2026-10-23)

What this is: one recorded run of `delentia demo init → compare → edit → approve` with the package installed from PyPI into a new virtual environment, so a stranger can compare what they see with what is below. What it is not: a test of any language model (`--scripted` replaces **only the model** with a fixed program; the files, the tools, the FDIA gate, the wait for a signature, the signature check and the signed audit log are real), a security certification, or a run by an outside person.

## Environment
- Python 3.13.14 (Windows 11), a new `venv`, `pip install delentia-os==2.3.1` from PyPI (no source checkout, no other Delentia on that venv).
- A new, empty demo folder given with `--dir` (the default `~/delentia-demo` was not used: see "What the first attempt showed").
- No model configured, no API key, no network call by the demo.
- Package version 2.3.1 is the one published on 2026-10-16; the source commit it was built from is the `v2.3.1` tag of this repository.

## What was observed

| Step | Command | Observed |
|---|---|---|
| 1 | `delentia demo init --dir <folder>` | the folder with three synthetic vendor quotes, a demo approver key and an audit key |
| 2 | `delentia demo run compare --scripted` | the agent read the three quotes (3 reads, each passed the FDIA gate, F = 0.736 against the 0.5 threshold), answered; **5 of 5 checks against the known answer passed**, including "the original files were not modified"; audit chain intact, 11 rows, 11 signed |
| 3 | `delentia demo run edit --scripted` | the agent read the file and asked to change it; **stopped at `pending_approval`**; the file still said `ราคารวม: 12,500 บาท` (sha256 prefix `dc53807782c65102`); the check "the original is unchanged before a signature" passed; audit chain intact, 20 rows, all signed |
| 4 | `delentia demo approve <id> --scripted` | signed with the demo key; the file now says `ราคารวม: 14,000 บาท` (sha256 prefix `1b5aa944e95c01b8`); the only file that changed is `quotes/vendor_a.md`; audit chain intact, 26 rows, all signed |
| 5 | `delentia demo status` | no approvals waiting; audit `ok: true`, 26 rows, 26 signed, checked against the folder's own key |
| 6 | `delentia demo approve <the same id> --scripted` | refused: the approval is already EXECUTED (a signature works once). Nothing ran again. In 2.3.1 this printed a Python traceback; the refusal was right, the message was not. Fixed in the PR that adds this file |

## The full output

### Steps 1 to 3 (init, compare, edit)
```text
## environment
Python 3.13.14
Name: delentia-os
Version: 2.3.1
date: 2026-10-23T10:18:47+07:00
folder: a new empty folder (--dir), not the default ~/delentia-demo

$ delentia demo init --dir <new folder>
เดโมอยู่ที่ <demo folder>
สร้างใหม่: quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md, README_TH.md, keys/demo-approver.pem, keys/audit.pem, data/originals.json
ต่อไป: delentia demo run compare --scripted  (ไม่ต้องมีโมเดล)  หรือ  delentia model show  แล้ว  delentia demo run compare

$ delentia demo run compare --scripted --dir <new folder>
# ผลการรัน 2026-10-23 10:18:49
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

ไฟล์ผล: <demo folder>\results\20261023-101849-compare-b4b8.md

$ delentia demo run edit --scripted --dir <new folder>
# ผลการรัน 2026-10-23 10:18:52
> ครั้งนี้ใช้ 'ตัวแทนโมเดลแบบสคริปต์' (ไม่ใช่โมเดลจริง): ลำดับขั้นและถ้อยคำของคำตอบถูกเขียนไว้ล่วงหน้า ส่วนที่เป็นของจริงคือเครื่องมือ ไฟล์ ประตูความปลอดภัย การรอลายเซ็น และ audit chain ผลนี้ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด

**โจทย์:** แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท
**โมเดล:** สคริปต์ (ไม่ใช่โมเดลจริง)
**สถานะ:** pending_approval — หยุดรอคนอนุมัติ: ขั้นตอนนี้ต้องมีลายเซ็นของผู้อนุมัติก่อนจึงจะทำ
**จำนวนขั้น:** 2 · เวลา 0.4 วินาที


## agent ทำอะไรบ้าง
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_a.md"} → ได้ผล 213 ตัวอักษร
- `delentia_patch_repo_file` {"relative_path": "quotes/vendor_a.md", "old_text": "ราคารวม: 12,500 บาท", "new_text": "ราคารวม: 14,000 บาท"} → รอลายเซ็นผู้อนุมัติ
- **รออนุมัติ รหัส `bfd4697b93d8`** → `delentia demo approve bfd4697b93d8`

## ประตูความปลอดภัย (FDIA) ตัดสินอย่างไร
- `delentia_read_repo_file`: D=0.465 I=0.5 A=1.0 → F=0.6819 (เกณฑ์ 0.5) → ผ่าน

## ข้อความจากภายนอก (taint)
- episode นี้ อ่านข้อความจากภายนอก: delentia_read_repo_file (quotes/vendor_a.md is in a folder declared untrusted) → การกระทำที่ส่งข้อมูลออก/เปลี่ยนแปลงต้องรอคนเซ็น

## ตรวจคำตอบกับสิ่งที่รู้ว่าจริง (ไม่ใช่การตรวจของ agent เอง)
- ผ่าน: ไฟล์ต้นฉบับยังไม่ถูกแก้ก่อนมีลายเซ็น

## บันทึกตรวจย้อนหลัง
- audit chain: ครบสมบูรณ์ · 20 แถว · เซ็นแล้ว 20 แถว
- คำว่า 'ไม่ถูกแก้' หมายถึงแฮชไฟล์ต้นฉบับยังตรงกับตอน init เท่านั้น ไม่ใช่การรับรองความจริงของข้อมูลในใบเสนอราคา

ไฟล์ผล: <demo folder>\results\20261023-101852-edit-8160.md
รออนุมัติ รหัส bfd4697b93d8  →  delentia demo approve bfd4697b93d8 --scripted
```

### Steps 4 and 5 (the file before and after, approve, status)
```text

## before approval: the file is unchanged (sha256 prefix dc53807782c65102)
3:ราคารวม: 12,500 บาท

$ delentia demo approve bfd4697b93d8 --scripted --dir <new folder>
# ผลการรัน 2026-10-23 10:18:59

**โจทย์:** แก้ไฟล์ quotes/vendor_a.md ให้ราคารวมเป็น 14,000 บาท
**โมเดล:** สคริปต์ (ไม่ใช่โมเดลจริง)
**สถานะ:** llm_finished — จบเอง: โมเดลตอบคำถามเสร็จ
**จำนวนขั้น:** 1 · เวลา 0.4 วินาที

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

ไฟล์ผล: <demo folder>\results\20261023-101859-approve-bfd4697b93d8.md

## after approval
sha256 prefix 1b5aa944e95c01b8
3:ราคารวม: 14,000 บาท

$ delentia demo status --dir <new folder>
{
  "root": "C:\\Users\\<user>\\daaes-results\\r92\\fresh\\work2\\demo",
  "waiting": [],
  "memories": 0,
  "audit": {
    "ok": true,
    "rows": 26,
    "signed": 26,
    "checked_against_own_key": true
  },
  "results": [
    "20261023-101849-compare-b4b8.md",
    "20261023-101852-edit-8160.md",
    "20261023-101859-approve-bfd4697b93d8.md"
  ],
  "untrusted_paths": "quotes/",
  "model": null
}
```

## What the first attempt showed (kept because it is useful to the next person)
The first attempt used the default folder `~/delentia-demo`, which already held an earlier demo (`demo init` never overwrites). `compare` then reported two failures ("the table has all three prices" and "the original file was not modified") because the sample files had been changed by that earlier demo. The demo was right to report them. For a clean run, give a new folder with `--dir` to every demo command; the quickstarts now say so.

## Limits
- One machine, one run, run by the maintainers: this is an observation, not a reproduction by someone else. A person outside the project reproducing it is the next step.
- The approver key for the demo sits on the same machine as the agent so that the steps can be shown; in a real deployment the approver key belongs on another device.
- `demo status` checks the audit chain with the demo folder's own key. It does not show that a witness outside the machine holds the head; none is configured here.
- The report line "ต้นทุน … None USD" (cost printed as `None`) was a cosmetic fault; it now says there is no billed cost.
