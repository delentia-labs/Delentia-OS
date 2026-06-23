"""
ALGO-28: Vector Search - Pytest Configuration

Mocks heavy dependencies (faiss, qdrant_client) for testing.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from types import ModuleType


class FakeFaissIndex:
    """Fake FAISS index that actually stores and searches vectors."""

    def __init__(self, dimension):
        self.d = dimension
        self.ntotal = 0
        self._vectors = []

    def add(self, vectors):
        if isinstance(vectors, np.ndarray):
            self._vectors.append(vectors.copy())
            self.ntotal += vectors.shape[0]

    def search(self, query, k):
        if self.ntotal == 0:
            distances = np.array([[]], dtype=np.float32)
            indices = np.array([[]], dtype=np.int64)
            return distances, indices
        all_vecs = np.vstack(self._vectors)
        k = min(k, self.ntotal)
        # Simple L2 distance
        diffs = all_vecs - query
        dists = np.sum(diffs ** 2, axis=1)
        top_k = np.argsort(dists)[:k]
        return np.array([dists[top_k]], dtype=np.float32), np.array([top_k], dtype=np.int64)

    def train(self, vectors):
        pass

    @property
    def is_trained(self):
        return True


class FakeFaissIPIndex(FakeFaissIndex):
    """Inner product index."""

    def search(self, query, k):
        if self.ntotal == 0:
            return np.array([[]], dtype=np.float32), np.array([[]], dtype=np.int64)
        all_vecs = np.vstack(self._vectors)
        k = min(k, self.ntotal)
        scores = np.dot(all_vecs, query.T).flatten()
        top_k = np.argsort(-scores)[:k]
        return np.array([scores[top_k]], dtype=np.float32), np.array([top_k], dtype=np.int64)


# Build the faiss module mock
faiss_mod = ModuleType('faiss')
faiss_mod.IndexFlatL2 = lambda dim: FakeFaissIndex(dim)
faiss_mod.IndexFlatIP = lambda dim: FakeFaissIPIndex(dim)
faiss_mod.IndexIVFFlat = lambda base, dim, nlist: FakeFaissIndex(dim)
faiss_mod.IndexHNSWFlat = lambda dim, m: FakeFaissIndex(dim)
faiss_mod.METRIC_L2 = 0
faiss_mod.METRIC_INNER_PRODUCT = 1
sys.modules['faiss'] = faiss_mod

# Mock qdrant_client
qdrant_mock = MagicMock()
sys.modules['qdrant_client'] = qdrant_mock
sys.modules['qdrant_client.models'] = MagicMock()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

