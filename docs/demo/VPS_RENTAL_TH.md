# คู่มือ: เช่า VPS เล็กหนึ่งเครื่องเพื่อรันทดสอบ 72 ชั่วโมง / 7 วัน (ยังไม่ต้องเปิดให้คนนอกใช้)

สำหรับเจ้าของระบบ (Architect) **ยังไม่ต้องทำตอนนี้**: ลำดับที่ถูกคือ (1) มีโมเดลที่ขับ agent ได้จริงรันงานสำเร็จบนเครื่องนี้ก่อน (2) notary + พยานภายนอกทำงานต่อเนื่องบนเครื่องนี้ (`WITNESS_SETUP_TH.md`) (3) แล้วจึงเช่า VPS เพื่อทดสอบว่าระบบอยู่ได้เองหลายวันโดยไม่มีคนแตะ และบนเครื่องที่ไม่ใช่โน้ตบุ๊กของคุณ

**สิ่งที่คู่มือนี้ยังไม่เคยถูกทดสอบจริง:** ชุด `deploy/host/` เคยรันจริงบน Docker Desktop (Windows) เท่านั้น ยังไม่เคยรันบน Linux VPS ใด ๆ ผมคาดว่า "รันครั้งแรกบน Linux จะเจอข้อบกพร่องที่เก้า" (ตามที่เขียนไว้ใน `HOST_RUNBOOK.md`) ถ้าเจอ ส่งข้อความผิดพลาดทั้งหมดมาให้ผมแก้ อย่าแก้เอง

## 1. เลือกอะไร และราคา

| รายการ | ข้อแนะนำ | เหตุผล |
|---|---|---|
| สเปก | 2 vCPU, 4 GB RAM, ดิสก์ 40 GB ขึ้นไป | วัดแล้ว: runtime ใช้ ~470-780 MB + notary + Docker; 2 GB ไม่พอ, 8 GB เกินจำเป็น (ถ้าโมเดลอยู่ที่ผู้ให้บริการภายนอก เช่น OpenRouter; **ห้ามรันโมเดลในเครื่องบน VPS เล็ก**) |
| สถาปัตยกรรม | **x86 (amd64)** ไม่ใช่ Arm | ชุดนี้เคยรันบน x86 เท่านั้น; Arm ต้อง build image บนเครื่อง Arm เอง จึงเพิ่มความเสี่ยงโดยไม่จำเป็นในรอบแรก |
| ระบบปฏิบัติการ | Ubuntu 24.04 LTS (หรือ 22.04) | สคริปต์ติดตั้ง `ubuntu_arm_setup.sh` เขียนสำหรับ Ubuntu |
| ราคา | ประมาณ 4-7 ยูโรต่อเดือน จ่ายรายเดือน **ไม่ผูกปี** | แหล่งข้อมูลบุคคลที่สามบอกราคาไม่ตรงกัน (เช่น Hetzner CX22/CX23 ราว €3.49-5.49 หลังปรับราคาปี 2569) **ดูราคาปัจจุบันที่หน้าเว็บของผู้ให้บริการเอง** ผมตรวจให้ไม่ได้ |
| ผู้ให้บริการ | เจ้าที่คุณไว้ใจและจ่ายด้วยบัตรเติมวงเงินต่ำได้ | Hetzner/DigitalOcean/Vultr ล้วนใช้ได้; Oracle Free ไม่แนะนำสำหรับรอบแรก (ที่นั่งเต็มบ่อย และมีกฎ reclaim เครื่องที่ว่าง) |
| โดเมน | **ยังไม่ต้อง** | ใช้ SSH tunnel เข้าหน้าควบคุม ไม่เปิดพอร์ตสาธารณะ (ดู `HOST_RUNBOOK.md` หัวข้อ 1c) |

เพดานเงินที่แนะนำ: VPS ไม่เกิน ~€7 ต่อเดือน + OpenRouter ที่ตั้งเพดานเครดิตต่อคีย์ (ดู `OPENROUTER_KEY_AND_CAP_TH.md`) ต้นทุน VPS ของการทดสอบ 7 วัน: ถ้าผู้ให้บริการคิดรายชั่วโมงจะราว €1-2 (สัดส่วนของราคารายเดือน) ถ้าคิดรายเดือนเต็มราว €4-7 **ตรวจเงื่อนไขการคิดเงินก่อนกดสร้าง** (ตัวเลขนี้เป็นการคำนวณของผม ไม่ใช่ราคาที่ผมเห็นจากผู้ให้บริการ) บวกเงินโมเดลตามเพดานที่ตั้ง

