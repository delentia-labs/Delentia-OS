# RCT Platform — 5-Platform Distribution Kits

**Version:** 1.0.4b0 Launch Wave  
**Created:** 2026-04-30  
**Claim source:** [`CLAIM_REGISTRY.md`](CLAIM_REGISTRY.md)

This file contains ready-to-post copy for each of the 5 distribution channels. All numbers have been verified against CLAIM_REGISTRY.md. Before posting, run `python -m pytest -q --no-header` one final time to confirm 1,287 passing.

---

## Platform 1 — X (Twitter)

### Primary Launch Tweet (Thread Root)

```
We just shipped the beta-preview wave of RCT Platform — the core SDK of an Intent-Centric AI OS.

1,287 tests · 92% coverage · Apache 2.0 · Python 3.10+

Try it in 30 seconds (no GPU, no API key needed):
→ github.com/rctlabs/rct-platform

🧵 What's inside and why it's different:
```

### Thread Tweet 2 — What it solves

```
Most AI stacks can't answer: "Why did the model do that?"

RCT Platform can. Every decision traces to an FDIA score:
- F = factual grounding
- D = declarative intent match
- I = inference confidence
- A = alignment with constraints

Intent-first. Not output-first.
```

### Thread Tweet 3 — Evidence

```
No benchmarks without proof.

Run it yourself:
python -m pytest -q --no-header

Expected: 1,287 passed · 0 failed
Coverage: 92% (verified, not estimated)

Or open in Colab — no login needed:
colab.research.google.com/github/rctlabs/rct-platform/blob/main/notebooks/rct_playground.ipynb
```

### Thread Tweet 4 — Scope boundary

```
Honest scoping:

Open SDK (Apache 2.0): core FDIA engine, SignedAI consensus, Delta Engine, Regional Adapter, RCT Control Plane DSL, 5 reference microservices

Enterprise: full orchestration layer, production deployments, ASEAN-specific modules

Public alpha today → stable v1.0.0 on roadmap.
```

### Thread Tweet 5 — CTA

```
If you're building AI agents that need to be:
- Auditable
- Regionally aware
- Hallucination-resistant

Star the repo and try the playground.

github.com/rctlabs/rct-platform
```

### Fallback Single Tweet (if thread underperforms)

```
Open SDK for Intent-Centric AI — 1,287 tests, 92% coverage, Apache 2.0.

Run: python -m pytest -q --no-header to verify.
Colab demo, no GPU needed.

github.com/rctlabs/rct-platform #AI #OpenSource #Python
```

---

## Platform 2 — Hacker News (Show HN)

### Title

```
Show HN: RCT Platform – Intent-centric AI OS with constitutional architecture (1,287 tests, Apache 2.0)
```

### Body (First Comment — post immediately after submission)

```
Hi HN,

I've been building enterprise AI systems for ASEAN clients and kept hitting the same wall: models produce outputs that can't be audited, don't respect regional context, and fail silently under pressure.

RCT Platform is the open SDK layer of what I built to solve that.

**What it is:**
- FDIA equation engine: formalizes intent grounding as a score, not a vibe check
- SignedAI: multi-LLM consensus with cryptographic signing — each decision has a proof chain
- Delta Engine: compresses conversation memory 74% (internal benchmark)
- Regional Adapter: ASEAN/JP/KR/CN context normalization built in
- RCT Control Plane DSL: declarative orchestration for multi-agent pipelines
- 5 reference microservices with 258 passing tests as integration examples

**Verification (no trust required):**
```
git clone https://github.com/rctlabs/rct-platform
cd rct-platform
pip install -e ".[dev]"
python -m pytest -q --no-header
# Expected: 1,287 passed · 0 failed · 92% coverage
```

Or run the Colab playground without installing anything: [link]

**Scope boundary (important):**
What's open (Apache 2.0): core SDK — FDIA, SignedAI, Delta Engine, Regional Adapter, Control Plane DSL, 5 microservices
What's not open: production orchestration layer, full enterprise deployment stack

**Status:** beta preview v1.0.4b0. This is a working, tested SDK surface — not just a demo or prototype. The full ecosystem runs separately in production, while this public layer is being hardened for PyPI release.

Happy to answer technical questions. What would you want to verify first?
```

### Objection Handling (prepared responses)

**"Show the benchmark methodology"**
```
Fair point. The 74% Delta Engine figure is from internal benchmarks on production conversation datasets — not yet independently verified. For public alpha I'm citing it as "internal benchmark" only. The FDIA scoring and test suite are fully reproducible (run pytest yourself). Third-party benchmark validation is on the v1.1.0 roadmap.
```

**"How is this different from LangChain/LlamaIndex?"**
```
LangChain/LlamaIndex are orchestration libraries — they connect components. RCT Platform is an intent OS — it governs what components are allowed to do and provides an audit trail for why. The FDIA equation is the key difference: every LLM call produces a confidence+grounding score that can be verified post-hoc. You can use it alongside LangChain if you want orchestration + governance together.
```

