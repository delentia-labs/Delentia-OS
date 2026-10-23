# คู่มือ: ให้ notary ส่งหัวบันทึก (head) ออกไปให้ "พยานภายนอก" เองทุกชั่วโมง (A3) และให้บุคคลที่สามประทับเวลา (RFC 3161)

สำหรับเจ้าของระบบ (Architect) ทำเองบนเครื่องนี้ ใช้เวลาประมาณ 15 นาที ไม่ต้องใช้รหัสผ่านหรือโทเค็นของใครนอกจากรหัสผ่านบัญชี `delentia-notary` ที่ตั้งไว้เอง **ห้ามวางคีย์/รหัสผ่านลงแชต**

## 0. ทำไมต้องมี และมันป้องกันอะไร (อ่านก่อน)

ตอนนี้ notary (บัญชี Windows แยก) เซ็นทุกการเรียก tool ลงบันทึกของมัน agent จึงปลอมประวัติไม่ได้ แต่คนที่เป็น Administrator ของเครื่องนี้ยังเขียนบันทึกใหม่ทั้งก้อนได้ ไม่มีใครจับได้ ทางแก้คือส่ง "ลายนิ้วมือ" (hash ของแถวล่าสุด) ออกไปให้ **คนอื่นที่เครื่องนี้แก้ไม่ได้** เก็บไว้เป็นระยะ:

| พยาน | คือใคร | ต้องใช้อะไร | ป้องกันอะไร |
|---|---|---|---|
| **Worker** (Cloudflare) | ระบบของคุณเองที่อยู่คนละที่ รับเฉพาะหัวที่เซ็นด้วยคีย์ที่ลงทะเบียน และ **ปฏิเสธการย้อนกลับ/แยกสาย** | URL ของ Worker (ไม่มีรหัสผ่าน) | เขียนบันทึกใหม่ทั้งก้อน, ตัดแถวท้ายทิ้ง |
| **RFC 3161** (DigiCert/Sectigo) | ผู้ให้บริการประทับเวลาสาธารณะ **คนละบริษัท** เซ็นว่า "hash นี้มีอยู่ ณ เวลานี้" ปลอมหรือย้อนวันไม่ได้ ใครก็ตรวจได้ด้วย `openssl` | ไม่ต้องมีบัญชี ไม่ต้องมีรหัส (ส่งเฉพาะ hash) | เหมือนกัน และพิสูจน์ **เวลา** โดยไม่ต้องเชื่อคุณเลย |

สองอย่างนี้ **เสริมกัน** ไม่ใช่ทางเลือก: Worker ปฏิเสธสายแยกได้ (มันจำลำดับ) ส่วนบุคคลที่สามพิสูจน์เวลาได้ (ไม่ขึ้นกับคุณหรือ Cloudflare)

**คำที่ใช้ได้หลังทำเสร็จและผ่านข้อ 6:** "tamper-evident against a compromise of this host (ภายในช่วงเวลาตั้งแต่สมอครั้งล่าสุด)". **ห้ามใช้:** tamper-proof / immutable / ป้องกันการแก้ไขได้ทั้งหมด

## 1. ดูสถานะปัจจุบันของ Worker (อ่านอย่างเดียว ไม่เปลี่ยนอะไร)

```powershell
curl.exe -s "https://delentia-fdia-mcp.delentia.workers.dev/v1/audit/anchor/host-notary-1?limit=5"
```
ผลที่ตรวจเมื่อ 2026-10-19: `count: 1` ที่ entries 12 (สมอครั้งเดียวที่เคยส่ง) และ `conflicts: []` คีย์ `host-1` (ของ runtime) ยัง **ไม่มีสมอเลย** (count 0)

## 2. อัปเดตโปรแกรมในบัญชี notary ให้มีตัวเลือกประทับเวลา

ตัวเลือก `--timestamp-url` อยู่ใน PR ของ Round 91 และจะมีในรุ่นถัดจาก 2.3.1 (ตรวจ `delentia.exe notary serve --help` ว่ามี `--timestamp-url` หรือยัง ถ้า **ไม่มี** ให้ข้ามไปทำเฉพาะ Worker ก่อน ข้อ 3 ใช้ได้กับรุ่นปัจจุบัน แล้วกลับมาทำข้อ 4 หลังอัปเดต)

```powershell
runas /user:%COMPUTERNAME%\delentia-notary "cmd /k C:\DelentiaNotary\venv\Scripts\python.exe -m pip install --upgrade delentia-os"
```
(หน้าต่างจะค้างให้อ่านผล; ปิดเองเมื่ออ่านเสร็จ)

## 3. ให้ notary ส่งหัวไป Worker ทุกชั่วโมง (ใช้ได้ทันที ไม่ต้องอัปเดต)

