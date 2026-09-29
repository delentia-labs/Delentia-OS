/**
 * Slack Adapter for Delentia OS
 *
 * Handles:
 *   - /delentia <intent>  slash command
 *   - @Delentia <intent>  app mentions in channels
 *   - Interactive component callbacks (button actions)
 *
 * Required ENV:
 *   SLACK_SIGNING_SECRET   — for request signature verification
 *   SLACK_BOT_TOKEN        — xoxb-... token for API calls
 *   DELENTIA_GATEWAY       — e.g. http://localhost:8000
 *   DELENTIA_API_KEY       — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";
import * as crypto from "crypto";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SlackSlashCommand {
  command: string;
  text: string;
  user_id: string;
  channel_id: string;
  response_url: string;
}

interface SlackEvent {
  type: "event_callback";
  event: {
    type: "app_mention" | "message";
    text: string;
    user: string;
    channel: string;
    ts: string;
  };
}

interface SlackBlock {
  type: string;
  text?: { type: string; text: string };
}

// ── Signature Verification ────────────────────────────────────────────────────

function verifySlackSignature(
  signingSecret: string,
  body: string,
  timestamp: string,
  signature: string
): boolean {
  // Reject stale requests (> 5 min) to prevent replay attacks
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp)) > 300) {
    return false;
  }

  const basestring = `v0:${timestamp}:${body}`;
  const expected   = "v0=" + crypto
    .createHmac("sha256", signingSecret)
    .update(basestring)
    .digest("hex");

  // Constant-time comparison
  return crypto.timingSafeEqual(
    Buffer.from(expected, "ascii"),
    Buffer.from(signature, "ascii")
  );
}

// ── Slack API helpers ─────────────────────────────────────────────────────────

async function postMessage(
  channel: string,
  text: string,
  blocks: SlackBlock[] | null,
  botToken: string
): Promise<void> {
  await fetch("https://slack.com/api/chat.postMessage", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${botToken}`,
    },
    body: JSON.stringify({ channel, text, blocks }),
  });
}

function buildResponseBlocks(intent: string, result: string, fdia?: number): SlackBlock[] {
  return [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: result.slice(0, 3000), // Slack block limit
      },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `Intent: \`${intent.slice(0, 80)}\`${fdia !== undefined ? `  •  FDIA: *${fdia.toFixed(3)}*` : ""}  •  Delentia OS`,
        },
      ],
    },
  ] as SlackBlock[];
}

// ── Slash Command Handler ─────────────────────────────────────────────────────

export async function handleSlashCommand(
  body: SlackSlashCommand,
  rawBody: string,
  timestamp: string,
  signature: string,
  options: { signingSecret?: string; botToken?: string; gateway?: string; apiKey?: string } = {}
): Promise<{ status: number; body: string }> {
  const signingSecret = options.signingSecret ?? process.env.SLACK_SIGNING_SECRET ?? "";
  const botToken      = options.botToken ?? process.env.SLACK_BOT_TOKEN ?? "";
  const gateway       = options.gateway ?? process.env.DELENTIA_GATEWAY ?? "http://localhost:8000";
  const apiKey        = options.apiKey ?? process.env.DELENTIA_API_KEY ?? "";

  if (!verifySlackSignature(signingSecret, rawBody, timestamp, signature)) {
    return { status: 401, body: JSON.stringify({ error: "Invalid Slack signature" }) };
  }

  const intent = body.text?.trim();
  if (!intent) {
    return {
      status: 200,
      body: JSON.stringify({
        response_type: "ephemeral",
        text: "Usage: `/delentia <your intent>`",
      }),
    };
  }

  // Immediate ACK (Slack requires < 3s response)
  setTimeout(async () => {
    try {
      const result = await executeIntent(intent, {
        apiKey, gateway, mode: "standard",
        userId: `slack:${body.user_id}`,
        channel: "slack",
      });
      const fdia = result.output.fdia_score?.F;
      const blocks = buildResponseBlocks(intent, result.output.result, fdia);

      await fetch(body.response_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response_type: "in_channel", text: result.output.result, blocks }),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Service error";
      await fetch(body.response_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response_type: "ephemeral", text: `⚠️ ${msg}` }),
      });
    }
  }, 0);

  return {
    status: 200,
    body: JSON.stringify({
      response_type: "ephemeral",
      text: `Processing: _${intent.slice(0, 80)}_…`,
    }),
  };
}

// ── App Mention Handler ───────────────────────────────────────────────────────

export async function handleAppMention(
  event: SlackEvent["event"],
  botUserId: string,
  options: { signingSecret?: string; botToken?: string; gateway?: string; apiKey?: string } = {}
): Promise<void> {
  const botToken = options.botToken ?? process.env.SLACK_BOT_TOKEN ?? "";
  const gateway  = options.gateway ?? process.env.DELENTIA_GATEWAY ?? "http://localhost:8000";
  const apiKey   = options.apiKey ?? process.env.DELENTIA_API_KEY ?? "";

  // Strip the bot mention from the intent text
  const intent = event.text
    .replace(new RegExp(`<@${botUserId}>`, "g"), "")
    .trim();

  if (!intent) {
    await postMessage(event.channel, "Please include an intent after the mention.", null, botToken);
    return;
  }

  try {
    const result = await executeIntent(intent, {
      apiKey, gateway, mode: "standard",
      userId: `slack:${event.user}`,
      channel: "slack",
    });
    const fdia = result.output.fdia_score?.F;
    const blocks = buildResponseBlocks(intent, result.output.result, fdia);
    await postMessage(event.channel, result.output.result, blocks, botToken);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Service error";
    await postMessage(event.channel, `⚠️ ${msg}`, null, botToken);
  }
}
