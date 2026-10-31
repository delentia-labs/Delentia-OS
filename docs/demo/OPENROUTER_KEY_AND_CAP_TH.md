# คู่มือ: การวัดที่ใช้เงินจริงครั้งแรก ด้วยเครดิต OpenRouter แบบจ่ายล่วงหน้า $15

สำหรับเจ้าของระบบ (Architect) ทำใน **เทอร์มินัลของตัวเอง** **ห้ามส่งคีย์ให้ใครหรือวางคีย์ลงแชต/ไฟล์ใด ๆ** ขั้นตอนเหล่านี้ให้คีย์อยู่ในหน่วยความจำของหน้าต่างเทอร์มินัลเดียวและหายเมื่อปิดหน้าต่าง

**สถานะตามจริง:** ทุกอย่างด้านล่างซ้อมกับ OpenRouter ปลอมที่คิดเงินในตัวนับของมันเอง (ไม่มีคีย์ ไม่เสียเงิน) แล้ว: ตัวนับของเราตรงกับตัวนับของเซิร์ฟเวอร์ปลอมถึงสตางค์ ($0.1595 เท่ากัน) เซิร์ฟเวอร์ปลอมที่คิดเงินมากกว่าที่คำตอบแสดงถูกสคริปต์ P0 จับได้ และทุกคำสั่งปฏิเสธที่จะส่งอะไรถ้าไม่มี freeze ที่ตรงกัน **ยังไม่เคยรันกับ OpenRouter จริง** สิ่งที่การรันจริงจะบอกคือโมเดลจริงทำอะไร ซึ่งสคริปต์บอกไม่ได้

## เงินนี้ซื้ออะไร และไม่ซื้ออะไร

| ขั้น | ตอบคำถามอะไร | เพดาน |
|---|---|---|
| P0 | ตัวนับเงินของเราตรงกับตัวเลขของผู้ให้บริการหรือไม่ | $0.10 |
| P1 | โมเดลไหนใน 21 ตัว (16 ค่าย) ขับ loop ที่มีธรรมาภิบาลได้เลย | $5.00 |
| P1b | เมนูเครื่องมือขนาดย่อ (ราว 1,000 token) แทนเมนูเต็ม (ราว 8,000) ได้โดยไม่เลือกแย่ลงหรือไม่ | $1.50 |
| P2 | judge, critic และ context judge ผ่านกฎของตัวเองบนโมเดลที่เก่ง บนชุดที่คุณลงป้ายและปิดผนึกไว้หรือไม่ | $1.50 |
| P4 | งานเดียวกันให้ผลต่างกันหรือไม่เมื่อมีและไม่มี runtime (TC-003, TC-006) | $4.00 |
| | **ผลรวมเพดาน** | **$12.10** (คาดว่าจะใช้จริงน้อยกว่านี้มาก) |

$2.90 ที่เหลือจาก $15 เป็นเงินสำรองที่ **คีย์เข้าไม่ถึง** (ขั้นที่ 2): จะใช้ได้ต้องให้คุณเพิ่มวงเงินของคีย์ด้วยตัวเอง กฎผ่าน/ไม่ผ่านของแต่ละขั้นเขียนไว้ใน `research/PREPAID_CRITERIA_R103.md` (commit ก่อนมีคีย์) ผลที่ไม่ถึงกฎบันทึกว่าไม่ถึง

มัน **ไม่** ซื้อ: การเทียบ Delentia กับ Hermes (รอบนี้ไม่รัน h0) ความเป็นอิสระหลายวัน host หรือผู้ใช้ภายนอก

## ขั้นที่ 1: ก่อนเริ่ม

* ที่ `C:\Users\whale\Delentia\Delentia-OS` รัน `git pull` แล้ว `git status` ต้องไม่มีอะไรค้าง freeze ปฏิเสธโฟลเดอร์ที่มีการแก้ไขยังไม่ commit
* ใช้ `py -3.13` (Python ของระบบที่มี dependency ครบ) ไม่ใช่ตัวใน Git Bash

## ขั้นที่ 2: เพดานเงินสามชั้น (ทำให้ครบ)

1. **เพิกถอนคีย์เก่าที่เคยรั่ว** (openrouter.ai → Keys → Delete) ถ้ายังไม่ได้ทำ
2. **เติมเครดิตแบบจ่ายล่วงหน้า $15 ครั้งเดียว** และ **ปิด auto top-up** (Settings → Credits) จ่ายด้วยบัตรมีค่าธรรมเนียมราว 5.5% (ขั้นต่ำ $0.80) รวมราว $15.83 ถ้าเครดิตหมด การเรียกจะถูกปฏิเสธ ไม่มีบิลตามหลัง
3. **สร้างคีย์ใหม่เฉพาะงานนี้**: Keys → Create Key → ตั้งชื่อ `delentia-prepaid-2026-10` → *Credit limit* = **12.10** (นี่คือเพดาน ณ ผู้ให้บริการ ซึ่ง freeze ให้คุณยืนยันว่ามีอยู่) คัดลอกครั้งเดียว
4. ชั้นของโปรแกรมเองซ้อนอยู่บน: ตัวรันปฏิเสธการเริ่มถ้า ค่าประมาณ × 1.5 สูงกว่างบที่ให้ และหยุดเมื่อโมเดลใช้เกิน 1.5 เท่าของค่าประมาณ ตัวนับของเอเจนต์ปฏิเสธการเรียกที่กรณีเลวร้ายที่สุดจะเกินงบ

