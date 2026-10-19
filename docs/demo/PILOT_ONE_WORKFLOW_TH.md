# Pilot: งานเดียว ด้วยโมเดลจริง (ใช้เงินจำกัด) — คู่มือสำหรับเจ้าของ

เป้าหมาย: ทำให้ **งานเดียว** สำเร็จซ้ำได้กับโมเดลที่ผ่านเกณฑ์ และบันทึกว่าอะไรพัง ใช้เงินเท่าไร และเจ้าของต้องเข้าไปช่วยกี่นาที — ก่อนจะเพิ่มอะไรอีก งานที่เลือก (workflow W02 ใน `research/MASTER_WORKFLOWS.md`):

> เปรียบเทียบใบเสนอราคา 3 ใบ → ร่างรายงาน → **รอลายเซ็น** → เขียนไฟล์ผลลัพธ์ → ตรวจ audit → (ทดสอบ) ฆ่ากระบวนการกลางงานแล้วทำต่อ

ขั้นตอนที่ต้องใช้คีย์/เงินเป็นของเจ้าของ ผมไม่ทำให้ (ไม่เก็บคีย์ในไฟล์ใด ๆ): ใส่คีย์เองใน PowerShell ของคุณ

## 0. เตรียม (ครั้งเดียว)

```powershell
# คีย์อยู่ในหน่วยความจำของหน้าต่างนี้เท่านั้น ห้ามบันทึกลงไฟล์
$env:OPENROUTER_API_KEY = "<คีย์ของคุณ>"
$env:DELENTIA_RUN_LIVE_TESTS = "1"
# เพดานต่อ episode และต่อวัน (ผู้ช่วยจะปฏิเสธการเรียกที่เกินเพดาน ก่อนเรียกโมเดล)
$env:DELENTIA_EPISODE_BUDGET_USD = "0.25"
$env:DELENTIA_DAILY_BUDGET_USD = "2"
```

เครดิตที่ OpenRouter: เติมแบบ prepaid เท่านั้น (ดู `docs/demo/OPENROUTER_KEY_AND_CAP_TH.md`) เริ่ม $5

## 1. เลือกโมเดล (คัดกรองก่อน — ใช้ราว $4.5 ตามประมาณการ)

```powershell
python scripts/full_test_orchestrator.py --tier S --models <id1>,<id2>,... --budget-usd 5 --live-prices            # ไม่มี --execute = ซ้อมแผนและประมาณการ ไม่เสียเงิน
python scripts/full_test_orchestrator.py --tier S --models <id1>,<id2>,... --budget-usd 5 --live-prices --execute  # รันจริงเมื่อพอใจกับประมาณการ
```
รายชื่อโมเดลที่ประมาณการไว้ (21 ตัว จาก 16 ผู้ผลิต) อยู่ใน `research/screen_models_2026-10-16.txt`; ราคา OpenRouter เปลี่ยนได้ ใช้ `--live-prices` ดึงราคาวันนี้ และคำสั่งละเอียดอยู่ใน `docs/demo/OPENROUTER_KEY_AND_CAP_TH.md`
เลือกโมเดลที่ผ่าน (K.1.5 ≥ 90%, T3 = 100%) แล้ว:
```powershell
delentia model set <model-id> --provider openrouter
delentia model show
```

## 2. รันงาน (บันทึกเวลาและค่าใช้จ่ายทุกครั้ง)

```powershell
delentia demo init
delentia demo run compare            # ผู้ช่วยอ่านใบเสนอราคา 3 ใบ และสรุป
delentia demo run edit               # ร่างไฟล์ผลลัพธ์ แล้ว "หยุดรอลายเซ็น" (ต้องเห็นข้อความ pending approval)
delentia demo status                 # เห็นคำขอที่รออยู่
delentia demo approve <approval-id>  # เซ็นด้วยกุญแจของ demo (บนเครื่องนี้) ผู้ช่วยทำต่อ
delentia audit-chain verify          # chain ต้อง OK และทุกแถวเซ็น
```
สำหรับคุณเอง ใช้กุญแจอนุมัติของคุณ (`delentia approvals keygen/sign`) แทนกุญแจ demo เมื่อจะใช้กับงานจริง

## 3. ทดสอบ "ดับกลางงาน แล้วทำต่อ"

1. เริ่ม `delentia demo run budget` (งานยาวกว่า) ในหน้าต่าง A
2. ในหน้าต่าง B: `taskkill /F /PID <pid ของ python ที่รันงาน>` ขณะที่มันกำลังทำงาน
3. `delentia episodes list` → เห็นงานที่ถูกขัด และ "ขั้นไหนไม่รู้ผล"
4. `delentia episodes resume <episode-id>` → ทำต่อเป็น episode ใหม่ (ขั้นที่เสร็จแล้วไม่ถูกทำซ้ำ) ถ้าขั้นที่เปลี่ยนโลกจริงไม่รู้ผล จะไม่ไปต่อเองจนกว่าคุณใช้ `--allow-unknown` หลังดูของจริงแล้ว

## 4. บันทึกผล (ทำทุกครั้ง ใช้ตารางนี้)

| รอบ | วันที่ | โมเดล | ผ่านไหม (ตรงกับ oracle ของ W02) | ค่าใช้จ่ายจริง (จาก OpenRouter ไม่ใช่จากเรา) | เวลาที่คุณต้องเข้าไปช่วย (นาที) | สิ่งที่พัง |
|---|---|---|---|---|---|---|

กติกา: ล้มเหลวของโมเดล/ผู้ช่วยนับเป็นล้มเหลว (ไม่ตัดทิ้ง); ล้มเหลวจากไฟดับ/เน็ตหลุดบันทึกแล้วทำรอบใหม่ ห้ามอ้างว่า "ทำได้ซ้ำ" จนกว่าจะมีอย่างน้อย 14 รอบที่ต่างงาน/seed (ดู `research/MASTER_WORKFLOWS.md` หัวข้อ How many runs make a claim)

## 5. เมื่อเสร็จ

```powershell
Remove-Item Env:OPENROUTER_API_KEY            # ปิดคีย์ในหน้าต่างนี้
```
แล้วบอกผม: ตารางผล + ไฟล์ `~/delentia-demo` ผมจะช่วยวิเคราะห์ (ไม่ต้องส่งคีย์ใด ๆ)
