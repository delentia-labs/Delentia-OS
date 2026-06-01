# Delentia Infra — Community Deployment

[![Docker Build](https://img.shields.io/github/actions/workflow/status/delentia-labs/delentia-infra-public/build-images.yml?label=Docker+Build)](https://github.com/delentia-labs/delentia-infra-public/actions/workflows/build-images.yml)
[![Helm Chart](https://img.shields.io/github/actions/workflow/status/delentia-labs/delentia-infra-public/publish-helm.yml?label=Helm+Chart)](https://github.com/delentia-labs/delentia-infra-public/actions/workflows/publish-helm.yml)
[![Helm](https://img.shields.io/badge/Helm-OCI-orange)](https://github.com/delentia-labs/delentia-infra-public/pkgs/container/charts%2Fdelentia-community)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-%3E%3D24-blue)](https://docs.docker.com/)

**Delentia Infra Public** is the community deployment package for [Delentia OS](https://github.com/delentia-labs/delentia-os).

## Quick Start

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.sh | bash

# Windows PowerShell
iwr -useb https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.ps1 | iex
```

See [docs/quick-start.md](docs/quick-start.md) for the full guide.

## Kubernetes (Helm OCI)

```bash
# Install directly from OCI registry — no git clone needed
helm install delentia \
  oci://ghcr.io/delentia-labs/charts/delentia-community \
  --version 2.0.0 \
  --namespace delentia --create-namespace \
  --set postgresql.auth.password="$(openssl rand -base64 32)"

# Upgrade
helm upgrade delentia \
  oci://ghcr.io/delentia-labs/charts/delentia-community \
  --version 2.1.0

# Pull chart locally to inspect values
helm pull oci://ghcr.io/delentia-labs/charts/delentia-community --version 2.0.0
```

## Services

| Service | Port | Image |
|---|---|---|
| gateway-api | 8000 | ghcr.io/delentia-labs/gateway-api:2.0 |
| intent-loop | 8001 | ghcr.io/delentia-labs/intent-loop:2.0 |
| analysearch-intent | 8002 | ghcr.io/delentia-labs/analysearch-intent:2.0 |
| vector-search (Qdrant) | 8003 | qdrant/qdrant:latest |
| crystallizer | 8004 | ghcr.io/delentia-labs/crystallizer:2.0 |
| postgres | 5432 | postgres:16-alpine |

## Minimum Requirements

| Deployment | CPU | RAM | Disk |
|---|---|---|---|
| Docker Compose (dev) | 2 cores | 4 GB | 20 GB |
| Docker Compose (prod) | 4 cores | 8 GB | 50 GB |
| Kubernetes (Helm) | 4 vCPU | 8 GB | 100 GB |
| Kubernetes (recommended) | 8 vCPU | 16 GB | 200 GB |

Requires: Docker ≥ 24, Helm ≥ 3.12, kubectl ≥ 1.28 (for K8s deployment).

---

## Troubleshooting

**PostgreSQL password error on Helm install:**
```bash
# Always set a strong password at install time
--set postgresql.auth.password="$(openssl rand -base64 32)"
# Or use an existing secret:
--set postgresql.auth.existingSecret=my-db-secret
```

**Qdrant vector-search pod CrashLoopBackOff:**
```bash
# Check storage class supports ReadWriteOnce
kubectl get storageclass
# Increase PVC size if needed: --set qdrant.persistence.size=10Gi
```

**Gateway-api returns 503 on first start:**
```bash
# Normal — wait 60s for intent-loop to initialize HexaCore models
kubectl rollout status deployment/gateway-api -n delentia
```

**Port 8000 already in use (Docker Compose):**
```bash
# Edit docker-compose.yml or override port
GATEWAY_PORT=8080 docker compose up -d
```

---

## Related Repos

- [delentia-os](https://github.com/delentia-labs/delentia-os)
- [delentia-gui](https://github.com/delentia-labs/delentia-gui)
- [delentia-ecosystem](https://github.com/delentia-labs/delentia-ecosystem)
- [delentia-infra-enterprise](https://github.com/delentia-labs/delentia-infra-enterprise)

## License

Apache 2.0 — © 2026 Delentia Labs