**"Is this production-ready?"**
```
The enterprise stack (not open-source) runs in production at rctlabs.co. This SDK is public alpha — stable surface, tested, but the API may evolve before v1.0.0. If you need production SLAs today, the enterprise tier is the path. The open SDK is for developers who want to build on the architecture with full source visibility.
```

---

## Platform 3 — Reddit

### Subreddits (ordered by fit)
1. r/MachineLearning — technical, reproducibility-focused
2. r/LocalLLaMA — open weights/open source focus
3. r/Python — SDK/library audience
4. r/artificial — general AI audience
5. r/ThailandTech — Thai audience (use Thai kit, §5 below)

### r/MachineLearning Post

**Title:** `RCT Platform: open-source intent-centric AI OS with FDIA equation engine, 1,287 tests, Apache 2.0`

**Body:**
```
We open-sourced the core SDK of RCT Platform — an intent-centric AI operating system built around the FDIA (Factual-Declarative-Inferential-Aligned) equation.

**What makes it different:**
Unlike standard orchestration layers, RCT Platform treats intent as a first-class measurable object. The FDIA equation produces a grounded confidence score for every LLM decision — not just a probability, but a decomposed signal with four independent axes.

**Reproducible claims:**
- 1,287 tests passing · 0 skipped · 0 failed
- 92% line coverage
- Python 3.10/3.11/3.12

Verify yourself:
```bash
git clone https://github.com/rctlabs/rct-platform
pip install -e ".[dev]"
python -m pytest -q --no-header
```

**What's in the SDK:**
- `core/fdia/` — FDIA scorer + equation engine
- `signedai/` — multi-LLM consensus with signing
- `core/delta_engine/` — memory compression
- `core/regional_adapter/` — ASEAN/JP/KR/CN context normalization
- `rct_control_plane/` — declarative DSL (15 modules)
- `microservices/` — 5 reference microservices (258 tests)

**Honest scope:**
Public alpha. Delta Engine 74% compression figure is from internal benchmarks — not independently verified yet. FDIA scoring and test suite are fully reproducible.

GitHub: https://github.com/rctlabs/rct-platform
Colab (no login): https://colab.research.google.com/github/rctlabs/rct-platform/blob/main/notebooks/rct_playground.ipynb
```

### r/LocalLLaMA Post

**Title:** `Built an open-source intent OS for AI agents — FDIA scoring, multi-LLM consensus, 1,287 tests`

**Body:** (Shorter, lead with the demo)
```
Open-sourced the SDK layer of RCT Platform today.

**30-second test:**
```bash
pip install -e ".[dev]"
python -m pytest -q --no-header
# 1,287 passed · 92% coverage
```

**Or Colab (no GPU, no login):** [link]

Core components: FDIA equation engine (grounded intent scoring), SignedAI (multi-LLM consensus), Delta Engine (memory compression), Regional Adapter (ASEAN/JP/KR/CN), Control Plane DSL.

Apache 2.0. Python 3.10+.

https://github.com/rctlabs/rct-platform
```

---

## Platform 4 — LinkedIn

### Primary Post

```
We've open-sourced RCT Platform — the SDK layer of an intent-centric AI operating system built for enterprise governance.

After 2+ years building AI systems for ASEAN enterprise clients, one problem kept appearing: AI decisions couldn't be explained to auditors, compliance teams, or the business stakeholders who needed to trust them.

RCT Platform addresses this with a constitutional architecture:

→ FDIA equation: Every LLM decision produces a decomposed confidence score — factual grounding, declarative intent match, inference confidence, and alignment — not just a raw probability

→ SignedAI consensus: Multi-LLM decisions are signed and traceable, creating an audit chain for every outcome

→ Regional Adapter: Native context normalization for ASEAN, Japan, Korea, and China — enterprise AI that respects local constraints by design

→ 1,287 tests passing · 92% coverage · Apache 2.0 · Python 3.10+

This is beta preview (v1.0.4b0). The full enterprise stack runs separately in production. We're hardening the core SDK for external validation and developer adoption ahead of PyPI release.

If you're an AI architect, ML engineer, or enterprise technology leader exploring AI governance infrastructure, I'd welcome your feedback.

→ GitHub: github.com/rctlabs/rct-platform
→ Documentation: rctlabs.co

#EnterpriseAI #AIGovernance #OpenSource #ConstitutionalAI #ASEAN #Python
```

### LinkedIn Article Headline Options
1. "Why Enterprise AI Needs an Intent Layer (Not Just an Orchestration Layer)"
2. "The FDIA Equation: A Formal Framework for Measuring AI Decision Confidence"
3. "Open-Sourcing Constitutional AI Architecture: What We Learned Building for ASEAN Enterprise"

---

