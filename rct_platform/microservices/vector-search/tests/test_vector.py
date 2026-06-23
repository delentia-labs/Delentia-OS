"""
Comprehensive Tests for ALGO-16 Vector Search Service
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import faiss
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.core.vector_engine import VectorEngine, cosine_similarity, euclidean_distance
from app.backends.faiss_backend import FAISSBackend
from app.api import routes


# Initialize engine for API tests
backend = FAISSBackend(index_type="flat", metric="cosine")
backend.initialize(dimension=768)
test_engine = VectorEngine(backend, dimension=768)
routes.set_vector_engine(test_engine)

# Test client
client = TestClient(app)


class TestVectorEngine:
    """Test VectorEngine core functionality"""
    
    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        
        engine = VectorEngine(backend, dimension=128)
        
        assert engine.dimension == 128
        assert engine.total_searches == 0
        assert engine.total_index_ops == 0
    
    def test_index_vectors(self):
        """Test indexing vectors"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        engine = VectorEngine(backend, dimension=128)
        
        # Create test vectors
        vectors = np.random.randn(10, 128).tolist()
        ids = [f"vec_{i}" for i in range(10)]
        
        result = engine.index(vectors, ids)
        
        assert result["indexed_count"] == 10
        assert result["total_vectors"] == 10
        assert "time_ms" in result
    
    def test_search_vectors(self):
        """Test vector search"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        engine = VectorEngine(backend, dimension=128)
        
        # Index vectors
        vectors = np.random.randn(100, 128).tolist()
        ids = [f"vec_{i}" for i in range(100)]
        engine.index(vectors, ids)
        
        # Search
        query = np.random.randn(128).tolist()
        result = engine.search(query, k=10)
        
        assert len(result["results"]) <= 10
        assert "time_ms" in result
        
        # Check results are sorted by score
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)
    
    def test_get_vector(self):
        """Test getting specific vector"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        engine = VectorEngine(backend, dimension=128)
        
        # Index
        vectors = [[0.1] * 128]
        ids = ["test_vec"]
        engine.index(vectors, ids)
        
        # Get
        result = engine.get("test_vec")
        
        assert result is not None
        assert result["id"] == "test_vec"
        assert len(result["vector"]) == 128
    
    def test_update_vector(self):
        """Test updating vector metadata"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        engine = VectorEngine(backend, dimension=128)
        
        # Index with metadata
        vectors = [[0.1] * 128]
        ids = ["test_vec"]
        metadata = [{"category": "test"}]
        engine.index(vectors, ids, metadata)
        
        # Update metadata
        result = engine.update("test_vec", metadata={"category": "updated"})
        
        assert result["updated"] is True
        assert result["vector_id"] == "test_vec"


class TestFAISSBackend:
    """Test FAISS backend implementation"""
    
    def test_faiss_initialization(self):
        """Test FAISS backend initializes"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        
        assert backend.dimension == 128
        assert backend.index is not None
        assert backend.count() == 0
    
    def test_faiss_index_and_search(self):
        """Test FAISS indexing and search"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        
        # Index
        vectors = np.random.randn(50, 128).tolist()
        ids = [f"vec_{i}" for i in range(50)]
        count = backend.index(vectors, ids)
        
        assert count == 50
        assert backend.count() == 50
        
        # Search
        query = np.random.randn(128).tolist()
        results = backend.search(query, k=10)
        
        assert len(results) <= 10
        assert all(r.score >= 0 for r in results)
    
    def test_faiss_with_metadata(self):
        """Test FAISS with metadata filtering"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        
        # Index with metadata
        vectors = np.random.randn(30, 128).tolist()
        ids = [f"vec_{i}" for i in range(30)]
        metadata = [{"category": "A" if i < 15 else "B"} for i in range(30)]
        backend.index(vectors, ids, metadata)
        
        # Search with filter
        query = np.random.randn(128).tolist()
        results = backend.search(query, k=20, filter_dict={"category": "A"})
        
        # All results should be category A
        assert all(r.metadata.get("category") == "A" for r in results if r.metadata)
    
    def test_faiss_get_stats(self):
        """Test FAISS statistics"""
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=128)
        
        stats = backend.get_stats()
        
        assert stats["backend"] == "faiss"
        assert stats["dimension"] == 128
        assert "memory_mb" in stats


