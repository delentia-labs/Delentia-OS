/**
 * delentia-client.ts
 *
 * Gateway address and API token handling for Delentia Desk. Everything else
 * the Desk shows comes through lib/desk-api.ts (typed calls to /v1/desk/*).
 */

import type { HealthResponse } from "./types";

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

/**
 * fetch() against the configured gateway with the session API token, for
 * pages that call the API directly. Round 50: these pages used a hardcoded
 * http://127.0.0.1:8000 and sent no token, so they ignored the Settings
 * gateway and failed with 401 whenever DELENTIA_API_TOKEN was set.
 */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const key = getApiKey();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  if (key && !headers.Authorization) headers.Authorization = `Bearer ${key}`;
  return fetch(`${getGateway()}${path}`, { ...init, headers });
}

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
