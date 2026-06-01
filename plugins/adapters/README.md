# Delentia Ecosystem Registry

[![Validate Adapters](https://img.shields.io/github/actions/workflow/status/delentia-labs/delentia-ecosystem/validate-adapter.yml?branch=main&label=Manifest+CI)](https://github.com/delentia-labs/delentia-ecosystem/actions)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Adapters](https://img.shields.io/badge/Adapters-2-purple)](registry/adapters)
[![Skills](https://img.shields.io/badge/Skills-2-teal)](registry/skills)
[![Registry](https://img.shields.io/badge/Registry-v1.0.0-brightgreen)](https://github.com/delentia-labs/delentia-ecosystem/releases)

**Delentia Ecosystem** is the plugin and skill registry for [Delentia OS](https://github.com/delentia-labs/delentia-os).

Register adapters that connect external platforms (LINE, Slack, etc.) and skills that extend AI capabilities, all via the JITNA v3 protocol.

---

## Architecture

```
delentia-ecosystem/
├── schema/
│   └── adapter-manifest.schema.json   ← JSON Schema v7 (source of truth)
├── registry/
│   ├── adapters/
│   │   ├── line-adapter/
│   │   │   ├── manifest.json          ← Validated against schema
│   │   │   └── index.ts               ← Adapter implementation
│   │   └── slack-adapter/
│   │       ├── manifest.json
│   │       └── index.ts
│   └── skills/
│       ├── thai-language/
│       │   └── manifest.json
│       └── legal-pdpa/
│           └── manifest.json
├── api/
│   ├── registry_api.py                ← FastAPI registry server (port 8090)
│   └── validation.py                  ← JSON Schema validation
└── .github/workflows/
    └── validate-adapter.yml           ← CI for every manifest change
```

---

## Registered Adapters

| ID | Name | Channel | Permissions | Regions |
|---|---|---|---|---|
| `line-adapter` | LINE Messaging Adapter | `line` | intent:read, intent:execute | TH, JP, TW |
| `slack-adapter` | Slack Adapter | `slack` | intent:read, intent:execute, user:read | US, GB, TH, SG |

## Registered Skills

| ID | Name | Permissions | Regions |
|---|---|---|---|
| `thai-language-skill` | Thai Language Constitutional Skill | intent:read, intent:execute, policy:read | TH |
| `legal-pdpa-skill` | PDPA Legal Compliance Skill | intent:read, policy:read | TH |

---

## Registry API

Start the local registry server:

```bash
pip install fastapi uvicorn jsonschema
uvicorn api.registry_api:app --reload --port 8090
```

| Endpoint | Description |
|---|---|
| `GET /adapters` | List all adapters |
| `GET /adapters/{id}` | Get adapter manifest |
| `GET /skills` | List all skills |
| `GET /skills/{id}` | Get skill manifest |
| `GET /search?q=term` | Search adapters + skills |
| `POST /validate` | Validate a manifest JSON |
| `GET /health` | Registry health |

### Example

```bash
curl http://localhost:8090/adapters
curl http://localhost:8090/adapters/line-adapter
curl http://localhost:8090/search?q=thai

curl -X POST http://localhost:8090/validate \
  -H "Content-Type: application/json" \
  -d @registry/adapters/line-adapter/manifest.json
```

---

## Creating an Adapter

1. **Create directory** under `registry/adapters/<your-adapter-id>/`

2. **Create `manifest.json`** following the schema:
   ```json
   {
     "id": "your-adapter",
     "name": "Your Adapter Name",
     "version": "1.0.0",
     "author": { "name": "You", "email": "you@example.com" },
     "description": "What it does",
     "jitna_channel": "your-channel",
     "api_version": ">=2.0.0",
     "permissions": ["intent:read", "intent:execute"],
     "entry_point": "index.ts",
     "regional_support": ["TH"],
     "tags": ["your-tag"],
     "license": "Apache-2.0"
   }
   ```

3. **Implement `index.ts`** — use `@delentia/rct-edge` `executeIntent()`:
   ```typescript
   import { executeIntent } from "@delentia/rct-edge";

   export async function handleWebhook(body: unknown): Promise<void> {
     const result = await executeIntent(intent, { apiKey, gateway, channel: "your-channel" });
     // reply with result.output.result
   }
   ```

4. **Validate locally**:
   ```bash
   python -c "
   import json
   from api.validation import validate_manifest
   validate_manifest(json.load(open('registry/adapters/your-adapter/manifest.json')))
   print('Valid!')
   "
   ```

5. **Open a PR** — CI runs `validate-adapter.yml` automatically.

> **Common validation errors:**
> ```
> ManifestValidationError: 'jitna_channel' is a required property
> ManifestValidationError: 'permissions[0]' must be one of: intent:read, intent:execute, memory:read...
> ManifestValidationError: 'api_version' must match pattern '^[><=~^]{1,2}\d+\.\d+\.\d+$'
> ```
> Run `python -c "from api.validation import validate_manifest; ..."` locally before pushing.

---

## Permissions Reference

| Permission | Description |
|---|---|
| `intent:read` | Read intent context and history |
| `intent:execute` | Submit intents to the kernel |
| `memory:read` | Read memory deltas |
| `memory:write` | Write/rollback memory (requires justification) |
| `policy:read` | Read constitutional policies |
| `policy:write` | Modify policies (enterprise only) |
| `user:read` | Read anonymized user metadata |
| `metrics:read` | Read system metrics |

---

## Related Repositories

| Repo | Purpose |
|---|---|
| [delentia-os](https://github.com/delentia-labs/delentia-os) | Core OS — JITNA v3, FDIA, IntentKernel |
| [delentia-ai](https://github.com/delentia-labs/delentia-ai) | SLM fine-tuning factory |
| [delentia-gui](https://github.com/delentia-labs/delentia-gui) | Desktop app |
| [delentia-infra-public](https://github.com/delentia-labs/delentia-infra-public) | Community deployment |
| [delentia-infra-enterprise](https://github.com/delentia-labs/delentia-infra-enterprise) | Enterprise Kubernetes + HA |

---

## License

Apache 2.0 — © 2026 Delentia Labs
