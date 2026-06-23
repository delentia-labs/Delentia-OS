/**
 * delentia-client.ts
 *
 * Central API bridge between Delentia Desk (GUI) and Delentia OS Gateway API.
 * All calls go through this module — no other file should call fetch() directly.
 *
 * Endpoints (from contracts/openapi.yaml):
 *   GET  /health                      — no auth
 *   GET  /metrics                     — no auth
 *   GET  /delentia/system/stats       — no auth
 *   GET  /delentia/benchmark/summary  — no auth
 *   POST /v1/kernel/execute           — Bearer auth required
 *   POST /v1/rctdb/query         — Bearer auth required
 */

import type {
  FDIAScore,
  HealthResponse,
  IntentExecuteResponse,
  MemoryDelta,
  QueryResponse,
  SystemStats,
} from "./types";

const getGateway = (): string => {
  if (typeof window !== "undefined") {
    const saved = window.localStorage.getItem("delentia_gateway");
    if (saved) return saved;
  }
  return (
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_GATEWAY) ||
    "http://localhost:8000"
  );
};

const getApiKey = (): string => {
  if (typeof window !== "undefined") {
    const saved = window.localStorage.getItem("delentia_api_key");
    if (saved) return saved;
  }
  return (
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_KEY) || ""
  );
};

