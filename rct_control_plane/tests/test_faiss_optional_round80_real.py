"""
Round 80: faiss-cpu (66 MB) is an optional extra now. Without it the kernel still starts and the exact ("flat") vector index runs in numpy.

What is checked:
  * the numpy index gives the same neighbours and the same scores as the real faiss index, for all three metrics (when faiss is installed here, as it is in CI);
  * with faiss made unimportable (child process) the whole kernel imports and builds, and a search works;
  * the approximate indexes (ivf, hnsw) refuse with a message that says what to install, instead of failing later;
  * `get_stats()` tells which engine answered.
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_16_vector import FAISSBackend, _NumpyFlatIndex

faiss = pytest.importorskip("faiss")


def _backend(metric, force_numpy=False):
    backend = FAISSBackend(index_type="flat", metric=metric)
    if force_numpy:
        saved = sys.modules.get("faiss")
        sys.modules["faiss"] = None                                  # makes `import faiss` raise ImportError
        try:
            backend.initialize(dimension=24)
        finally:
            sys.modules["faiss"] = saved
    else:
        backend.initialize(dimension=24)
    return backend


@pytest.mark.parametrize("metric", ["cosine", "dot", "euclidean"])
def test_numpy_index_agrees_with_faiss(metric):
    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(300, 24)).astype(np.float32).tolist()
    ids = [f"v{i}" for i in range(300)]
    real, fallback = _backend(metric), _backend(metric, force_numpy=True)
    assert isinstance(fallback.faiss_index, _NumpyFlatIndex) and not isinstance(real.faiss_index, _NumpyFlatIndex)
    real.index(vectors, ids)
    fallback.index(vectors, ids)
    for query in rng.normal(size=(25, 24)).astype(np.float32).tolist():
        a, b = real.search(query, k=7), fallback.search(query, k=7)
        assert [r.id for r in a] == [r.id for r in b]
        assert [round(r.score, 4) for r in a] == [round(r.score, 4) for r in b]


def test_fewer_vectors_than_k_gives_fewer_results_not_an_error():
    backend = _backend("cosine", force_numpy=True)
    backend.index([[1.0] + [0.0] * 23, [0.0, 1.0] + [0.0] * 22], ["a", "b"])
    results = backend.search([1.0] + [0.0] * 23, k=10)
    assert [r.id for r in results] == ["a", "b"] and results[0].score > results[1].score
    assert FAISSBackend(index_type="flat", metric="cosine").search is not None
    empty = _backend("cosine", force_numpy=True)
    assert empty.search([1.0] + [0.0] * 23, k=3) == []


def test_clear_and_count_work_on_the_fallback():
    backend = _backend("euclidean", force_numpy=True)
    backend.index([[0.0] * 24, [1.0] * 24], ["x", "y"])
    assert backend.count() == 2 and backend.clear() == 2 and backend.count() == 0 and backend.faiss_index.ntotal == 0


def test_stats_name_the_engine():
    assert _backend("cosine").get_stats()["engine"] == "faiss"
    assert _backend("cosine", force_numpy=True).get_stats()["engine"] == "numpy-flat"


def test_approximate_indexes_say_what_to_install_when_faiss_is_missing():
    backend = FAISSBackend(index_type="hnsw", metric="cosine")
    saved = sys.modules.get("faiss")
    sys.modules["faiss"] = None
    try:
        with pytest.raises(ImportError, match=r"delentia-os\[vector\]"):
            backend.initialize(dimension=24)
    finally:
        sys.modules["faiss"] = saved


CHILD = """
import sys
sys.modules['faiss'] = None
import rct_control_plane.algorithm_kernel_41 as k      # the kernel builds its vector engine at import
engine = k.ALGORITHM_KERNEL
assert engine is not None
from rct_control_plane.algo_16_vector import FAISSBackend
b = FAISSBackend(index_type='flat', metric='cosine'); b.initialize(8)
b.index([[1.0] + [0.0] * 7, [0.0, 1.0] + [0.0] * 6], ['a', 'b'])
assert [r.id for r in b.search([1.0] + [0.0] * 7, k=2)] == ['a', 'b']
assert b.get_stats()['engine'] == 'numpy-flat'
print('OK kernel without faiss')
"""


def test_the_kernel_starts_without_faiss():
    done = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert done.returncode == 0, done.stderr[-1500:]
    assert "OK kernel without faiss" in done.stdout
