"""
FDIA contract via shared golden vectors (Round 48 R3.3), Python side.

contracts/fdia_vectors.v1.json is committed byte-identically here and in
delentia-mcp-ecosystem (tests/fdia_contract_vectors.test.mjs), pinned by the
same SHA-256. Both AlgorithmKernel41.algo_01_fdia and its copy
governed_autonomous_loop.fdia_score must match every agreed vector, and the
documented edge divergences must stay exactly as recorded - changing the
formula on either side fails that side's CI until the contract is
regenerated for both.

Round 48 (Architect decision 2026-09-28): D <= 0 or I <= 0 -> F = 0 on both
sides ("no data / no intent = no future"); contract version 2. The only
remaining divergences are clamping of out-of-range values (D > 100,
I > 10, A > 1), which the TypeScript request schema never lets through.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.governed_autonomous_loop import fdia_score

FDIA_VECTORS_SHA256 = "9bf3a660b5cfc8546cc329bd48c4660312fc636920763bc591033aa10700a496"
RAW = (Path(__file__).resolve().parents[2] / "contracts" / "fdia_vectors.v1.json").read_bytes().replace(b"\r\n", b"\n")
VECTORS = json.loads(RAW)


def _kernel_f(D, I, A):
    # algo_01_fdia only touches self.executed_counts; no need to build the
    # whole kernel (and its ~20 s of heavy imports) for pure arithmetic.
    return AlgorithmKernel41.algo_01_fdia(SimpleNamespace(executed_counts=defaultdict(int)), D, I, A)


def test_contract_file_is_the_agreed_version():
    assert hashlib.sha256(RAW).hexdigest() == FDIA_VECTORS_SHA256


def test_both_python_implementations_match_every_agreed_vector():
    assert len(VECTORS["agreed"]) > 400
    tol = VECTORS["tolerance"] + 1e-12
    for v in VECTORS["agreed"]:
        for name, f in (("algo_01_fdia", _kernel_f), ("fdia_score", fdia_score)):
            got = f(v["D"], v["I"], v["A"])
            assert abs(got - v["F"]) <= tol, f"{name} D={v['D']} I={v['I']} A={v['A']}: {got} != {v['F']}"


def test_known_divergences_stay_as_documented_on_the_python_side():
    for v in VECTORS["known_divergences"]:
        assert _kernel_f(v["D"], v["I"], v["A"]) == v["py"], v["why"]
        assert fdia_score(v["D"], v["I"], v["A"]) == v["py"], v["why"]
