# 🌐 Delentia OS MCP Ecosystem

[![Model Context Protocol](https://img.shields.io/badge/MCP-Standard%202026-blue.svg)](https://modelcontextprotocol.io)
[![Runtime](https://img.shields.io/badge/Runtime-Cloudflare%20Workers%20%2B%20Durable%20Objects-orange.svg)](https://workers.cloudflare.com)
[![Language](https://img.shields.io/badge/Language-TypeScript%20NodeNext-blue.svg)](https://www.typescriptlang.org)
[![Security Gate](https://img.shields.io/badge/ZK--FDIA-Deterministic%20Safety-green.svg)](https://delentia.com)

**Delentia OS MCP Ecosystem** คือระบบนิเวศเซิร์ฟเวอร์ปัญญาประดิษฐ์ระดับองค์กร (Enterprise Model Context Protocol) ขับเคลื่อนด้วยสถาปัตยกรรมแบบมุ่งเน้นเจตนา (Intent-Centric AI Architecture) ประกอบด้วย 4 เซิร์ฟเวอร์อัจฉริยะที่ทำงานร่วมกันผ่านตัวแปร **I (Intent)** เพื่อแก้ปัญหาคอขวดด้านความปลอดภัย ค่าใช้จ่ายหน่วยความจำ และการหลอนของ AI (Hallucination)

---

## 🏛️ สถาปัตยกรรม 4 สมองกล (The 4 MCP Servers)

```
                       ┌────────────────────────────────────────┐
                       │       User Intent (Natural Query)      │
                       └───────────────────┬────────────────────┘
                                           │
                                           ▼
       [1. RCT-7 Thinking MCP]  ◄──────────┴──────────► บังคับคิดย้อนกลับ 7 ขั้นตอน (Zero Hallucination)
                                           │
                                           ▼
       [2. JITNA Protocol MCP]  ◄──────────┴──────────► ห่อเป็นแพ็กเก็ต [I, D, Delta, A, R, M] 
                                                        ควบคุมฝูง 1+4 Pillars LoRA Swarm
                                           │
                                           ▼
       [3. Delta Engine MCP]    ◄──────────┴──────────► บีบอัด Context เก็บเฉพาะ State Diffs 
                                                        ลดทอน Token สูงสุด 74.2% - 91.5%
                                           │
                                           ▼
       [4. FDIA Security MCP]   ◄──────────┴──────────► ด่านตรวจสิทธิ์คณิตศาสตร์ F = (D^I) * A
                                                        ถ้า A = 0 (ปิดสิทธิ์/บุกรุก) -> F = 0 ทันที
```

| เซิร์ฟเวอร์ | แพ็กเกจ | บทบาทหลัก | ฟังก์ชันเด่น / เครื่องมือ (Tool) |
| :--- | :--- | :--- | :--- |
| **FDIA Security** | `@delentia/mcp-fdia` | **Crown Jewel:** ด่านตรวจความมั่นคงเชิงคณิตศาสตร์ | `evaluate_fdia`: ประเมินสมการ `F = (D^I) * A` (Zero-Auth Preemption Cutoff) |
| **RCT-7 Thinking** | `@delentia/mcp-rct7` | **Crown Jewel:** ท่อคิดย้อนกลับ 7 ขั้นตอน | `rct_think`: บังคับกระบวนการคิด Observe, Analyze, Deconstruct, Reverse Reasoning, Core Intent, Reconstruct, Compare |
| **Delta Engine** | `@delentia/mcp-delta` | **Cash Cow:** บีบอัดบริบทและจัดการหน่วยความจำ | `compress_context`: ถอด State Differential ลดทอน Token/VRAM ได้ถึง 74.2% - 91.5% |
| **JITNA Swarm** | `@delentia/mcp-jitna` | **Cash Cow:** ผู้จัดสรรงานแบบ Multi-agent | `orchestrate_swarm`: แตกเจตนาเป็นแพ็กเก็ต JITNA กระจายสู่ 4 เสาหลัก (Router, Guardian, Executor, Scribe) |

---

## 🚀 สถาปัตยกรรมระดับ Enterprise (The Cole Medin Blueprint)

โปรเจกต์นี้ถูกออกแบบตามมาตรฐาน **Cole Medin (`remote-mcp-server-with-auth`)**:
1. **Cloudflare Durable Objects:** รักษาและจัดเก็บสถานะของผู้ใช้งาน (Session State) ข้ามเซสชันบน Edge ทั่วโลก
2. **Dual-Transport Interface:** รองรับทั้ง **Streamable HTTP** (`/mcp`) สำหรับระบบยุคใหม่ และ **SSE** (`/sse`) สำหรับระบบเดิม
3. **The "mcp-remote" Bridge:** แก้ปัญหาที่ Claude Desktop และ Cursor ยังไม่รองรับ Remote Auth ในตัว โดยใช้ตัวกลางสะพานเชื่อม

---

## 💻 การเชื่อมต่อใช้งานใน Cursor IDE & Claude Desktop

ผู้ใช้งานหรือลูกค้าของคุณสามารถเชื่อมต่อเข้าสู่เซิร์ฟเวอร์ Delentia ได้อย่างง่ายดายผ่านสะพานเชื่อม `mcp-remote`:

### การตั้งค่าใน `claude_desktop_config.json` หรือ Cursor `mcp.json`:

#### 1. การเชื่อมต่อตรงผ่าน Cloudflare Workers Edge (Direct Live URLs):
```json
{
  "mcpServers": {
    "delentia-fdia": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://delentia-fdia-mcp.delentia.workers.dev/mcp"
      ],
      "env": {
        "AUTH_TOKEN": "your_session_token_here"
      }
    },
    "delentia-rct7": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://delentia-rct7-mcp.delentia.workers.dev/mcp"
      ],
      "env": {
        "AUTH_TOKEN": "your_session_token_here"
      }
    },
    "delentia-delta": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://delentia-delta-mcp.delentia.workers.dev/mcp"
      ],
      "env": {
        "AUTH_TOKEN": "your_session_token_here"
      }
    },
    "delentia-jitna": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://delentia-jitna-mcp.delentia.workers.dev/mcp"
      ],
      "env": {
        "AUTH_TOKEN": "your_session_token_here"
      }
    }
  }
}
```

#### 2. การเชื่อมต่อผ่าน Commercial Gateway (Zuplo + Stripe 29 USD/เดือน):
แทนที่ URL ด้วย `https://api.delentialabs.com/mcp/<server>` พร้อมแนบ `sk_delentia_...` API Key จาก Developer Portal


---

## 🛠️ ขั้นตอนการทดสอบและการขึ้นระบบ (0 to 100 Deployment)

### 1. ติดตั้งและคอมไพล์โปรเจกต์
```bash
# ติดตั้ง dependencies ทั้งหมดใน Monorepo
npm install

# คอมไพล์ TypeScript ทุกแพ็กเกจ
npm run build
```

### 2. ทดสอบในเครื่อง (Local Sandbox)
```bash
# เปิดเซิร์ฟเวอร์จำลองของ FDIA
npm run dev:fdia

# ในอีกหน้าต่าง Terminal เปิดตัวตรวจสอบ MCP Inspector ของ Anthropic
npx @modelcontextprotocol/inspector
```
* เชื่อมต่อไปที่ `http://localhost:8787/mcp` เพื่อทดสอบยิง Tool `evaluate_fdia`

### 3. นำขึ้นระบบคลาวด์ (Cloudflare Workers Deploy)
```bash
# ล็อกอินเข้าสู่ระบบ Cloudflare (ทำครั้งแรกครั้งเดียว)
npx wrangler login

# ปล่อยเซิร์ฟเวอร์ขึ้น Edge ทั่วโลกทีละตัว
cd packages/fdia && npx wrangler deploy && cd ../..
cd packages/rct7 && npx wrangler deploy && cd ../..
cd packages/delta && npx wrangler deploy && cd ../..
cd packages/jitna && npx wrangler deploy && cd ../..
```

---

## 💳 การตั้งด่านเก็บเงินเชิงพาณิชย์ (Zuplo + Stripe)

1. **Zuplo Developer Portal:**
   * สมัครใช้งานที่ **Zuplo.com**
   * นำไฟล์ `docs/openapi.yaml` ไปวาง (Paste) ในส่วน OpenAPI เพื่อเสกหน้าเว็บคู่มือและระบบสมัครสมาชิกสำเร็จรูป
2. **ผูกระบบตัดเงิน Stripe:**
   * **Developer Tier (ฟรี):** ทดสอบใช้งานได้ 100 requests / เดือน
   * **Pro Tier (29 USD / เดือน):** โควต้า 10,000 requests / เดือน ตัดบัตรเครดิตผ่าน Stripe Checkout อัตโนมัติ
   * **Enterprise Tier:** ใบอนุญาตเฉพาะองค์กร (Private Air-Gapped License)
3. **การขึ้นทะเบียนตลาดสากล (Global Registry):**
   * นำไฟล์ `.well-known/mcp/server-card.json` (SEP-1649) และ Gateway URL จาก Zuplo ไปลงทะเบียนที่ **Smithery.ai**, **Glama.ai**, และ **PulseMCP**

---

## 📄 ลิขสิทธิ์และสิทธิ์ในทรัพย์สินทางปัญญา
สงวนลิขสิทธิ์ (c) 2026 **Delentia Labs**  
สถาปนิกและผู้สร้างสรรค์: **อิทธิฤทธิ์ แซ่โง้ว (Ittirit Saengow) — The Architect**  
ข้อมูลอ้างอิง: [https://delentia.com](https://delentia.com)