คีย์ `host-notary-1` ลงทะเบียนที่ Worker แล้ว จึงไม่ต้อง deploy อะไร เปิด PowerShell **แบบ Administrator** แล้วลงทะเบียนงาน `DelentiaNotary` ใหม่ (คำสั่งนี้ดัดจากข้อ 6 ของคู่มือบัญชี notary เพิ่มสามตัวเลือก):

```powershell
$cmd = 'set "DELENTIA_NOTARY_TOKEN_FILE=C:\DelentiaNotary\token.txt" && C:\DelentiaNotary\venv\Scripts\delentia.exe notary serve --db C:\DelentiaNotary\notary.db --key C:\DelentiaNotary\notary_key.pem --port 8765 --anchor-url https://delentia-fdia-mcp.delentia.workers.dev --anchor-key-id host-notary-1 --anchor-every 3600'
$act  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd" -WorkingDirectory C:\DelentiaNotary
$trg  = New-ScheduledTaskTrigger -AtStartup
$cred = Get-Credential -UserName "$env:COMPUTERNAME\delentia-notary" -Message "รหัสผ่านของ delentia-notary"
Unregister-ScheduledTask -TaskName "DelentiaNotary" -Confirm:$false
Register-ScheduledTask -TaskName "DelentiaNotary" -Action $act -Trigger $trg -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited
Start-ScheduledTask -TaskName "DelentiaNotary"
```
(ตัวเลข `3600` = ทุก 1 ชั่วโมง; โปรแกรมส่งเฉพาะเมื่อหัวขยับ ถ้าไม่มีการเรียก tool ก็ไม่ส่ง; ถ้า Worker ล่ม notary ไม่หยุด แค่ข้ามรอบ)

ตรวจ (รอประมาณ 1 นาทีหลังเริ่ม เพราะสมอรอบแรกส่งทันทีที่เริ่ม):
```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
curl.exe -s "https://delentia-fdia-mcp.delentia.workers.dev/v1/audit/anchor/host-notary-1?limit=5"
```
`count` ควรเพิ่มจาก 1 เป็น 2 (ถ้ามีการเรียก tool ใหม่ตั้งแต่ครั้งก่อน)

## 4. ให้บุคคลที่สามประทับเวลาด้วย (หลังอัปเดตตามข้อ 2)

สร้างโฟลเดอร์เก็บโทเค็นในบัญชี notary (เจ้าของคือ notary จึง **agent ลบทิ้งไม่ได้**) แล้วเพิ่มอีกสองตัวเลือกในคำสั่งงาน:

```powershell
New-Item -ItemType Directory -Path C:\DelentiaNotary\timestamps -Force | Out-Null
icacls C:\DelentiaNotary\timestamps /inheritance:r /grant "delentia-notary:(OI)(CI)F" /grant "SYSTEM:(OI)(CI)F"
```
แล้วรันข้อ 3 ซ้ำโดยต่อท้ายตัวแปร `$cmd` ด้วย ` --timestamp-url http://timestamp.digicert.com --timestamp-dir C:\DelentiaNotary\timestamps`

(หมายเหตุ: DigiCert ใช้ `http://` เป็นปกติของมาตรฐานนี้ ไม่ใช่ช่องโหว่ เพราะส่งแค่ hash และโทเค็นที่ได้กลับมา **เซ็นตัวเอง** ปลอมระหว่างทางไม่ได้ ถ้าอยากสำรองอีกเจ้าให้ใช้ `http://timestamp.sectigo.com` สลับกันได้; ตรวจแล้วเมื่อ 2026-10-19 ว่าทั้งสองตอบกลับและโทเค็นผ่านการตรวจด้วย `openssl` ด้วยชุด CA ที่มากับ Python)

## 5. สั่งประทับเวลาด้วยมือหนึ่งครั้ง (ทดสอบ ไม่ต้องรอชั่วโมง)

```powershell
runas /user:%COMPUTERNAME%\delentia-notary "cmd /k C:\DelentiaNotary\venv\Scripts\delentia.exe notary timestamp --url http://timestamp.digicert.com --dir C:\DelentiaNotary\timestamps --key-id host-notary-1 --db C:\DelentiaNotary\notary.db --key C:\DelentiaNotary\notary_key.pem"
```
ผลที่ต้องเห็น: `{"timestamped": true, "entries": <เลข>, "head": "...", "note": "time-stamped 2026...Z"}`
(รันด้วยตัวอย่างจริงบน notary ชั่วคราวเมื่อ 2026-10-19 ได้ผลแบบนี้และตรวจผ่าน)

## 6. ตรวจว่ามันได้ผลจริง (ทำเสมอ อย่าเชื่อ)

