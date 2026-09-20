# Deploying the Python Kernel API (Real HTTP Bridge, Production Prep)

**Status:** the container is now genuinely built and verified working
end-to-end (Round 35) — `docker build` succeeds, the running container's
`/v1/kernel/fdia/evaluate`, `/health`, `/delentia/system/stats`, and
`/v1/memory/history` endpoints all confirmed returning real, varying,
correctly-computed data via real `curl` calls. What's still prep-only:
nothing has been deployed to a real, publicly-reachable host yet — this
document exists so the Architect can complete that last real step
(choosing and provisioning a host) whenever ready.

**Round 35 build fixes (4 real issues found and fixed via actually running
`docker build`, not assumed):** the base `requirements.txt` alone isn't
enough - `algorithm_kernel_41.py` is monolithic and imports all 41
algorithms' dependencies at construction time, even for this one
lightweight endpoint. Fixed: (1) `robotexclusionrulesparser` was
genuinely undeclared in every manifest; (2) `pyproject.toml`'s `full`
extras group needed manual sync with `web-intelligence`'s deps (it's a
flat list, not a composition); (3) the default `torch` wheel pulls
~1.5GB of unused NVIDIA CUDA libraries inside the Linux container - now
pinned to the real CPU-only wheel; (4) `ultralytics`'s `opencv-python`
dependency needs real X11 libraries absent from the slim base image -
now force-reinstalls `opencv-python-headless` last (the code never uses
any GUI cv2 function).

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

**Verified working (Round 35)**: real build succeeds (~3 min once
Docker's layer cache is warm), real container starts cleanly, and a
real end-to-end test confirmed genuinely varying, correctly-computed
scores:

```
curl -X POST http://localhost:8000/v1/kernel/fdia/evaluate -d '{"data_quality":0.95,"intent_precision":1.0,"authorized":1.0}'
# -> {"future_score":0.95,"authorized":true,...,"source":"python_kernel_real_computation"}
curl -X POST http://localhost:8000/v1/kernel/fdia/evaluate -d '{"data_quality":0.1,"intent_precision":2.0,"authorized":1.0}'
# -> {"future_score":0.01,...}  (genuinely different, not hardcoded)
curl -X POST http://localhost:8000/v1/kernel/fdia/evaluate -d '{"data_quality":0.95,"intent_precision":1.0,"authorized":0.0}'
# -> {"future_score":0.0,"authorized":false,...}  (real veto)
```

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
