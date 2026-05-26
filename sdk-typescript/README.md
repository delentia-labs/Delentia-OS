# @rctlabs/rct-platform

[![npm](https://img.shields.io/npm/v/@rctlabs/rct-platform?color=cb3837&logo=npm)](https://www.npmjs.com/package/@rctlabs/rct-platform)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](https://github.com/rctlabs/rct-platform/blob/main/LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

**TypeScript / JavaScript SDK for [RCT Platform](https://rctlabs.co)** — the world's first Intent-Centric AI Operating System with constitutional architecture.

---

## What is RCT Platform?

RCT Platform provides:
- **FDIA Formula** — `F = D^I × A` — constitutional scoring that governs AI freedom to act
- **JITNA Packets** — Just-In-Time Need Analysis structured intent envelopes
- **SignedAI Tiers** — HexaCore role assignment based on user tier and risk profile
- **REST Client** — typed Axios wrapper for the rct-platform FastAPI backend

---

## Installation

```bash
npm install @rctlabs/rct-platform
# or
yarn add @rctlabs/rct-platform
# or
pnpm add @rctlabs/rct-platform
```

---

## CLI — `npx rct`

The package ships a full command-line interface. Run without installing:

```bash
npx @rctlabs/rct-platform --help
```

Or install globally for the `rct` command:

```bash
npm install -g @rctlabs/rct-platform
rct --help
```

### Commands

| Command | Description |
|---------|-------------|
| `rct compile "<intent>"` | Compile intent → FDIA + JITNA + policy evaluation |
| `rct status` | Show control plane metrics (requires running server) |
| `rct init` | Interactive wizard → writes `.rct.json` config |
| `rct fdia <d> <i> <a>` | Offline constitutional gate check |

### Examples

```bash
# Check constitutional gate offline
npx @rctlabs/rct-platform fdia 0.9 0.95 1.0
# ╭────── FDIA — Constitutional Gate PASSED ──────╮
# │  F Score:  0.9048  Risk: LOW  Gate: 0.75 PASS ✔ │
# ╰───────────────────────────────────────────────╯

# Compile intent (requires rct-platform server running)
npx @rctlabs/rct-platform compile "Refactor the authentication module" --url http://localhost:8000

# Interactive project setup
npx @rctlabs/rct-platform init

# Server health + metrics
npx @rctlabs/rct-platform status
```

### `rct fdia` — Offline Mode

```bash
rct fdia <d> <i> <a> [--gate <threshold>] [--no-banner]
```

| Arg | Range | Description |
|-----|-------|-------------|
| `d` | 0.0–1.0 | Delta — change vector magnitude |
| `i` | 0.0–1.0 | Identity — role confidence |
| `a` | 0.0–1.0 | Architect gate (0=blocked, 1=approved) |
| `--gate` | 0.0–1.0 | Minimum pass threshold (default: `0.75`) |

---

## Quick Start

### FDIA Constitutional Formula

```typescript
import { computeFDIA, meetsThreshold } from "@rctlabs/rct-platform";

// Compute F = D^I × A
const result = computeFDIA(0.7, 0.9, 1.0);
console.log(result);
// {
//   f: 0.667,
//   d: 0.7, i: 0.9, a: 1.0,
//   riskLevel: "LOW",
//   isBlocked: false,
//   explanation: "F=0.667 = D^I × A = 0.70^0.90 × 1.00 → Risk=LOW"
// }

// Check against governance threshold
const allowed = meetsThreshold(result, 0.5);
console.log(allowed); // true
```

### JITNA Packet Construction

```typescript
import { constructJITNA, serializeJITNA } from "@rctlabs/rct-platform";

const packet = constructJITNA({
  intent: "Refactor the authentication module",
  userTier: "PRO",
  region: "ASEAN",
});

console.log(packet.packetId);     // "jitna_<uuid>"
console.log(packet.scope.region); // "ASEAN"

const json = serializeJITNA(packet);
```

### SignedAI Tier Selection

```typescript
import { selectSignedAITier } from "@rctlabs/rct-platform";

const selection = selectSignedAITier("PRO", "STRUCTURAL");
console.log(selection.roles);
// ["SUPREME_ARCHITECT", "LEAD_BUILDER", "JUNIOR_BUILDER",
//  "SPECIALIST", "LIBRARIAN", "HUMANIZER"]
console.log(selection.maxParallelAgents); // 4
```

### REST Client (requires running rct-platform server)

```typescript
import { RCTClient } from "@rctlabs/rct-platform";

const client = new RCTClient({
  baseURL: "https://your-rct-instance.com",
  apiKey: "your-api-key",
});

// Compile an intent
const compiled = await client.compile("Optimize database queries");
console.log(compiled.intent_id);
console.log(compiled.risk_profile);

// Evaluate against governance policies
const evaluation = await client.evaluatePolicy(compiled.intent_id);
console.log(evaluation.decision); // "approve" | "reject" | "require_approval"

// Get system metrics
const metrics = await client.getMetrics();
console.log(metrics.total_intents);
```

---

## API Reference

### `computeFDIA(d, i, a): FDIAResult`

Compute the constitutional FDIA score using `F = D^I × A`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `d` | `number` (0.0–1.0) | Delta — change vector magnitude |
| `i` | `number` (0.0–1.0) | Identity — role confidence |
| `a` | `number` (0.0–1.0) | Architect gate (0=blocked, 1=approved) |

Returns `FDIAResult` with: `f`, `d`, `i`, `a`, `riskLevel`, `isBlocked`, `explanation`.

---

### `meetsThreshold(result, threshold): boolean`

Check if an `FDIAResult` meets the minimum freedom threshold.

---

### `constructJITNA(options): JITNAPacket`

Build a structured JITNA intent packet.

| Option | Type | Default |
|--------|------|---------|
| `intent` | `string` | required |
| `userTier` | `"FREE" \| "PRO" \| "ENTERPRISE"` | `"FREE"` |
| `region` | `string` | `"GLOBAL"` |
| `budgetTokens` | `number` | `4096` |

---

### `selectSignedAITier(tier, riskProfile): TierSelection`

Map user tier + risk profile to HexaCore role assignments.

| Tier | Roles | Max Parallel Agents |
|------|-------|-------------------|
| `FREE` | 4 roles | 2 |
| `PRO` | 6 roles | 4 |
| `ENTERPRISE` | 8 roles (full HexaCore) | 8 |

---

### `RCTClient`

Typed Axios client for the rct-platform REST API.

```typescript
const client = new RCTClient(config?: RCTClientConfig);
await client.compile(intentText: string): Promise<CompileResponse>
await client.evaluatePolicy(intentId: string): Promise<PolicyEvalResponse>
await client.getMetrics(): Promise<MetricsResponse>
```

---

## TypeScript Support

Full TypeScript support with bundled type declarations (`dist/index.d.ts`).

```typescript
import type {
  FDIAResult, FDIAScores, RiskLevel,
  JITNAPacket, JITNAMeta,
  TierSelection, UserTier, HexaCoreRole,
  RCTClientConfig, CompileResponse,
} from "@rctlabs/rct-platform";
```

---

## Links

- **Website**: [rctlabs.co](https://rctlabs.co)
- **Python SDK (PyPI)**: [rct-platform](https://pypi.org/project/rct-platform/)
- **GitHub**: [rctlabs/rct-platform](https://github.com/rctlabs/rct-platform)
- **Docs**: [rctlabs.github.io/rct-platform](https://rctlabs.github.io/rct-platform/)
- **Issues**: [GitHub Issues](https://github.com/rctlabs/rct-platform/issues)

---

## License

[Apache 2.0](https://github.com/rctlabs/rct-platform/blob/main/LICENSE) © RCT Labs