class TestSimilarityFunctions:
    """Test similarity calculation functions"""
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation"""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        
        sim = cosine_similarity(a, b)
        assert abs(sim - 1.0) < 1e-6  # Should be 1.0 for identical vectors
        
        # Orthogonal vectors
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        sim = cosine_similarity(a, b)
        assert abs(sim) < 1e-6  # Should be 0.0
    
    def test_euclidean_distance(self):
        """Test Euclidean distance calculation"""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        
        dist = euclidean_distance(a, b)
        assert abs(dist) < 1e-6  # Should be 0.0 for identical vectors
        
        # Test known distance
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([3.0, 4.0, 0.0])
        dist = euclidean_distance(a, b)
        assert abs(dist - 5.0) < 1e-6  # 3-4-5 triangle


class TestAPI:
    """Test API endpoints"""
    
    def test_root_endpoint(self):
        """Test root endpoint returns service info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Vector Search Service"
        assert data["algorithm"] == "ALGO-16"
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/vector/health")
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "vector_count" in data
    
    def test_index_endpoint(self):
        """Test index endpoint"""
        vectors = [[0.1, 0.2, 0.3] * 256]  # 768-dim
        ids = ["test_001"]
        
        response = client.post("/vector/index", json={
            "vectors": vectors,
            "ids": ids
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data["indexed_count"] == 1
    
    def test_search_endpoint(self):
        """Test search endpoint"""
        # First index some vectors
        vectors = [np.random.randn(768).tolist() for _ in range(10)]
        ids = [f"vec_{i}" for i in range(10)]
        client.post("/vector/index", json={"vectors": vectors, "ids": ids})
        
        # Then search
        query = np.random.randn(768).tolist()
        response = client.post("/vector/search", json={
            "query_vector": query,
            "k": 5
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 5
        assert "time_ms" in data
    
    def test_get_vector_endpoint(self):
        """Test get vector endpoint"""
        # Index a vector first
        vector = np.random.randn(768).tolist()
        client.post("/vector/index", json={
            "vectors": [vector],
            "ids": ["get_test"]
        })
        
        # Get it
        response = client.get("/vector/get_test")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "get_test"
        assert len(data["vector"]) == 768
    
    def test_stats_endpoint(self):
        """Test stats endpoint"""
        response = client.get("/vector/stats")  # Fixed path
        assert response.status_code == 200
        data = response.json()
        assert "total_vectors" in data
        assert "dimension" in data
        assert "backend" in data


class TestIntegration:
    """Integration tests for complete workflows"""
    
    def test_complete_workflow(self):
        """Test complete indexing and search workflow"""
        # 1. Index vectors
        num_vectors = 100
        vectors = np.random.randn(num_vectors, 768).tolist()
        ids = [f"workflow_{i}" for i in range(num_vectors)]
        metadata = [{"batch": "test", "idx": i} for i in range(num_vectors)]
        
        index_response = client.post("/vector/index", json={
            "vectors": vectors,
            "ids": ids,
            "metadata": metadata
        })
        assert index_response.status_code == 201
        
        # 2. Search
        query = np.random.randn(768).tolist()
        search_response = client.post("/vector/search", json={
            "query_vector": query,
            "k": 10,
            "metric": "cosine"
        })
        assert search_response.status_code == 200
        results = search_response.json()["results"]
        assert len(results) <= 10
        
        # 3. Get specific vector
        vec_id = results[0]["id"]
        get_response = client.get(f"/vector/{vec_id}")
        assert get_response.status_code == 200
        
        # 4. Check stats
        stats_response = client.get("/vector/stats")
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats["total_vectors"] >= num_vectors
    
    def test_batch_operations(self):
        """Test batch search"""
        # Index
        vectors = np.random.randn(50, 768).tolist()
        ids = [f"batch_{i}" for i in range(50)]
        client.post("/vector/index", json={"vectors": vectors, "ids": ids})
        
        # Batch search
        queries = np.random.randn(5, 768).tolist()
        response = client.post("/vector/search/batch", json={
            "query_vectors": queries,
            "k": 10
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 5  # 5 queries
        assert all(len(r) <= 10 for r in data["results"])  # Max 10 results each


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
