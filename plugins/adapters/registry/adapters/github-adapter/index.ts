/**
 * GitHub App Adapter for Delentia OS
 *
 * Connects GitHub webhooks to the Delentia OS Gateway via JITNA v3.
 * Handles issue comments, PR reviews, and repository dispatch events.
 *
 * Required ENV:
 *   GITHUB_WEBHOOK_SECRET  — for HMAC signature verification
 *   GITHUB_APP_TOKEN       — GitHub App installation token for API calls
 *   DELENTIA_GATEWAY       — e.g. http://localhost:8000
 *   DELENTIA_API_KEY       — Bearer token for /v1/* endpoints
 */

import { executeIntent } from "@delentia/rct-edge";
import * as crypto from "crypto";

// ── Types ─────────────────────────────────────────────────────────────────────

type GitHubEventType =
  | "issue_comment"
  | "pull_request_review_comment"
  | "pull_request"
  | "repository_dispatch"
  | "issues";

interface GitHubIssueCommentEvent {
  action: "created" | "edited" | "deleted";
  issue: { number: number; title: string; body: string | null; html_url: string };
  comment: { id: number; body: string; user: { login: string } };
  repository: { full_name: string; html_url: string };
  installation?: { id: number };
}

interface GitHubPRReviewCommentEvent {
  action: "created";
  pull_request: { number: number; title: string; html_url: string };
  comment: { body: string; path: string; line: number | null; user: { login: string } };
  repository: { full_name: string };
}

// ── HMAC Signature Verification ──────────────────────────────────────────────

export function verifyGitHubSignature(
  payload: string,
  signature: string,
  secret: string
): boolean {
  const expected = `sha256=${crypto
    .createHmac("sha256", secret)
    .update(payload)
    .digest("hex")}`;
  // Constant-time comparison
  try {
    return crypto.timingSafeEqual(
      Buffer.from(signature, "utf8"),
      Buffer.from(expected, "utf8")
    );
  } catch {
    return false;
  }
}

// ── Post GitHub Comment ───────────────────────────────────────────────────────

async function postIssueComment(
  repoFullName: string,
  issueNumber: number,
  body: string,
  token: string
): Promise<void> {
  const url = `https://api.github.com/repos/${repoFullName}/issues/${issueNumber}/comments`;
  await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ body: body.slice(0, 65536) }),
  });
}

// ── Main Webhook Handler ──────────────────────────────────────────────────────

export async function handleGitHubWebhook(
  eventType: GitHubEventType,
  payload: GitHubIssueCommentEvent | GitHubPRReviewCommentEvent,
  appToken: string,
  gateway: string,
  apiKey: string
): Promise<void> {
  // Handle issue comments that mention @delentia-bot or /delentia command
  if (eventType === "issue_comment") {
    const event = payload as GitHubIssueCommentEvent;
    if (event.action !== "created") return;

    const body = event.comment.body.trim();
    const mentionMatch = body.match(/(?:@delentia(?:-bot)?|\/delentia)\s+(.+)/i);
    if (!mentionMatch) return;

    const intentText = mentionMatch[1].trim();
    const repoFullName = event.repository.full_name;
    const issueNumber = event.issue.number;

    try {
      const result = await executeIntent({
        intent: intentText,
        gateway,
        apiKey,
        metadata: {
          channel: "github",
          user_id: event.comment.user.login,
          repo: repoFullName,
          issue_number: String(issueNumber),
          issue_title: event.issue.title,
        },
      });

      const reply =
        typeof result === "string"
          ? result
          : result?.response ?? result?.output ?? JSON.stringify(result);

      await postIssueComment(
        repoFullName,
        issueNumber,
        `> 🤖 **Delentia OS Response** (JITNA v3 · FDIA scored)\n\n${reply}`,
        appToken
      );
    } catch (err) {
      console.error("[GitHub Adapter] Intent failed:", err);
      await postIssueComment(
        repoFullName,
        issueNumber,
        "⚠️ Delentia OS: Unable to process intent at this time.",
        appToken
      );
    }
  }
}