## ขั้นที่ 3: คีย์และการตั้งค่า ในหน้าต่างเทอร์มินัลเดียว

เปิด PowerShell ใหม่ (ไม่ใช่หน้าต่างที่ Claude ใช้):

```powershell
$k = Read-Host "OpenRouter key" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $k).Password
$env:DELENTIA_RUN_LIVE_TESTS = "1"
$env:DELENTIA_OPENROUTER_DATA_COLLECTION = "deny"
$env:DELENTIA_OPENROUTER_REQUIRE_PARAMETERS = "1"
cd C:\Users\whale\Delentia\Delentia-OS
```

ใช้ **หน้าต่างเดียวกันนี้ทุกขั้นต่อไป** freeze บันทึกค่าเหล่านี้ไว้ หน้าต่างที่ตั้งต่างกันจะถูกปฏิเสธ โมเดลที่ไม่มีผู้ให้บริการภายใต้ `deny` จะเรียกไม่สำเร็จ นั่นถูกต้อง (บันทึกเป็น `not_run`) ไม่ใช่ความผิดพลาด

## ขั้นที่ 4: freeze สิ่งที่จะวัด

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\daaes-results | Out-Null
$m = (Get-Content research/screen_models_2026-10-16.txt) -join ","
py -3.13 -m research.paid_run_freeze write --models $m --live-prices --stages P0,P1,P1b,P2,P4 --budget-usd 12.10 --provider-cap-confirmed --out $env:USERPROFILE\daaes-results\freeze.json
$env:DELENTIA_FREEZE_FILE = "$env:USERPROFILE\daaes-results\freeze.json"
py -3.13 -m research.paid_run_freeze check $env:DELENTIA_FREEZE_FILE
```

คำสั่งแรกเขียน commit การตั้งค่า โมเดลพร้อมราคาวันนี้ เพดานต่อขั้น และ SHA-256 ของไฟล์เกณฑ์ `check` ต้องพิมพ์ `the run matches the freeze` มันปฏิเสธถ้าไม่ใส่ `--provider-cap-confirmed` (ใส่เมื่อทำขั้น 2.3 แล้วเท่านั้น) ราคาหายหรือผิดรูป หรือเพดานรวมเกินงบ นับจากนี้ทุกคำสั่งที่ใช้เงินได้จะถามไฟล์นี้ก่อน ถ้ามีอะไรเปลี่ยน (commit การตั้งค่า ราคา ไฟล์เกณฑ์) มันบอกว่าอะไรต่างและไม่ส่งอะไร

## ขั้นที่ 5: P0 ตัวนับเงิน (ราว $0.03 เพดาน $0.10)

เลือกโมเดลที่ถูกที่สุดในรายการที่มีราคา (ไฟล์ freeze แสดง `price_in_per_mtok` และ `price_out_per_mtok` ของแต่ละตัว):

```powershell
py -3.13 scripts/calibrate_meter_p0.py <ไอดีโมเดลถูก> --price-in <ราคา input> --price-out <ราคา output> --budget-usd 0.10 --json $env:USERPROFILE\daaes-results\p0.json
```

ส่งคำขอสั้น 24 ครั้งผ่านตัวนับของเอเจนต์เอง อ่านตัวเลขการใช้งานของคีย์จนกว่าจะนิ่ง แล้วพิมพ์ PASS ถ้าสองยอดต่างกันไม่เกิน 10% `INCONCLUSIVE` (ตัวเลขยังขยับ หรือไม่ขยับ) ไม่ใช่ fail: รันอีกครั้งเดียว **ถ้าพิมพ์ FAIL หยุดแล้วส่ง `p0.json` ให้ผม ไม่มีอะไรอื่นรันจนกว่าจะเข้าใจตัวนับ**

## ขั้นที่ 6: P1 คัดกรองความสามารถ (ประมาณ $3.0 เพดาน $5.00)

ดูก่อนโดยไม่ใช้เงิน:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier W --models $m --budget-usd 5 --live-prices
```

