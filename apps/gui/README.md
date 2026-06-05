# Delentia Desk — Enterprise Visual Control Surface

> **Enterprise Visual Control Surface & Security Monitor** สำหรับระบบปฏิบัติการ **Delentia OS** พัฒนาขึ้นด้วยสถาปัตยกรรม **Tauri v2** ร่วมกับ **Next.js 15** และ **Tailwind CSS** มอบความปลอดภัยระดับสูง ขนาดไฟล์ที่เบาเป็นพิเศษ (3 MB binary) และอินเตอร์เฟสตอบสนองที่สวยงาม ลื่นไหล ตามแนวทางการประมวลผล Intent-centric Constitutional AI

[![Release](https://img.shields.io/github/v/tag/delentia-labs/delentia-gui?label=Release&color=blue)](https://github.com/delentia-labs/delentia-gui/releases)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org)
[![Tauri](https://img.shields.io/badge/Tauri-v2-blueviolet)](https://tauri.app)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Powered by](https://img.shields.io/badge/Powered%20by-Delentia%20OS%20v2.4.1-gold)](https://delentia.com)

---

## 🇹🇭 บทนำ (Introduction)

**Delentia Desk** คือแอปพลิเคชันเดสก์ท็อปอย่างเป็นทางการของ **Delentia OS** ทำหน้าที่เป็นศูนย์ควบคุมภาพ (Visual Control Surface) สำหรับสถาปัตยกรรมปัญญาประดิษฐ์เชิงกติกา (Constitutional AI) ที่เน้นความโปร่งใส ความปลอดภัย และสิทธิ์การลงมติพหุภาคี 

แอปพลิเคชันนี้ทำหน้าที่ประสานงานร่วมกับ **Delentia OS Gateway** (พอร์ต `8000`) เพื่อดึงข้อมูลสถานะแบบ Real-time, ตรวจสอบและย้อนสถานะหน่วยความจำ (Delta Engine Timeline Rollback), รันกระบวนการทำงานอัตโนมัติ (JITNA Workflows) และสนทนาตอบโต้ผ่านโมเดล **HexaCore** ภายใต้การควบคุมสิทธิ์รับประกันความปลอดภัยด้วยสมการคณิตศาสตร์ **FDIA Verification** ($F = D^I \times A$) และตราประทับความสอดคล้องทางความปลอดภัย **SignedAI Consensus**

---

## 📸 ภาพตัวอย่างการใช้งานระบบ (Screenshots & Modules)

ระบบมาพร้อม 9 หน้าเพจและโมดูลการใช้งานหลักที่ออกแบบมาอย่างประณีตและเปี่ยมไปด้วยเอกลักษณ์ทางสถาปัตยกรรมระดับ Enterprise:

### 1. แผงควบคุมระบบหลัก (System Dashboard — `/`)
ศูนย์กลางแสดงสถานะสุขภาพของระบบปฏิบัติการแบบ Real-time รวบรวมข้อมูลผ่าน Gateway API ได้แก่ จำนวนการประมวลผล Intent ที่ผ่านการตรวจสอบความถูกต้องแล้ว, จำนวนไมโครเซอร์วิส (62 บริการ), โมเดล HexaCore (9 โมดูลหลัก) และสถิติความพร้อมใช้งานของระบบ (SLA 99.98%) พร้อมช่องใส่คำสั่งด่วน (Quick Intent Command Bar) เพื่อรันคำสั่งโดยตรงผ่าน AI แกนหลัก
![System Dashboard](./public/screenshots/main-page.png)

### 2. ห้องสนทนาวิเคราะห์เจตนา (Intent Chat — `/chat`)
ห้องสนทนากับเอเจนต์ผ่านการวิเคราะห์เจตนาอย่างครอบคลุม รองรับการตั้งค่าความปลอดภัยระดับหน้าต่างการรัน (Standard, Deep Reasoning, Mirror Execution) ทุกๆ คำตอบของระบบจะมีตราประทับตรวจความสอดคล้องความมั่นคง (SignedAI TIER_4 Badge) และคะแนน FDIA พร้อมรายละเอียดความเกี่ยวข้องของ JITNA Fleet ที่ประมวลผลอยู่เบื้องหลัง
![Intent Chat](./public/screenshots/chat-page.png)

### 3. สายเวลาการทำงานของหน่วยความจำ (Memory Timeline — `/memory`)
ระบบตรวจสอบประวัติการเขียนและจัดระเบียบข้อมูลสิทธิ์ลงมติพหุภาคีผ่าน **Delta Engine** โดยบันทึกการจัดหมวดความสอดคล้องทางสิทธิ์ในรูปแบบ Timeline ประวัติการละเมิดกติกา ผู้ใช้สามารถเลื่อนสไลด์ Scrubber ย้อนเวลาแบบเรียลไทม์ และทำ **Rollback** เพื่อรีเซ็ตสถานะระบบปฏิบัติการย้อนคืนสู่จุดตรวจสอบ (Tick) ที่ต้องการได้อย่างปลอดภัย
![Memory Timeline](./public/screenshots/memory-page.png)

### 4. ทำเนียบโมดูลและการเชื่อมต่อ (Ecosystem Registry — `/ecosystem`)
บอร์ดแสดงสถานะการเชื่อมต่ออะแดปเตอร์และเครื่องมือปลั๊กอินเสริมของระบบ เช่น Qdrant Vector Database, arXiv Connector, API Gateway หรือ Typhoon-v2 เชื่อมโยงสิทธิ์การใช้งานผ่าน Unified Security Policy เพื่อเสริมขีดความสามารถการใช้งาน Dynamic Skills ของเอเจนต์
![Ecosystem Registry](./public/screenshots/ecosystem-page.png)

### 5. ระบบจัดการและดาวน์โหลดโมเดลภาษาภายใน (Local SLM Models — `/models`)
แดชบอร์ดจัดการและดาวน์โหลดโมเดลภาษาขนาดเล็ก (Small Language Models - SLM) ผ่าน Ollama Adapter โดยระบุรายละเอียดโมเดล เช่น `typhoon-v2-7b`, `llama3-8b` หรือ `delentia-slm-jitna` พร้อมแสดงสถานะการเชื่อมต่อเครือข่ายออฟไลน์/ออนไลน์ และขั้นตอนการติดตั้งโมเดลไว้ประมวลผลแบบ Edge Compute ภายในเครือข่ายปลอดภัย
![Local SLM Models](./public/screenshots/models-page.png)

### 6. เครื่องมือสร้างและจำลองเอเจนต์ (JITNA Workflows — `/workflow`)
ผืนผ้าใบอินเตอร์เฟสจำลอง (Visual Workflow Builder - Alpha Version) สำหรับออกแบบโครงข่ายเอเจนต์ประสานงาน (JITNA Multi-Agent Fleet) โดยเชื่อมโยงโหนดประเภทต่างๆ เช่น Triggers, Webhooks, LLMs, Memory Read/Write, และ FDIA Security Filters พร้อมระบบแสดงผลข้อบกพร่องระหว่างขั้นตอนประมวลผลจำลอง
![JITNA Workflows](./public/screenshots/workflow-page.png)

### 7. แดชบอร์ดตรวจสอบมิติความปลอดภัย (System Monitor — `/monitor`)
แผงติดตามและวิเคราะห์ความปลอดภัยและการตอบสนองของเครือข่าย ประกอบด้วยกราฟวิเคราะห์พิกัดความสอดคล้อง (Model Drift), ประวัติคะแนนเฉลี่ย FDIA Safety Score, อัตรา Latency รายไมโครเซอร์วิส และรายงานประวัติการเชื่อมโยงข้อมูล RAG ที่ผิดปกติเพื่อป้องกันภัยคุกคามสิทธิ์ป้อนกลับเชิงลบ (Negative Feedback Attestation)
![System Monitor](./public/screenshots/monitor-page.png)

### 8. ศูนย์ข้อมูลวิจัยและการค้นพบ (Research Discovery — `/discovery`)
อินเตอร์เฟสสืบค้นและดึงเอกสารงานวิจัยวิชาการปัญญาประดิษฐ์ผ่านคลัง arXiv โดยตรง มาพร้อมการประเมินคะแนนความเข้ากันได้ของการเรียนรู้เชิงลึกแบบกติกา (Constitutional AI Alignment Score) และการดึงข้อมูลเพื่อใช้อ้างอิงการจัดลำดับชั้นข้อมูลสิทธิ์ของ SignedAI
![Research Discovery](./public/screenshots/discovery-page.png)

### 9. การตั้งค่าระบบเชื่อมต่อ (Settings — `/settings`)
หน้าควบคุมพารามิเตอร์การทำงานหลักของตัวแอปพลิเคชัน ได้แก่ การปรับเปลี่ยนการแสดงผล (สลับ Dark/Light mode และเปลี่ยนชุดธีมระบบ 27 รูปแบบ), ตั้งค่าที่อยู่เครือข่ายเซิร์ฟเวอร์ (Gateway URL และ API Key), บันทึกสิทธิ์การจำแนกประเภทบทบาทเอเจนต์ และตารางค่าบริการคลาวด์เปรียบเทียบความคุ้มค่า
![Settings](./public/screenshots/settings-page.png)

---

## ⚙️ คุณสมบัติเด่นของระบบ (Key Features)

1. **Enterprise Theme Engine:**
    - สลับชุดธีมแสดงผลระดับองค์กรได้ถึง 27 ธีม (เช่น PowerShell ISE, solarized, quiet light, abyss, monokai, tokyo-night)
    - ระบบป้องกันการกระพริบของสไตล์ (Style flashing protection) ด้วย `ThemeProvider` และ `suppressHydrationWarning` ที่มีประสิทธิภาพสูงสุด
2. **Delta Engine Memory Management:**
    - ค้นหา กรอง และตรวจสอบ Timeline เหตุการณ์เชิงสิทธิ์ของระบบ
    - สั่งการ **Memory State Rollback** ผ่านปุ่มอินเตอร์เฟสพร้อมระบบยืนยันความปลอดภัยระดับ Kernel
3. **Intent Execution & Control:**
    - กล่องป้อนข้อมูล Auto-growing Textarea ในการป้อนคำถามประมวลผล
    - ความสอดคล้องกับ **Ollama & Local SLM Adapter** สำหรับการทำงานประมวลผลออฟไลน์ที่สมบูรณ์แบบ
4. **Visual Security Monitoring:**
    - วิเคราะห์สถิติความปลอดภัยด้วยแผนภูมิเรขาคณิต (Recharts) ครบครัน
    - รายงานสถานะพอร์ตและ API เครือข่ายแบบ Real-time ตลอด 24 ชั่วโมง

---

## 🛠️ สถาปัตยกรรมระดับระบบ (System Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                      Delentia Desk (Tauri v2)               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Next.js 15 (Static HTML Export) — src/app/         │    │
│  │  ├── 9 Routes (Dashboard, Chat, Memory, Ecosystem, │    │
│  │  │   Models, Workflows, Monitors, Discovery, Settings)│    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ Tauri IPC & Commands              │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │  Rust Backend (src-tauri/)                           │    │
│  │  ├── execute_intent()     → POST /v1/kernel/execute │    │
│  │  ├── get_system_stats()   → GET  /delentia/system/stats│ │
│  │  ├── health_check()       → GET  /health             │    │
│  │  └── get_memory_history() → GET  /v1/memory/history │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ reqwest (HTTPS/WSS)               │
└─────────────────────────┼───────────────────────────────────┘
                          ▼
          Delentia OS Gateway  (localhost:8000)
          ├── RCT v5 — 9 HexaCore models
          ├── FDIA scoring engine
          ├── JITNA v3 packet routing
          └── Delta Engine (memory timeline)
```

---

## 🚀 การเริ่มต้นใช้งานด่วน (Quick Start)

### 1. เครื่องมือที่จำเป็น (Prerequisites)

| เครื่องมือ (Tool) | เวอร์ชันที่ต้องการ | หมายเหตุ |
|---|---|---|
| **Node.js** | $\ge 20$ | ใช้บริหารจัดการ Next.js frontend |
| **Rust** | Stable Channel | ใช้ในการคอมไพล์ Tauri Rust backend |
| **Tauri CLI v2** | ล่าสุด | ติดตั้งมาพร้อมในโปรเจกต์ `devDependencies` |

#### ความต้องการเพิ่มเติมรายระบบปฏิบัติการ
* **Windows:** WebView2 Runtime (มาพร้อมกับ Windows 11 เป็นค่าเริ่มต้น)
* **Linux:** ติดตั้งไลบรารีระบบ:
  ```bash
  sudo apt-get update
  sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev
  ```

### 2. การเปิดใช้งานโหมดนักพัฒนา (Development)

```bash
# 1. Clone รีโปนี้
git clone https://github.com/delentia-labs/delentia-gui
cd delentia-gui

# 2. คัดลอกและสร้างการตั้งค่าจำลองสภาพแวดล้อม
cp .env.example .env.local

# 3. ติดตั้ง Dependencies ทั้งหมด
npm install

# 4. เริ่มระบบทำงานจำลองในโหมดพัฒนา (Tauri + Next.js Hot Reload)
npm run tauri:dev
```
*ตัวระบบแอปพลิเคชันจะเปิดหน้าต่างเดสก์ท็อปขึ้นมา และเชื่อมต่อกับ Gateway Simulation อัตโนมัติ*

### 3. การตรวจสอบสิทธิ์ประมวลผลและการรันเว็บเซิร์ฟเวอร์
หากต้องการเปิดและทดสอบเฉพาะส่วนเว็บแอปพลิเคชัน (Next.js เท่านั้น) โดยไม่เปิด Tauri window:
```bash
npm run dev
```
บราวเซอร์จะเริ่มทำงานที่พอร์ต **`http://localhost:3000`**

### 4. การทดสอบความสอดคล้องของโค้ด (Validation)
```bash
# ทดสอบ TypeScript Type Check
npm run type-check

# ตรวจสอบ Lint ด้วย ESLint
npm run lint
```

### 5. การคอมไพล์เพื่อผลิตใช้งาน (Build)
```bash
# คอมไพล์โปรแกรมสำหรับ OS ที่กำลังใช้งาน
npm run tauri:build
```
ผลลัพธ์ตัวติดตั้งของแต่ละระบบจะถูกสร้างไว้ที่โฟลเดอร์: `src-tauri/target/release/bundle/`
* **Windows:** ไฟล์ `.msi` และ `.exe`
* **macOS:** ไฟล์ `.dmg` และ `.app`
* **Linux:** ไฟล์ `.AppImage` และ `.deb`

---

## ⚖️ เปรียบเทียบสถาปัตยกรรม (Architecture Comparison)

| หัวข้อการประเมิน (Assessment Dimension) | Electron GUI (ดั้งเดิม) | Delentia Desk (Tauri v2) |
| :--- | :---: | :---: |
| **ขนาดของตัวติดตั้ง (Installer Size)** | ~150 MB | **~3.2 MB (ลดลง 97.8%)** |
| **การใช้หน่วยความจำ (RAM Idle)** | ~250 MB | **~42 MB (ลดลง 83.2%)** |
| **ความมั่นคงปลอดภัย (Security)** | รันสิทธิ์ Node.js บนเครื่อง | **Isolated Sandbox, Rust IPC, CSP enforced** |
| **ความเร็วในการบู๊ต (Cold Start Time)** | ~2.5 วินาที | **< 300 มิลลิวินาที** |
| **ความเข้ากันได้ออฟไลน์ (Offline Mode)** | มี (ผ่าน Local Ollama Adapter) | **มี (ผ่าน Local Ollama Adapter)** |

---

## 📜 สิทธิการใช้งาน (License)

ซอร์สโค้ดนี้เผยแพร่ภายใต้สิทธิการใช้งาน **Apache License 2.0** — พัฒนาโดย © 2026 Delentia Labs  
สามารถอ่านรายละเอียดเพิ่มเติมได้ที่ไฟล์ [LICENSE](LICENSE)
