# สร้างบัญชี OS แยกสำหรับ notary (Windows) — ทีละขั้น

เขียน 2026-10-17 อ่านประกอบ: `deploy/host/HOST_RUNBOOK.md` (ทางเลือก Docker), `delentia host-check` (ข้อ H05/H06)

## ทำไมต้องมีบัญชีแยก (ภาษาคน)

ลองนึกถึงสมุดบัญชีของบริษัท: ถ้าคนที่ **ทำรายการ** เป็นคนเดียวกับคนที่ **ลงชื่อรับรองในสมุด** เขาก็แก้สมุดย้อนหลังแล้วเซ็นใหม่ได้
Delentia แก้ปัญหานี้ด้วย **notary** = โปรแกรมเล็ก ๆ ที่ถือกุญแจเซ็นของมันเอง agent ส่งได้แค่ "ต่อท้าย" (append) ส่วนการเซ็น/ลำดับ/โซ่แฮชเป็นของ notary

แต่ถ้า notary รันด้วย **บัญชีผู้ใช้ Windows เดียวกับ agent** (บัญชี `whale`) agent ที่ถูกหลอกก็อ่านไฟล์กุญแจของ notary ได้ → ปลอมประวัติได้ → การแยกก็ไม่มีความหมาย
จึงต้องให้ notary เป็น **บัญชีอื่น** ที่ `whale` อ่านกุญแจไม่ได้ นี่คือสิ่งที่เอกสารเรียกว่า tier A2 ("แยกหน้าที่")

ที่ผมทำให้ไม่ได้: การสร้างบัญชี/ตั้งสิทธิ์ระบบเป็น "การแก้ค่าความปลอดภัยของระบบ" และต้องใช้สิทธิ์ผู้ดูแลเครื่อง (Administrator) กับรหัสผ่านที่คุณตั้งเอง ผมไม่ควรตั้งรหัสผ่านหรือยกสิทธิ์ให้ตัวเอง

## ก่อนเริ่ม: เลือกทาง (ซื่อสัตย์ว่าทางไหนแข็งแรงแค่ไหน)

| ทาง | แยกจาก agent ได้แค่ไหน | ความยาก |
|---|---|---|
| **A. บัญชี Windows แยก** (เอกสารนี้) | แข็งแรงกว่า ถ้า agent รันเป็น `whale` และ `whale` ไม่ใช่ผู้ที่ agent ยกสิทธิ์ Admin ได้ | ปานกลาง |
| **B. Docker (ชุด `deploy/host`)** | notary อยู่ container + uid แยก ใช้ได้สำหรับ VPS Linux; **บนเครื่องนี้อ่อนกว่า** เพราะ `whale` อยู่ในกลุ่ม docker → สั่ง `docker exec` เข้า notary ได้ | ง่าย (มีสคริปต์) |

ถ้าจะใช้เครื่องนี้ทดสอบแบบมี A2 จริง → ทาง A. ถ้าเช่า VPS ภายหลัง → ทาง B บนเซิร์ฟเวอร์ที่ agent ไม่มีสิทธิ์ docker

## ทาง A ขั้นตอน (เปิด PowerShell แบบ "Run as administrator")

### 1) สร้างบัญชี (ผู้ใช้ธรรมดา ไม่ใช่ Admin)
```powershell
$pw = Read-Host -AsSecureString "ตั้งรหัสผ่านของ delentia-notary (จดไว้ในที่ปลอดภัย)"
New-LocalUser -Name "delentia-notary" -Password $pw -PasswordNeverExpires -UserMayNotChangePassword -Description "Delentia notary (audit signer)"
Get-LocalGroupMember -Group "Administrators"      # ต้องไม่มี delentia-notary อยู่ในรายการ
```
บัญชีใหม่อยู่ในกลุ่ม Users โดยปริยาย (ผู้ใช้ธรรมดา) ซึ่งพอสำหรับงานนี้

