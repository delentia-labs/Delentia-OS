"""
Round 111: the cut detector's measurement (criteria: research/REFERENCE_CUTS_CRITERIA_R111.md, written before the detector was changed).

The shot lists are the creator's own README tables; matching, scoring, the search space, the verdict rules and the refusals that keep a holdout from being looked at twice are tested here.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import argparse
import json

import pytest

from rct_control_plane import reference_analysis as ra
from research import reference_cuts_eval as ce

README = """# EP99 - test

## Format
| Shot | From +len |
|---|---|
| not a shot | 12 +3 |

## Shot list (global frames)
| Shot | from + len | Set | Action |
|---|---|---|---|
| hook | 0 +112 | 2D map | x |
| s02 | 112 +58 | L1 | y |
| S03 | 170 +130 | L1 | z |
| s06a | 494 +42 | L2 | w |

## Build
| Area | Files |
|---|---|
| s09 | 999 +9 |
"""


def test_the_shot_table_is_read_and_nothing_else(tmp_path):
    f = tmp_path / "README.md"
    f.write_text(README, encoding="utf-8")
    assert ce.shot_starts(f) == [("hook", 0), ("s02", 112), ("S03", 170), ("s06a", 494)]
    assert ce.truth_cuts(f) == [round(112 / 30, 3), round(170 / 30, 3), round(494 / 30, 3)]      # the first shot starts the clip: it is not a cut


@pytest.mark.skipif(not (ce.ROOT / "ep03_cher_ami" / "README.md").is_file(), reason="the creator's episode folders are not on this computer")
def test_the_real_readmes_give_the_numbers_the_criteria_state():
    assert len(ce.shot_starts(ce.ROOT / "ep03_cher_ami" / "README.md")) == 19
    assert len(ce.shot_starts(ce.ROOT / "ep01_elevator" / "README.md")) == 14
    assert len(ce.shot_starts(ce.ROOT / "ep02_emu_war" / "README.md")) == 16


def test_matching_is_one_to_one_within_the_tolerance():
    m = ce.match([1.0, 1.05, 5.0, 9.5], [1.02, 5.3, 9.6])
    assert sorted(m["matched"]) == [(1.0, 1.02), (9.5, 9.6)] or sorted(m["matched"]) == [(1.05, 1.02), (9.5, 9.6)]
    assert m["missed"] == [5.3]                                         # 5.0 is 0.3 s away: outside 0.20 s
    assert len(m["extra"]) == 2                                         # the second detection near 1.0 and the one at 5.0 are extras
    edge = ce.match([1.20], [1.0])
    assert edge["matched"] == [(1.2, 1.0)]
    assert ce.match([1.21], [1.0])["matched"] == []


def test_scores():
    m = ce.match([1.0, 2.0, 3.0, 9.0], [1.0, 2.0, 5.0])
    s = ce.score(m, 4, 3)
    assert (s["matched"], s["missed"], s["extra"]) == (2, 1, 2)
    assert s["recall"] == pytest.approx(2 / 3, abs=1e-3) and s["precision"] == 0.5
    p = ce.pooled([{"true_cuts": 10, "detected_cuts": 12, "matched": 9}, {"true_cuts": 5, "detected_cuts": 5, "matched": 4}])
    assert p["matched"] == 13 and p["recall"] == pytest.approx(13 / 15, abs=1e-3) and p["precision"] == pytest.approx(13 / 17, abs=1e-3)


def test_the_search_space_is_the_one_in_the_criteria():
    c = ce.candidates()
    assert len(c) == 74
    assert len({ce.label(x) for x in c}) == 74
    assert ce.BASELINE in c
    assert sum(1 for x in c if x["mode"] == "scene_only") == 2
    assert min(ce.simplicity(x) for x in c) == 0 and ce.simplicity(ce.BASELINE) == 0
    text = ce.CRITERIA.read_text(encoding="utf-8")
    assert "74 candidates" in text and "0.20 s" in text and "recall >= 0.85 AND precision >= 0.75" in text


def sig(diff, cells=None, back=None, scene=(), fps=10):
    return {"sample_fps": fps, "scene": list(scene), "diff": diff, "cells": cells or [1.0] * len(diff), "back": back or [False] * len(diff)}


def test_the_default_rule_is_the_one_first_shipped():
    s = sig([0, 40, 0, 0, 0, 0, 0, 90, 0, 0], scene=[0.9])
    assert ra.cuts_from_signals(s) == [0.2, 0.8]                       # the scene cut at 0.9 s is within 0.5 s of the colour cut at 0.8 s and merges into it


def test_each_part_of_the_rule_can_remove_a_cut():
    diff = [0.0] * 25
    cells = [1.0] * 25
    back = [False] * 25
    diff[1], cells[1], back[1] = 40, 0.2, True                          # at 0.2 s: a graphic that pops in and a flash
    diff[9] = 90                                                         # at 1.0 s: a real cut
    diff[19] = 50                                                        # at 2.0 s: a real cut
    s = sig(diff, cells=cells, back=back)
    assert ra.cuts_from_signals(s, mode="colour_only") == [0.2, 1.0, 2.0]
    assert ra.cuts_from_signals(s, mode="colour_only", cell_fraction=0.5) == [1.0, 2.0]          # a change in a fifth of the picture is a graphic, not a cut
    assert ra.cuts_from_signals(s, mode="colour_only", flash_filter=True) == [1.0, 2.0]           # the picture came back: a flash
    assert ra.cuts_from_signals(s, mode="colour_only", colour_jump=60) == [1.0]
    assert ra.cuts_from_signals(s, mode="colour_only", min_gap=1.0) == [0.2, 2.0]                 # 1.0 s is 0.8 s after 0.2 s: merged
    assert ra.cuts_from_signals(s, mode="scene_only") == []
    assert ra.cuts_from_signals(sig([0, 0], scene=[1.0, 3.0]), mode="scene_only") == [1.0, 3.0]
    with pytest.raises(ValueError):
        ra.cuts_from_signals(s, mode="other")


def row(recall, precision):
    return {"recall": recall, "precision": precision}


def test_the_verdict_rules():
    base = {"recall": 0.857, "precision": 0.80}
    same = {"recall": 0.857, "precision": 0.80}
    v = ce.verdict(base, same, [row(0.77, 0.7), row(0.93, 0.87)], [row(0.77, 0.7), row(0.93, 0.87)])
    assert v["baseline_useful_for_planning"] and v["chosen_useful_for_planning"] and not v["adopt_chosen_as_default"]      # no precision gain: not adopted
    better = {"recall": 0.86, "precision": 0.86}
    assert ce.verdict(base, better, [row(0.8, 0.8)], [row(0.8, 0.86)])["adopt_chosen_as_default"]
    lost_recall = {"recall": 0.80, "precision": 0.95}
    assert not ce.verdict(base, lost_recall, [row(0.8, 0.8)], [row(0.8, 0.9)])["adopt_chosen_as_default"]      # below the recall bar, and 0.057 lower than the baseline
    assert not ce.verdict({"recall": 0.84, "precision": 0.9}, {"recall": 0.84, "precision": 0.9}, [row(0.8, 0.9)], [row(0.8, 0.9)])["baseline_useful_for_planning"]
    assert not ce.verdict(base, same, [row(0.7, 0.9)], [row(0.7, 0.9)])["baseline_useful_for_planning"]      # one clip under 0.75 recall


def test_the_holdout_will_not_run_without_a_selection_and_will_not_run_twice(tmp_path, capsys):
    ns = argparse.Namespace(out=str(tmp_path), again=False)
    assert ce.cmd_holdout(ns) == 2
    assert "selection.json does not exist" in capsys.readouterr().out
    (tmp_path / "selection.json").write_text(json.dumps({"chosen": ce.BASELINE, "chosen_label": "x", "selection_sha256": "0"}), encoding="utf-8")
    (tmp_path / "holdout_results.json").write_text("{}", encoding="utf-8")
    assert ce.cmd_holdout(ns) == 2
    assert "run once" in capsys.readouterr().out


def test_only_the_dev_clip_is_decoded_before_the_selection(capsys):
    assert ce.cmd_signals(argparse.Namespace(set="holdout", out="x")) == 2
    assert {n for n, m in ce.CLIPS.items() if m["set"] == "holdout"} == {"ep01_v1", "ep02_v3"}
    assert {n for n, m in ce.CLIPS.items() if m["set"] == "dev"} == {"ep03_v2"}


# ------------------------------------------------------------------------------------------------ round 2: dissolves
BREAKDOWN = """# Breakdown

