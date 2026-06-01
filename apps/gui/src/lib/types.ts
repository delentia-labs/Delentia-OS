/**
 * types.ts
 *
 * Canonical TypeScript types for Delentia OS data structures.
 * Derived from:
 *   - contracts/openapi.yaml (API schemas)
 *   - rct_control_plane/jitna_protocol_v3.py (JITNA v3 packet)
 *   - core/delta_engine/memory_delta.py (MemoryDelta)
 *   - signedai/core/registry.py (HexaCoreRole)
 */

// ─────────────────────────────────────────────
// JITNA v3 Protocol
// ─────────────────────────────────────────────

export type JITNAMessageType =
  | "INTENT_REQUEST"
  | "INTENT_RESPONSE"
  | "NEGOTIATION"
  | "CONFIRMATION"
  | "STATUS_UPDATE"
  | "ERROR"
  | "HEARTBEAT"
  | "STREAM_CHUNK"
  | "STREAM_END";

export type JITNAStatus =
  | "CREATED"
  | "SENT"
  | "RECEIVED"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED";

/** Full JITNA v3 packet — matches JITNAPacketV3 in jitna_protocol_v3.py */
export interface JITNAPacketV3 {
  packet_id: string;
  source_agent_id: string;
  target_agent_id: string;
  message_type: JITNAMessageType;
  payload: Record<string, unknown>;
  timestamp: string; // ISO 8601 UTC
  schema_version: "3.0";
  priority: 1 | 2 | 3 | 4 | 5;
  correlation_id?: string;
  signature?: string; // ED25519 hex
  metadata: Record<string, unknown>;
  status: JITNAStatus;
  /** v3: ordered list of visited agent IDs (routing trace) */
  hop_trace: string[];
  /** v3: remaining hops before packet is dropped (default 8) */
  ttl: number;
  /** v3: payload compressed with zstd or zlib */
  compressed: boolean;
}

// ─────────────────────────────────────────────
// FDIA Score — F = D^I × A
// ─────────────────────────────────────────────

/** FDIA scoring dimensions — from core/fdia/fdia.py */
export interface FDIAScore {
  D: number; // Data quality       0.0 – 1.0
  I: number; // Intent clarity     0.0 – 1.0
  A: number; // Action confidence  0.0 – 1.0
  F: number; // Final: D^I × A     0.0 – 1.0
  signed: boolean;
  signature_hash: string; // SHA-256 of (D, I, A, F, timestamp)
}

export type FDIALevel = "critical" | "low" | "acceptable" | "high";

export function fdiaLevel(F: number): FDIALevel {
  if (F < 0.3) return "critical";
  if (F < 0.5) return "low";
  if (F < 0.8) return "acceptable";
  return "high";
}

// ─────────────────────────────────────────────
// HexaCore Roles — from signedai/core/registry.py
// ─────────────────────────────────────────────

export type HexaCoreRole =
  | "SUPREME_ARCHITECT"
  | "LEAD_BUILDER"
  | "JUNIOR_BUILDER"
  | "SPECIALIST"
  | "LIBRARIAN"
  | "HUMANIZER"
  | "REGIONAL_THAI"
  | "OLLAMA_ADAPTER"
  | "GROQ_ADAPTER";

export interface HexaCoreModel {
  role: HexaCoreRole;
  model_id: string;
  provider: string;
  country: string;
  input_cost_per_1m: number;  // USD
  output_cost_per_1m: number; // USD
  context_window: number;     // tokens
  specialties: string[];
}

