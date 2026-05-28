# Observability Guide

**Metrics, tracing, and health monitoring for RCT Platform deployments.**

---

## Overview

RCT Platform exposes observability through three layers:

| Layer | What it measures | Endpoint / Method |
|-------|-----------------|------------------|
| **Health probes** | Liveness + readiness | `GET /health`, `GET /health/detailed` |
| **FDIA metrics** | Scoring throughput, avg score, tier distribution | `GET /metrics` |
| **Audit trail** | Full signed decision chain per intent | `GET /audit/{intent_id}` |

---

## Health Endpoints

### Liveness — `GET /health`

Fast probe suitable for Kubernetes `livenessProbe`:

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2026-04-21T10:00:00+00:00"
}
```

HTTP 200 = healthy. HTTP 503 = degraded.

### Readiness — `GET /health/detailed`

Full component check suitable for Kubernetes `readinessProbe`:

```bash
curl http://localhost:8000/health/detailed
```

```json
{
  "status": "healthy",
  "version": "1.0.2a0",
  "components": {
    "fdia_engine": "ok",
    "delta_engine": "ok",
    "signedai_registry": "ok",
    "intent_compiler": "ok",
    "dsl_parser": "ok",
    "policy_engine": "ok"
  },
  "timestamp": "2026-04-21T10:00:00+00:00"
}
```

Any component with `"error"` status causes the overall `status` to become `"degraded"`.

---

## CLI Metrics — `rct metrics`

The CLI exposes runtime metrics from the in-memory control plane:

```bash
rct metrics
rct metrics --output json
```

**Table output:**

```
Metric                        Value
────────────────────────────────────────
Intents processed             1,247
FDIA avg score                0.8734
FDIA min score                0.1200
FDIA max score                0.9980
Warm recall hit rate          89.3%
Consensus tier S2 calls       187
Consensus tier S4 calls       847
Consensus tier S5 calls       213
Policy violations (blocked)   2
Active intents                5
Uptime                        14d 06h 23m
```

**JSON output** (for dashboards):

```json
{
  "intents_processed": 1247,
  "fdia_avg": 0.8734,
  "warm_recall_hit_rate": 0.893,
  "policy_violations": 2,
  "uptime_seconds": 1231380
}
```

---

## Prometheus Integration

The Control Plane exposes a Prometheus-compatible metrics endpoint when the
`ENABLE_PROMETHEUS=1` environment variable is set.

```bash
ENABLE_PROMETHEUS=1 rct serve --port 8000
```

Metrics are available at `GET /metrics` in Prometheus text format.

### Key metrics

| Metric name | Type | Description |
|-------------|------|-------------|
| `rct_intents_total` | Counter | Total intents processed |
| `rct_fdia_score` | Histogram | FDIA score distribution (buckets: 0.1 steps) |
| `rct_warm_recall_total` | Counter | Number of warm (cached) recalls |
| `rct_cold_start_total` | Counter | Number of cold-start (full compute) recalls |
| `rct_consensus_tier_calls` | Counter | Calls per SignedAI tier (label: `tier`) |
| `rct_policy_violations_total` | Counter | Constitutional blocks (A=0 events) |
| `rct_processing_duration_ms` | Histogram | Intent processing latency |

### Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: delentia-os
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## Grafana Dashboard

Import the sample dashboard from `docs/assets/grafana-dashboard.json`
(included in v1.1.0+ releases) or build your own using the metrics above.

**Recommended panels:**

- **Intent throughput** — `rate(rct_intents_total[5m])`
- **FDIA score heatmap** — `histogram_quantile(0.95, rct_fdia_score)` 
- **Warm vs cold recall** — `rct_warm_recall_total / (rct_warm_recall_total + rct_cold_start_total)`
- **Policy violations** — `increase(rct_policy_violations_total[1h])`

---

## Kubernetes Probe Configuration

```yaml
# k8s deployment snippet
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/detailed
    port: 8000
  initialDelaySeconds: 15
  periodSeconds: 5
  failureThreshold: 2
```

---

## Audit Trail

Every intent generates a signed audit chain accessible via:

```bash
rct audit INTENT_ID
rct audit INTENT_ID --output json
```

The audit record contains:

```json
{
  "intent_id": "a1b2c3d4-...",
  "user_id": "alice",
  "intent_text": "Deploy microservice to staging",
  "created_at": "2026-04-21T10:00:00+00:00",
  "completed_at": "2026-04-21T10:00:02+00:00",
  "fdia_score": 0.8734,
  "data_quality": 0.92,
  "intent_precision": 0.88,
  "architect_score": 0.95,
  "consensus_tier": "S4",
  "consensus_models": ["claude-opus", "kimi-k2", "minimax-m2", "gemini-flash"],
  "policy_status": "COMPLIANT",
  "audit_hash": "sha256:abc123..."
}
```

The `audit_hash` is a SHA-256 of the complete record — enables tamper detection.

---

## Structured Logging

The Control Plane emits structured JSON logs by default:

```json
{
  "timestamp": "2026-04-21T10:00:00+00:00",
  "level": "INFO",
  "service": "rct-control-plane",
  "intent_id": "a1b2c3d4-...",
  "event": "intent_compiled",
  "fdia_score": 0.8734,
  "duration_ms": 12.4
}
```

**Log level configuration:**

```bash
# Environment variable
RCT_LOG_LEVEL=DEBUG rct serve

# CLI flag
rct serve --verbose
```

| Level | When to use |
|-------|-------------|
| `DEBUG` | Development — shows all internal events |
| `INFO` | Production — intent lifecycle events |
| `WARNING` | Degraded component, low FDIA score |
| `ERROR` | Policy violations, consensus failures |

---

## Setting Up Local Monitoring Stack

```bash
# Start full local stack with Prometheus + Grafana
docker compose -f docker-compose.dev.yml -f docker-compose.monitoring.yml up

# Prometheus UI: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

!!! note
    `docker-compose.monitoring.yml` is planned for v1.1.0. For v1.0.2a0,
    use `rct metrics` and the REST endpoints for observability.