**ตรวจให้แน่ว่ามีรหัสผ่านจริง** (ถ้าตอนถามรหัสผ่านกด Enter เปล่า ๆ บัญชีจะไม่มีรหัสผ่าน และ `runas`/Task Scheduler จะใช้ไม่ได้):
```powershell
Get-LocalUser delentia-notary | Format-List Name,Enabled,PasswordRequired
# ถ้า PasswordRequired เป็น False ให้ตั้งรหัสผ่านใหม่:
$pw = Read-Host -AsSecureString "รหัสผ่านใหม่"
Set-LocalUser -Name delentia-notary -Password $pw
```
(ถ้าคอนโซลแสดงภาษาไทยเพี้ยน ไม่เป็นไร เป็นแค่การแสดงผล ตอนคัดลอกคำสั่งให้ **ไม่ต้องคัดลอกส่วน `# ...` ที่เป็นคอมเมนต์ท้ายบรรทัด**)

### 2) สร้างโฟลเดอร์ที่ `whale` เข้าไม่ได้
```powershell
New-Item -ItemType Directory -Path C:\DelentiaNotary | Out-Null
icacls C:\DelentiaNotary /inheritance:r /grant "delentia-notary:(OI)(CI)F" /grant "SYSTEM:(OI)(CI)F" /grant "Administrators:(OI)(CI)F"
icacls C:\DelentiaNotary          # ตรวจ: ต้องไม่มี whale หรือ Users อยู่ในรายการ
```
`/inheritance:r` ตัดสิทธิ์ที่สืบมาจากโฟลเดอร์แม่ (ที่ปกติให้ Users อ่านได้) ออก
หมายเหตุ: ถ้า `whale` เป็น Administrator, โปรแกรมที่รันแบบปกติ (ไม่ยกสิทธิ์) จะ **ไม่ใช้** สิทธิ์ Administrators นี้ — แต่ agent ที่ขอยกสิทธิ์ (UAC) ได้จะผ่านได้ ดังนั้นห้ามให้ agent รันแบบยกสิทธิ์ และควรให้ agent รันภายใต้บัญชีผู้ใช้ธรรมดาในอนาคต (ดู "ข้อจำกัด")

### 3) ติดตั้ง Python + delentia ให้บัญชีนี้ใช้ได้
Python ของ `whale` อยู่ใต้ `C:\Users\whale\...` (Microsoft Store) บัญชีอื่นเข้าไม่ได้ ต้องมีชุดของ notary เอง:
1. ติดตั้ง Python 3.12 แบบ **ทุกผู้ใช้** (ลงที่ `C:\Program Files\Python312`): ใน PowerShell แบบ Administrator พิมพ์
   `winget install --id Python.Python.3.12 -e --scope machine` (หรือโหลดตัวติดตั้งจาก python.org แล้วติ๊ก "Install for all users") ตรวจด้วย `Test-Path "C:\Program Files\Python312\python.exe"` ต้องได้ True
   (ปรับพาธในข้อถัดไปให้ตรงกับเวอร์ชันที่ลง)
2. ```powershell
   & "C:\Program Files\Python312\python.exe" -m venv C:\DelentiaNotary\venv
   C:\DelentiaNotary\venv\Scripts\pip install delentia-os==2.3.0
   icacls C:\DelentiaNotary\venv /grant "delentia-notary:(OI)(CI)RX" /T
   ```
   (`delentia-os` 2.3.0 อยู่บน PyPI แล้ว; venv ต้องสร้างหลังตั้งสิทธิ์ข้อ 2 เพื่อให้ไฟล์ได้สิทธิ์ของ notary)

### 4) สร้างกุญแจของ notary **ในฐานะบัญชี notary** (สำคัญ: ห้ามสร้างด้วย whale)
```powershell
runas /user:%COMPUTERNAME%\delentia-notary "C:\DelentiaNotary\venv\Scripts\delentia.exe notary keygen --out C:\DelentiaNotary\notary_key.pem"
```
ใส่รหัสผ่านที่ตั้งไว้ จะได้ไฟล์กุญแจที่ **เจ้าของคือ delentia-notary** และพิมพ์ public key ออกมา — จด public key นี้ไว้ (ใช้ตรวจ `delentia notary verify --pubkey <hex>`)

