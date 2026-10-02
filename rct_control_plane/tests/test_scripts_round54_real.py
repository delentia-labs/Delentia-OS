"""Round 54: the measuring scripts are code too. Their structure is tested; the numbers they print are in the Round 54 report."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import asyncio

import dag_wave_benchmark as bench
import measure_toon_tokens as toon
from rct_control_plane import dag_executor as dag


def test_toon_payloads_are_built_from_the_runtime_and_each_is_counted():
    payloads = toon.payloads()
    assert len(payloads) == 6 and len(payloads["tool list (36 name + description)"]) >= 30
    assert toon.count_tokens("hello world") >= 2


def test_toon_round_trip_is_checked_not_assumed():
    from rct_control_plane.toon_formatter import toon_deserialize, toon_serialize
    simple = {"a": 1, "b": ["x", "y"], "c": {"d": True}}
    assert toon_deserialize(toon_serialize(simple)) == simple


def test_every_benchmark_shape_compiles_to_a_valid_graph_with_the_expected_waves():
    shapes = bench.shapes()
    waves = {name: dag.waves_of(dag.compile_batch(shape["calls"])) for name, shape in shapes.items()}
    assert waves["latency-bound (4 independent waits)"] == [["a", "b", "c", "d"]]
    assert waves["diamond (a -> b,c -> d)"] == [["a"], ["b", "c"], ["d"]]
    assert len(waves["chain (a -> b -> c -> d)"]) == 4


def test_one_real_call_of_the_benchmark_runner_works():
    calls = bench.shapes()["cpu-bound (4 repository searches)"]["calls"][:2]
    result = asyncio.run(bench.run_once(calls, True))
    assert result["failed"] == [] and result["waves"] == [["a", "b"]]