## 3. Shot-by-shot breakdown (see `keyshots.jpg`)
| # | Time | Location |
|---|---|---|
| 1 | 0.0\u20131.2 | track |
| 2 | 1.2\u20132.6 | loop |
| 3 | 2.7\u20134.0 | tower |

## 4. Visual language
| 4 | 9.0\u20139.9 | not read |
"""


def test_a_breakdown_table_gives_the_starts_of_every_shot_but_the_first(tmp_path):
    f = tmp_path / "b.md"
    f.write_text(BREAKDOWN, encoding="utf-8")
    assert ce.breakdown_cuts(f) == [1.2, 2.7]


@pytest.mark.skipif(not (ce.ROOT / "library" / "REF_BREAKDOWN_roller_coaster_TH.md").is_file(), reason="the creator's breakdown is not on this computer")
def test_the_real_roller_coaster_breakdown_gives_the_18_cuts_the_criteria_list():
    cuts = ce.breakdown_cuts(ce.ROOT / "library" / "REF_BREAKDOWN_roller_coaster_TH.md")
    assert len(cuts) == 18 and cuts[0] == 1.2 and cuts[-1] == 59.6


def test_a_window_catches_a_dissolve_that_no_single_step_shows():
    # a dissolve spread over three samples: each neighbouring step is 12, the picture three samples apart is 36
    s = sig([0, 0, 12, 12, 12, 0, 0, 0], scene=[])
    s["diffw"] = {"2": [0, 0, 24, 24, 12, 0, 0], "3": [0, 12, 36, 24, 12, 0]}
    assert ra.cuts_from_signals(s, mode="union", colour_jump=30) == []                    # window 1: no step above 30
    assert ra.cuts_from_signals(s, mode="union", colour_jump=30, window=3) == [0.5]       # window 3 sees 36 between samples 2 and 5: the later sample, 0.5 s
    assert ra.cuts_from_signals(s, mode="union", colour_jump=20, window=2) == [0.4]                                                    # 24 at 0.4 s and 0.5 s: one cut, the first
    with pytest.raises(ValueError):
        ra.cuts_from_signals(s, mode="union", window=4)
    with pytest.raises(ValueError):
        ra.cuts_from_signals(sig([0, 0]), mode="union", window=2)                       # signals made without windows say so


def test_window_one_is_exactly_the_shipped_rule():
    s = sig([0, 40, 0, 0, 0, 0, 0, 90, 0, 0], scene=[0.9])
    assert ra.cuts_from_signals(s, window=1) == ra.cuts_from_signals(s) == [0.2, 0.8]


def test_the_round_two_search_space_and_choice_order():
    c = ce.candidates2()
    assert len(c) == 30 and ce.BASELINE2 in c
    assert len({ce.label2(x) for x in c}) == 30
    assert sorted(c, key=ce.simplicity2)[0] == {**ce.BASELINE, "window": 1, "min_gap": 1.0}       # a tie: smaller window, jump nearest 30, then the larger gap
    text = ce.CRITERIA2.read_text(encoding="utf-8")
    assert "30 candidates" in text and "15 and 24" in text and "0.30 s" in text


def test_the_round_two_verdict_needs_all_three_parts():
    base = {"f1": 0.1, "recall": 0.05}
    ok_dev = {"f1": 0.6}
    guard = {"recall": 0.9, "precision": 0.8}
    e3b, e3c = {"f1": 0.727}, {"f1": 0.714}
    assert ce.verdict2(base, ok_dev, guard, guard, e3b, e3c, 19)["adopt_chosen_as_default"]
    assert not ce.verdict2(base, ok_dev, guard, guard, e3b, e3c, 26)["adopt_chosen_as_default"]                      # EP04 count outside 15-24
    assert not ce.verdict2(base, {"f1": 0.15}, guard, guard, e3b, e3c, 19)["adopt_chosen_as_default"]                # gain under 0.10
    assert not ce.verdict2(base, ok_dev, guard, {"recall": 0.8, "precision": 0.8}, e3b, e3c, 19)["adopt_chosen_as_default"]      # the guard no longer holds
    assert not ce.verdict2(base, ok_dev, guard, guard, e3b, {"f1": 0.6}, 19)["adopt_chosen_as_default"]             # EP03 fell by more than 0.05
    assert not ce.verdict2(base, ok_dev, guard, guard, e3b, e3c, 19)["baseline_finds_dissolves"]


def test_the_round_two_guard_refuses_without_a_selection_and_a_second_run(tmp_path, capsys):
    ns = argparse.Namespace(out=str(tmp_path), again=False)
    assert ce.cmd_r2_guard(ns) == 2
    assert "r2_selection.json does not exist" in capsys.readouterr().out
    (tmp_path / "r2_selection.json").write_text(json.dumps({"chosen": ce.BASELINE2, "selection_sha256": "0"}), encoding="utf-8")
    (tmp_path / "r2_guard_results.json").write_text("{}", encoding="utf-8")
    assert ce.cmd_r2_guard(ns) == 2
    assert "run once" in capsys.readouterr().out
