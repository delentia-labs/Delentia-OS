/**
 * LINE Messaging Adapter for Delentia OS
 *
 * Connects LINE webhooks to the Delentia OS Gateway via JITNA v3.
 * Handles incoming LINE events, routes them as intents, and replies
 * with the AI-generated response.
 *
 * Required ENV:
 *   LINE_CHANNEL_SECRET   — for webhook signature verification
 *   LINE_CHANNEL_ACCESS_TOKEN — for reply API calls
 *   DELENTIA_GATEWAY      — e.g. http://localhost:8000
 *   DELENTIA_API_KEY      — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LineWebhookBody {
  destination: string;
  events: LineEvent[];
}

interface LineEvent {
  type: "message" | "follow" | "unfollow" | "postback";
  replyToken?: string;
  source: { type: string; userId?: string; groupId?: string };
  message?: { type: "text" | "sticker" | "image"; id: string; text?: string };
}

// ── Signature Verification ────────────────────────────────────────────────────

async function verifyLineSignature(
  body: string,
  signature: string,
  channelSecret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(channelSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const computed = btoa(String.fromCharCode(...new Uint8Array(mac)));
  return computed === signature;
}

// ── Reply to LINE ─────────────────────────────────────────────────────────────

async function replyToLine(
  replyToken: string,
  text: string,
  accessToken: string
): Promise<void> {
  await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text: text.slice(0, 5000) }], // LINE 5000 char limit
    }),
  });
}

// ── Main Webhook Handler ──────────────────────────────────────────────────────

export async function handleWebhook(
  body: string,
  signature: string,
  options: {
    channelSecret?: string;
    accessToken?: string;
    gateway?: string;
    apiKey?: string;
  } = {}
): Promise<{ status: number; body: string }> {
  const channelSecret = options.channelSecret ?? process.env.LINE_CHANNEL_SECRET ?? "";
  const accessToken   = options.accessToken ?? process.env.LINE_CHANNEL_ACCESS_TOKEN ?? "";
  const gateway       = options.gateway ?? process.env.DELENTIA_GATEWAY ?? "http://localhost:8000";
  const apiKey        = options.apiKey ?? process.env.DELENTIA_API_KEY ?? "";

  // Verify LINE signature
  const valid = await verifyLineSignature(body, signature, channelSecret);
  if (!valid) {
    return { status: 401, body: JSON.stringify({ error: "Invalid LINE signature" }) };
  }

  let parsed: LineWebhookBody;
  try {
    parsed = JSON.parse(body) as LineWebhookBody;
  } catch {
    return { status: 400, body: JSON.stringify({ error: "Invalid JSON" }) };
  }

  // Process each event (LINE may batch multiple)
  const promises = parsed.events.map(async (event) => {
    if (event.type !== "message" || event.message?.type !== "text") return;
    if (!event.replyToken || !event.message.text) return;

    const intent  = event.message.text;
    const userId  = event.source.userId ?? "anonymous";

    try {
      const result = await executeIntent(intent, {
        apiKey,
        gateway,
        mode: "standard",
        userId: `line:${userId}`,
        channel: "line",
      });

      await replyToLine(event.replyToken, result.output.result, accessToken);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Service error";
      await replyToLine(event.replyToken, `⚠️ ${msg}`, accessToken);
    }
  });

  await Promise.all(promises);
  return { status: 200, body: JSON.stringify({ status: "ok" }) };
}

/** Send a proactive message to a LINE user (not a reply) */
export async function sendMessage(
  userId: string,
  text: string,
  options: { accessToken?: string } = {}
): Promise<void> {
  const accessToken = options.accessToken ?? process.env.LINE_CHANNEL_ACCESS_TOKEN ?? "";
  await fetch("https://api.line.me/v2/bot/message/push", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      to: userId,
      messages: [{ type: "text", text: text.slice(0, 5000) }],
    }),
  });
}
