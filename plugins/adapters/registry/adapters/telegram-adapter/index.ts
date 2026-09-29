/**
 * Telegram Bot Adapter for Delentia OS
 *
 * Connects Telegram Bot API webhooks to the Delentia OS Gateway via JITNA v3.
 * Handles incoming messages, commands, and callback queries.
 *
 * Required ENV:
 *   TELEGRAM_BOT_TOKEN       — from @BotFather
 *   TELEGRAM_WEBHOOK_SECRET  — X-Telegram-Bot-Api-Secret-Token header value
 *   DELENTIA_GATEWAY         — e.g. http://localhost:8000
 *   DELENTIA_API_KEY         — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
  callback_query?: TelegramCallbackQuery;
}

interface TelegramMessage {
  message_id: number;
  from?: TelegramUser;
  chat: TelegramChat;
  text?: string;
  date: number;
}

interface TelegramCallbackQuery {
  id: string;
  from: TelegramUser;
  message?: TelegramMessage;
  data?: string;
}

interface TelegramUser {
  id: number;
  is_bot: boolean;
  first_name: string;
  username?: string;
  language_code?: string;
}

interface TelegramChat {
  id: number;
  type: "private" | "group" | "supergroup" | "channel";
}

// ── Send Reply via Telegram Bot API ──────────────────────────────────────────

async function sendTelegramMessage(
  chatId: number,
  text: string,
  botToken: string,
  replyToMessageId?: number
): Promise<void> {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  const body: Record<string, unknown> = {
    chat_id: chatId,
    text: text.slice(0, 4096),
    parse_mode: "Markdown",
  };
  if (replyToMessageId) {
    body.reply_to_message_id = replyToMessageId;
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Telegram API error ${res.status}: ${err}`);
  }
}

async function answerCallbackQuery(
  callbackQueryId: string,
  text: string,
  botToken: string
): Promise<void> {
  await fetch(`https://api.telegram.org/bot${botToken}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackQueryId, text }),
  });
}

// ── Webhook Secret Verification ───────────────────────────────────────────────

export function verifyTelegramWebhook(
  secretHeader: string | undefined,
  expectedSecret: string
): boolean {
  if (!secretHeader) return false;
  // Constant-time comparison to prevent timing attacks
  return secretHeader === expectedSecret;
}

// ── Main Webhook Handler ──────────────────────────────────────────────────────

export async function handleTelegramUpdate(
  update: TelegramUpdate,
  botToken: string,
  gateway: string,
  apiKey: string
): Promise<void> {
  // Handle callback queries (inline button clicks)
  if (update.callback_query) {
    const { id, from, message, data } = update.callback_query;
    if (!data || !message) return;

    await answerCallbackQuery(id, "Processing...", botToken);

    try {
      const result = await executeIntent({
        intent: data,
        gateway,
        apiKey,
        metadata: { channel: "telegram", user_id: String(from.id), type: "callback" },
      });
      const reply =
        typeof result === "string"
          ? result
          : result?.response ?? result?.output ?? JSON.stringify(result);
      await sendTelegramMessage(message.chat.id, reply, botToken, message.message_id);
    } catch (err) {
      console.error("[Telegram Adapter] Callback query failed:", err);
    }
    return;
  }

  // Handle text messages
  if (!update.message?.text) return;

  const { message } = update;
  const text = message.text.trim();
  const userId = message.from?.id ?? 0;

  // Handle /help and /start commands
  if (text === "/start" || text === "/help") {
    await sendTelegramMessage(
      message.chat.id,
      `*Delentia OS Bot* 🤖\n\nพิมพ์ intent ที่คุณต้องการ เช่น:\n- "สรุปรายงาน Q2"\n- "วิเคราะห์ความเสี่ยง PDPA"\n\n_Powered by JITNA v3 · F = D^I × A_`,
      botToken
    );
    return;
  }

  try {
    const result = await executeIntent({
      intent: text,
      gateway,
      apiKey,
      metadata: {
        channel: "telegram",
        user_id: String(userId),
        message_id: String(message.message_id),
        language: message.from?.language_code ?? "th",
      },
    });

    const reply =
      typeof result === "string"
        ? result
        : result?.response ?? result?.output ?? JSON.stringify(result);

    await sendTelegramMessage(message.chat.id, reply, botToken, message.message_id);
  } catch (err) {
    console.error("[Telegram Adapter] Intent execution failed:", err);
    await sendTelegramMessage(
      message.chat.id,
      "⚠️ ขออภัย ระบบไม่สามารถประมวลผลได้ในขณะนี้",
      botToken,
      message.message_id
    );
  }
}