ในหน้าต่าง `runas` ของบัญชี notary (เพราะฐานข้อมูลอ่านได้เฉพาะบัญชีนั้น):
```powershell
runas /user:%COMPUTERNAME%\delentia-notary "cmd /k C:\DelentiaNotary\venv\Scripts\delentia.exe notary check-anchors --url https://delentia-fdia-mcp.delentia.workers.dev --key-id host-notary-1 --db C:\DelentiaNotary\notary.db"
runas /user:%COMPUTERNAME%\delentia-notary "cmd /k C:\DelentiaNotary\venv\Scripts\delentia.exe notary check-timestamps --dir C:\DelentiaNotary\timestamps --key-id host-notary-1 --db C:\DelentiaNotary\notary.db"
```
ต้องเห็น `"ok": true` ทั้งสองคำสั่ง และ `"unchecked_signatures": 0` ในคำสั่งหลัง (ถ้าเป็นเลขอื่น แปลว่าเครื่องไม่มี `openssl` จึงอ่านโทเค็นได้แต่ยังไม่ได้ตรวจลายเซ็น: ติดตั้ง Git for Windows ซึ่งมี openssl ให้)

ความหมายของผลที่ผิด: `rewritten` = แถวที่เคยส่งไปแล้วถูกเขียนใหม่; `truncated` = แถวท้ายถูกตัดทิ้ง; `no valid signature` = โทเค็นไม่ได้มาจาก TSA ที่เชื่อถือ; `does not cover` = โทเค็นถูกย้ายมาใส่กับ hash อื่น ทุกข้อคือเรื่องร้ายแรง: หยุดและสืบก่อน

**ตรวจจากเครื่องอื่นที่คุณคุม (เป็นการตรวจที่มีค่าที่สุด):** ก๊อปปี้ `C:\DelentiaNotary\timestamps\host-notary-1\*.json` (โทเค็นไม่ใช่ความลับ) ไปเครื่องอื่น แล้ว `openssl ts -verify` กับ digest ในไฟล์ (ดูตัวอย่างใน `rct_control_plane/tests/test_audit_witness_tsa_round91_real.py` ฟังก์ชัน `test_the_token_file_is_a_standalone_proof`)

## 7. ส่วนของ runtime (ไม่บังคับ และมีข้อควรระวัง)

บันทึกของ **runtime** (`agentic.db`, คีย์ `host-1`) ก็ส่งสมอได้ผ่านตัวแปร `DELENTIA_AUDIT_WITNESSES` แต่:
- คีย์ `host-1` **ยังไม่ได้ลงทะเบียนที่ Worker** (count 0) การลงทะเบียน = แก้ `AUDIT_ANCHOR_KEYS_JSON` ใน `delentia-mcp/ecosystem/packages/fdia/wrangler.jsonc` แล้ว deploy Worker ซึ่งเป็นขั้นที่ต้องให้คุณสั่งเอง (ผมไม่ deploy ให้) พิมพ์รายการที่ต้องเพิ่มด้วย `delentia audit-chain witness-entry --key-id host-1`
- พยานแบบ RFC 3161 ของ runtime เก็บโทเค็นในบัญชีเดียวกับ agent จึง **agent ลบโทเค็นทิ้งได้** (ลบแล้วหลักฐานหาย แต่ปลอมไม่ได้) ตัวอย่างค่า (ใส่ใน `START_DAEMON.bat` เป็นบรรทัดเดียว): `set DELENTIA_AUDIT_WITNESSES=[{"type":"rfc3161","name":"tsa","url":"http://timestamp.digicert.com","path":"C:/Users/whale/delentia-host/timestamps","key_id":"host-1"}]`
- ดังนั้นลำดับความสำคัญคือ **notary ก่อน** (ข้อ 3-6) เพราะอยู่ในบัญชีที่ agent แตะไม่ได้ ส่วน runtime ทำทีหลัง

## 8. สิ่งที่ยังไม่ได้ทดสอบ (ซื่อสัตย์)

- ขั้นตอนที่แก้งานตั้งเวลาของบัญชี notary (ข้อ 3-4) **ผมไม่ได้รันบนเครื่องคุณ** (บัญชีนั้นผมเข้าไม่ได้ตามที่ตั้งใจ) สิ่งที่ผมทดสอบแล้วคือโปรแกรมเอง: notary จริงบนโฟลเดอร์ชั่วคราว + DigiCert/Sectigo จริง + `openssl` จริง + การแก้บันทึก/ตัดบันทึกแล้วจับได้
- ยังไม่มีผลของการรันต่อเนื่องหลายวัน ให้ดูว่า `count` ที่ Worker เพิ่มทุกชั่วโมงที่มีการใช้งานจริงหรือไม่
- ถ้ามีข้อผิดพลาด ให้ส่งข้อความผิดพลาด **ทั้งหมดที่ปรากฏ** (ไม่ใช่รหัสผ่าน) มาให้ผมดู
