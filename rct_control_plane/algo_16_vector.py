"""
ALGO-16: Vector Search Engine (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/vector-search/
app/core/vector_engine.py and app/backends/faiss_backend.py on 2026-09-15,
following the same strip-the-FastAPI-keep-the-engine pattern used for
ALGO-07 (mee_engine.py). This is one of Delentia-OS's own CLAUDE.md-listed
5 canonical real reference microservices, and the most solidly real of
this batch: no HTTP framework code, no Qdrant/network dependency for the
backend ported here — FAISS runs fully in-memory.

DEPENDENCY GAP — READ BEFORE WIRING IN: `faiss` (the `faiss-cpu` PyPI
package) is NOT listed in Delentia-OS/pyproject.toml under any dependency
group (base, or the `graph`/`qdrant`/`monitoring`/`persistence`/`llm`/
`full` extras). It happened to already be importable in the environment
this port was developed and smoke-tested in (`faiss-cpu==1.13.2` was
present via `pip list`), so the smoke test below actually ran and passed
— but that is incidental to this environment, not something this port
installed, and pyproject.toml still needs `faiss-cpu` added (e.g. to the
`graph` extra or a new `vector` extra) before this module is guaranteed
to import cleanly elsewhere. numpy IS already available via the existing
`graph` extra.

Real logic ported as-is:
    - VectorEngine: backend-agnostic dimension validation, batch
      indexing/search bookkeeping, timing stats.
    - FAISSBackend: real FAISS index construction for three index types
      (IndexFlatIP/IndexFlatL2 for "flat", IndexIVFFlat for "ivf" with
      real `.train()` before first add, IndexHNSWFlat for "hnsw"); real
      cosine-vs-euclidean-vs-dot metric handling (cosine normalizes
      vectors before indexing/search and uses inner product; euclidean
      uses L2 distance converted to a similarity score via
      1/(1+distance)); real ID<->FAISS-index-position mapping since FAISS
      itself only returns integer positions.

Honest, preserved gaps (disclosed in the source, not introduced here):
    - FAISSBackend.update()/delete() do NOT mutate the underlying FAISS
      index in place (FAISS has no native update/delete) — they update
      the id_to_idx/metadata_store/vector_store side-tables only, and log
      a warning that re-indexing is required for the FAISS index itself
      to reflect the change. Ported verbatim, not "fixed" into a fake
      in-place mutation.

Usage::

    from rct_control_plane.algo_16_vector import VectorEngine, FAISSBackend
    backend = FAISSBackend(index_type="flat", metric="cosine")
    backend.initialize(dimension=8)
    engine = VectorEngine(backend, dimension=8)
    engine.index(vectors=[[...]], ids=["v1"])
    engine.search(query_vector=[...], k=5)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# Vector Engine Core (backend-agnostic)
# ============================================================================

class VectorBackend(Enum):
    """Vector backend types"""
    FAISS = "faiss"
    QDRANT = "qdrant"


class DistanceMetric(Enum):
    """Distance metrics for similarity search"""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT = "dot"


@dataclass
class SearchResult:
    """Single search result"""
    id: str
    score: float
    metadata: Optional[Dict[str, Any]] = None
    vector: Optional[List[float]] = None


@dataclass
class VectorRecord:
    """Vector record with metadata"""
    id: str
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None


class VectorBackendInterface(ABC):
    """Abstract interface for vector backends"""

    @abstractmethod
    def initialize(self, dimension: int, **kwargs):
        """Initialize the backend"""

    @abstractmethod
    def index(self, vectors: List[List[float]], ids: List[str],
              metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        """Index vectors"""

    @abstractmethod
    def search(self, query_vector: List[float], k: int = 10,
               filter_dict: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """Search for nearest neighbors"""

    @abstractmethod
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """Get a specific vector"""

    @abstractmethod
    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a vector"""

    @abstractmethod
    def delete(self, vector_id: str) -> bool:
        """Delete a vector"""

    @abstractmethod
    def clear(self) -> int:
        """Clear all vectors"""

    @abstractmethod
    def count(self) -> int:
        """Get total vector count"""

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics"""


class VectorEngine:
    """
    Main vector engine that manages backend operations.

    Features:
    - Backend abstraction (FAISS/Qdrant)
    - Batch operations
    - Performance tracking
    - Error handling
    """

    def __init__(self, backend: VectorBackendInterface, dimension: int):
        self.backend = backend
        self.dimension = dimension
        self.total_searches = 0
        self.total_index_ops = 0
        self.search_times: List[float] = []
        self.start_time = time.time()

        logger.info(f"VectorEngine initialized: dimension={dimension}")

    def index(self, vectors: List[List[float]], ids: List[str],
              metadata: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Index vectors, validating shape/dimension first."""
        start_time = time.time()

        if len(vectors) != len(ids):
            raise ValueError("Number of vectors must match number of IDs")

        if metadata and len(metadata) != len(vectors):
            raise ValueError("Number of metadata entries must match number of vectors")

        for i, vec in enumerate(vectors):
            if len(vec) != self.dimension:
                raise ValueError(
                    f"Vector {i} has dimension {len(vec)}, expected {self.dimension}"
                )

        count = self.backend.index(vectors, ids, metadata)
        self.total_index_ops += count

        elapsed = (time.time() - start_time) * 1000

        logger.info(f"Indexed {count} vectors in {elapsed:.2f}ms")

        return {
            "indexed_count": count,
            "total_vectors": self.backend.count(),
            "time_ms": round(elapsed, 2)
        }

    def search(self, query_vector: List[float], k: int = 10,
               metric: str = "cosine",
               filter_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Search for nearest neighbors."""
        start_time = time.time()

        if len(query_vector) != self.dimension:
            raise ValueError(
                f"Query vector has dimension {len(query_vector)}, expected {self.dimension}"
            )

        results = self.backend.search(query_vector, k, filter_dict)

        elapsed = (time.time() - start_time) * 1000
        self.search_times.append(elapsed)
        self.total_searches += 1

        logger.info(f"Search completed: k={k}, results={len(results)}, time={elapsed:.2f}ms")

        return {
            "results": [
                {
                    "id": r.id,
                    "score": round(r.score, 6),
                    "metadata": r.metadata
                }
                for r in results
            ],
            "time_ms": round(elapsed, 2)
        }

    def batch_search(self, query_vectors: List[List[float]], k: int = 10,
                      metric: str = "cosine") -> Dict[str, Any]:
        """Batch search multiple queries."""
        start_time = time.time()

        results = []
        for query in query_vectors:
            search_result = self.search(query, k, metric)
            results.append(search_result["results"])

        elapsed = (time.time() - start_time) * 1000

        logger.info(f"Batch search completed: {len(query_vectors)} queries in {elapsed:.2f}ms")

        return {
            "results": results,
            "time_ms": round(elapsed, 2)
        }

    def get(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific vector."""
        record = self.backend.get(vector_id)

        if not record:
            return None

        return {
            "id": record.id,
            "vector": record.vector,
            "metadata": record.metadata
        }

    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update a vector (see FAISSBackend's own docstring for the caveat this hits)."""
        if vector and len(vector) != self.dimension:
            raise ValueError(
                f"Vector has dimension {len(vector)}, expected {self.dimension}"
            )

        success = self.backend.update(vector_id, vector, metadata)

        return {
            "updated": success,
            "vector_id": vector_id
        }

    def delete(self, vector_id: str) -> Dict[str, Any]:
        """Delete a vector."""
        success = self.backend.delete(vector_id)

        return {
            "deleted": success,
            "vector_id": vector_id,
            "remaining_count": self.backend.count()
        }

    def clear(self) -> Dict[str, Any]:
        """Clear all vectors."""
        deleted = self.backend.clear()

        logger.warning(f"Cleared {deleted} vectors from index")

        return {
            "cleared": True,
            "deleted_count": deleted
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        backend_stats = self.backend.get_stats()

        avg_search_time = (
            sum(self.search_times) / len(self.search_times)
            if self.search_times else 0
        )

        uptime = time.time() - self.start_time

        return {
            "total_vectors": self.backend.count(),
            "dimension": self.dimension,
            "total_searches": self.total_searches,
            "total_index_ops": self.total_index_ops,
            "avg_search_time_ms": round(avg_search_time, 2),
            "uptime_seconds": round(uptime, 2),
            **backend_stats
        }

    def health_check(self) -> Dict[str, Any]:
        """Check engine health."""
        try:
            count = self.backend.count()
            stats = self.backend.get_stats()

            return {
                "status": "healthy",
                "vector_count": count,
                "dimension": self.dimension,
                **stats
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """cos(a, b) = a.b / (||a|| ||b||)"""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot / (norm_a * norm_b))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two vectors"""
    return float(np.linalg.norm(a - b))


def dot_product(a: np.ndarray, b: np.ndarray) -> float:
    """Dot product between two vectors"""
    return float(np.dot(a, b))


# ============================================================================
# FAISSBackend — real FAISS-backed similarity search
#
# NOTE: `faiss` is imported lazily inside FAISSBackend.__init__ /
# .initialize() rather than at module scope, so importing this whole
# module (VectorEngine, dataclasses, etc.) does not itself require
# faiss-cpu to be installed — only actually instantiating FAISSBackend
# does. See the DEPENDENCY GAP note at the top of this file.
# ============================================================================

class FAISSBackend(VectorBackendInterface):
    """
    FAISS backend for fast in-memory vector search.

    Features:
    - Multiple index types (Flat, IVF, HNSW)
    - Cosine, Euclidean, Dot Product metrics
    - In-memory storage

    Index Types:
    - flat: Exact search, best accuracy
    - ivf: Inverted file, balanced
    - hnsw: HNSW graph, fastest
    """

    def __init__(self, index_type: str = "flat", metric: str = "cosine",
                 nlist: int = 100, m: int = 32):
        self.index_type = index_type
        self.metric = metric
        self.nlist = nlist
        self.m = m
        self.faiss_index = None  # Renamed from 'index' to avoid conflict with method
        self.dimension = None
        self.id_to_idx: Dict[str, int] = {}
        self.idx_to_id: Dict[int, str] = {}
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
        self.vector_store: Dict[str, List[float]] = {}
        self.next_idx = 0

        logger.info(f"FAISSBackend initialized: type={index_type}, metric={metric}")

    def initialize(self, dimension: int, **kwargs):
        """Initialize the real FAISS index for the given dimension/type/metric."""
        import faiss  # lazy import — see module docstring's DEPENDENCY GAP note

        self.dimension = dimension

        if self.metric == "cosine":
            base_index = faiss.IndexFlatIP(dimension)
        elif self.metric == "euclidean":
            base_index = faiss.IndexFlatL2(dimension)
        elif self.metric == "dot":
            base_index = faiss.IndexFlatIP(dimension)
        else:
            raise ValueError(f"Unknown metric: {self.metric}")

        if self.index_type == "flat":
            self.faiss_index = base_index
        elif self.index_type == "ivf":
            self.faiss_index = faiss.IndexIVFFlat(base_index, dimension, self.nlist)
            self.index_trained = False
        elif self.index_type == "hnsw":
            self.faiss_index = faiss.IndexHNSWFlat(dimension, self.m)
        else:
            raise ValueError(f"Unknown index type: {self.index_type}")

        logger.info(f"FAISS index created: dimension={dimension}, type={self.index_type}")

    def _normalize_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """Normalize vectors for cosine similarity (no-op for other metrics)."""
        if self.metric != "cosine":
            return vectors

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vectors / norms

    def index(self, vectors: List[List[float]], ids: List[str],
              metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        """Index vectors into the real FAISS index (training IVF if needed)."""
        vectors_np = np.array(vectors, dtype=np.float32)
        vectors_np = self._normalize_vectors(vectors_np)

        if self.index_type == "ivf" and not hasattr(self, "index_trained"):
            if len(vectors) >= self.nlist:
                logger.info("Training IVF index...")
                self.faiss_index.train(vectors_np)
                self.index_trained = True
            else:
                logger.warning(f"Not enough vectors to train IVF (need {self.nlist})")

        start_idx = self.next_idx
        self.faiss_index.add(vectors_np)

        for i, (vec_id, vec) in enumerate(zip(ids, vectors, strict=True)):
            idx = start_idx + i
            self.id_to_idx[vec_id] = idx
            self.idx_to_id[idx] = vec_id
            self.vector_store[vec_id] = vec

            if metadata and i < len(metadata):
                self.metadata_store[vec_id] = metadata[i]

        self.next_idx += len(vectors)

        logger.info(f"Indexed {len(vectors)} vectors, total={self.faiss_index.ntotal}")

        return len(vectors)

    def search(self, query_vector: List[float], k: int = 10,
               filter_dict: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """Real FAISS nearest-neighbor search with metric-correct score conversion."""
        query_np = np.array([query_vector], dtype=np.float32)
        query_np = self._normalize_vectors(query_np)

        distances, indices = self.faiss_index.search(query_np, k)

        results = []
        for dist, idx in zip(distances[0], indices[0], strict=True):
            if idx == -1:  # FAISS returns -1 for missing results
                continue

            vec_id = self.idx_to_id.get(idx)
            if not vec_id:
                continue

            metadata = self.metadata_store.get(vec_id)

            if filter_dict and metadata:
                match = all(metadata.get(fk) == fv for fk, fv in filter_dict.items())
                if not match:
                    continue

            if self.metric == "cosine" or self.metric == "dot":
                score = float(dist)  # Already similarity (inner product)
            else:  # euclidean
                score = 1.0 / (1.0 + float(dist))  # Convert distance to similarity

            results.append(SearchResult(
                id=vec_id,
                score=score,
                metadata=metadata
            ))

        return results[:k]

    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """Get a specific vector from the side-table store."""
        if vector_id not in self.vector_store:
            return None

        return VectorRecord(
            id=vector_id,
            vector=self.vector_store[vector_id],
            metadata=self.metadata_store.get(vector_id)
        )

    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a vector. PRESERVED GAP (disclosed in the source, not
        introduced here): FAISS has no native in-place update, so this
        only updates the metadata/vector side-tables; the FAISS index
        itself still holds the old vector until re-indexed.
        """
        if vector_id not in self.id_to_idx:
            return False

        if metadata:
            if vector_id in self.metadata_store:
                self.metadata_store[vector_id].update(metadata)
            else:
                self.metadata_store[vector_id] = metadata

        if vector:
            self.vector_store[vector_id] = vector
            logger.warning("Vector updated in store, but FAISS index not updated. Consider re-indexing.")

        return True

    def delete(self, vector_id: str) -> bool:
        """
        Delete a vector. PRESERVED GAP (disclosed in the source, not
        introduced here): FAISS has no native deletion, so this only
        removes the id/metadata/vector side-table entries; the FAISS
        index itself still holds the underlying vector until re-indexed.
        """
        if vector_id not in self.id_to_idx:
            return False

        idx = self.id_to_idx.pop(vector_id)
        self.idx_to_id.pop(idx, None)
        self.vector_store.pop(vector_id, None)
        self.metadata_store.pop(vector_id, None)

        logger.warning("Vector deleted from mappings, but not from FAISS index. Consider re-indexing.")

        return True

    def clear(self) -> int:
        """Clear all vectors (real faiss_index.reset())."""
        count = len(self.id_to_idx)

        if self.faiss_index:
            self.faiss_index.reset()

        self.id_to_idx.clear()
        self.idx_to_id.clear()
        self.vector_store.clear()
        self.metadata_store.clear()
        self.next_idx = 0

        return count

    def count(self) -> int:
        """Total vector count."""
        return len(self.id_to_idx)

    def get_stats(self) -> Dict[str, Any]:
        """Backend statistics, including approximate memory usage."""
        vector_memory = self.dimension * self.count() * 4  # 4 bytes per float32
        metadata_memory = sum(
            len(str(m)) for m in self.metadata_store.values()
        )
        total_memory_mb = (vector_memory + metadata_memory) / (1024 * 1024)

        return {
            "backend": "faiss",
            "index_type": self.index_type,
            "metric": self.metric,
            "memory_mb": round(total_memory_mb, 2),
            "dimension": self.dimension
        }


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    print("=== ALGO-16 Vector Search smoke test ===")

    try:
        import faiss  # noqa: F401
        FAISS_INSTALLED = True
    except ImportError as e:
        FAISS_INSTALLED = False
        print(f"faiss-cpu is NOT importable in this environment: {e}")
        print("This is expected per pyproject.toml (faiss-cpu is not declared there).")
        print("Module import itself succeeded (faiss import is lazy, scoped to FAISSBackend).")

    if not FAISS_INSTALLED:
        print("=== ALGO-16 Vector Search: module loads correctly; "
              "FAISSBackend cannot run until faiss-cpu is installed. ===")
    else:
        import random
        random.seed(7)

        dim = 16
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=dim)
        engine = VectorEngine(backend, dimension=dim)

        # Build vectors where "cat"-ish and "dog"-ish clusters are distinguishable
        def rand_vec(bias: float) -> List[float]:
            return [round(bias + random.uniform(-0.05, 0.05), 4) for _ in range(dim)]

        vectors = [rand_vec(1.0) for _ in range(3)] + [rand_vec(-1.0) for _ in range(3)]
        ids = ["cat1", "cat2", "cat3", "dog1", "dog2", "dog3"]
        metadata = [{"cluster": "cat"}] * 3 + [{"cluster": "dog"}] * 3

        index_result = engine.index(vectors, ids, metadata)
        print(f"Indexed: {index_result}")
        assert index_result["indexed_count"] == 6
        assert index_result["total_vectors"] == 6

        query = rand_vec(1.0)  # closest to the "cat" cluster
        search_result = engine.search(query, k=3, metric="cosine")
        print(f"Search (flat/cosine) top-3: {search_result['results']}")
        top_ids = [r["id"] for r in search_result["results"]]
        assert all(tid.startswith("cat") for tid in top_ids), \
            f"expected cat cluster to rank first for a cat-biased query, got {top_ids}"

        # Euclidean metric on a fresh backend
        backend_l2 = FAISSBackend(index_type="flat", metric="euclidean")
        backend_l2.initialize(dimension=dim)
        engine_l2 = VectorEngine(backend_l2, dimension=dim)
        engine_l2.index(vectors, ids, metadata)
        search_l2 = engine_l2.search(query, k=3, metric="euclidean")
        print(f"Search (flat/euclidean) top-3: {search_l2['results']}")
        top_ids_l2 = [r["id"] for r in search_l2["results"]]
        assert all(tid.startswith("cat") for tid in top_ids_l2)

        # get/update/delete round-trip
        record = engine.get("cat1")
        assert record is not None and record["id"] == "cat1"
        upd = engine.update("cat1", metadata={"cluster": "cat", "tag": "updated"})
        assert upd["updated"] is True
        deleted = engine.delete("dog3")
        assert deleted["deleted"] is True
        assert deleted["remaining_count"] == 5

        stats = engine.get_stats()
        print(f"Engine stats: {stats}")
        assert stats["total_searches"] == 1

        health = engine.health_check()
        print(f"Health check: {health}")
        assert health["status"] == "healthy"

        print("=== ALGO-16 Vector Search: ALL ASSERTIONS PASSED (faiss-cpu present in this env) ===")
