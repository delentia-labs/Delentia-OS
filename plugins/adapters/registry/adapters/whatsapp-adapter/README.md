# WhatsApp Business Adapter

Connects WhatsApp Business Cloud API to **Delentia OS** via JITNA v3 intent routing.

## Features
- Handles incoming text + interactive button messages
- Routes intent through Delentia OS Gateway
- Sends AI response back to user via WhatsApp Cloud API
- Webhook verification for Meta's security handshake

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WHATSAPP_PHONE_NUMBER_ID` | From Meta Business Manager → WhatsApp → Phone Numbers |
| `WHATSAPP_ACCESS_TOKEN` | Meta Graph API permanent access token |
| `WHATSAPP_VERIFY_TOKEN` | Your custom webhook verification secret |
| `DELENTIA_GATEWAY` | Delentia OS gateway URL (default: `http://localhost:8000`) |
| `DELENTIA_API_KEY` | Bearer token for `/v1/*` endpoints |

## Quick Start

```bash
# 1. Install
npm install

# 2. Configure .env
cp .env.example .env

# 3. Register webhook at Meta Business Manager
# URL: https://your-domain.com/webhook/whatsapp
# Verify Token: your WHATSAPP_VERIFY_TOKEN
```

## Webhook Endpoints

```
GET  /webhook/whatsapp   — Meta webhook verification
POST /webhook/whatsapp   — Incoming message handler
```

## JITNA Channel

`whatsapp` — messages are routed via `jitna_channel: "whatsapp"` in the manifest.

## Regional Support

Optimized for: 🇹🇭 TH · 🇧🇷 BR · 🇮🇳 IN · 🇺🇸 US · 🌍 GLOBAL