ต้องพิมพ์ `DRY RUN: nothing was sent and nothing was spent` กับค่าประมาณ (ราว $3.0 หรือ $4.5 เมื่อคูณ margin ตามราคา 2026-10-26 ราคาวันนี้คือที่ถูกต้อง) แล้วคำสั่งเดิมเพิ่ม `--execute --freeze-file`:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier W --models $m --budget-usd 5 --live-prices --execute --freeze-file $env:DELENTIA_FREEZE_FILE --out $env:USERPROFILE\daaes-results\screen-w.json
```

หยุดเองเมื่อโมเดลใช้เงินเกิน 1.5 เท่าของค่าประมาณ เมื่อธรรมาภิบาล (T3) ต่ำกว่า 100% เมื่อบัญชีปฏิเสธการเรียก (เครดิตหมด คีย์ถูกเพิกถอน) หรือเมื่อพบสิ่งที่หน้าตาเหมือนคีย์ในผลลัพธ์ใด ๆ ตรวจยอดที่ openrouter.ai → Activity ส่ง `screen-w.json` ให้ผม (ไม่มีคีย์) **ผมเลือกไม่เกินสามโมเดล** (ต่างค่าย ต่างราคา) และบันทึกการเลือกไว้ **ก่อน** เริ่ม P1b

## ขั้นที่ 7: P1b A/B เมนู (ราว $0.05-0.7 ต่อโมเดล เพดานรวม $1.50)

หนึ่งโมเดลต่อหนึ่งคำสั่ง รัน dry run ก่อน (ไม่ใส่ `--execute` และ `--freeze-file`) มันพิมพ์ค่าประมาณพร้อม margin และ `--budget-usd` คือตัวเลขนั้นปัดขึ้น แต่ไม่เกินส่วนที่เหลือของ $1.50:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier M --models <ไอดีโมเดลที่เลือกหนึ่งตัว> --budget-usd <ตัวเลขจาก dry run ปัดขึ้น> --live-prices
py -3.13 scripts/full_test_orchestrator.py --tier M --models <ไอดีโมเดลที่เลือกหนึ่งตัว> --budget-usd <ตัวเลขเดียวกัน> --live-prices --execute --freeze-file $env:DELENTIA_FREEZE_FILE --out $env:USERPROFILE\daaes-results\menu-m-<ชื่อ>.json
```

โมเดลที่ราคาแพงจนขั้นนี้ขั้นเดียวไม่พอดีเพดาน $1.50 จะถูกปฏิเสธ ไม่รันที่นี่ ผลต่อโมเดลคือ PASS, FAIL หรือ INCONCLUSIVE อ่านทีละโมเดล ไม่รวมกัน **ผ่านไม่ได้เปลี่ยนอะไรเอง**: เมนูตั้งต้นของโมเดลบนคลาวด์ยังเป็นเมนูเต็มจนกว่าคุณจะตัดสินใจ

## ขั้นที่ 8: P2 ชุด RCT-7 (เพดาน $1.50)

ต่อโมเดลที่เลือก ชุดละครั้ง (ตัวรันปฏิเสธการดูซ้ำสำหรับโมเดล prompt และป้ายเดียวกัน) ไฟล์ชุดอยู่ใน `C:\Users\whale\Delentia` งบสี่คำสั่งรวม $0.45 ต่อโมเดล สามโมเดลจึงอยู่ในเพดาน $1.50 โมเดลที่แพงกว่าควรรันน้อยชุดลง และตัวรันหยุดที่งบที่คุณให้:

```powershell
py -3.13 -m research.rct7_holdout run C:\Users\whale\Delentia\RCT7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md --provider openrouter --model <id> --budget-usd 0.15
py -3.13 -m research.rct7_holdout run C:\Users\whale\Delentia\RCT7_R7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md --provider openrouter --model <id> --budget-usd 0.10
py -3.13 -m research.rct7_holdout_twoaxis run C:\Users\whale\Delentia\RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md --variant plain --provider openrouter --model <id> --budget-usd 0.10
py -3.13 -m research.rct7_holdout_twoaxis run C:\Users\whale\Delentia\RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md --variant context --provider openrouter --model <id> --budget-usd 0.10
```

## ขั้นที่ 9: P4 มีและไม่มี runtime (เพดาน $4.00)

```powershell
py -3.13 -m research.daaes benchmark --provider openrouter --model <id> --arms b0,d0 --seeds 1700-1703 --budget-usd 1.0 --price-in <in> --price-out <out> --out $env:USERPROFILE\daaes-results\p4-tc003
py -3.13 -m research.daaes live --case TC-006 --provider openrouter --model <id> --budget-usd 0.3 --price-in <in> --price-out <out> --out $env:USERPROFILE\daaes-results\p4-tc006
```

สองงบรวม $1.30 ต่อโมเดล สามโมเดลจึงอยู่ในเพดาน $4.00 สี่รอบต่อแขนเป็นการบรรยาย ไม่ใช่ข้อค้นพบ: ไม่อ้างว่าดีขึ้นเว้นแต่ช่วงความเชื่อมั่นไม่คร่อมศูนย์ และอ้างได้เฉพาะโมเดลนั้นกับงานนั้น