## 2. สร้างกุญแจ SSH บนเครื่องคุณ (ทำครั้งเดียว)

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\delentia_vps -C "delentia-vps"
```
ตั้งรหัสผ่านให้ไฟล์กุญแจ (passphrase) เมื่อถูกถาม; จะได้ไฟล์ `delentia_vps` (ลับ **ห้ามส่งให้ใคร**) และ `delentia_vps.pub` (เปิดเผยได้; อัปโหลดให้ผู้ให้บริการ)
```powershell
Get-Content $env:USERPROFILE\.ssh\delentia_vps.pub
```
คัดลอกบรรทัดนี้ไปวางในหน้า "SSH keys" ของผู้ให้บริการตอนสร้างเครื่อง

## 3. สร้างเครื่อง

1. เลือก Ubuntu 24.04, สเปกข้อ 1, เลือกกุญแจ SSH ที่เพิ่งอัปโหลด, **ไม่เลือก** "root password"
2. สร้าง Firewall ที่ผู้ให้บริการ: อนุญาตเฉพาะพอร์ต 22 ขาเข้า (จำกัดเฉพาะ IP บ้านคุณถ้าเป็น IP คงที่) ไม่เปิด 80/443 (ยังไม่ใช้)
3. จดที่อยู่ IP ของเครื่อง

## 4. เข้าเครื่อง ติดตั้ง Docker (สคริปต์ของเราอ่านก่อนรัน)

```powershell
ssh -i $env:USERPROFILE\.ssh\delentia_vps root@<IP>
```
ผู้ให้บริการส่วนใหญ่ให้เข้าด้วย `root` ในครั้งแรก ให้สร้างผู้ใช้ธรรมดาแล้วใช้แทน (สคริปต์ปฏิเสธการรันเป็น root โดยตั้งใจ):
```bash
adduser --disabled-password --gecos "" delentia
usermod -aG sudo delentia
echo "delentia ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/delentia
mkdir -p /home/delentia/.ssh && cp ~/.ssh/authorized_keys /home/delentia/.ssh/ && chown -R delentia:delentia /home/delentia/.ssh && chmod 700 /home/delentia/.ssh
exit
```
แล้วเข้าใหม่เป็นผู้ใช้ `delentia`:
```powershell
ssh -i $env:USERPROFILE\.ssh\delentia_vps delentia@<IP>
```
บนเครื่อง VPS:
```bash
curl -fsSLO https://raw.githubusercontent.com/delentia-labs/Delentia-OS/main/deploy/host/ubuntu_arm_setup.sh
less ubuntu_arm_setup.sh          # อ่านให้ครบ (q เพื่อออก): ติดตั้ง docker, compose, git, อัปเดตความปลอดภัยอัตโนมัติ, swap 2 GB; ไม่เปิดพอร์ต ไม่สร้างความลับ
bash ubuntu_arm_setup.sh
exit                               # ออกแล้วเข้าใหม่เพื่อให้กลุ่ม docker มีผล
```

## 5. ดึงโค้ด ตั้งค่า เริ่มระบบ (ไม่เปิดพอร์ตสาธารณะ)

```bash
git clone https://github.com/delentia-labs/Delentia-OS && cd Delentia-OS/deploy/host
echo 'DELENTIA_DOMAIN=unused.invalid' > .env
docker compose -f docker-compose.yml -f docker-compose.private.yml build      # ครั้งแรกช้า (หลายนาที ถึงสิบกว่านาที)
./bootstrap.sh alice                                                          # สร้างกุญแจ + โทเค็นของ alice: โทเค็นขึ้น ONCE จดไว้ในที่ลับ
docker compose -f docker-compose.yml -f docker-compose.private.yml up -d
docker compose -f docker-compose.yml -f docker-compose.private.yml ps         # delentia ต้อง healthy ภายในประมาณ 90 วินาที
docker compose -f docker-compose.yml -f docker-compose.private.yml exec delentia delentia host-check
```
`host-check` ต้อง **ไม่มี FAIL** (WARN ตอนเริ่มเป็นเรื่องปกติ: ยังไม่มี approver/นโยบาย/สมอ ตามที่ `HOST_RUNBOOK.md` หัวข้อ 3 อธิบายไว้ทีละข้อ)

เข้าหน้าควบคุมจากเครื่องคุณผ่านอุโมงค์ (พอร์ตไม่เปิดสู่อินเทอร์เน็ต):
```powershell
ssh -i $env:USERPROFILE\.ssh\delentia_vps -N -L 8000:127.0.0.1:8000 delentia@<IP>
```
(ปล่อยหน้าต่างนี้ค้างไว้) แล้วเปิด `http://127.0.0.1:8000` ด้วยโทเค็นของ alice (ใช้พอร์ต 8000 ซึ่ง **ชนกับ host ในเครื่องคุณ** ถ้ามันรันอยู่: ใช้ `-L 8001:127.0.0.1:8000` แทนแล้วเข้า `:8001`)

## 6. ใส่โมเดล (ความลับ: คุณพิมพ์เอง)

1. เพดานเงินที่ผู้ให้บริการโมเดลก่อน (OpenRouter คีย์ใหม่ + Credit limit; `OPENROUTER_KEY_AND_CAP_TH.md`)
2. บน VPS: `nano ~/Delentia-OS/deploy/host/secrets/runtime.env` ใส่บรรทัดเดียว `OPENROUTER_API_KEY=<คีย์>` (พิมพ์เอง ห้ามส่งผ่านแชต) `chmod 600` ไฟล์นี้
3. ตั้งโมเดลและเพดานต่อตอน (`EPISODE_BUDGET_USD`, `EPISODE_MAX_TOKENS` ใน `.env`) ตาม `HOST_RUNBOOK.md` หัวข้อ 3.4 แล้ว `docker compose ... up -d` ใหม่

