/**
 * Delentia Ecosystem — Adapter Template
 *
 * Copy this file to registry/adapters/<your-adapter-id>/index.ts
 * and replace "MY_PLATFORM" / "MyPlatform" with your platform name.
 *
 * Required exports:
 *   - verifyWebhook()
 *   - parsePayload()
 *   - handleWebhook() (main entry point)
 *
 * See ADAPTER_SDK.md for full documentation.
 */

import { createHmac, timingSafeEqual } from "crypto";
import { executeIntent } from "@delentia/rct-edge";
import type { JITNAIntent, AdapterConfig, ExecuteResult } from "../../sdk/types";

// ── Config ────────────────────────────────────────────────────────────────────

function getConfig(): AdapterConfig {
  const gateway = process.env.DELENTIA_GATEWAY;
  const apiKey = process.env.DELENTIA_API_KEY;
  const webhookSecret = process.env.MY_PLATFORM_WEBHOOK_SECRET;
  const apiToken = process.env.MY_PLATFORM_API_TOKEN;

  if (!gateway || !apiKey || !webhookSecret || !apiToken) {
    throw new Error(
      "Missing required env vars: DELENTIA_GATEWAY, DELENTIA_API_KEY, MY_PLATFORM_WEBHOOK_SECRET, MY_PLATFORM_API_TOKEN"
    );
  }

  return { gateway, apiKey, webhookSecret, platformToken: apiToken };
}

// ── Signature verification ────────────────────────────────────────────────────

/**
 * Verify that the incoming webhook was sent by My Platform.
 *
 * Replace this with the actual signature algorithm your platform uses.
 * Common patterns:
 *   - HMAC-SHA256 over the raw body (LINE, GitHub, WhatsApp)
 *   - Ed25519 public key verification (Discord)
 *   - Simple token comparison (Telegram)
 *
 * NEVER skip this verification — it is your only protection against
 * spoofed requests.
 */
export function verifyWebhook(
  headers: Record<string, string>,
  rawBody: string,
  secret: string
): boolean {
  const signature = headers["x-my-platform-signature"] ?? "";
  if (!signature) return false;

  const hmac = createHmac("sha256", secret).update(rawBody, "utf8").digest("hex");
  const expected = `sha256=${hmac}`;

  try {
    return timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
  } catch {
    return false;
  }
}

// ── Payload types (replace with actual platform types) ────────────────────────

interface MyPlatformMessage {
  userId: string;
  sessionId?: string;
  text: string;
  messageId: string;
}

interface MyPlatformWebhookBody {
  events?: MyPlatformMessage[];
}

// ── Payload parsing ───────────────────────────────────────────────────────────

/**
 * Parse the platform-specific webhook body into a JITNAIntent.
 *
 * Return null if the event should be silently ignored (e.g. delivery receipts).
 */
export function parsePayload(body: unknown): JITNAIntent | null {
  const payload = body as MyPlatformWebhookBody;
  const event = payload?.events?.[0];

  if (!event || !event.text) return null;

  return {
    user_id: event.userId,
    session_id: event.sessionId ?? event.userId,
    intent_text: event.text,
    channel: "my-platform",
    metadata: {
      message_id: event.messageId,
    },
  };
}

// ── Platform reply ────────────────────────────────────────────────────────────

/**
 * Send the AI response back to the user on My Platform.
 *
 * Replace the URL and payload shape with the actual platform API.
 */
async function sendMessage(
  userId: string,
  text: string,
  platformToken: string
): Promise<void> {
  const res = await fetch("https://api.my-platform.example.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${platformToken}`,
    },
    body: JSON.stringify({ to: userId, text }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Platform API error: ${err}`);
  }
}

// ── Main webhook handler ──────────────────────────────────────────────────────

/**
 * Main entry point — wire this to your HTTP route handler.
 *
 * Example (Express):
 *   app.post('/webhook', express.raw({ type: '*\/*' }), async (req, res) => {
 *     const response = await handleWebhook(
 *       JSON.parse(req.body),
 *       Object.fromEntries(Object.entries(req.headers).map(([k, v]) => [k, String(v)])),
 *       getConfig()
 *     );
 *     res.status(response.status).send(await response.text());
 *   });
 */
export async function handleWebhook(
  body: unknown,
  headers: Record<string, string>,
  config: AdapterConfig
): Promise<Response> {
  // 1. Verify signature
  if (!verifyWebhook(headers, JSON.stringify(body), config.webhookSecret)) {
    return new Response("Unauthorized", { status: 401 });
  }

  // 2. Parse payload
  const intent = parsePayload(body);
  if (!intent) {
    // Silently ACK non-actionable events (delivery receipts, etc.)
    return new Response("OK", { status: 200 });
  }

  // 3. Execute intent via Delentia OS
  let result: ExecuteResult;
  try {
    result = await executeIntent(intent, {
      gateway: config.gateway,
      apiKey: config.apiKey,
    });
  } catch (err) {
    console.error("[my-platform-adapter] executeIntent error:", err);
    // Return 200 to prevent platform retry loops
    return new Response("OK", { status: 200 });
  }

  // 4. Send response back to user
  if (result.response && config.platformToken) {
    await sendMessage(intent.user_id, result.response, config.platformToken);
  }

  return new Response("OK", { status: 200 });
}
