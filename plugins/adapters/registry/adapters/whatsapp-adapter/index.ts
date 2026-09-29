/**
 * WhatsApp Business Cloud API Adapter for Delentia OS
 *
 * Connects WhatsApp Business webhooks to the Delentia OS Gateway via JITNA v3.
 * Handles incoming messages, routes them as intents, and replies
 * with the AI-generated response using WhatsApp message templates.
 *
 * Required ENV:
 *   WHATSAPP_PHONE_NUMBER_ID  — your WhatsApp Business phone number ID
 *   WHATSAPP_ACCESS_TOKEN     — Meta Graph API access token
 *   WHATSAPP_VERIFY_TOKEN     — webhook verification token (any secret string)
 *   DELENTIA_GATEWAY          — e.g. http://localhost:8000
 *   DELENTIA_API_KEY          — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";

// ── Types ─────────────────────────────────────────────────────────────────────

interface WhatsAppWebhookBody {
  object: string;
  entry: WhatsAppEntry[];
}

interface WhatsAppEntry {
  id: string;
  changes: WhatsAppChange[];
}

interface WhatsAppChange {
  value: {
    messaging_product: string;
    metadata: { phone_number_id: string; display_phone_number: string };
    contacts?: Array<{ wa_id: string; profile: { name: string } }>;
    messages?: WhatsAppMessage[];
    statuses?: Array<{ id: string; status: string }>;
  };
  field: string;
}

interface WhatsAppMessage {
  id: string;
  from: string;
  timestamp: string;
  type: "text" | "image" | "audio" | "document" | "interactive" | "button";
  text?: { body: string };
  interactive?: {
    type: "button_reply" | "list_reply";
    button_reply?: { id: string; title: string };
  };
}

// ── Send Reply via WhatsApp Cloud API ─────────────────────────────────────────

async function sendWhatsAppMessage(
  to: string,
  text: string,
  phoneNumberId: string,
  accessToken: string
): Promise<void> {
  const url = `https://graph.facebook.com/v19.0/${phoneNumberId}/messages`;
  const body = {
    messaging_product: "whatsapp",
    recipient_type: "individual",
    to,
    type: "text",
    text: { preview_url: false, body: text.slice(0, 4096) },
  };

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`WhatsApp API error ${res.status}: ${err}`);
  }
}

// ── Webhook Verification ──────────────────────────────────────────────────────

export function verifyWebhook(
  mode: string,
  token: string,
  challenge: string,
  verifyToken: string
): string | null {
  if (mode === "subscribe" && token === verifyToken) {
    return challenge;
  }
  return null;
}

// ── Main Webhook Handler ──────────────────────────────────────────────────────

export async function handleWhatsAppWebhook(
  body: WhatsAppWebhookBody,
  phoneNumberId: string,
  accessToken: string,
  gateway: string,
  apiKey: string
): Promise<void> {
  for (const entry of body.entry ?? []) {
    for (const change of entry.changes ?? []) {
      const { messages } = change.value;
      if (!messages) continue;

      for (const msg of messages) {
        // Extract text from supported message types
        let intentText: string | undefined;

        if (msg.type === "text" && msg.text?.body) {
          intentText = msg.text.body.trim();
        } else if (
          msg.type === "interactive" &&
          msg.interactive?.button_reply?.title
        ) {
          intentText = msg.interactive.button_reply.title;
        }

        if (!intentText) continue;

        try {
          // Route to Delentia OS via JITNA v3
          const result = await executeIntent({
            intent: intentText,
            gateway,
            apiKey,
            metadata: {
              channel: "whatsapp",
              user_id: msg.from,
              message_id: msg.id,
            },
          });

          const reply =
            typeof result === "string"
              ? result
              : result?.response ?? result?.output ?? JSON.stringify(result);

          await sendWhatsAppMessage(msg.from, reply, phoneNumberId, accessToken);
        } catch (err) {
          console.error("[WhatsApp Adapter] Intent execution failed:", err);
          await sendWhatsAppMessage(
            msg.from,
            "ขออภัย ระบบไม่สามารถประมวลผลได้ในขณะนี้ / Sorry, unable to process your request right now.",
            phoneNumberId,
            accessToken
          );
        }
      }
    }
  }
}
