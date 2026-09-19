# Deploying the Python Kernel API (Real HTTP Bridge, Production Prep)

**Status:** prep-only (Round 32). Nothing here has been deployed to a real,
publicly-reachable host by this engagement — this document exists so the
Architect can complete the last real step (choosing and provisioning a
host) whenever ready, without another round needing to re-derive the
wiring from scratch.

## Why this exists

Round 31 built and verified (locally, via `uvicorn` + real `curl` calls,
plus the real TS bridge logic run as Node.js against it) a real HTTP
bridge: `POST /v1/kernel/fdia/evaluate` on this repo's FastAPI app, called
from `delentia-mcp-ecosystem`'s deployed Cloudflare Worker via
`packages/fdia/src/pythonKernelBridge.ts`. That bridge only activates when
the Worker's `PYTHON_KERNEL_URL` environment variable points at a real,
running instance of this API. Today, no such instance exists outside a
developer's own machine.

## 1. Build the container

```bash
docker build -t delentia-os-kernel .
docker run -p 8000:8000 delentia-os-kernel
```

(Not verified this round — the Docker daemon was not running on the
machine this was written on. Docker's CLI was present; verify the build
once the daemon is available.)

## 2. Choose a real host

Any of these work with the `Dockerfile` as-is (this is not a recommendation
of one over another — the Architect's own cost/ops preference decides):

- A VPS you already control (the exchange bridge's own docstring already
  references "Cloud VPS" as part of Delentia's existing multi-machine
  setup — if that VPS already exists, it may be the simplest option).
- Fly.io, Railway, Render, or a similar container-first PaaS.
- A Cloudflare-adjacent option (e.g. a Cloudflare Tunnel to a home/office
  machine) if avoiding a separate paid host is a priority.

Whichever is chosen, the result needed for step 3 is one thing: a real,
stable HTTPS URL that reaches port 8000 of the running container.

## 3. Wire the URL into the deployed Cloudflare Worker

In `delentia-mcp-ecosystem/packages/fdia/wrangler.jsonc`, add the real URL
to the existing `vars` block (this is not a secret — it's just a URL, so
`vars` is correct, not `wrangler secret put`):

```jsonc
"vars": {
  "ENVIRONMENT": "production",
  "SERVER_NAME": "Delentia FDIA Security MCP",
  "PYTHON_KERNEL_URL": "https://<your-real-host>"
}
```

Then deploy the Worker for real:

```bash
cd delentia-mcp-ecosystem/packages/fdia
npx wrangler deploy
```

**This last command is a real, production-affecting action against the
Architect's actual deployed Worker.** No round of this engagement has run
it without the Architect first confirming a specific, real, already-
reachable host — do the same here.

## 4. Verify end-to-end in production

```bash
curl -X POST https://<your-real-host>/v1/kernel/fdia/evaluate \
  -H "Content-Type: application/json" \
  -d '{"data_quality":0.98,"intent_precision":1.0,"authorized":1.0}'
```

Then call the deployed `evaluate_fdia` MCP tool for real and confirm the
response includes a real `python_kernel_cross_check` field (only present
when the bridge call succeeded — see `worker.ts`'s handler).