## ขั้นที่ 10: หลังแต่ละขั้น

* ส่งไฟล์ผลให้ผม (ไม่มีไฟล์ไหนมีคีย์) ผมเพิ่มลง `research/RESULTS_REGISTER.jsonl` พร้อมต้นทุนจริงจากตัวเลขของผู้ให้บริการ การตั้งค่า และไฟล์เกณฑ์ ผลจึงไม่ถูกบันทึกโดยไม่มีราคาที่จ่ายจริง
* เทียบ openrouter.ai → Activity กับที่แต่ละขั้นพิมพ์
* เสร็จแล้วปิดหน้าต่าง PowerShell และถ้าไม่ใช้คีย์ต่อ ให้ลบที่ OpenRouter

## ผลนี้พิสูจน์และไม่พิสูจน์อะไร

ผ่าน P1 บอกว่าโมเดลเลือก tool ถูกและปฏิเสธเป้าหมายที่ทำไม่ได้ในงานสั้น ไม่ได้บอกว่าตัวไหนทำงานจริงได้ดีกว่า และไม่ได้บอกว่า Delentia ทำให้ดีขึ้น: นั่นคือ P4 ซึ่งมีสี่รอบ ผลเป็นอย่างไรก็บันทึกตามนั้น

## ภาคผนวก: ปักผู้ให้บริการปลายทาง และเรื่องโมเดลฟรี

**ปักผู้ให้บริการ:** OpenRouter อาจส่งโมเดลเดียวกันไปให้ผู้ให้บริการต่างรายในแต่ละคำขอ (quantization, หน้าต่างบริบท, ความเร็ว, นโยบายข้อมูลต่างกัน) ซึ่งทำให้วัดซ้ำไม่ได้ ตั้งตัวแปรเหล่านี้ในหน้าต่างเดียวกับคีย์ (ถ้าไม่ตั้ง คำขอเหมือนเดิมทุกประการ):

```powershell
$env:DELENTIA_OPENROUTER_DATA_COLLECTION = "deny"        # เฉพาะผู้ให้บริการที่ไม่เก็บ/ไม่ใช้ prompt ฝึก (บางโมเดล โดยเฉพาะ :free ต้องใช้ allow)
$env:DELENTIA_OPENROUTER_REQUIRE_PARAMETERS = "1"        # เฉพาะผู้ให้บริการที่รองรับพารามิเตอร์ทั้งหมดที่เราส่ง (เช่น JSON mode)
$env:DELENTIA_OPENROUTER_PROVIDER_ORDER = "anthropic"    # (ไม่บังคับ) ผู้ให้บริการที่ต้องการ ตามลำดับ; เมื่อตั้งแล้วจะไม่ fallback เงียบ ๆ (ตั้ง DELENTIA_OPENROUTER_ALLOW_FALLBACKS=1 ถ้าต้องการ)
$env:DELENTIA_OPENROUTER_ZDR = "1"                       # (ไม่บังคับ) เฉพาะ endpoint แบบ zero-data-retention
$env:DELENTIA_OPENROUTER_QUANTIZATIONS = "fp8,bf16,fp16" # (ไม่บังคับ) จำกัดระดับ quantization
```

ค่าที่ใช้ไม่ได้ถูกข้ามพร้อมคำเตือน ไม่ถูกส่ง หลังรัน `provider.last_served_by` บอกว่าใครตอบ บันทึกไว้กับผล ข้อควรรู้: `deny` หรือ `zdr` อาจทำให้บางโมเดลไม่มีผู้ให้บริการที่ตรงเงื่อนไขและคำขอล้มเหลว นั่นเป็นพฤติกรรมที่ถูกต้อง (ล้มแทนที่จะส่งข้อมูลไปที่ที่ไม่ต้องการ)

**โมเดลฟรี (`:free`):** ตามหน้าขีดจำกัดของ OpenRouter (https://openrouter.ai/docs/api/reference/limits อ่านเมื่อ 2026-10-25) โมเดลที่ลงท้าย `:free` จำกัด 20 คำขอ/นาทีเสมอ และ 50 คำขอ/วัน ถ้าซื้อเครดิตสะสมตลอดเวลาน้อยกว่า 10 หน่วย แต่เป็น **1,000 คำขอ/วัน เมื่อซื้อเครดิตสะสม ≥ 10** (นับยอดที่ซื้อทั้งหมด ไม่ใช่ยอดคงเหลือ) การเติม $15 จึงปลดล็อกชั้น 1,000 ครั้ง/วัน ยอดคงเหลือติดลบทำให้ใช้โมเดลฟรีไม่ได้ด้วย
