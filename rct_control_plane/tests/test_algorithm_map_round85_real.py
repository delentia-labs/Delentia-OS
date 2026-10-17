"""
Round 85, the algorithm-to-behaviour map: all 41 algorithms are in it, each with a channel that follows from the pipeline's own registry, and the committed file matches what the registry says.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path

from research import algorithm_map


def test_all_41_algorithms_are_mapped_each_with_a_channel_and_a_removal_statement():
    data = algorithm_map.rows()
    ids = {r["id"] for r in data}
    assert ids == {f"ALGO-{i:02d}" for i in range(1, 42)}
    assert all(r["channel"] in ("direct", "advice", "record") and r["behaviour"] and r["removal"] for r in data)


def test_the_channel_follows_the_registry_not_a_guess():
    from rct_control_plane.algorithm_pipeline import ADAPTERS
    phases = {a.algo_id: a.phase for a in ADAPTERS}
    for r in algorithm_map.rows():
        if r["channel"] == "advice":
            assert r["phase"] == "pre"
        if r["channel"] == "record":
            assert r["phase"] == "post"
    assert {r["id"] for r in algorithm_map.rows() if r["channel"] == "direct"} <= set(phases) and set(algorithm_map.DIRECT) == {"ALGO-01", "ALGO-04", "ALGO-07", "ALGO-21", "ALGO-25"}


def test_the_direct_algorithms_name_the_switch_that_exists_and_the_others_say_there_is_none():
    by_id = {r["id"]: r for r in algorithm_map.rows()}
    assert "A101" in by_id["ALGO-01"]["removal"] and "A011" in by_id["ALGO-04"]["removal"]
    assert all("none" in r["removal"] or "DELENTIA_ALGORITHM_PIPELINE" in r["removal"] for r in algorithm_map.rows() if r["channel"] != "direct")


def test_the_committed_file_matches_the_registry():
    committed = (Path(algorithm_map.__file__).with_name("ALGORITHM_BEHAVIOUR_MAP.md")).read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == algorithm_map.render(), "run `python -m research.algorithm_map` to regenerate the map"
