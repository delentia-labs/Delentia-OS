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
 *   POST /v1/delentiadb/query         — Bearer auth required
 */

import type {
  FDIAScore,
  HealthResponse,
  IntentExecuteResponse,
  MemoryDelta,
  QueryResponse,
  SystemStats,
} from "./types";

const getGateway = (): string =>
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_GATEWAY) ||
  "http://localhost:8000";

const getApiKey = (): string =>
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_KEY) || "";

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
// PUBLIC — no auth
// ─────────────────────────────────────────────

/** GET /health — poll every 30 s to show connection status */
export async function getHealthStatus(
  gateway = getGateway()
): Promise<HealthResponse> {
  const res = await fetch(`${gateway}/health`);
  return handleResponse<HealthResponse>(res);
}

/** GET /delentia/system/stats — live ecosystem stats */
export async function getSystemStats(gateway = getGateway()): Promise<SystemStats> {
  const res = await fetch(`${gateway}/delentia/system/stats`);
  return handleResponse<SystemStats>(res);
}

/** GET /delentia/benchmark/summary — radar/bar benchmark data */
export async function getBenchmarkSummary(gateway = getGateway()): Promise<unknown> {
  const res = await fetch(`${gateway}/delentia/benchmark/summary`);
  return handleResponse<unknown>(res);
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

  const res = await fetch(`${gateway}/v1/kernel/execute`, {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ intent, mode, context: { user_id: userId } }),
  });
  return handleResponse<IntentExecuteResponse>(res);
}

/** POST /v1/delentiadb/query — vector / graph / hybrid search */
export async function queryDelentiaDB(
  query: string,
  queryType: "vector" | "graph" | "hybrid" = "hybrid",
  options: { apiKey?: string; gateway?: string; topK?: number } = {}
): Promise<QueryResponse> {
  const { apiKey = getApiKey(), gateway = getGateway(), topK = 5 } = options;

  const res = await fetch(`${gateway}/v1/delentiadb/query`, {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ query, query_type: queryType, top_k: topK }),
  });
  return handleResponse<QueryResponse>(res);
}

/** GET /v1/memory/history — fetch delta timeline entries */
export async function getMemoryHistory(
  options: { apiKey?: string; gateway?: string; limit?: number } = {}
): Promise<MemoryDelta[]> {
  const { apiKey = getApiKey(), gateway = getGateway(), limit = 50 } = options;

  const res = await fetch(`${gateway}/v1/memory/history?limit=${limit}`, {
    headers: authHeaders(apiKey),
  });
  return handleResponse<MemoryDelta[]>(res);
}

/** POST /v1/memory/rollback — roll back N memory ticks */
export async function rollbackMemory(
  ticks: number,
  options: { apiKey?: string; gateway?: string } = {}
): Promise<{ success: boolean; rolledback_to_tick: number }> {
  const { apiKey = getApiKey(), gateway = getGateway() } = options;

  const res = await fetch(`${gateway}/v1/memory/rollback`, {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ ticks }),
  });
  return handleResponse(res);
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
 *
 * Yields StreamEvent objects as they arrive from the gateway:
 *   { type: "token",  data: " word " }        — partial text token
 *   { type: "fdia",   data: FDIAScore }        — FDIA scores
 *   { type: "done",   data: { ... } }          — stream complete
 *   { type: "error",  data: "message" }        — fatal error
 *
 * Usage:
 *   for await (const event of streamIntent("summarize ...", opts)) {
 *     if (event.type === "token") setPartial(p => p + event.data);
 *   }
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

  let ws: WebSocket;
  try {
    ws = new WebSocket(wsUrl);
  } catch {
    yield { type: "error", data: `Cannot open WebSocket to ${wsUrl}` };
    return;
  }

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({ intent, mode }));
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
    push({ type: "error", data: "WebSocket connection error" });
    done = true;
    resolve?.();
    resolve = null;
  });

  ws.addEventListener("close", () => {
    done = true;
    resolve?.();
    resolve = null;
  });

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

  if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
    ws.close();
  }
}