## Platform 5 — Thai Communities (ภาษาไทย)

### Facebook / LINE Group Post (ไทย)

```
🔓 เปิด Source Code ส่วน SDK ของ RCT Platform แล้ว — ระบบปฏิบัติการ AI ที่ออกแบบมาเพื่อองค์กร

ผ่านการทดสอบ 1,287 tests · Coverage 92% · License Apache 2.0 · Python 3.10+

---

RCT Platform คืออะไร?

มันคือ "ชั้นกำกับดูแล Intent" สำหรับ AI Agent — ทุกการตัดสินใจของ AI จะถูกวัดด้วยสมการ FDIA ก่อนที่จะออกมาเป็น output

FDIA = Factual × Declarative × Inferential × Aligned

ถ้า AI ตอบอะไรมา มันต้อง "พิสูจน์ได้" ว่า:
- ข้อมูลที่ใช้มาจากแหล่งจริง (F)
- ตรงกับ Intent ที่ตั้งใจ (D)
- Confidence ในการอนุมานสมเหตุสมผล (I)
- ไม่ขัดกับ Constitutional constraints (A)

---

ทดสอบเองได้เลย (ไม่ต้องมี GPU, ไม่ต้องมี API Key):

1. เปิด Colab: [ลิงก์ Colab]
2. กด Run All
3. ดูผล FDIA score สำหรับ 5 scenarios จริง

หรือจะ Clone และ run tests เอง:
git clone https://github.com/rctlabs/rct-platform
pip install -e ".[dev]"  
python -m pytest -q --no-header
# ผลที่ควรได้: 1,287 passed · 0 failed

---

สร้างให้ทีมที่ต้องการ:
✅ AI ที่ตรวจสอบได้ ไม่ใช่แค่ฉลาด
✅ รองรับบริบท ASEAN โดย default (ไทย, JP, KR, CN)
✅ Multi-LLM consensus พร้อม audit trail
✅ เหมาะกับ enterprise ที่ต้องการ governance จริง

Beta preview v1.0.4b0 — SDK core กำลังถูก harden สำหรับ external feedback และเส้นทาง PyPI

GitHub: github.com/rctlabs/rct-platform
เว็บไซต์: rctlabs.co

ถ้าสนใจหรืออยากพูดคุย mention มาได้เลย 🙏
```

### Pantip Post (ไทย)

**หมวด:** อินเทอร์เน็ต / โปรแกรมมิ่ง

**หัวข้อ:** `เปิด Source ระบบ AI ที่ออกแบบมาเพื่อ "ตรวจสอบได้" — RCT Platform SDK`

```
สวัสดีชาว Pantip ครับ

วันนี้เปิด Source Code ส่วน SDK ของ RCT Platform แล้ว

เล่าให้ฟังแบบสั้นๆ ว่าทำไมถึงสร้าง:
ทำงานกับองค์กรใหญ่ๆ ในไทยและ ASEAN มาหลายปี ปัญหาที่เจอซ้ำๆ คือ "AI ให้คำตอบมา แต่ไม่มีใครอธิบายได้ว่าทำไม" ซึ่งมันเป็นปัญหาใหญ่มากสำหรับ audit, compliance, และ risk management

เลยสร้าง Framework ที่ทุกการตัดสินใจของ AI ต้องผ่านสมการ FDIA ก่อน — ทำให้ตรวจสอบได้จริง

สิ่งที่เปิด Source (Apache 2.0):
- FDIA equation engine
- SignedAI: Multi-LLM consensus พร้อม signing
- Delta Engine: Memory compression
- Regional Adapter: รองรับบริบทไทย/ASEAN
- Control Plane DSL: Declarative orchestration

ตัวเลขที่ยืนยันได้:
- 1,287 tests ผ่านทั้งหมด · 0 failed
- Coverage 92%
- Python 3.10/3.11/3.12

ทดสอบได้ใน Colab โดยไม่ต้อง install อะไร: [ลิงก์]

GitHub: https://github.com/rctlabs/rct-platform

มีคำถามหรืออยากคุยเรื่องนี้ comment มาได้เลยครับ
```

---

## Anti-Fragile Routing (ถ้าช่องทางหลักมีปัญหา)

| สถานการณ์ | Action |
| --- | --- |
| HN post โดน flagged/dead | Shift budget ไปยัง r/MachineLearning + r/LocalLLaMA ทันที |
| Reddit post โดนลบ | Post ใน r/Python แทน + Twitter thread เสริม |
| ไม่มี engagement ใน 2h แรก | Quote tweet พร้อมเพิ่ม "technical detail" thread เสริม |
| ถูก attack credibility | อ้าง CLAIM_REGISTRY §4 + เชิญ reproduce |
| Colab link ไม่ทำงาน | เพิ่ม Binder backup ในทุก post: mybinder.org/v2/gh/rctlabs/rct-platform/main |
