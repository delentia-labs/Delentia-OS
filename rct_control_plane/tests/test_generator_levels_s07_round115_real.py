"""Difficulty levels of the research generators (research/EFFICACY_S07_CRITERIA_R115.md B2, B3): free, no model."""
import json
from pathlib import Path

import pytest

from research import generate_tasks as gq
from research import generate_tickets as gt

HERE = Path(gq.HERE)
SEEDS = {("dev", "quotes"): 20261008, ("validation", "quotes"): 20261009, ("dev", "tickets"): 20261014, ("validation", "tickets"): 20261015}


def _disk(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


@pytest.mark.parametrize("split", ["dev", "validation"])
def test_level_1_reproduces_the_committed_quote_splits_byte_for_byte(split):
    data = gq.build(split, SEEDS[(split, "quotes")], 1)
    for tid, fixture in data["fixtures"].items():
        assert (HERE / "fixtures" / f"{tid}.json").read_bytes() == (json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"), tid
    for tid, oracle in data["hidden"].items():
        assert (HERE / "hidden" / f"{tid}.json").read_bytes() == (json.dumps(oracle, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"), tid


TICKET_SEEDS = {"dev": 20261010, "validation": 20261011}


@pytest.mark.parametrize("split", ["dev", "validation"])
def test_level_1_reproduces_the_committed_ticket_splits_byte_for_byte(split):
    data = gt.build(split, TICKET_SEEDS[split], 1)
    assert data["hidden"]
    for tid, oracle in data["hidden"].items():
        assert (HERE / "hidden" / f"{tid}.json").read_bytes() == _disk(oracle), tid
    for tid, fixture in data["fixtures"].items():
        assert (HERE / "fixtures" / f"{tid}.json").read_bytes() == _disk(fixture), tid


def test_a_bad_level_is_refused_and_the_sealed_test_split_is_level_1_only():
    with pytest.raises(ValueError):
        gq.build("dev", 1, 4)
    with pytest.raises(ValueError):
        gt.build("dev", 1, 0)


def _files(data):
    return sum(len(f["files"]) for k, f in data["fixtures"].items() if "budget" in k or "tix-plain" in k or "injection" in k)


@pytest.mark.parametrize("module", [gq, gt])
def test_each_level_makes_the_tasks_larger_and_never_changes_their_number_or_oracle_shape(module):
    by = {level: module.build("dev", 777, level) for level in (1, 2, 3)}
    assert _files(by[1]) < _files(by[2]) < _files(by[3])
    for level in (2, 3):
        assert [t["task_id"] for t in by[level]["tasks"]] == [t["task_id"] for t in by[1]["tasks"]]
        assert len(by[level]["trajectories"]) == len(by[1]["trajectories"])
        assert {tid: sorted(o) for tid, o in by[level]["hidden"].items()} == {tid: sorted(o) for tid, o in by[1]["hidden"].items()}


def test_the_forbidden_write_and_trajectory_tasks_are_not_resized():
    d1, d3 = gq.build("dev", 777, 1), gq.build("dev", 777, 3)
    for tid in d1["fixtures"]:
        if "forbidden" in tid:
            assert len(d1["fixtures"][tid]["files"]) == len(d3["fixtures"][tid]["files"]), tid


def test_the_quote_answer_is_derivable_from_the_fixture_at_every_level():
    """B3: for every plain and attacked quote task the expected list is exactly what the rule gives from the task's own quotes."""
    checked = 0
    for level in (1, 2, 3):
        for seed in (31, 32):
            data = gq.build("dev", seed, level)
            for tid, o in data["hidden"].items():
                if "budget" not in tid and "injection" not in tid:
                    continue
                within = sorted(q["vendor"] for q in o["quotes"] if q["price"] <= o["budget"])
                assert sorted(o["expected_in_budget"]) == within and 0 < len(within) < len(o["quotes"]), (level, tid)
                assert len({q["price"] for q in o["quotes"]}) == len(o["quotes"])
                checked += 1
    assert checked >= 60


def test_the_ticket_answer_is_derivable_from_the_fixture_at_every_level():
    checked = 0
    for level in (1, 2, 3):
        data = gt.build("dev", 31, level)
        for tid, o in data["hidden"].items():
            tickets = o.get("tickets")
            if "plain" not in tid and "injection" not in tid:
                continue                                              # the forbidden-write tasks expect a wait for a person, not a list
            urgent = sorted(t["id"] for t in tickets if gt._is_urgent(t, o["limit_hours"]))
            assert sorted(o["expected_urgent"]) == urgent and urgent, (level, tid)
            checked += 1
    assert checked >= 6


def test_a_harder_level_is_written_to_its_own_folder_and_never_over_the_committed_files(tmp_path):
    gq.write("dev", 5, out=tmp_path, level=2)
    assert (tmp_path / "level2" / "tasks" / "dev_static.jsonl").exists() and not (tmp_path / "tasks").exists()
    gt.write("dev", 5, out=tmp_path, level=3)
    assert (tmp_path / "level3" / "tasks" / "dev_tickets_static.jsonl").exists()
