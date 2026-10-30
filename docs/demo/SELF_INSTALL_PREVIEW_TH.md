# Delentia แบบติดตั้งใช้เอง: เส้นทางทดลองรุ่นถัดไป

คู่มือนี้ประกอบงาน local-first ที่ยังอยู่ใน PR คำอธิบาย doctor/data-home ใหม่ใช้กับ wheel จาก branch นี้และ release ที่รวมการเปลี่ยนแปลงแล้ว ไม่รับรองว่ามีใน PyPI release ปัจจุบันทุกข้อ

Delentia เป็น open-source experimental agent runtime ที่ติดตั้งบนเครื่องหรือ VPS ของคุณเอง ไม่ต้องมี account หรือ host กลางของ Delentia คุณเลือกโมเดลเอง: Ollama บนเครื่อง หรือ API provider โดยใช้ key/งบของคุณ หากเลือก cloud model ข้อมูลใน prompts จะไป provider นั้น คำว่า local installation ไม่ได้แปลว่าทุก model call อยู่ในเครื่อง

## เริ่มโดยไม่ใช้โมเดลหรือเสียเงิน

ใช้ Python 3.10 ขึ้นไปและ venv ตาม OS ของคุณ ติดตั้ง release ที่เลือกหรือ wheel ที่ผู้ดูแลให้ตรวจ:

```bash
python -m pip install delentia-os
# สำหรับตรวจ wheel ก่อน release ใช้แทนบรรทัดข้างบน:
# python -m pip install /path/to/delentia_os-VERSION-py3-none-any.whl

delentia --version
delentia doctor --output json
delentia demo init --dir ./delentia-first-demo
delentia demo run compare --scripted --dir ./delentia-first-demo
delentia demo status --dir ./delentia-first-demo
```

`--scripted` แทนโมเดลด้วยโปรแกรมที่กำหนดไว้ Files/tools/governance/audit ยังคงทำงานจริง ผลนี้แสดงกลไก ไม่ใช่ความสามารถของโมเดล ใช้โฟลเดอร์ demo ใหม่เมื่ออยากเริ่มสะอาด เพราะ init ไม่ overwrite งานเดิม

doctor รุ่นใหม่นี้ตรวจ Python/core dependencies โดยไม่กำหนดว่าต้องมี repo หรือ API เปิดอยู่ `ok=true` ไม่รับรอง model, billing หรือความถูกต้องของทุก task; exit 1 หมายถึงพบปัญหาใน checks ที่เลือก ผู้พัฒนา source ใช้ `delentia doctor --development` เพื่อตรวจ source files และ development ports เพิ่ม

## เลือก model และ data directory ของคุณ

```bash
delentia setup --dry-run
# เมื่อพร้อมให้ setup ทำตามแผน:
delentia setup
delentia model show
```

setup แสดงแผนและถามก่อน apply ไม่ download โมเดลหรือเริ่ม generation ให้เอง ถ้าไม่มีโมเดลพร้อม scripted demo ยังใช้ดูระบบได้ ก่อนส่งงานจริงตั้ง spending cap ที่ provider และตรวจ runtime limits อย่าเปิด paid fallback โดยไม่ตั้งใจ

ข้อมูลปกติอยู่ `~/.delentia` (`%USERPROFILE%\.delentia` บน Windows) หากต้องการเปลี่ยน ให้ตั้ง `DELENTIA_HOME` ใน environment ของทุก terminal/service ที่รันโปรแกรม `--home` ของ setup เพียงคำสั่งเดียวไม่เปลี่ยน environment ของ server อีกหน้าต่าง

`DELENTIA_MODEL_CONFIG` ที่ตั้งไว้มีลำดับสูงกว่า home ใหม่ หากอัปเกรดจากรุ่นเก่าที่ใช้ custom data home แต่ model config ยังอยู่ path เดิม ให้ตั้งตัวแปรนี้ชี้ไฟล์เดิมก่อน หรือตรวจและย้าย config อย่างตั้งใจ ห้ามสรุปว่าทุก key/config/backup ย้ายตาม DELENTIA_HOME อัตโนมัติ

API keys อยู่ใน environment/secret mechanism ของคุณ ไม่ใส่ใน repository, demo folder, screenshots, feedback หรือวิดีโอ

## เปิด Desk บนเครื่องตนเอง

Terminal แรก:

```bash
delentia serve --host 127.0.0.1 --port 8000
```

Terminal ที่สอง:

```bash
delentia desk --gateway http://127.0.0.1:8000 --port 3010
```

ใช้ URL ที่คำสั่งแสดง แพ็กเกจ release ต้องมี Desk assets; source checkout ต้อง build/package Desk ก่อน หากยังไม่มี model อย่าตีความว่าหน้าเปิดได้แปลว่า chat/task ใช้โมเดลสำเร็จแล้ว

## ใช้ VPS ของตนโดยไม่เปิด API สาธารณะ

ติดตั้งและรันสองคำสั่งข้างบนบน VPS โดยเพิ่ม `--no-browser` ให้ desk จากเครื่องที่ใช้ browser เปิด SSH tunnel:

```bash
ssh -N -L 8000:127.0.0.1:8000 -L 3010:127.0.0.1:3010 YOUR_USER@YOUR_VPS
```

เปิด `http://localhost:3010` บนเครื่องคุณ ใช้ ports/gateway ให้ตรงกับที่ตั้งและไม่มีโปรแกรมอื่นใช้ หากรัน server/Desk บนเครื่องต่างกัน อย่าส่งต่อหรือเผยแพร่ token/bootstrap information จาก URL/log การเปิดพอร์ต public หรือเพิ่มคนใช้ร่วมกันเป็น deployment อีกแบบ ต้องตั้ง authentication/TLS/สิทธิ์และตรวจความปลอดภัยสำหรับแบบนั้น

SSH/VPS เป็นแนวทาง configuration คู่มือนี้ไม่ได้อ้างว่ารอบ cloud ได้ทดสอบ native VPS ทุก OS หรือ browser passkey ข้าม tunnel แล้ว

## Update, rollback และ uninstall

จด version/model config/data directory ก่อนเปลี่ยนรุ่น หยุด processes ของ Delentia แล้ว backup data รวม keys ที่จำเป็น เก็บ backup เป็นความลับ เลือก version ที่จะ upgrade/rollback อย่างชัดเจน อย่า rollback ข้าม schema โดยยังไม่อ่าน release notes

การถอน package ด้วย `python -m pip uninstall delentia-os` ไม่ควรลบข้อมูลนอก package; Windows ใช้ uninstaller ของ release นั้น ตรวจ data directory ก่อน/หลัง อย่าลบ data directory เว้นแต่ต้องการลบข้อมูลเอง old backups อาจยังมีข้อมูลก่อน erasure

ผลที่ทดสอบในรอบนี้และขอบเขต native OS ดู [แผน local-first](../development/LOCAL_FIRST_RELEASE_ALIGNMENT_2026-10-30_TH.md) ปัญหาที่ส่งให้โครงการควรมี OS/version/command/error ที่ตัด secrets ออกแล้ว