## 7. ตั้งพยานภายนอกบน VPS (ต้องทำก่อนเริ่มนับชั่วโมง)

ทำตาม `HOST_RUNBOOK.md` หัวข้อ 3.5 (พิมพ์รายการคีย์ → ลงทะเบียนที่ Worker → ตั้งค่า → ตรวจ) และเพิ่มพยานแบบประทับเวลา RFC 3161 ตาม `WITNESS_SETUP_TH.md` ข้อ 4 โดยเรียกจาก notary ใน container: ใช้ `--timestamp-url http://timestamp.digicert.com --timestamp-dir /notary/timestamps` ที่ `notary serve` (แก้ที่ `docker-compose.yml` บรรทัด command ของ service notary) การลงทะเบียนคีย์ที่ Worker ต้อง deploy Worker ซึ่ง **คุณสั่งเอง**

## 8. เริ่มทดสอบ และสิ่งที่ต้องดู

**ทดสอบ 1 ชั่วโมงก่อน (smoke):**
```bash
for i in $(seq 1 60); do echo "$(date -u +%FT%TZ) $(curl -s -m 10 -o /dev/null -w '%{http_code} %{time_total}s' http://127.0.0.1:8000/health) $(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | tr '\n' ' ')"; sleep 60; done | tee ~/soak_1h.txt
```
เกณฑ์ผ่านที่ผมตั้งไว้ล่วงหน้า: `/health` ตอบ 200 ทุกนาที, ความจำของ container ไม่ไต่ขึ้นเกิน ~100 MB จากต้นชั่วโมง, ไม่มี container restart (`docker compose ps` แสดง uptime ตั้งแต่เริ่ม)

**แล้ว 8-12 ชั่วโมง → 72 ชั่วโมง → 7 วัน** (เพิ่มทีละขั้น ถ้าขั้นก่อนไม่ผ่านอย่าไปต่อ) ระหว่างนั้นให้ใช้งานจริงเบา ๆ วันละสองสามงาน (ผ่านหน้า Chat) ให้ระบบมีบันทึกให้พิสูจน์ แล้วเมื่อจบ:
```bash
docker compose -f docker-compose.yml -f docker-compose.private.yml exec delentia delentia host-check
docker compose -f docker-compose.yml -f docker-compose.private.yml exec delentia delentia audit-chain verify --db /data/agentic.db
docker compose -f docker-compose.yml -f docker-compose.private.yml exec delentia delentia audit-chain witness-status
```
(คำสั่งบน notary ต้องรันในฐานะ uid ของมัน ดู `HOST_RUNBOOK.md` หัวข้อ 6)

## 9. ความปลอดภัยที่ต้องคงไว้ตลอด

- SSH ด้วยกุญแจเท่านั้น; อย่าเปิด 80/443 หรือ 8000 สู่อินเทอร์เน็ตจนกว่าจะมีเหตุผล (และเมื่อเปิด ต้องมี `DELENTIA_API_TOKEN` + โดเมน + Caddy ตาม `HOST_RUNBOOK.md`)
- คีย์ approver (ลายเซ็นอนุมัติ) สร้างบนอุปกรณ์ของคุณเอง **ห้ามสร้างบน VPS** (`HOST_RUNBOOK.md` หัวข้อ 0 ข้อ 4)
- ห้ามนำข้อมูลจริงของลูกค้าหรือใครก็ตามมาใส่ในช่วงทดสอบ; ผู้ใช้ภายนอกคนแรกต้องผ่านข้อตกลงก่อน (ดู `PILOT_ONE_WORKFLOW_TH.md`)
- ปิดเครื่อง/ลบเมื่อไม่ใช้: สำรองข้อมูลก่อน (ข้อมูลบน volume: `HOST_RUNBOOK.md` หัวข้อ 6) ค่าบริการนับตามเวลาที่เครื่องอยู่ แม้ปิดเครื่องก็ยังคิดเงิน ต้อง "ลบเครื่อง" ที่หน้าผู้ให้บริการเมื่อเลิกใช้

## 10. สิ่งที่ผมทำให้ได้ และสิ่งที่ผมทำให้ไม่ได้

ทำให้ได้: อ่านข้อความผิดพลาดที่คุณส่งมาแล้วแก้ชุด `deploy/host/`, ปรับคู่มือนี้ให้ตรงกับสิ่งที่เกิดจริง, วิเคราะห์ไฟล์ผลการทดสอบ (soak) ที่คุณคัดลอกกลับมา
ทำให้ไม่ได้: สร้างบัญชีผู้ให้บริการ จ่ายเงิน เข้า VPS แทนคุณ ถือคีย์ SSH/โทเค็น/คีย์โมเดล หรือ deploy Worker
