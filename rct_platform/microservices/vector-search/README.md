# ALGO-16: Vector Search Service

**RCT v13.0 - Phase 3 Advanced Algorithm**

![Status](https://img.shields.io/badge/status-active-success)
![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Port](https://img.shields.io/badge/port-8016-orange)

## Overview

High-performance vector search service supporting FAISS and Qdrant backends for semantic similarity search, embedding indexing, and nearest neighbor retrieval. Critical dependency for ALGO-17, 18, and 19.

### Key Features

- 🔍 **Dual Backend Support**: FAISS (in-memory) and Qdrant (distributed)
- ⚡ **Fast Search**: <50ms for 1M vectors (FAISS), <100ms (Qdrant)
- 📊 **Multiple Metrics**: Cosine, Euclidean, Dot Product
- 🔄 **Batch Operations**: Efficient bulk indexing and search
- 📈 **Scalable**: Handles millions of vectors
- 🎯 **High Accuracy**: 99%+ recall@10 for ANN search

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Vector Search Service                     │
│                         (Port 8016)                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌─────────────────┐                      ┌─────────────────┐
│  FAISS Backend  │                      │ Qdrant Backend  │
│   (In-Memory)   │                      │  (Distributed)  │
│                 │                      │                 │
│ • IndexFlatIP   │                      │ • Collections   │
│ • IndexIVFFlat  │                      │ • Vectors       │
│ • IndexHNSW     │                      │ • Payloads      │
│ • Cosine Sim    │                      │ • Filters       │
└─────────────────┘                      └─────────────────┘
        │                                           │
        └─────────────────────┬─────────────────────┘
                              │
                              ▼
                   ┌───────────────────┐
                   │  Vector Engine    │
                   │  - Index          │
                   │  - Search         │
                   │  - Update         │
                   │  - Delete         │
                   └───────────────────┘
```

## Quick Start

### Installation

```bash
# Clone and navigate
cd services/vector-search

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run service
uvicorn app.main:app --host 0.0.0.0 --port 8016
```

### Docker

```bash
# Build image
docker build -t rct-vector-search:1.0.0 .

# Run container
docker run -d \
  --name vector-search \
  -p 8016:8016 \
  -e BACKEND=faiss \
  -e DIMENSION=768 \
  rct-vector-search:1.0.0
```

## API Documentation

### Base URL
```
http://localhost:8016
```

### Interactive Docs
```
http://localhost:8016/docs      # Swagger UI
http://localhost:8016/redoc     # ReDoc
```

---

## API Endpoints

### **1. Service Info**

```http
GET /
```

**Response:**
```json
{
  "service": "Vector Search Service",
  "version": "1.0.0",
  "algorithm": "ALGO-16",
  "phase": "Phase 3",
  "backend": "faiss",
  "dimension": 768
}
```

---

### **2. Health Check**

```http
GET /vector/health
```

**Response:**
```json
{
  "status": "healthy",
  "backend": "faiss",
  "vector_count": 10000,
  "dimension": 768,
  "index_type": "IndexFlatIP",
  "memory_usage_mb": 245.8
}
```

---

### **3. Index Vectors**

Add vectors to the index.

```http
POST /vector/index
Content-Type: application/json
```

**Request Body:**
```json
{
  "vectors": [
    [0.1, 0.2, ..., 0.768],  // 768-dimensional vector
    [0.3, 0.4, ..., 0.768]
  ],
  "ids": ["vec_001", "vec_002"],
  "metadata": [
    {"doc_id": "doc1", "category": "tech"},
    {"doc_id": "doc2", "category": "science"}
  ]
}
```

**Response:**
```json
{
  "indexed_count": 2,
  "total_vectors": 10002,
  "time_ms": 12.5
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8016/vector/index \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    "ids": ["v1", "v2"]
  }'
```

---

### **4. Search Vectors**

Find nearest neighbors.

```http
POST /vector/search
Content-Type: application/json
```

**Request Body:**
```json
{
  "query_vector": [0.1, 0.2, ..., 0.768],
  "k": 10,
  "metric": "cosine",
  "filter": {
    "category": "tech"
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "vec_001",
      "score": 0.985,
      "metadata": {"doc_id": "doc1", "category": "tech"}
    },
    {
      "id": "vec_005",
      "score": 0.972,
      "metadata": {"doc_id": "doc5", "category": "tech"}
    }
  ],
  "time_ms": 8.3
}
```

**Metrics:**
- `cosine`: Cosine similarity (default)
- `euclidean`: Euclidean distance
- `dot`: Dot product

---

### **5. Batch Search**

Search multiple queries at once.

```http
POST /vector/search/batch
Content-Type: application/json
```

**Request Body:**
```json
{
  "query_vectors": [
    [0.1, 0.2, ..., 0.768],
    [0.3, 0.4, ..., 0.768]
  ],
  "k": 5
}
```

**Response:**
```json
{
  "results": [
    [
      {"id": "vec_001", "score": 0.985},
      {"id": "vec_002", "score": 0.972}
    ],
    [
      {"id": "vec_010", "score": 0.968},
      {"id": "vec_015", "score": 0.951}
    ]
  ],
  "time_ms": 15.7
}
```

---

### **6. Get Vector**

Retrieve a specific vector.

```http
GET /vector/{vector_id}
```

**Response:**
```json
{
  "id": "vec_001",
  "vector": [0.1, 0.2, ..., 0.768],
  "metadata": {"doc_id": "doc1", "category": "tech"}
}
```

---

### **7. Update Vector**

Update vector or metadata.

```http
PUT /vector/{vector_id}
Content-Type: application/json
```

**Request Body:**
```json
{
  "vector": [0.15, 0.25, ..., 0.768],
  "metadata": {"category": "updated"}
}
```

**Response:**
```json
{
  "updated": true,
  "vector_id": "vec_001"
}
```

---

### **8. Delete Vector**

Remove a vector from the index.

```http
DELETE /vector/{vector_id}
```

**Response:**
```json
{
  "deleted": true,
  "vector_id": "vec_001",
  "remaining_count": 9999
}
```

---

### **9. Clear Index**

Remove all vectors.

```http
DELETE /vector/clear
```

**Response:**
```json
{
  "cleared": true,
  "deleted_count": 10000
}
```

---

### **10. Index Statistics**

Get index information.

```http
GET /vector/stats
```

**Response:**
```json
{
  "total_vectors": 10000,
  "dimension": 768,
  "backend": "faiss",
  "index_type": "IndexFlatIP",
  "memory_mb": 245.8,
  "avg_search_time_ms": 8.5,
  "total_searches": 1523,
  "uptime_seconds": 3600
}
```

---

## Backend Configuration

### FAISS (In-Memory)

**Best For:**
- Fast prototyping
- Small to medium datasets (<10M vectors)
- Single-machine deployments
- Real-time applications (<50ms latency)

**Configuration:**
```python
BACKEND = "faiss"
DIMENSION = 768
INDEX_TYPE = "flat"  # flat, ivf, hnsw
METRIC = "cosine"    # cosine, euclidean, dot
```

**Index Types:**
- `flat`: Exact search, best accuracy
- `ivf`: Inverted file, balanced speed/accuracy
- `hnsw`: HNSW graph, fastest approximation

### Qdrant (Distributed)

**Best For:**
- Large datasets (>10M vectors)
- Distributed deployments
- Rich metadata filtering
- Production systems

**Configuration:**
```python
BACKEND = "qdrant"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "vectors"
DIMENSION = 768
```

**Setup Qdrant:**
```bash
docker run -p 6333:6333 qdrant/qdrant
```

---

## Usage Examples

### Python Client

```python
import requests
import numpy as np

BASE_URL = "http://localhost:8016"

# 1. Index vectors
vectors = np.random.randn(100, 768).tolist()
ids = [f"vec_{i}" for i in range(100)]

response = requests.post(f"{BASE_URL}/vector/index", json={
    "vectors": vectors,
    "ids": ids
})
print(f"Indexed: {response.json()['indexed_count']}")

# 2. Search
query = np.random.randn(768).tolist()
response = requests.post(f"{BASE_URL}/vector/search", json={
    "query_vector": query,
    "k": 10
})
results = response.json()["results"]
for r in results:
    print(f"ID: {r['id']}, Score: {r['score']:.3f}")

# 3. Get stats
response = requests.get(f"{BASE_URL}/vector/stats")
print(response.json())
```

### Integration with ALGO-17 (Graph Traversal)

```python
# Embed nodes and search
import requests

# Index graph nodes
node_embeddings = get_node_embeddings(graph)
requests.post("http://localhost:8016/vector/index", json={
    "vectors": node_embeddings,
    "ids": node_ids,
    "metadata": [{"type": "node", "graph": "kg1"} for _ in node_ids]
})

# Find similar nodes
query_embedding = get_node_embedding(query_node)
response = requests.post("http://localhost:8016/vector/search", json={
    "query_vector": query_embedding,
    "k": 20,
    "filter": {"type": "node", "graph": "kg1"}
})
similar_nodes = response.json()["results"]
```

### Integration with ALGO-18 (Adaptive Prompting)

```python
# Retrieve relevant context for prompts
import requests

# Index prompt templates
template_embeddings = embed_templates(templates)
requests.post("http://localhost:8016/vector/index", json={
    "vectors": template_embeddings,
    "ids": template_ids,
    "metadata": [{"type": "prompt"} for _ in template_ids]
})

# Find best prompt
query_embedding = embed_query(user_query)
response = requests.post("http://localhost:8016/vector/search", json={
    "query_vector": query_embedding,
    "k": 5
})
best_prompts = response.json()["results"]
```

---

## Performance Benchmarks

### FAISS Backend

| Vectors | Dimension | Search Time | Memory |
|---------|-----------|-------------|--------|
| 10K | 768 | 3ms | 30 MB |
| 100K | 768 | 8ms | 300 MB |
| 1M | 768 | 25ms | 3 GB |
| 10M | 768 | 180ms | 30 GB |

### Qdrant Backend

| Vectors | Dimension | Search Time | Memory |
|---------|-----------|-------------|--------|
| 10K | 768 | 10ms | 50 MB |
| 100K | 768 | 25ms | 500 MB |
| 1M | 768 | 50ms | 5 GB |
| 10M | 768 | 120ms | 50 GB |

**Note:** Times are for k=10, cosine similarity, HNSW index

---

## Algorithm Details

### Cosine Similarity

```
similarity(A, B) = (A · B) / (||A|| × ||B||)

Range: [-1, 1]
1.0 = identical vectors
0.0 = orthogonal
-1.0 = opposite
```

### HNSW (Hierarchical Navigable Small World)

```
Algorithm: NSW + Hierarchical Layers

1. Build multi-layer graph
2. Navigate from top layer
3. Refine at each layer
4. Return nearest neighbors

Complexity:
- Build: O(N log N)
- Search: O(log N)
- Memory: O(N × M)
```

### IVF (Inverted File)

```
Algorithm: Clustering + Inverted Index

1. Cluster vectors (k-means)
2. Assign to clusters
3. Search nearby clusters
4. Rank results

Complexity:
- Build: O(N × k × d)
- Search: O(k × d + n_probe × d)
```

---

## Configuration

### Environment Variables

```bash
# Backend selection
BACKEND=faiss              # faiss or qdrant
DIMENSION=768              # Vector dimension

# FAISS settings
FAISS_INDEX_TYPE=flat      # flat, ivf, hnsw
FAISS_METRIC=cosine        # cosine, euclidean, dot
FAISS_NLIST=100            # IVF clusters
FAISS_M=32                 # HNSW M parameter

# Qdrant settings
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=vectors
QDRANT_DISTANCE=cosine     # cosine, euclidean, dot

# Performance
MAX_BATCH_SIZE=1000
CACHE_SIZE=10000
```

### Docker Compose

```yaml
version: '3.8'

services:
  vector-search:
    build: .
    ports:
      - "8016:8016"
    environment:
      - BACKEND=qdrant
      - QDRANT_URL=http://qdrant:6333
      - DIMENSION=768
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

---

## Testing

### Run Tests

```bash
# All tests
pytest tests/test_vector.py -v

# Specific tests
pytest tests/test_vector.py::TestFAISSBackend -v
pytest tests/test_vector.py::TestQdrantBackend -v

# With coverage
pytest tests/test_vector.py --cov=app --cov-report=html
```

### Test Structure

```
tests/
├── conftest.py          # Test fixtures
├── test_vector.py       # Main tests
├── test_faiss.py        # FAISS-specific
└── test_qdrant.py       # Qdrant-specific
```

---

## Monitoring

### Metrics Endpoint

```http
GET /vector/metrics
```

**Response:**
```json
{
  "requests_total": 1523,
  "requests_per_second": 4.2,
  "avg_search_time_ms": 8.5,
  "p95_search_time_ms": 15.3,
  "p99_search_time_ms": 24.7,
  "index_operations": 150,
  "search_operations": 1373,
  "cache_hit_rate": 0.68,
  "error_rate": 0.002
}
```

### Logging

```python
# Configure logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Example logs
INFO - Indexed 1000 vectors in 125ms
INFO - Search completed: k=10, time=8.3ms
WARNING - High memory usage: 85%
ERROR - Failed to connect to Qdrant
```

---

## Troubleshooting

### Issue: Slow Search Performance

**Solution:**
```python
# Switch to IVF or HNSW index
INDEX_TYPE = "hnsw"
FAISS_M = 32
FAISS_EF_CONSTRUCTION = 200
```

### Issue: High Memory Usage

**Solution:**
```python
# Use Qdrant for large datasets
BACKEND = "qdrant"

# Or reduce vector dimension
from sklearn.decomposition import PCA
pca = PCA(n_components=384)
vectors = pca.fit_transform(vectors)
```

### Issue: Low Recall

**Solution:**
```python
# Increase search parameters
FAISS_NPROBE = 50      # IVF probes
FAISS_EF_SEARCH = 100  # HNSW search
```

---

## Integration Examples

### With ALGO-19 (Data Fusion v2)

```python
# Multi-modal search
text_embedding = embed_text(query_text)
image_embedding = embed_image(query_image)

# Search both modalities
text_results = search_vectors(text_embedding)
image_results = search_vectors(image_embedding)

# Fuse results
fused = data_fusion_service.fuse(text_results, image_results)
```

### With ALGO-20 (Workflow Orchestrator v2)

```python
# Workflow task
workflow = {
    "tasks": [
        {
            "id": "embed",
            "service": "embedding-service",
            "input": "documents"
        },
        {
            "id": "index",
            "service": "vector-search",
            "endpoint": "/vector/index",
            "input": "embed.output"
        },
        {
            "id": "search",
            "service": "vector-search",
            "endpoint": "/vector/search",
            "input": "query_embedding"
        }
    ]
}
```

---

## Dependencies

```
faiss-cpu==1.9.0              # FAISS library
qdrant-client==1.12.1         # Qdrant client
fastapi==0.128.0              # Web framework
uvicorn==0.40.0               # ASGI server
pydantic==2.12.5              # Data validation
numpy==2.2.1                  # Vector operations
pytest==9.0.2                 # Testing
httpx==0.28.1                 # HTTP client
```

---

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/algo-16`
3. Make changes
4. Run tests: `pytest tests/ -v`
5. Commit: `git commit -m "Add feature"`
6. Push: `git push origin feature/algo-16`
7. Create Pull Request

---

## License

MIT License - RCT v13.0 Project

---

## Support

- **Documentation**: `/docs`
- **Issues**: GitHub Issues
- **Email**: support@rct-project.com

---

## Changelog

### v1.0.0 (January 2026)
- ✅ Initial release
- ✅ FAISS backend support
- ✅ Qdrant backend support
- ✅ REST API with 10 endpoints
- ✅ Batch operations
- ✅ Comprehensive tests

---

**Algorithm**: ALGO-16 (Vector Search)  
**Phase**: Phase 3 (Advanced Algorithms)  
**Port**: 8016  
**Status**: Active Development  
**Version**: 1.0.0  

---
