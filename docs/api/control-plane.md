# Control Plane API

The Control Plane exposes a FastAPI-based REST interface for intent compilation, graph building, and policy evaluation.

**Base URL (local dev):** `http://localhost:8000`  
**OpenAPI spec:** `http://localhost:8000/docs`

---

## Start the Server

```bash
# Development server
uvicorn rct_control_plane.api:app --reload --port 8000

# Or via CLI
rct serve --port 8000
```

---

## Endpoints

### `GET /`

Root health check — returns server info and timestamp.

```bash
curl http://localhost:8000/
```

```json
{
  "service": "rct-control-plane",
  "version": "1.0.2a0",
  "status": "running",
  "timestamp": "2026-04-21T10:00:00+00:00"
}
```

---

### `GET /health`

Lightweight liveness probe for load balancers and Kubernetes.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2026-04-17T10:00:00+00:00"
}
```

---

### `GET /health/detailed`

Detailed component health — checks each subsystem.

```bash
curl http://localhost:8000/health/detailed
```

```json
{
  "status": "healthy",
  "components": {
    "fdia_engine": "ok",
    "delta_engine": "ok",
    "signedai_registry": "ok",
    "intent_compiler": "ok"
  },
  "timestamp": "2026-04-21T10:00:00+00:00",
  "version": "1.0.2a0"
}
```

---

### `POST /compile`

Compile an intent into a signed execution graph.

**Request:**

```json
{
  "intent_text": "Deploy authentication service to staging",
  "domain": "backend-engineering",
  "architect_constraint": "No production database changes",
  "requirements": "All tests pass, p99 < 500ms"
}
```

**Response:**

```json
{
  "intent_id": "int_abc123",
  "state": "COMPLETED",
  "fdia_score": 0.847,
  "execution_graph": { ... },
  "signature": "ed25519:...",
  "duration_ms": 1842,
  "cache_hit": false
}
```

---

### `POST /graph/build`

Build an execution graph from DSL text.

**Request:**

```json
{
  "dsl_text": "intent: \"Deploy\"\nsteps:\n  - build: docker\n  - test: pytest"
}
```

---

### `POST /policy/evaluate`

Evaluate a policy against a set of actions.

**Request:**

```json
{
  "policy_name": "default",
  "actions": ["deploy", "delete_database", "read_logs"],
  "context": { "environment": "staging" }
}
```

---

## Python Client

```python
import httpx

with httpx.Client(base_url="http://localhost:8000") as client:
    # Health check
    r = client.get("/health")
    assert r.status_code == 200

    # Compile intent
    r = client.post("/compile", json={
        "intent_text": "Refactor payment module",
        "domain": "backend",
        "architect_constraint": "Keep existing API contract",
        "requirements": "Tests pass, no regressions",
    })
    result = r.json()
    print(f"Score: {result['fdia_score']}")
```

---

## Authentication

The SDK control plane has no authentication by default — it is intended for local development and reference use. For production deployments in the Enterprise stack, JWT-based auth and mTLS are added at the Gateway layer.

## Read-only budget request retries

The opt-in `/v1/agent/readonly/budget` create request accepts an optional
`request_id` (1–128 ASCII letters, digits, `.`, `_`, `:`, `-`). Reusing the key
with identical input returns the actor's current persisted contract. Reusing it
with changed input or policy binding returns 409. Without a key, each request
creates a new plan. Authorization and file grants are checked on every retry.
This does not confirm a plan or replay execution. The updated wire schema is
[readonly-budget-v1.schema.json](readonly-budget-v1.schema.json).

See the [lifecycle audit and recovery plan](../development/LIFECYCLE_REVIEW_2026-10-30_TH.md)
for transaction boundaries, outstanding job ownership/cancel findings and the
separate roles of request idempotency and tool-effect idempotency.
