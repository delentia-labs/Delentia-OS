"""
Round 109: the Delta engine's effect on the tokens sent to a model, measured in the form the loop applies it (scripts/measure_delta_tokens_r109.py; questions and rules written first in
research/DELTA_TOKEN_SAVINGS_CRITERIA_R109.md, and for the goal-aware policy research/COMPRESS_POLICY_CRITERIA_R109.md). This runs the measurement in its quick form in a child process (it sets its
own data home and repository), once with the goal-aware policy (the default) and once with it off (the old behaviour), and pins what must stay true:

  * Q6  a compressed message never has more tokens than the raw one (both settings);
  * Q7  the stored original comes back byte for byte, and an expand of the whole range returns every line (both settings);
  * Q4  for a lookup the saving of a whole episode does not shrink when more calls follow the read (the compressed message is re-sent in each);
  * Q8  compressing 30 KB takes well under a second;
  * Q9  the history renderer never sends more than writing every step out (by tokens), and it does use a patch for a status dictionary with one changing field;
  * fidelity: with the policy a goal that shares words with the line keeps it, and a whole-text, no-signal or edit goal shows EVERY line; with the policy off a generic goal often hides the line
    (the old behaviour, kept reproducible so the before and after stay comparable).
The numbers themselves (the full corpus) are in research/DELTA_TOKEN_SAVINGS_RESULTS_R109.md and research/COMPRESS_POLICY_RESULTS_R109.md; they are a measurement, not a pinned value.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(out: Path, policy_off: bool) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DELENTIA_")}
    env.update({"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)})
    if policy_off:
        env["DELENTIA_COMPRESS_POLICY"] = "off"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "measure_delta_tokens_r109.py"), "--quick", "--out", str(out)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900, env=env, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("deltatokens") / "on.json", policy_off=False)


@pytest.fixture(scope="module")
def report_old(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("deltatokens") / "off.json", policy_off=True)


@pytest.mark.parametrize("which", ["report", "report_old"])
def test_a_compressed_message_never_has_more_tokens_than_the_raw_one(which, request):
    assert request.getfixturevalue(which)["q6_never_worse_violations"] == []


@pytest.mark.parametrize("which", ["report", "report_old"])
def test_the_original_comes_back_exactly(which, request):
    assert request.getfixturevalue(which)["q7_recovery_mismatches"] == []


def test_for_a_lookup_more_calls_after_the_read_never_shrink_the_saving_of_the_episode(report):
    groups = {}
    for key, value in report["episodes"].items():
        item, task, menu, later = [part.strip() for part in key.split("|")]
        groups.setdefault((item, task, menu), []).append((int(later.split()[0]), value["saved_pct"]))
    assert groups
    saw_a_saving = False
    for (item, task, menu), points in groups.items():
        points.sort()
        savings = [s for _, s in points]
        assert savings == sorted(savings), (item, task, menu, points)          # the compressed message is re-sent in every later call: the saving grows with the calls
        if task == "task=whole":
            assert savings == [0.0, 0.0, 0.0], (item, savings)                  # the policy shows a whole-text task's text whole: no saving to claim, nothing removed
        else:
            saw_a_saving = saw_a_saving or any(s > 0 for s in savings)
    assert saw_a_saving


def test_compressing_thirty_kilobytes_takes_far_less_than_a_second(report):
    assert all(v["max_ms"] < 1000 for v in report["q8_time_ms"].values())


def test_the_history_renderer_never_costs_tokens_and_does_use_a_patch_for_a_status_dictionary(report):
    for name, v in report["q9_history"].items():
        assert v["tokens_with_render_history"] <= v["tokens_written_out"] * 1.01, name
    keyed = next(v for k, v in report["q9_history"].items() if "40 separate fields" in k)
    assert keyed["patch_lines"] >= 1 and keyed["saved_pct"] > 30
    string_shaped = report["q9_history"]["the same file read six times, one number changing"]
    assert string_shaped["patch_lines"] == 0                                      # a changing field inside one long string cannot be patched: stated, not hidden


def test_with_the_policy_a_lookup_keeps_its_line_and_every_other_goal_shows_every_line(report):
    filtered = 0
    for item in report["corpus"]:
        goals = item["goals"]
        for kind in ("literal", "partial", "single"):
            assert goals[kind]["needle_kept_pct"] == 100.0, (item["name"], kind)
            filtered += goals[kind]["applied_pct"] > 0
        for kind in ("edit", "generic"):
            assert goals[kind]["applied_pct"] == 0 and goals[kind]["lines_shown_pct_median"] == 100.0 and goals[kind]["needle_kept_pct"] == 100.0, (item["name"], kind)
    assert filtered >= 1                                                           # the filter is still used where it is right


def test_with_the_policy_off_a_generic_goal_often_hides_the_line_which_is_the_old_behaviour(report_old):
    hidden = [i["name"] for i in report_old["corpus"] if i["goals"]["generic"]["applied_pct"] > 0 and i["goals"]["generic"]["needle_kept_pct"] < 100.0]
    assert hidden
