"""
FDIA contract via shared golden vectors (Round 48 R3.3), Python side.

contracts/fdia_vectors.v1.json is committed byte-identically here and in
delentia-mcp-ecosystem (tests/fdia_contract_vectors.test.mjs), pinned by the
same SHA-256. Both AlgorithmKernel41.algo_01_fdia and its copy
governed_autonomous_loop.fdia_score must match every agreed vector, and the
documented edge divergences must stay exactly as recorded - changing the
formula on either side fails that side's CI until the contract is
regenerated for both.

Open decision recorded in the contract (not changed here): for D = 0 the
Python side floors D at 0.01, so F = 0.01^I > 0 and the governed loop's
`F <= 0` block does not fire, while TypeScript returns 0 (blocks).
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

FDIA_VECTORS_SHA256 = "98f2a7f72ceaefe5d13e1ba7a797a1cd8c78c5ec3c2253f939825cebad3ec475"
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
