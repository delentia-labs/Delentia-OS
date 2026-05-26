# แผนการพัฒนา RCT Platform (ภาษาไทย)

> **เวอร์ชัน:** 1.1.0 — อัปเดตล่าสุด: 2026-04

---

## ภาพรวม

**RCT Platform** คือ AI Orchestration SDK ที่ออกแบบมาเพื่อควบคุมและ
ประสานงาน AI agents แบบ agentic workflow โดยมีเป้าหมายหลักดังนี้:

- **ความปลอดภัย** — ทุก intent ต้องผ่าน policy evaluation ก่อน execute
- **ตรวจสอบได้** — audit trail ด้วย SHA-256 hash chain
- **ยืดหยุ่น** — รองรับทั้ง FastAPI HTTP API และ CLI
- **สังเกตการณ์ได้** — รองรับ Prometheus metrics และ OpenTelemetry

---

## สถานะปัจจุบัน (Phase A — เสร็จสมบูรณ์ ✅)

| งาน | สถานะ |
|-----|-------|
| แก้ไข Ruff lint errors 15 จุด (6 ไฟล์) | ✅ |
| เพิ่ม test coverage: 85.81% → 90.02% | ✅ |
| สร้าง test files ใหม่ 5 ไฟล์ (882 tests) | ✅ |
| commit + push branch `Betasystem-Maintenance-Update` | ✅ |
| เพิ่ม npm badge ใน README.md | ✅ |

---

## Sprint ที่ผ่านมา

### Sprint 1 — Core Infrastructure
- `IntentSchema` / `ExecutionGraphIR` / `ControlPlaneState`
- SQLite persistence ด้วย aiosqlite
- FastAPI HTTP endpoints: `/submit`, `/execute`, `/status/{id}`
- CLI commands: `submit`, `execute`, `status`, `memory`

### Sprint 2 — Policy & Safety Layer
- `PolicyLanguage` — DSL for defining approval rules
- `ApprovalGateway` — HTTP callback + retry loop
- `ArchitectPolicyLoader` — load YAML policy files
- Default policies สำหรับ STRUCTURAL / SYSTEMIC risk

### Sprint 3 — Observability & Audit
- `ControlPlaneObserver` — event-driven metrics collector
- `AuditTrail` — hash-chain audit log
- Prometheus counter/gauge/histogram integration (optional)
- OpenTelemetry adapter (optional)

### Sprint 4 — Execution & Planning
- `PlanEngine` — cost estimation + risk profile
- `ReplayEngine` — checkpoint save/restore + hash verification
- `IntentCompiler` — DSL → IR compilation pipeline
- `RichFormatter` — CLI rich output rendering

---

## แผนงาน Phase B — ถัดไป

### B1: npm Package
- เผยแพร่ `@rctlabs/rct-platform` บน npm
- TypeScript type definitions สำหรับ API schema
- `npm install @rctlabs/rct-platform` เพื่อใช้งาน REST client

### B2: PyPI Release
- เผยแพร่ `rct-platform==1.1.0` บน PyPI
- `pip install rct-platform` พร้อมใช้งาน CLI ได้ทันที

### B3: Multi-Agent Coordination
- Shared `ControlPlaneState` ระหว่าง agents
- Intent dependency graph (DAG scheduling)
- Parallel execution paths

### B4: Enhanced Policy Engine
- Dynamic policy reload โดยไม่ต้อง restart
- Policy versioning และ rollback
- Fine-grained RBAC สำหรับ intent types

---

## โครงสร้างโปรเจกต์

```
rct-platform/
├── rct_control_plane/          # Core SDK
│   ├── api.py                  # FastAPI application
│   ├── cli.py                  # Click CLI
│   ├── intent_schema.py        # Pydantic models
│   ├── intent_compiler.py      # DSL → IR compiler
│   ├── execution_graph_ir.py   # Intermediate representation
│   ├── plan_engine.py          # Cost/risk estimation
│   ├── replay_engine.py        # Checkpoint management
│   ├── approval_gateway.py     # HTTP approval loop
│   ├── observability.py        # Metrics + audit trail
│   ├── policy_language.py      # Policy DSL
│   ├── persistence.py          # SQLite async layer
│   └── tests/                  # 882 unit tests
├── microservices/              # Microservice examples
├── core/                       # Shared utilities
├── signedai/                   # Signed AI integration
├── docs/                       # Documentation
└── benchmark/                  # Benchmark suite
```

---

## วิธีติดตั้งและใช้งาน

### Python SDK
```bash
pip install rct-platform

# เริ่ม API server
rct-platform serve --port 8000

# ส่ง intent ผ่าน CLI
rct-platform submit --intent-type refactor --risk-level LOW
```

### npm (TypeScript client)
```bash
npm install @rctlabs/rct-platform
```

```typescript
import { RCTPlatformClient } from "@rctlabs/rct-platform";

const client = new RCTPlatformClient({ baseUrl: "http://localhost:8000" });
const result = await client.submitIntent({ intentType: "refactor", riskLevel: "LOW" });
```

---

## การทดสอบ

```bash
# รัน test ทั้งหมด
pytest rct_control_plane/tests/ -q

# รันพร้อม coverage report
pytest rct_control_plane/tests/ --cov=rct_control_plane --cov-report=term-missing

# ตรวจ lint
ruff check rct_control_plane/
```

**Coverage ปัจจุบัน:** 90.02% (threshold: 90%)

---

## CI/CD Pipeline

```
push → GitHub Actions
  ├── Lint & Type Check (ruff + mypy)
  ├── Tests (Python 3.10 / 3.11 / 3.12)
  │   └── pytest --cov-fail-under=90
  └── Security Scan (Bandit + Safety)
```

---

## ผู้ดูแล

| บทบาท | รายละเอียด |
|-------|-----------|
| Core SDK | rct_control_plane/ |
| CI/CD | .github/workflows/ |
| Documentation | docs/ |
| Benchmarks | benchmark/ |

---

*เอกสารนี้อัปเดตอัตโนมัติเมื่อ Sprint เสร็จสมบูรณ์*