### 5) สร้างโทเค็นที่ agent ใช้คุยกับ notary
โทเค็นคือ "รหัสผ่านสำหรับต่อท้าย" ที่ **ทั้งสองฝั่งต้องรู้** (agent ต้องมี) แต่กุญแจเซ็นไม่ต้องให้ agent รู้
```powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$tok = -join ($bytes | ForEach-Object { $_.ToString("x2") })
$tok.Length                                                  # ต้องได้ 64
Set-Content -Path C:\DelentiaNotary\token.txt -Value $tok -NoNewline -Encoding ascii
Set-Content -Path C:\Users\whale\delentia-host\notary_token.txt -Value $tok -NoNewline -Encoding ascii
Remove-Variable tok, bytes
icacls C:\DelentiaNotary\token.txt /inheritance:r /grant "delentia-notary:R" /grant "SYSTEM:F"
```

### 6) ให้ notary รันเองตอนเปิดเครื่อง (Task Scheduler)
```powershell
$cmd = 'set "DELENTIA_NOTARY_TOKEN_FILE=C:\DelentiaNotary\token.txt" && C:\DelentiaNotary\venv\Scripts\delentia.exe notary serve --db C:\DelentiaNotary\notary.db --key C:\DelentiaNotary\notary_key.pem --port 8765'
$act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd" -WorkingDirectory C:\DelentiaNotary
$trg = New-ScheduledTaskTrigger -AtStartup
$cred = Get-Credential -UserName "$env:COMPUTERNAME\delentia-notary" -Message "รหัสผ่านของ delentia-notary"      # หน้าต่างถามรหัสผ่าน: รหัสไม่ปรากฏในคำสั่งหรือประวัติ
Register-ScheduledTask -TaskName "DelentiaNotary" -Action $act -Trigger $trg -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited
Start-ScheduledTask -TaskName "DelentiaNotary"
```
ตรวจ: `Invoke-RestMethod http://127.0.0.1:8765/health` ต้องตอบ ok
(บรรทัด `set "DELENTIA_NOTARY_TOKEN_FILE=..."` คือวิธีส่งโทเค็นให้ notary; โค้ดอ่านได้ทั้ง `DELENTIA_NOTARY_TOKEN` และ `DELENTIA_NOTARY_TOKEN_FILE`)

### 7) ชี้ agent ไปที่ notary
ตั้งใน host (ผ่าน `scripts/local_host.py` หรือ env):
```
DELENTIA_NOTARY_URL=http://127.0.0.1:8765
DELENTIA_NOTARY_TOKEN_FILE=C:\Users\whale\delentia-host\notary_token.txt
```
จากนี้ทุก tool call ถูกบันทึกที่ notary **ก่อน** รัน; ถ้า notary ล่ม episode จะหยุด (`notary_unavailable`) — ตั้งใจให้ fail closed

### 8) พิสูจน์ว่าแยกจริง (อย่าเชื่อ ให้ทดสอบ)
```powershell
# ในเทอร์มินัลปกติของ whale (ไม่ใช่ Admin):
Get-Content C:\DelentiaNotary\notary_key.pem        # ต้องได้ "Access is denied"
delentia notary head --db C:\DelentiaNotary\notary.db   # ก็ต้องอ่านไม่ได้
delentia host-check                                      # ข้อ H05/H06 ควรเลิกเตือนเรื่อง notary
```
ถ้า `Get-Content` อ่านกุญแจได้ → การแยกยังไม่สำเร็จ (ตรวจ `icacls` ข้อ 2 อีกรอบ)

## ข้อจำกัด (พูดตรง ๆ)
- ถ้า agent รันด้วย `whale` ที่เป็น Administrator และยกสิทธิ์ได้ → ผู้โจมตีที่คุมเครื่องก็ผ่านได้; ทางแก้จริงคือรัน agent เป็น **บัญชีผู้ใช้ธรรมดาอีกบัญชี** (เช่น `delentia-agent`)
- A2 ป้องกัน "agent ปลอมประวัติ" ไม่ป้องกัน "คนที่เป็น Administrator ของเครื่อง" → ต้องมี witness ภายนอก (A3) ซึ่งตั้งแล้วที่ `host-1`/`host-notary-1`
- ห้ามอ้างคำว่า tamper-proof; ใช้ "tamper-evident against a compromise of the agent's account" เมื่อทำข้อ 8 ผ่านเท่านั้น
