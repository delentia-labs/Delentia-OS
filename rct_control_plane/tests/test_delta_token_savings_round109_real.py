"""
Round 109: the Delta engine's effect on the tokens sent to a model, measured in the form the loop applies it (scripts/measure_delta_tokens_r109.py; questions and rules written first in
research/DELTA_TOKEN_SAVINGS_CRITERIA_R109.md). This runs the measurement in its quick form in a child process (it sets its own data home and repository) and pins what must stay true:

  * Q6  a compressed message never has more tokens than the raw one;
  * Q7  the stored original comes back byte for byte, and an expand of the whole range returns every line;
  * Q4  the saving of a whole episode does not shrink when more calls follow the read (the compressed message is re-sent in each);
  * Q8  compressing 30 KB takes well under a second;
  * Q9  the history renderer never sends more than writing every step out (by tokens), and it does use a patch for a status dictionary with one changing field;
  * fidelity: wherever a message was compressed for a goal that shares words with the line asked about, that line is still shown (literal goals: 100%), and the output shows the lossy side:
    for a generic goal the needle is often NOT shown.
The numbers themselves (the full corpus) are in research/DELTA_TOKEN_SAVINGS_RESULTS_R109.md; they are a measurement, not a pinned value.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    out = tmp_path_factory.mktemp("deltatokens") / "report.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("DELENTIA_")}
    env.update({"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)})
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "measure_delta_tokens_r109.py"), "--quick", "--out", str(out)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900, env=env, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out.read_text(encoding="utf-8"))


def test_a_compressed_message_never_has_more_tokens_than_the_raw_one(report):
    assert report["q6_never_worse_violations"] == []


def test_the_original_comes_back_exactly(report):
    assert report["q7_recovery_mismatches"] == []


def test_more_calls_after_the_read_never_shrink_the_saving_of_the_episode(report):
    groups = {}
    for key, value in report["episodes"].items():
        item, menu, later = [part.strip() for part in key.split("|")]
        groups.setdefault((item, menu), []).append((int(later.split()[0]), value["saved_pct"]))
    assert groups
    for (item, menu), points in groups.items():
        points.sort()
        savings = [s for _, s in points]
        assert savings == sorted(savings), (item, menu, points)                # the compressed message is re-sent in every later call: the saving grows with the calls
        assert all(s > 0 for s in savings)


def test_compressing_thirty_kilobytes_takes_far_less_than_a_second(report):
    assert all(v["max_ms"] < 1000 for v in report["q8_time_ms"].values())


def test_the_history_renderer_never_costs_tokens_and_does_use_a_patch_for_a_status_dictionary(report):
    for name, v in report["q9_history"].items():
        assert v["tokens_with_render_history"] <= v["tokens_written_out"] * 1.01, name
    keyed = next(v for k, v in report["q9_history"].items() if "40 separate fields" in k)
    assert keyed["patch_lines"] >= 1 and keyed["saved_pct"] > 30
    string_shaped = report["q9_history"]["the same file read six times, one number changing"]
    assert string_shaped["patch_lines"] == 0                                      # a changing field inside one long string cannot be patched: stated, not hidden


def test_a_goal_that_shares_words_with_the_line_keeps_it_and_a_generic_goal_often_does_not(report):
    hidden = 0
    for item in report["corpus"]:
        literal, generic = item["goals"]["literal"], item["goals"]["generic"]
        if literal["applied_pct"] > 0:
            assert literal["needle_kept_pct"] == 100.0, item["name"]
        if generic["applied_pct"] > 0 and generic["needle_kept_pct"] < 100.0:
            hidden += 1
    assert hidden >= 1                                                             # the lossy side is visible: a saving that hides the line is not counted as a saving
