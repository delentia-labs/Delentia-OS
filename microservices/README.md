# 🧬 Delentia OS — Microservices Suite

This folder houses the core microservices for the **Delentia OS** control plane ecosystem. Each service is packaged as an independent container and can be run collaboratively using the provided `docker-compose.yml` configuration.

---

## 🚦 Microservice Port & Endpoint Mapping

| Microservice | Port | Key Endpoints | Description |
| :--- | :--- | :--- | :--- |
| **gateway-api** | `8000` | `GET /`<br>`GET /health`<br>`GET /delentia/system/stats`<br>`WS /v1/kernel/stream` | Main unified gateway routing client intents and streaming real-time tokens. |
| **intent-loop** | `8001` | `POST /process`<br>`GET /health`<br>`GET /metrics` | Stateful Intent Loop Engine managing cold-start, memory checking, and evolution metrics. |
| **analysearch-intent** | `8020` | `POST /analysearch/analyze`<br>`POST /analysearch/crystallize`<br>`GET /analysearch/health` | Deep intent analysis, research synthesis, and Mirror Mode refinement dialog. |
| **vector-search** | `8016` | `POST /vector/index`<br>`POST /vector/search`<br>`GET /vector/health` | Fast semantic similarity vector database wrapper using FAISS or Qdrant. |
| **crystallizer** | `8004` | `POST /crystallize`<br>`GET /health`<br>`GET /stats` | Entropy-based keyword extraction and concept map builder (ALGO-41). |

---

## 🛠️ Running Locally (Docker Compose)

To start the entire microservices stack, run the following command from the project root:

```bash
docker-compose -f microservices/docker-compose.yml up --build
```

### Checking Service Health

Once running, verify that each service is healthy via healthchecks:

```bash
# gateway-api
curl -f http://localhost:8000/health

# intent-loop
curl -f http://localhost:8001/health

# analysearch-intent
curl -f http://localhost:8020/analysearch/health

# vector-search
curl -f http://localhost:8016/vector/health

# crystallizer
curl -f http://localhost:8004/health
```

---

## 📦 Service Architecture & Dependencies

* All services run on lightweight **Python 3.11 slim** base images.
* Common library modules (`core/` and `signedai/`) are injected into the build context to enable zero-knowledge logic (`ZKFDIAProver`), multi-model registry rules, and reputation scoring.
