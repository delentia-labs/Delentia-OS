# CLI Review Playbook

ไฟล์นี้ใช้สำหรับตรวจ `rct` CLI surface หลังงานด้าน DX, header, splash, boot sequence, และ runtime dashboard

ตอนนี้เอกสารนี้ทำหน้าที่เป็นทั้ง review checklist และ visual doctrine แบบย่อสำหรับ RCT OS CLI

## 1. Quick review path

จากโฟลเดอร์ `delentia-os`

```bash
.venv_ci_check\Scripts\rct.exe version
.venv_ci_check\Scripts\rct.exe start --ui-test
```

ถ้าต้องการดู runtime จริงที่ค้างอยู่:

```bash
.venv_ci_check\Scripts\rct.exe start --host 127.0.0.1 --port 8123
```

ถ้าต้องการตรวจว่า dashboard เปลี่ยนจาก pre-bind ไป post-bind จริง:

```bash
.venv_ci_check\Scripts\rct.exe start --host 127.0.0.1 --port 8000
```

Reviewer ต้องเห็น launch surface ช่วงแรกเป็น `STARTING` / `LAUNCHING` ก่อน แล้วมี runtime snapshot ใหม่หลัง bind สำเร็จ

## 2. สิ่งที่ reviewer ต้องดู

### Header
- version ต้องตรงกับ runtime จริง
- mode ต้องตรงกับ `--ui-test` หรือ live start
- endpoint ต้องสะท้อน host/port จริง
- wording ต้องไม่ทำให้ public SDK proof ปนกับ enterprise snapshot
- wide tier ต้องให้ brand stack เป็น first frame จริง ไม่ใช่โดน panel ห่อจนกลายเป็น generic Rich UI
- compact tier ต้องยังอ่านออกว่าเป็น RCT ทันที แม้ไม่มีสีและพื้นที่แคบ

### Visual doctrine
- เฟรมแรกต้องเป็น brand surface ก่อน runtime detail
- proof lanes ต้องใช้ถ้อยคำคงที่: public SDK proof, enterprise runtime footprint, benchmark scope
- splash ต้องไม่พูดเหมือนระบบ online แล้ว ถ้ายังไม่ bind พอร์ตจริง
- dashboard หลัง bind ต้องดูเป็นเฟรมที่สองของแบรนด์เดียวกัน ไม่ใช่คนละระบบ

### Layout
- wide terminal: glyph + wordmark + runtime rail ต้องอ่านง่าย
- narrow terminal: ต้อง degrade เป็น compact panel โดยไม่แตกบรรทัดจนอ่านไม่รู้เรื่อง
- non-TTY / redirected output: ต้องเหลือข้อความที่ยังตีความได้

### Boot sequence
- ลำดับ service ต้องสื่อสถานะ launch อย่างสม่ำเสมอ
- UI test mode ต้องไม่ทำให้เข้าใจว่าเป็น health proof ของ production
- dashboard หลัง splash ต้องใช้ภาษาออกแบบเดียวกัน

### Runtime truth pass
- ก่อน bind ต้องเห็น `Launch sequence prepared — awaiting API bind`
- หลัง bind ต้องมี runtime snapshot ใหม่ที่ไม่ค้าง `LAUNCHING`
- ถ้า health endpoint ยังไม่ตอบ แต่พอร์ตเปิดแล้ว ต้องแสดง `health-unknown` หรือ `port-probe` อย่าง truthful
- ถ้า server ใช้งานจริงได้ ต้องไม่ใช้ข้อความแบบ marketing success ที่ข้ามสถานะกลาง

## 3. Automation gate

```bash
.venv_ci_check\Scripts\python.exe -m pytest rct_control_plane/tests/test_formatters_dsl.py rct_control_plane/tests/test_cli_coverage_gaps.py
.venv_ci_check\Scripts\python.exe -m pytest rct_control_plane/tests/test_cli_api.py -k "start or version or doctor"
```

## 4. ผ่านเมื่อไร

ถือว่าผ่านเมื่อ:
- wide / narrow / ui-test path อ่านได้ชัด
- runtime context ถูกส่งเข้า header ครบ
- live bind path refresh dashboard หลัง server start จริง
- tests ผ่าน
- ไม่มี regression ที่ทำให้ start path ใช้งานจริงไม่ได้บน Windows terminal