/**
 * Discord Bot Adapter for Delentia OS
 *
 * Connects Discord interactions (slash commands + mentions) to the
 * Delentia OS Gateway via JITNA v3.
 *
 * Required ENV:
 *   DISCORD_PUBLIC_KEY      — from Discord Developer Portal (for signature verification)
 *   DISCORD_BOT_TOKEN       — Bot token for REST API calls
 *   DISCORD_APPLICATION_ID  — Your Discord application ID
 *   DELENTIA_GATEWAY        — e.g. http://localhost:8000
 *   DELENTIA_API_KEY        — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";
import * as crypto from "crypto";

// ── Types ─────────────────────────────────────────────────────────────────────

export const InteractionType = {
  PING: 1,
  APPLICATION_COMMAND: 2,
  MESSAGE_COMPONENT: 3,
} as const;

export const InteractionResponseType = {
  PONG: 1,
  CHANNEL_MESSAGE_WITH_SOURCE: 4,
  DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: 5,
} as const;

interface DiscordInteraction {
  id: string;
  application_id: string;
  type: number;
  data?: {
    name: string;
    options?: Array<{ name: string; value: string }>;
  };
  member?: { user: { id: string; username: string } };
  user?: { id: string; username: string };
  channel_id?: string;
  token: string;
}

// ── Ed25519 Signature Verification ───────────────────────────────────────────

export function verifyDiscordRequest(
  publicKey: string,
  signature: string,
  timestamp: string,
  body: string
): boolean {
  try {
    const isValid = crypto.verify(
      "ed25519",
      Buffer.from(timestamp + body),
      Buffer.from(publicKey, "hex"),
      Buffer.from(signature, "hex")
    );
    return isValid;
  } catch {
    return false;
  }
}

// ── Follow-up via Discord Webhook ─────────────────────────────────────────────

async function sendFollowUpMessage(
  applicationId: string,
  interactionToken: string,
  content: string
): Promise<void> {
  const url = `https://discord.com/api/v10/webhooks/${applicationId}/${interactionToken}`;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: content.slice(0, 2000) }),
  });
}

// ── Main Interaction Handler ──────────────────────────────────────────────────

export async function handleDiscordInteraction(
  interaction: DiscordInteraction,
  applicationId: string,
  gateway: string,
  apiKey: string
): Promise<{ type: number; data?: { content: string } }> {
  // PING — Discord health check
  if (interaction.type === InteractionType.PING) {
    return { type: InteractionResponseType.PONG };
  }

  // Slash command: /delentia <intent>
  if (interaction.type === InteractionType.APPLICATION_COMMAND) {
    const intentOption = interaction.data?.options?.find(
      (o) => o.name === "intent"
    );
    const intentText = intentOption?.value?.trim();

    if (!intentText) {
      return {
        type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        data: { content: "⚠️ Please provide an intent. Usage: `/delentia intent:<your request>`" },
      };
    }

    const userId =
      interaction.member?.user.id ?? interaction.user?.id ?? "unknown";

    // Defer response — Discord requires reply within 3s
    // The actual reply is sent as a follow-up webhook
    setTimeout(async () => {
      try {
        const result = await executeIntent({
          intent: intentText,
          gateway,
          apiKey,
          metadata: {
            channel: "discord",
            user_id: userId,
            command: interaction.data?.name ?? "delentia",
          },
        });
        const reply =
          typeof result === "string"
            ? result
            : result?.response ?? result?.output ?? JSON.stringify(result);
        await sendFollowUpMessage(applicationId, interaction.token, reply);
      } catch (err) {
        console.error("[Discord Adapter] Intent failed:", err);
        await sendFollowUpMessage(
          applicationId,
          interaction.token,
          "⚠️ Unable to process intent. Please try again."
        );
      }
    }, 0);

    return { type: InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE };
  }

  return {
    type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
    data: { content: "Unsupported interaction type." },
  };
}
