# Delentia Ecosystem — Adapter SDK

Build a channel adapter for Delentia OS in under 30 minutes.

---

## Overview

An **adapter** connects an external messaging or enterprise platform (LINE, Slack, Notion, etc.) to the Delentia OS **JITNA v3** intent pipeline. When a message arrives on your platform, the adapter:

1. Verifies the webhook signature (prevents spoofing)
2. Parses the incoming payload into a **JITNA Packet** (`JITNAIntent`)
3. Calls `executeIntent()` from `@delentia/rct-edge`
4. Sends the response back to the user on the platform

---

## Quick Start

```bash
# Copy the template
cp -r sdk/adapter-template/ registry/adapters/my-platform-adapter/

# Install deps
cd registry/adapters/my-platform-adapter
npm install

# Fill in manifest.json
# Implement index.ts
```

---

## File Structure

Each adapter lives in `registry/adapters/<adapter-id>/` and must contain:

```
registry/adapters/my-platform-adapter/
├── manifest.json   # Metadata + security declaration
├── index.ts        # Adapter logic (TypeScript)
└── README.md       # Setup guide (optional but recommended)
```

---

## manifest.json Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | ✅ | Kebab-case unique identifier, e.g. `my-platform-adapter` |
| `name` | `string` | ✅ | Human-readable name |
| `version` | `string` | ✅ | SemVer, e.g. `1.0.0` |
| `description` | `string` | ✅ | One-sentence description |
| `author` | `string` | ✅ | Author or org name |
| `license` | `string` | ✅ | SPDX license, e.g. `Apache-2.0` |
| `jitna_channel` | `string` | ✅ | Lowercase platform name, e.g. `my-platform` |
| `regional_support` | `string[]` | ✅ | ISO 3166-1 codes or `GLOBAL` |
| `security_scan_passed` | `boolean` | ✅ | Set `false` until reviewed; CI sets `true` |
| `permissions` | `string[]` | ✅ | Scopes needed (see Permissions table) |
| `env_required` | `string[]` | ✅ | Environment variable names |
| `tags` | `string[]` | — | Searchable tags |
| `homepage` | `string` | — | Platform homepage URL |
| `repository` | `string` | — | Adapter source repo |

### Permissions

| Permission | Meaning |
|---|---|
| `intent:read` | Read JITNA packet fields |
| `intent:execute` | Call `executeIntent()` |
| `data:read` | Read documents/pages from platform |
| `data:write` | Write/create content on platform |
| `media:read` | Download media files |
| `media:write` | Upload media files |
| `admin:read` | Read admin/org settings |
| `network:read` | Inbound/read network endpoints access |
| `network:outbound` | Outbound network connections (fetch, axios, external HTTP) |

---

## index.ts Pattern

Your adapter must export at minimum one handler function. The recommended pattern:

```typescript
import { executeIntent } from "@delentia/rct-edge";
import type { JITNAIntent, AdapterConfig } from "../../sdk/types";

// 1. Verify incoming webhook signature (NEVER skip this)
export function verifyWebhook(headers: Record<string, string>, body: string, secret: string): boolean {
  // Use HMAC-SHA256 or platform-specific signature method
  // Use timing-safe comparison (crypto.timingSafeEqual)
}

// 2. Parse platform payload → JITNAIntent
export function parsePayload(body: unknown): JITNAIntent | null {
  // Extract user_id, intent_text, channel, session_id from platform payload
}

// 3. Main webhook handler
export async function handleWebhook(
  body: unknown,
  headers: Record<string, string>,
  config: AdapterConfig
): Promise<Response> {
  // Verify → parse → execute → respond
  if (!verifyWebhook(headers, JSON.stringify(body), config.webhookSecret)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const intent = parsePayload(body);
  if (!intent) return new Response("OK", { status: 200 });

  const result = await executeIntent(intent, {
    gateway: config.gateway,
    apiKey: config.apiKey,
  });

  // Send result back to platform
  await sendPlatformMessage(config, intent.user_id, result.response);

  return new Response("OK", { status: 200 });
}
```

---

## Security Checklist

Before submitting your adapter for review, verify:

- [ ] Webhook signature verified on every request (constant-time comparison)
- [ ] All secrets loaded from environment variables — never hardcoded
- [ ] No user PII logged beyond what is needed
- [ ] `security_scan_passed: false` in manifest (reviewer sets `true`)
- [ ] HTTPS-only outbound requests (no `http://` platform API calls)
- [ ] Input validated before calling `executeIntent()`
- [ ] Error responses do not leak internal stack traces

---

## Testing Your Adapter

```bash
# Run the ecosystem test suite
cd registry/adapters/my-platform-adapter
npx jest

# Or run the full ecosystem tests
cd ../../..
pytest tests/ -v
```

Include at minimum:
- Signature verification test (valid + invalid cases)
- Payload parsing test (valid message + edge cases)
- Mock `executeIntent()` and assert response sent to platform

---

## Submitting to the Registry

1. Add your adapter folder under `registry/adapters/`
2. Open a PR to `delentia-labs/delentia-ecosystem`
3. CI will run `pytest tests/` and manifest JSON Schema validation
4. Security review: a maintainer sets `security_scan_passed: true` in your manifest
5. Merged adapters appear in the GUI Ecosystem page and website registry

---

## Environment Variables

All secrets must be declared in `manifest.json` under `env_required`. Document them in your README:

```markdown
| Variable | Description |
|---|---|
| `MY_PLATFORM_WEBHOOK_SECRET` | Used to verify incoming webhook signatures |
| `MY_PLATFORM_API_TOKEN` | Bearer token for sending messages |
| `DELENTIA_GATEWAY` | Delentia OS gateway URL (default: http://localhost:8000) |
| `DELENTIA_API_KEY` | API key issued by Delentia OS admin |
```

---

## Resources

- [JITNA v3 Protocol Spec](https://docs.delentia.com/jitna/v3)
- [FDIA Scoring Reference](https://docs.delentia.com/fdia)
- [rct-edge TypeScript SDK](https://docs.delentia.com/sdk/rct-edge)
- [Ecosystem Registry](https://github.com/delentia-labs/delentia-ecosystem)
- [Delentia OS](https://github.com/delentia-labs/delentia-os)