/** Complete registry of all 9 HexaCore roles */
export const HEXACORE_REGISTRY: HexaCoreModel[] = [
  {
    role: "SUPREME_ARCHITECT",
    model_id: "claude-opus-4-6",
    provider: "Anthropic",
    country: "US",
    input_cost_per_1m: 5.00,
    output_cost_per_1m: 25.00,
    context_window: 1_000_000,
    specialties: ["architecture", "planning", "complex reasoning"],
  },
  {
    role: "LEAD_BUILDER",
    model_id: "kimi-k2.5",
    provider: "Moonshot AI",
    country: "CN",
    input_cost_per_1m: 0.45,
    output_cost_per_1m: 2.25,
    context_window: 1_000_000,
    specialties: ["programming", "visual coding", "debugging"],
  },
  {
    role: "JUNIOR_BUILDER",
    model_id: "minimax-2.1",
    provider: "MiniMax",
    country: "CN",
    input_cost_per_1m: 0.27,
    output_cost_per_1m: 0.95,
    context_window: 200_000,
    specialties: ["unit tests", "JSON formatting"],
  },
  {
    role: "SPECIALIST",
    model_id: "gemini-3-flash",
    provider: "Google",
    country: "US",
    input_cost_per_1m: 0.50,
    output_cost_per_1m: 3.00,
    context_window: 1_000_000,
    specialties: ["finance", "health", "speed", "multimodal"],
  },
  {
    role: "LIBRARIAN",
    model_id: "grok-4.1-fast",
    provider: "xAI",
    country: "US",
    input_cost_per_1m: 0.20,
    output_cost_per_1m: 0.50,
    context_window: 2_000_000,
    specialties: ["long context", "science", "memory", "RAG"],
  },
  {
    role: "HUMANIZER",
    model_id: "deepseek-v3.2",
    provider: "DeepSeek",
    country: "CN",
    input_cost_per_1m: 0.25,
    output_cost_per_1m: 0.38,
    context_window: 200_000,
    specialties: ["roleplay", "natural language", "translation"],
  },
  {
    role: "REGIONAL_THAI",
    model_id: "typhoon-v2",
    provider: "SCB10X",
    country: "TH",
    input_cost_per_1m: 0.40,
    output_cost_per_1m: 1.20,
    context_window: 128_000,
    specialties: ["Thai NLP", "legal", "finance"],
  },
  {
    role: "OLLAMA_ADAPTER",
    model_id: "llama-3.1-8b",
    provider: "Local / Ollama",
    country: "—",
    input_cost_per_1m: 0,
    output_cost_per_1m: 0,
    context_window: 128_000,
    specialties: ["offline", "privacy", "air-gapped inference"],
  },
  {
    role: "GROQ_ADAPTER",
    model_id: "llama-3.3-70b-versatile",
    provider: "Groq",
    country: "US",
    input_cost_per_1m: 0.59,
    output_cost_per_1m: 0.79,
    context_window: 128_000,
    specialties: ["LPU speed", "latency optimization"],
  },
];

// ─────────────────────────────────────────────
// Memory / Delta Engine
// ─────────────────────────────────────────────

/** Single memory state-change record — from core/delta_engine/memory_delta.py */
export interface MemoryDelta {
  agent_id: string;
  tick: number;
  intent_type: string;
  action_type: string;
  outcome: "success" | "blocked" | "partial";
  changes: Record<string, unknown>;
  relationship_change: Record<string, number>;
  governance_violation: boolean;
  resources_delta: Record<string, unknown>;
  sha256_hash?: string; // audit chain hash
}

// ─────────────────────────────────────────────
// API Response types — from openapi.yaml
// ─────────────────────────────────────────────

export interface HealthResponse {
  status: "ok" | "degraded";
  timestamp: string;
  version: string;
  service: string;
  trace_id?: string;
}

/** Live ecosystem stats from GET /delentia/system/stats */
export interface SystemStats {
  testCount: number;         // 4849
  microserviceCount: number; // 62
  algorithmCount: number;    // 41
  layerCount: number;        // 10
  hexaCoreCount: number;     // 9
  consensusModels: number;
  sla: string;               // "99.9%"
  version: string;
}

/** Response from POST /v1/kernel/execute */
export interface IntentExecuteResponse {
  output: {
    result: string;
    summary?: string;
    fdia_score?: FDIAScore;
    hexa_role?: HexaCoreRole;
    signed?: boolean;
  };
  trace_id: string;
  jitna_packet?: JITNAPacketV3;
}

/** Response from POST /v1/delentiadb/query */
export interface QueryResponse {
  results: Array<{
    id: string;
    score: number;
    payload: Record<string, unknown>;
  }>;
  query_type: "vector" | "graph" | "hybrid";
  total: number;
}
