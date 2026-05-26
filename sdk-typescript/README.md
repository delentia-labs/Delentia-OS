# @rctlabs/rct-platform

<div align="center">

```text
  ██████╗  ██████╗████████╗   ██████╗ ███████╗
  ██╔══██╗██╔════╝╚══██╔══╝   ██╔══██╗╚══███╔╝
  ██████╔╝██║        ██║      ██████╔╝  ███╔╝ 
  ██╔══██╗██║        ██║      ██╔═══╝  ███╔╝  
  ██║  ██║╚██████╗   ██║      ██║     ███████╗
  ╚═╝  ╚═╝ ╚═════╝   ╚═╝      ╚═╝     ╚══════╝
      Intent-Centric AI Operating System
```

**TypeScript / JavaScript SDK + High-Fidelity CLI for RCT Platform**  
*The world's first Intent-Centric AI Operating System with constitutional architecture.*

---

[![npm version](https://img.shields.io/npm/v/@rctlabs/rct-platform?color=cb3837&logo=npm&logoColor=white&style=flat-square)](https://www.npmjs.com/package/@rctlabs/rct-platform)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square)](https://github.com/rctlabs/rct-platform/blob/main/LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white&style=flat-square)](https://www.typescriptlang.org/)
[![Downloads](https://img.shields.io/npm/dm/@rctlabs/rct-platform?color=brightgreen&style=flat-square)](https://www.npmjs.com/package/@rctlabs/rct-platform)
[![Website](https://img.shields.io/badge/website-rctlabs.co-0099EE?style=flat-square)](https://rctlabs.co)

</div>

---

## 🏛️ What is RCT Platform?

**Reverse Component Thinking (RCT)** is the core architectural paradigm that decomposes complex AI operations into lightweight, verifiable intent packets, verifying their safety under mathematical and human-in-the-loop governance. 

This SDK and CLI exposes the public interfaces of **RCT OS** — a constitutional control plane that acts as **"Linux for AI Agents."**

### 🌟 Core Architectural Layers in This SDK
- **FDIA constitutional formula:** Evaluates systemic execution risk before firing commands.
- **JITNA intent envelopes:** Standardizes intent payloads with structured scoping, budget caps, and regional tags.
- **SignedAI HexaCore Consensus:** Resolves agent role assignments based on user privilege tiers and computed risk.
- **Robust REST Client:** Fully typed Axios client for seamless local and cloud FastAPI orchestration.

---

## 🚀 Installation

Install the package via your preferred package manager:

```bash
# npm
npm install @rctlabs/rct-platform

# yarn
yarn add @rctlabs/rct-platform

# pnpm
pnpm add @rctlabs/rct-platform
```

---

## 💻 CLI Tool — `npx rct`

The package bundles a fully functional, highly interactive command-line interface. Run it instantly via `npx` without global installation:

```bash
npx @rctlabs/rct-platform --help
```

Or install globally to gain the native `rct` command:

```bash
npm install -g @rctlabs/rct-platform
rct --help
```

### 📋 CLI Command Matrix

| Command | Args | Description | Offline? |
|:---|:---|:---|:---|
| **`rct fdia`** | `<d> <i> <a>` | Check constitutional gate offline (F = Dᴵ × A) | **Yes** |
| **`rct init`** | — | Launch interactive wizard to write `.rct.json` config | **Yes** |
| **`rct compile`**| `"<intent>"` | Compile active intent into structured FDIA + JITNA | *No (Needs Server)* |
| **`rct status`** | — | Print rich timeline dashboard of control plane metrics | *No (Needs Server)* |

### 🛠️ CLI Execution Examples

#### 1. Check the Constitutional Gate (`rct fdia`)
Instantly verify change metrics offline:
```bash
npx @rctlabs/rct-platform fdia 0.9 0.95 1.0
```
**Output:**
```text
  ██████╗  ██████╗████████╗
  ██╔══██╗██╔════╝╚══██╔══╝
  ██████╔╝██║        ██║   
  ██╔══██╗██║        ██║   
  ██║  ██║╚██████╗   ██║   
  ╚═╝  ╚═╝ ╚═════╝   ╚═╝  
  Intent-Centric AI Operating System  v1.2.0

╭──────── FDIA — Constitutional Gate PASSED ────────╮
│                                                   │
│  Formula:     F = Dᴵ × A                          │
│  Inputs:      D = 0.9000  I = 0.9500  A = 1.0000  │
│                                                   │
│  F Score:     0.904754                            │
│  Risk Level:   LOW                                │
│  Gate:        0.7500 — PASS ✔                     │
│                                                   │
╰───────────────────────────────────────────────────╯
```

#### 2. Interactive Workspace Setup (`rct init`)
Run the setup wizard to produce a valid project config:
```bash
npx @rctlabs/rct-platform init
```

---

## ⚡ Quick Start (API Usage)

### 1. Compute the FDIA Formula
$$\text{Friction (F)} = \text{Data (D)}^{\text{Intent (I)}} \times \text{Alignment (A)}$$
If alignment $A = 0$ (e.g. human architect veto), execution is completely halted ($F = 0$).

```typescript
import { computeFDIA, meetsThreshold } from "@rctlabs/rct-platform";

// Compute F = Dᴵ × A
const result = computeFDIA(0.7, 0.9, 1.0);
console.log(result);
/*
{
  f: 0.724,
  d: 0.7, i: 0.9, a: 1.0,
  riskLevel: "LOW",
  isBlocked: false,
  explanation: "F=0.724 = D^I × A = 0.70^0.90 × 1.00 → Risk=LOW"
}
*/

// Check if result passes governance threshold
const isSafe = meetsThreshold(result, 0.75); // false
```

### 2. Construct a JITNA Packet
Just-In-Time Need Analysis (JITNA) structures raw intents into secure, standardized transaction envelopes:

```typescript
import { constructJITNA, serializeJITNA } from "@rctlabs/rct-platform";

const packet = constructJITNA({
  intent: "Deploy primary gateway server",
  userTier: "PRO",
  region: "ASEAN",
  budgetTokens: 8192,
});

console.log(packet.packetId);      // "jitna_<uuid>"
console.log(packet.scope.region);  // "ASEAN"

const serialized = serializeJITNA(packet);
```

### 3. SignedAI HexaCore Role Selection
SignedAI routes intent complexity to distinct, cryptographically attested model configurations:

```typescript
import { selectSignedAITier } from "@rctlabs/rct-platform";

const selection = selectSignedAITier("PRO", "STRUCTURAL");
console.log(selection.roles);
// ["SUPREME_ARCHITECT", "LEAD_BUILDER", "JUNIOR_BUILDER", "SPECIALIST", "LIBRARIAN", "HUMANIZER"]
console.log(selection.maxParallelAgents); // 4
```

### 4. Full REST Integration (`RCTClient`)
Orchestrate local or remote RCT Control Planes using the built-in HTTP client:

```typescript
import { RCTClient } from "@rctlabs/rct-platform";

const client = new RCTClient({
  baseURL: "http://localhost:8000",
  apiKey: "your-secret-api-token",
});

// Compile an intent into structural parameters
const compiled = await client.compile("Refactor active database schemas");
console.log(compiled.intent_id);
console.log(compiled.risk_profile); // "STRUCTURAL"

// Evaluate JITNA against active governance policy
const decision = await client.evaluatePolicy(compiled.intent_id);
console.log(decision.decision); // "require_approval" | "approve" | "reject"
```

---

## 🛡️ Full TypeScript Type Guarantees

The package bundles complete TypeScript declarations (`dist/index.d.ts`), offering deep autocomplete support for all types:

```typescript
import type {
  FDIAResult,
  JITNAPacket,
  TierSelection,
  UserTier,
  HexaCoreRole,
  CompileResponse,
  PolicyEvalResponse,
} from "@rctlabs/rct-platform";
```

---

## 🔗 Resources & Community
- **Official Website:** [rctlabs.co](https://rctlabs.co)
- **GitHub Core Repo:** [rctlabs/rct-platform](https://github.com/rctlabs/rct-platform)
- **PyPI Python Package:** [rct-platform](https://pypi.org/project/rct-platform/)
- **Developer Documentation:** [rctlabs.github.io/rct-platform](https://rctlabs.github.io/rct-platform/)
- **Active Issues:** [GitHub Issue Tracker](https://github.com/rctlabs/rct-platform/issues)

---

## 📄 License

Licensed under the [Apache License 2.0](https://github.com/rctlabs/rct-platform/blob/main/LICENSE) © RCT Labs.
