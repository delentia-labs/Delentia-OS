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

export const getGateway = (): string => {
  if (typeof window !== "undefined") {
    const saved = window.localStorage.getItem("delentia_gateway");
    if (saved) return saved;
  }
  return (
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_GATEWAY) ||
    "http://localhost:8000"
  );
};

// The API key is kept in memory for this app session only. Versions before
// 2026-09 saved it in localStorage, in clear text on disk, readable by any
// script on the origin (CodeQL js/clear-text-storage-of-sensitive-data).
let sessionApiKey: string | null = null;
let legacyKeyForgotten = false;

/** Remove an API key an older version saved in clear text. */
export function forgetStoredApiKey(): void {
  if (legacyKeyForgotten || typeof window === "undefined") return;
  window.localStorage.removeItem("delentia_api_key");
  legacyKeyForgotten = true;
}

export function setSessionApiKey(key: string): void {
  sessionApiKey = key || null;
}

export function getSessionApiKey(): string | null {
  return sessionApiKey;
}

export const getApiKey = (): string => {
  forgetStoredApiKey();
  if (sessionApiKey) return sessionApiKey;
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

// Round 50: no offline simulation. When the API cannot be reached the GUI says
// so (offlineError) instead of showing invented results, scores or signatures.
function offlineError(gateway: string, what: string): Error {
  return new Error(
    `เชื่อมต่อ Delentia API ที่ ${gateway} ไม่ได้ จึงไม่ได้${what} ` +
      "(เริ่ม API ด้วย `delentia serve` แล้วลองใหม่)",
  );
}

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
      version: "offline",
      service: "Delentia OS API (unreachable)",
    };
  }
}

/** GET /delentia/system/stats — live ecosystem stats */
export async function getSystemStats(gateway = getGateway()): Promise<SystemStats | null> {
  // Round 50: offline means no numbers. The old fallback showed withdrawn
  // claims (4,849 tests, 62 microservices, 99.98% SLA) as if they were live.
  try {
    const res = await fetch(`${gateway}/delentia/system/stats`);
    return await handleResponse<SystemStats>(res);
  } catch {
    return null;
  }
}

/** GET /delentia/benchmark/summary — radar/bar benchmark data */
export async function getBenchmarkSummary(gateway = getGateway()): Promise<unknown> {
  try {
    const res = await fetch(`${gateway}/delentia/benchmark/summary`);
    return await handleResponse<unknown>(res);
  } catch {
    return { success: false, data: [] };
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
    mode?: "quick" | "standard" | "deep" | "mirror" | "agent";
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
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("[Delentia API]")) throw err;
    throw offlineError(gateway, "ประมวลผลคำสั่งนี้");
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
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("[Delentia API]")) throw err;
    throw offlineError(gateway, "ค้นหาใน RCTDB");
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
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("[Delentia API]")) throw err;
    throw offlineError(gateway, "โหลดประวัติ memory");
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
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("[Delentia API]")) throw err;
    throw offlineError(gateway, "ย้อน memory (ไม่มีอะไรถูกเปลี่ยน)");
  }
}

/** Compute FDIA score locally (offline, no API call needed) */
export function computeFDIALocal(D: number, I: number, A: number): FDIAScore {
  // FDIA invariants (CLAUDE.md "FDIA"): A = 0, I <= 0 or D <= 0 means F = 0.
  // Plain Math.pow(0, 0) is 1, which would score "no intent" as a full pass.
  // I is an exponent, not a [0, 1] value, so it is not clamped to 1.
  const d = Math.max(0, Math.min(1, D));
  const a = Math.max(0, Math.min(1, A));
  const i = Math.max(0, I);
  const F = d <= 0 || i <= 0 || a <= 0 ? 0 : Math.pow(d, i) * a;
  return {
    D: d,
    I: i,
    A: a,
    F: Math.max(0, Math.min(1, F)),
    signed: false,
    signature_hash: "",
  };
}

// ─── Runtime status (Round 50: real values for the status bar) ───────────────
export interface RuntimeTask {
  name: string;
  is_enabled: boolean;
  last_status: string;
  last_output: string | null;
  last_run_at: string | null;
}

export interface RuntimeStatus {
  apiUp: boolean;
  version?: string;
  daemonRunning?: boolean;
  uptimeSeconds?: number;
  tasks: RuntimeTask[];
}

/** GET /health and /v1/daemon/status. Anything unreachable is reported as such, never simulated. */
export async function fetchRuntimeStatus(gateway = getGateway()): Promise<RuntimeStatus> {
  const apiKey = getApiKey();
  const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  try {
    const health = await fetch(`${gateway}/health`, { signal: AbortSignal.timeout(4000) });
    if (!health.ok) return { apiUp: false, tasks: [] };
    const h = await health.json();
    const status: RuntimeStatus = { apiUp: true, version: h?.version, tasks: [] };
    const daemon = await fetch(`${gateway}/v1/daemon/status`, { headers, signal: AbortSignal.timeout(4000) });
    if (daemon.ok) {
      const d = await daemon.json();
      status.daemonRunning = Boolean(d?.running);
      status.uptimeSeconds = typeof d?.uptime_seconds === "number" ? d.uptime_seconds : undefined;
      status.tasks = Array.isArray(d?.tasks) ? d.tasks : [];
    }
    return status;
  } catch {
    return { apiUp: false, tasks: [] };
  }
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
    mode?: "quick" | "standard" | "deep" | "mirror" | "agent";
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
    }, 2500);
    if (ws) {
      ws.addEventListener("open", () => { clearTimeout(timer); r(); });
      ws.addEventListener("error", () => { clearTimeout(timer); simulatedStream = true; r(); });
    }
  });

  if (simulatedStream) {
    // Round 50: no simulated answer and no invented FDIA score or signature.
    // Say plainly that the API was not reached.
    yield {
      type: "error",
      data: `เชื่อมต่อ Delentia API ที่ ${gateway} ไม่ได้ จึงไม่มีการประมวลผลใดๆ ` +
        "เริ่ม API ด้วย `delentia serve` (หรือ `python -m rct_control_plane.cli serve`) แล้วลองใหม่",
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
