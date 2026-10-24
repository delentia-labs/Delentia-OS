/**
 * local-config.ts (Round 92)
 *
 * The one-click launcher (scripts/open_desk.py, OPEN_DESK.bat) serves this app from 127.0.0.1 and also answers GET /__delentia_local.json with the address of the host and the owner's API token,
 * so the owner does not have to open a settings page and paste a token. Everywhere else that path does not exist (the dev server, the Tauri app, a hosted copy) and this does nothing.
 *
 * Why not put the token in the address: a token in a URL ends up in the browser history and in logs. Here it travels only from the launcher's loopback server to this page, is kept in memory
 * (setSessionApiKey, never localStorage) and is gone when the tab closes. Only the gateway address is remembered, as before.
 */
import { setSessionApiKey } from "./delentia-client";

export function isLoopbackPage(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host === "127.0.0.1" || host === "localhost" || host === "[::1]" || host === "::1";
}

export async function loadLocalConfig(): Promise<boolean> {
  if (!isLoopbackPage()) return false;
  try {
    const res = await fetch("/__delentia_local.json", { cache: "no-store" });
    if (!res.ok) return false;
    const body = (await res.json()) as { gateway?: unknown; token?: unknown };
    if (typeof body.token === "string" && body.token) setSessionApiKey(body.token);
    if (typeof body.gateway === "string" && /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(body.gateway)) {
      try {
        window.localStorage.setItem("delentia_gateway", body.gateway);
      } catch {
        /* storage blocked: the default gateway (http://localhost:8000) is used */
      }
    }
    return true;
  } catch {
    return false;
  }
}
