# Quick Start — Delentia OS Community

Get Delentia OS running in under 5 minutes.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | ≥ 24 | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | plugin | bundled with Docker Desktop |
| Python | ≥ 3.10 | [python.org](https://python.org) |

---

## Option 1 — One-Line Install (Linux / macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.sh | bash
```

## Option 2 — One-Line Install (Windows PowerShell)

```powershell
iwr -useb https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.ps1 | iex
```

## Option 3 — Manual Docker Compose

```bash
# 1. Clone this repo
git clone https://github.com/delentia-labs/delentia-infra-public
cd delentia-infra-public/docker

# 2. Configure secrets
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and DELENTIA_API_KEY

# 3. Start all 6 services
docker compose up -d

# 4. Verify health
../scripts/health-check.sh
```

---

## Services

| Service | Port | Description |
|---|---|---|
| Gateway API | 8000 | Main entry point for all API calls |
| Intent Loop | 8001 | JITNA v3 intent orchestration engine |
| Analysearch | 8002 | Semantic search + intent analysis |
| Qdrant | 8003 | Vector database (via port mapping) |
| Crystallizer | 8004 | Memory crystallization and compaction |
| PostgreSQL | 5432 | Relational store (localhost only) |

---

## First API Call

```bash
# Get your API key from .env
API_KEY=$(grep DELENTIA_API_KEY ~/.delentia/.env | cut -d= -f2)

# Health check
curl http://localhost:8000/health

# System stats
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/delentia/system/stats

# Execute an intent
curl -X POST http://localhost:8000/v1/kernel/execute \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "What is the FDIA score formula?", "mode": "standard"}'
```

---

## Connecting the Desktop App

1. Install [Delentia Desk](https://github.com/delentia-labs/delentia-gui/releases)
2. Open **Settings** → set Gateway URL to `http://localhost:8000`
3. Paste your API key from `~/.delentia/.env`
4. Click **Test Connection** — you should see a green checkmark

---

## Stopping & Uninstalling

```bash
# Stop all services (keeps data)
docker compose -f ~/.delentia/docker-compose.yml down

# Stop and remove all data
docker compose -f ~/.delentia/docker-compose.yml down -v
rm -rf ~/.delentia
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Port already in use | `sudo lsof -i :8000` — kill conflicting process |
| Container unhealthy | `docker compose logs gateway-api` |
| Permission denied | `sudo usermod -aG docker $USER` then re-login |
| Images not found | Ensure Docker Hub access — `docker pull delentia/gateway-api:2.0` |

---

## Next Steps

- [API Reference](https://github.com/delentia-labs/delentia-os/blob/main/docs/api.md)
- [Desktop App](https://github.com/delentia-labs/delentia-gui)
- [Enterprise Deployment](https://github.com/delentia-labs/delentia-infra-enterprise)
- [Custom Adapters](https://github.com/delentia-labs/delentia-ecosystem)
