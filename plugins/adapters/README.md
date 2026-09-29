# Delentia Ecosystem Registry

[![Validate Adapters](https://img.shields.io/github/actions/workflow/status/delentia-labs/delentia-ecosystem/validate-adapter.yml?branch=main&label=Manifest+CI)](https://github.com/delentia-labs/delentia-ecosystem/actions)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Registry](https://img.shields.io/badge/Registry-v1.0.0-brightgreen)](https://github.com/delentia-labs/Delentia-Ecosystem/releases)

<p align="center">
  <a href="#-english">🇺🇸 English Description</a> •
  <a href="#-ภาษาไทย">🇹🇭 คำอธิบายภาษาไทย</a>
</p>

---

## 🇺🇸 English

**Delentia Ecosystem** is the plugin and skill registry for [Delentia OS](https://github.com/delentia-labs/Delentia-OS). It handles the manifests for external connection adapters (LINE, Slack, etc.) and specialized skills (PDPA Compliance, Thai NLP, Document Intelligence, etc.) routing through the JITNA v3 protocol.

---

### 🏗️ Architecture
```
Delentia-Ecosystem/
├── schema/
│   └── adapter-manifest.schema.json   ← JSON Schema v7 (source of truth)
├── registry/
│   ├── adapters/
│   │   ├── line-adapter/
│   │   │   ├── manifest.json          ← Validated against schema
│   │   │   └── index.ts               ← Adapter implementation
│   │   └── slack-adapter/
│   └── skills/
│       ├── thai-language/
│       └── legal-pdpa/
├── api/
│   ├── registry_api.py                ← FastAPI registry server (port 8090)
│   └── validation.py                  ← JSON Schema validation
```

---

### 🔌 Registered Adapters
| ID | Name | Channel | Permissions | Regions |
|---|---|---|---|---|
| `discord-adapter` | Discord Bot Adapter | `discord` | intent:read, intent:execute, network:outbound | GLOBAL |
| `github-adapter` | GitHub App Adapter | `github` | intent:read, intent:execute, data:write, network:outbound | GLOBAL |
| `line-adapter` | LINE Messaging Adapter | `line` | intent:read, intent:execute, network:outbound | TH, JP, TW |
| `slack-adapter` | Slack Adapter | `slack` | intent:read, intent:execute, user:read, network:outbound | US, GB, AU, TH, SG |
| `whatsapp-adapter` | WhatsApp Business Adapter | `whatsapp` | intent:read, intent:execute, media:read, network:outbound | TH, BR, IN, US, GLOBAL |

### 🧠 Registered Skills
| ID | Name | Permissions | Regions |
|---|---|---|---|
| `legal-pdpa` | PDPA Legal Compliance Skill | intent:read, policy:read | TH |
| `thai-language` | Thai Language Constitutional Skill | intent:read, intent:execute, policy:read | TH |
| `thai-nlp` | Thai Advanced NLP Skill | intent:read, intent:execute, policy:read | TH |
| `web-search-skill` | Web Search Skill | intent:read, intent:execute, network:read | TH, GLOBAL |

---

### 🚀 Quick Start
Start the local registry server:
```bash
pip install fastapi uvicorn jsonschema
uvicorn api.registry_api:app --reload --port 8090
```

---

## 🇹🇭 ภาษาไทย

**Delentia Ecosystem** คือทะเบียนระบบปลั๊กอินและทักษะของ [Delentia OS](https://github.com/delentia-labs/Delentia-OS) ทำหน้าที่จัดเก็บและตรวจสอบความถูกต้องของ Manifest สำหรับแอดแดปเตอร์ภายนอก (เช่น LINE, Slack) และโมดูลทักษะจำเพาะ (เช่น การตรวจสอบข้อกฎหมาย PDPA, ระบบจำแนกภาษาไทย) ผ่านโปรโตคอลการทำงาน JITNA v3

---

### 🏗️ สถาปัตยกรรมระบบ
* **`schema/`**: เก็บไฟล์ข้อกำหนดแบบ JSON Schema v7 สำหรับตรวจสอบสิทธิ์ปลั๊กอิน
* **`registry/`**: แบ่งแยกพื้นที่ปลั๊กอิน (Adapters) และทักษะเอเจนต์ (Skills)
* **`api/`**: เซิร์ฟเวอร์ทะเบียนกลางพัฒนาด้วย FastAPI (พอร์ต 8090)

---

### 🔌 อะแดปเตอร์ภายนอกที่ลงทะเบียนแล้ว
* **LINE Adapter** (`line`): เชื่อมการรับส่งข้อมูลผ่านช่องทางไลน์ รองรับพื้นที่ TH, JP, TW
* **Slack Adapter** (`slack`): เชื่อมต่อแอปร่วมงานขององค์กร
* **WhatsApp Adapter** (`whatsapp`): เชื่อมต่อธุรกิจและบริการลูกค้าทั่วไป

### 🧠 โมดูลทักษะเอเจนต์ที่ลงทะเบียนแล้ว
* **legal-pdpa**: ตรวจสอบการเปิดเผยข้อมูลตามมาตรา PDPA ประเทศไทย
* **thai-language**: ตรวจสอบและแปลเจตนาภาษาไทยเชิงกติกาข้อกฎหมาย
* **thai-nlp**: ระบบคัดแยกคำศัพท์ภาษาไทยความเร็วสูงร่วมกับสมองแม่

---

### 🚀 การเริ่มต้นใช้งานระบบทะเบียนโลคัล
รันเซิร์ฟเวอร์ด้วยคำสั่ง:
```bash
pip install fastapi uvicorn jsonschema
uvicorn api.registry_api:app --reload --port 8090
```

---

## Related Repositories / คลังข้อมูลที่เกี่ยวข้อง

| Repo | Purpose / วัตถุประสงค์ |
|---|---|
| [Delentia-OS](https://github.com/delentia-labs/Delentia-OS) | Core OS — JITNA v3, FDIA, IntentKernel |
| [Delentia-AI-SLM](https://github.com/delentia-labs/Delentia-AI-SLM) | SLM fine-tuning factory |
| [Delentia-OS-Gui](https://github.com/delentia-labs/Delentia-OS-Gui) | Desktop app (Delentia Desk) |
| [Delentia-Website](https://github.com/delentia-labs/Delentia-Website) | Marketing & Documentation portal |
| [Delentia-Infra-Public](https://github.com/delentia-labs/Delentia-Infra-Public) | Community deployment scripts |
| [Delentia-Infra-Enterprise](https://github.com/delentia-labs/Delentia-Infra-Enterprise) | Enterprise HA Kubernetes & Terraform configurations |

---

## License / สัญญาอนุญาต
Apache 2.0 — © 2026 Delentia Labs
