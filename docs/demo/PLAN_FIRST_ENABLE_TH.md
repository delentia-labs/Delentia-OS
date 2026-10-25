# เปิดใช้ plan-first บน host ของคุณ ทีละขั้น (พร้อมสิ่งที่ต้องตรวจในแต่ละขั้น)

คู่มือนี้เขียนจากเครื่องของคุณจริง: host อยู่ที่ `C:\Users\whale\delentia-host`, รันจากโฟลเดอร์ `C:\Users\whale\Delentia\Delentia-OS`, กุญแจผู้อนุมัติ `Architect` อยู่ที่ `C:\Users\whale\.delentia\keys\architect.pem` (ลงทะเบียนใน `C:\Users\whale\.delentia\approvers.json`) และไฟล์นโยบายของเจ้าของคือ `C:\Users\whale\.delentia\fdia_policy.json` (ตอนนี้ **ยังไม่มีไฟล์นี้** ระบบจึงใช้ starter `argaware` ที่ฝังอยู่ในโค้ด)

## 0. สิ่งที่ต้องรู้ก่อน (แก้คำแนะนำเดิมของผม)

* **host ของคุณบังคับให้เซ็นเวลาแก้นโยบายอยู่แล้ว** เพราะ host ตั้ง `DELENTIA_API_TOKEN` ไว้ (ระบบถือว่า "มี token = เป็น host" และการแก้นโยบายต้องมีลายเซ็นผู้อนุมัติ) ผมเคยบอกให้ตั้ง `DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE=1` นั่นจำเป็นเฉพาะเมื่อรันเซิร์ฟเวอร์แบบไม่มี token เช่น `START_DAEMON.bat` ไม่ใช่ host นี้
* **โค้ด plan-first ต้องอยู่ในโฟลเดอร์ที่ host รัน** ตอนนี้ `C:\Users\whale\Delentia\Delentia-OS` ตามหลัง `origin/main` อยู่ 115 คอมมิต (ยังอยู่ที่ PR #173) และ plan-first จะเข้า `main` เมื่อ PR #194 ถูก merge ต้อง `git pull` ก่อน (ขั้นที่ 1)
* host ตอนนี้ **ไม่ได้รันอยู่** (`local_host.py status` บอก `healthy: False`)

## 1. อัปเดตโค้ดของ host (หลัง #194 merge)

```powershell
cd C:\Users\whale\Delentia\Delentia-OS
git pull --ff-only
```

ถ้า git บ่นว่ามีไฟล์ที่ไม่ได้ติดตามชนกัน (`results/`, `scripts/.run_suite_313.tmp.sh`) ให้บอกผม อย่าลบเอง

## 2. เริ่ม host แล้วเปิด Desk

```powershell
python scripts\local_host.py start
python scripts\local_host.py status
```

ต้องเห็น `healthy: True` แล้วดับเบิลคลิก `OPEN_DESK.bat` ที่ `C:\Users\whale\Delentia`

## 3. สร้างนโยบายจาก starter plan-first (ในหน้าเว็บ)

1. เมนู **FDIA / Policy**
2. กดปุ่ม **Start from: plan-first** แล้วอ่านกฎที่ปรากฏ: ต้องมี `plan_first` 7 ชนิด (ลบ, ส่งออก, เงิน, สิทธิ์, เผยแพร่, ยกเลิก/กู้คืน, ย้าย/ปิดระบบ) และ "แก้ไฟล์เล็กที่คำขอระบุชื่อ รันได้โดยไม่ต้องเซ็น" ติ๊กอยู่ (ไม่มี "แก้เอกสาร" ในรายการ ตามที่คุณอนุมัติ)
3. กด **Save**

หน้าจอจะตอบ **"รอลายเซ็น"** พร้อมรหัสคำขอ และคำสั่งที่ต้องรัน คำขอนี้ผูกกับ *นโยบายฉบับนี้ตัวอักษรต่อตัวอักษร* (ลายเซ็นครอบ digest ของนโยบาย รวมทั้ง `plan_first` และ `small_edit_autorun`) ถ้าแก้อะไรแม้เล็กน้อยทีหลัง ลายเซ็นเดิมใช้ไม่ได้

## 4. เซ็นด้วยกุญแจของคุณ

ในเทอร์มินัลที่ **ตั้งโฟลเดอร์ข้อมูลของ host** (สำคัญ: คำขอรออยู่ในฐานข้อมูลของ host ไม่ใช่ของโฟลเดอร์พัฒนา):

```powershell
$env:DELENTIA_HOME = "C:\Users\whale\delentia-host\home"
cd C:\Users\whale\Delentia\Delentia-OS
python -m rct_control_plane.cli approvals list
python -m rct_control_plane.cli approvals approve <รหัสคำขอ> --key C:\Users\whale\.delentia\keys\architect.pem
```

* บรรทัดแรก (`approvals list`) ต้องเห็นคำขอ `Owner policy change: fdia_policy_change` สถานะ PENDING; ถ้าเห็น "No pending actions" แปลว่าตั้ง `DELENTIA_HOME` ผิด (ผมแก้บั๊กในรอบนี้แล้ว: ก่อนหน้านี้คำสั่ง `approvals` มองฐานข้อมูลผิดไฟล์ จึงว่างเปล่าเสมอถ้าไม่ใส่ `--db`)
* คำสั่ง `approve` ใช้กุญแจส่วนตัวเซ็นในเครื่องนี้ ไม่ส่งกุญแจไปไหน

## 5. กลับไปที่ Desk กด Save อีกครั้ง

Desk จำรหัสคำขอไว้แล้ว กด Save ซ้ำ ระบบตรวจลายเซ็นกับ digest แล้วบันทึกนโยบาย

## 6. ตรวจว่าเปิดจริง

```powershell
python -m rct_control_plane.cli fdia show
python -m rct_control_plane.cli fdia history
```

* `fdia show` ต้องแสดง `plan_first` 7 ชนิดและ `small_edit_autorun: true`
* `fdia history` ต้องแสดงเวอร์ชันใหม่ **และระบุว่า "a small edit of a file the request names now runs without a signature" เป็นการผ่อนกฎ** ซึ่งตั้งใจให้เห็น

ทดลองสั้นๆ ผ่านหน้า Chat ของ Desk: "ลบไฟล์ docs/old.md" ควรได้ **แผน** ที่รอยืนยันในหน้า Approvals (การ์ดแผนมีขั้นเลข) ไม่ใช่ถูกลบทันที

## 7. ถ้าต้องการปิด

เอานโยบายเดิมกลับด้วยปุ่ม **Disable policy** (เปลี่ยนชื่อไฟล์ ไม่ลบ) หรือบันทึกนโยบายใหม่ที่ไม่มี `plan_first`/`small_edit_autorun` ซึ่งต้องเซ็นเช่นกัน

## 8. ใช้งานจริง 2 สัปดาห์แล้วดูอะไร

```powershell
python -m rct_control_plane.cli clarify stats       # คำถามที่ระบบถามคุณ ตอบ/ข้าม/หมดอายุ
python -m rct_control_plane.cli approvals suggest   # ชนิดการกระทำที่คุณอนุมัติซ้ำ 5 ครั้งขึ้นไปโดยไม่เคยปฏิเสธ (เสนออย่างเดียว)
```

ตัวเลขเหล่านี้คือข้อมูลการใช้จริงชุดแรกของระบบ และเป็นเกณฑ์ตัดสินว่าชนิดที่เลือกพอดีไหม เช่น ถ้าขั้น "ส่งออก" ของ `delentia_save_exchange_file` ขวางบ่อยเกินไป ให้บอกผมก่อนค่อยเปลี่ยน (แก้บรรทัดเดียวใน `plan_approval.action_kind`)