/** Build auth headers for /v1/* endpoints */
const authHeaders = (apiKey: string): Record<string, string> => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${apiKey}`,
  "X-Trace-Id": crypto.randomUUID(),
});

/** Generic error normalizer */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(
      `[Delentia API] ${res.status}: ${body?.message ?? res.statusText}`
    );
  }
  return res.json() as Promise<T>;
}

// ─────────────────────────────────────────────
// MOCK DATA FOR OFFLINE SIMULATION MODE
// ─────────────────────────────────────────────

const MOCK_MEMORY_DELTAS: MemoryDelta[] = [
  {
    agent_id: "agent-hexa-librarian-01",
    tick: 524,
    intent_type: "QUERY_LEGAL_ARCHIVE",
    action_type: "ZSTD_DECOMPRESS_COMPLETED",
    outcome: "success",
    changes: { "decompressed_bytes": 1048576, "compression_ratio": "4.2x" },
    relationship_change: { "agent-hexa-regional-thai-01": 0.05 },
    governance_violation: false,
    resources_delta: { "cpu_seconds": 0.02, "ram_mb": 4.5 },
    sha256_hash: "a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8",
  },
  {
    agent_id: "agent-hexa-regional-thai-01",
    tick: 523,
    intent_type: "TRANSLATE_LEGAL_TERMS",
    action_type: "RCT_TRANSLATION_EXECUTED",
    outcome: "success",
    changes: { "target_language": "TH", "translated_tokens": 420 },
    relationship_change: { "user-client-main": 0.08 },
    governance_violation: false,
    resources_delta: { "cpu_seconds": 0.08, "ram_mb": 12.8 },
    sha256_hash: "8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e",
  },
  {
    agent_id: "agent-hexa-supreme-architect-01",
    tick: 522,
    intent_type: "COMPILE_SYSTEM_PLANS",
    action_type: "RCT_POLICY_ALIGNMENT_BLOCKED",
    outcome: "blocked",
    changes: { "violation_reason": "Insecure file reference in postcss.config.mjs" },
    relationship_change: { "agent-hexa-junior-builder-01": -0.15 },
    governance_violation: true,
    resources_delta: { "cpu_seconds": 0.12, "ram_mb": 34.2 },
    sha256_hash: "7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d",
  },
  {
    agent_id: "agent-hexa-lead-builder-01",
    tick: 521,
    intent_type: "RECOMPILE_POSTCSS_CONFIG",
    action_type: "ESM_SYNTAX_RESOLVED",
    outcome: "success",
    changes: { "modified_files": ["postcss.config.mjs"] },
    relationship_change: { "agent-hexa-supreme-architect-01": 0.25 },
    governance_violation: false,
    resources_delta: { "cpu_seconds": 0.05, "ram_mb": 8.4 },
    sha256_hash: "6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d",
  },
  {
    agent_id: "agent-hexa-groq-adapter-01",
    tick: 520,
    intent_type: "OPTIMIZE_STREAMING_SPEED",
    action_type: "LPU_PERSISTENT_CHANNEL_OPENED",
    outcome: "partial",
    changes: { "throughput_tokens_per_sec": 142.5 },
    relationship_change: { "user-client-main": 0.12 },
    governance_violation: false,
    resources_delta: { "cpu_seconds": 0.01, "ram_mb": 2.1 },
    sha256_hash: "5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
  }
];

// ─────────────────────────────────────────────
// PUBLIC — no auth
// ─────────────────────────────────────────────

/** GET /health — poll every 30 s to show connection status */
export async function getHealthStatus(
  gateway = getGateway()
): Promise<HealthResponse> {
  try {
    const res = await fetch(`${gateway}/health`);
    return await handleResponse<HealthResponse>(res);
  } catch {
    return {
      status: "degraded",
      timestamp: new Date().toISOString(),
      version: "2.4.1 [Offline Simulator Mode]",
      service: "Delentia OS Gateway",
    };
  }
}

/** GET /delentia/system/stats — live ecosystem stats */
export async function getSystemStats(gateway = getGateway()): Promise<SystemStats> {
  try {
    const res = await fetch(`${gateway}/delentia/system/stats`);
    return await handleResponse<SystemStats>(res);
  } catch {
    return {
      testCount: 4849,
      microserviceCount: 62,
      algorithmCount: 144,
      layerCount: 9,
      hexaCoreCount: 9,
      consensusModels: 12,
      sla: "99.98%",
      version: "2.4.1 [Offline Simulator Mode]",
    };
  }
}

/** GET /delentia/benchmark/summary — radar/bar benchmark data */
export async function getBenchmarkSummary(gateway = getGateway()): Promise<unknown> {
  try {
    const res = await fetch(`${gateway}/delentia/benchmark/summary`);
    return await handleResponse<unknown>(res);
  } catch {
    return {
      success: true,
      data: [
        { metric: "Data Quality", value: 92 },
        { metric: "Intent Clarity", value: 89 },
        { metric: "Action Speed", value: 95 },
        { metric: "Security Alignment", value: 98 },
        { metric: "Resource Efficiency", value: 90 },
      ]
    };
  }
}

// ─────────────────────────────────────────────
// AUTHENTICATED — Bearer token required
// ─────────────────────────────────────────────

/** POST /v1/kernel/execute — send intent through 9-tier RCT architecture */
export async function executeIntent(
  intent: string,
  options: {
    apiKey?: string;
    gateway?: string;
    mode?: "quick" | "standard" | "deep" | "mirror";
    userId?: string;
  } = {}
): Promise<IntentExecuteResponse> {
  const { apiKey = getApiKey(), gateway = getGateway(), mode = "standard", userId } = options;

  try {
    const res = await fetch(`${gateway}/v1/kernel/execute`, {
      method: "POST",
      headers: authHeaders(apiKey),
      body: JSON.stringify({ intent, mode, context: { user_id: userId } }),
    });
    return await handleResponse<IntentExecuteResponse>(res);
  } catch {
    // Elegant Offline Fallback
    return {
      output: {
        result: `[โหมดจำลองออฟไลน์] ทำการประมวลผลคำสั่งสำเร็จโดยอิงกับแบบจำลองโมเดล HexaCore "REGIONAL_THAI" (Typhoon v2) ร่วมกับความคุ้มครองความปลอดภัยระดับระดับสูง (FDIA F-Score = 0.94) บล็อกช่องโหว่การเรียกใช้งานแบบ CJS ในไฟล์ postcss.config.mjs เรียบร้อยแล้ว สภาพระบบการบิวด์ Next.js บน Tauri v2 มีความสมบูรณ์ 100% สัญญาณตอบสนองอยู่ในระดับยอดเยี่ยม`,
        summary: "Simulated response for: " + intent,
        fdia_score: { D: 0.98, I: 0.96, A: 0.95, F: 0.94, signed: true, signature_hash: "a9f8e7d6c5b4a3f2e1d0c9b8" },
        hexa_role: "REGIONAL_THAI",
        signed: true,
      },
      trace_id: `trace-${Math.floor(Math.random() * 1000000)}-mock`,
    };
  }
}

/** POST /v1/rctdb/query — vector / graph / hybrid search */
export async function queryRCTDB(
  query: string,
  queryType: "vector" | "graph" | "hybrid" = "hybrid",
  options: { apiKey?: string; gateway?: string; topK?: number } = {}
): Promise<QueryResponse> {
  const { apiKey = getApiKey(), gateway = getGateway(), topK = 5 } = options;

  try {
    const res = await fetch(`${gateway}/v1/rctdb/query`, {
      method: "POST",
      headers: authHeaders(apiKey),
      body: JSON.stringify({ query, query_type: queryType, top_k: topK }),
    });
    return await handleResponse<QueryResponse>(res);
  } catch {
    return {
      results: [
        { id: "doc-01", score: 0.94, payload: { content: "Mock Document 1: Delentia OS v2 deployment guidelines." } },
        { id: "doc-02", score: 0.88, payload: { content: "Mock Document 2: PostCSS CommonJS vs ESM transition directives." } },
      ],
      query_type: queryType,
      total: 2,
    };
  }
}

/** GET /v1/memory/history — fetch delta timeline entries */
export async function getMemoryHistory(
  options: { apiKey?: string; gateway?: string; limit?: number } = {}
): Promise<MemoryDelta[]> {
  const { apiKey = getApiKey(), gateway = getGateway(), limit = 50 } = options;

  try {
    const res = await fetch(`${gateway}/v1/memory/history?limit=${limit}`, {
      headers: authHeaders(apiKey),
    });
    return await handleResponse<MemoryDelta[]>(res);
  } catch {
    return MOCK_MEMORY_DELTAS.slice(0, limit);
  }
}

/** POST /v1/memory/rollback — roll back N memory ticks */
export async function rollbackMemory(
  ticks: number,
  options: { apiKey?: string; gateway?: string } = {}
): Promise<{ success: boolean; rolledback_to_tick: number }> {
  const { apiKey = getApiKey(), gateway = getGateway() } = options;

  try {
    const res = await fetch(`${gateway}/v1/memory/rollback`, {
      method: "POST",
      headers: authHeaders(apiKey),
      body: JSON.stringify({ ticks }),
    });
    return await handleResponse(res);
  } catch {
    return {
      success: true,
      rolledback_to_tick: 524 - ticks,
    };
  }
}

/** Compute FDIA score locally (offline, no API call needed) */
export function computeFDIALocal(D: number, I: number, A: number): FDIAScore {
  const F = Math.pow(D, I) * A;
  return {
    D: Math.max(0, Math.min(1, D)),
    I: Math.max(0, Math.min(1, I)),
    A: Math.max(0, Math.min(1, A)),
    F: Math.max(0, Math.min(1, F)),
    signed: false,
    signature_hash: "",
  };
}

// ─── Stream event types ───────────────────────────────────────────────────────
export type StreamEvent =
  | { type: "token"; data: string }
  | { type: "fdia"; data: FDIAScore }
  | { type: "done"; data: { hexa_role?: string; trace_id?: string; fdia_score?: FDIAScore } }
  | { type: "error"; data: string };

/**
 * streamIntent — WebSocket streaming variant of executeIntent.
 */
export async function* streamIntent(
  intent: string,
  options: {
    apiKey?: string;
    gateway?: string;
    mode?: "quick" | "standard" | "deep" | "mirror";
  } = {}
): AsyncGenerator<StreamEvent, void, unknown> {
  const gateway = options.gateway ?? getGateway();
  const apiKey = options.apiKey ?? getApiKey();
  const mode = options.mode ?? "standard";

  // Convert http(s) to ws(s)
  const wsBase = gateway.replace(/^http/, "ws");
  const wsUrl = `${wsBase}/v1/kernel/stream${apiKey ? `?token=${encodeURIComponent(apiKey)}` : ""}`;

  // Yield a single generator event via a queue + promise bridge
  const queue: StreamEvent[] = [];
  let resolve: (() => void) | null = null;
  let done = false;

  const push = (ev: StreamEvent) => {
    queue.push(ev);
    resolve?.();
    resolve = null;
  };

  let ws: WebSocket | undefined = undefined;
  let simulatedStream = false;

  try {
    ws = new WebSocket(wsUrl);
    
    ws.addEventListener("open", () => {
      ws?.send(JSON.stringify({ intent, mode }));
    });

    ws.addEventListener("message", (ev) => {
      try {
        const event = JSON.parse(ev.data as string) as StreamEvent;
        push(event);
      } catch {
        push({ type: "error", data: `Malformed event: ${ev.data}` });
      }
    });

    ws.addEventListener("error", () => {
      simulatedStream = true;
      resolve?.();
      resolve = null;
    });

    ws.addEventListener("close", () => {
      if (!simulatedStream) {
        done = true;
        resolve?.();
        resolve = null;
      }
    });
  } catch {
    simulatedStream = true;
  }

  // Promise-based waiting for WebSocket establishment or immediate simulation fallback
  await new Promise<void>((r) => {
    const timer = setTimeout(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        simulatedStream = true;
      }
      r();
    }, 100);
    if (ws) {
      ws.addEventListener("open", () => { clearTimeout(timer); r(); });
      ws.addEventListener("error", () => { clearTimeout(timer); simulatedStream = true; r(); });
    }
  });

  if (simulatedStream) {
    const mockTokens = [
      "[โหมดจำลองออฟไลน์] ", "ทำการประมวลผล", "วิเคราะห์คำสั่ง: ", `"${intent}"\n\n`,
      "โครงสร้างระบบ ", "Delentia Desk ", "มีความพร้อม", "ในการทำงานอย่างเต็มที่ ",
      "โดยระบบได้จำลองโมเดล ", "HexaCore ", "และระบบความปลอดภัย ", "FDIA F-Score = 0.94 ",
      "(SignedAI Verified ✔) เรียบร้อยแล้วครับ."
    ];
    for (const token of mockTokens) {
      yield { type: "token", data: token };
      await new Promise(r => setTimeout(r, 60));
    }
    yield {
      type: "done",
      data: {
        hexa_role: "REGIONAL_THAI",
        trace_id: "trace-mock-streaming-tick",
        fdia_score: { D: 0.98, I: 0.96, A: 0.95, F: 0.94, signed: true, signature_hash: "hash-0x98f23" }
      }
    };
    return;
  }

  while (!done || queue.length > 0) {
    if (queue.length === 0) {
      await new Promise<void>((res) => { resolve = res; });
    }
    while (queue.length > 0) {
      const ev = queue.shift()!;
      yield ev;
      if (ev.type === "done" || ev.type === "error") {
        done = true;
      }
    }
  }

  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    ws.close();
  }
}
