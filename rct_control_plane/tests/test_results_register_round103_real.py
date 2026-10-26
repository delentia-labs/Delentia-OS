"""Round 103: the results register ties a result to its commit, its pre-registered rule and its cost, and refuses what would make that meaningless."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research import results_register as rr  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture()
def world(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    criteria = repo / "criteria.md"
    criteria.write_text("pass if found >= 0.80\n", encoding="utf-8")
    _git(repo, "add", "criteria.md")
    _git(repo, "commit", "-q", "-m", "rule")
    result = repo / "result.json"
    result.write_text(json.dumps({"found": 0.85}), encoding="utf-8")
    os.utime(result, (result.stat().st_atime, criteria.stat().st_mtime + 3600))     # the result was written an hour AFTER the rule was committed
    return {"repo": repo, "criteria": criteria, "result": result, "register": tmp_path / "reg" / "R.jsonl"}


def _add(w, **kw):
    args = dict(stage="P2", model="qwen/x", provider="openrouter", criteria=w["criteria"], result=w["result"], verdict="pass", est_usd=0.05, actual_usd=0.04, register=w["register"])
    args.update(kw)
    return rr.add_entry(**args)


def test_an_entry_records_the_hashes_the_commit_and_the_cost(world):
    e = _add(world)
    assert e["id"] == "R0001" and e["verdict"] == "pass" and e["actual_usd"] == 0.04 and e["estimated_usd"] == 0.05
    assert e["criteria"]["sha256"] == rr.sha256_file(world["criteria"]) and e["result"]["sha256"] == rr.sha256_file(world["result"])
    assert len(e["commit"]) >= 7 and isinstance(e["tree_dirty"], bool)
    assert [x["id"] for x in rr.read_entries(world["register"])] == ["R0001"]
    assert _add(world)["id"] == "R0002"                                  # append-only, numbered in order


def test_a_rule_committed_before_the_result_is_a_pre_registration(world):
    assert _add(world)["criteria"]["criteria_after_result"] is False


def test_a_rule_committed_after_the_result_is_marked_late(world):
    os.utime(world["result"], (1_000_000_000, 1_000_000_000))            # the result is older than the commit of the rule
    e = _add(world)
    assert e["criteria"]["criteria_after_result"] is True
    assert "late rule" in rr.render(world["register"])


def test_a_rule_that_was_never_committed_is_also_late(world):
    loose = world["repo"] / "loose.md"
    loose.write_text("a rule nobody committed\n", encoding="utf-8")
    assert _add(world, criteria=loose)["criteria"]["criteria_after_result"] is True


@pytest.mark.parametrize("bad", [{"verdict": "great"}, {"provider": "magic"}, {"stage": " "}, {"model": ""}])
def test_nonsense_is_refused(world, bad):
    with pytest.raises(rr.RegisterError):
        _add(world, **bad)
    assert rr.read_entries(world["register"]) == []


def test_a_paid_run_without_its_actual_cost_is_refused_but_a_local_one_may_leave_it(world):
    with pytest.raises(rr.RegisterError, match="actual cost"):
        _add(world, actual_usd=None)
    assert _add(world, provider="ollama", actual_usd=None)["actual_usd"] is None


def test_a_missing_file_or_an_unknown_replacement_is_refused(world):
    with pytest.raises(rr.RegisterError, match="does not exist"):
        _add(world, result=world["repo"] / "nope.json")
    with pytest.raises(rr.RegisterError, match="no entry"):
        _add(world, replaces="R0099")


def test_a_correction_is_a_new_entry_and_the_old_one_is_shown_as_replaced(world):
    first = _add(world, verdict="fail")
    second = _add(world, verdict="pass", replaces=first["id"])
    text = rr.render(world["register"])
    assert "fail (replaced)" in text and second["replaces"] == first["id"]
    assert len(rr.read_entries(world["register"])) == 2                  # nothing was edited or deleted


def test_verify_finds_a_result_that_changed_after_it_was_registered(world):
    _add(world)
    assert rr.verify(world["register"], root=world["repo"]) == []
    world["result"].write_text(json.dumps({"found": 0.99}), encoding="utf-8")
    problems = rr.verify(world["register"], root=world["repo"])
    assert len(problems) == 1 and "changed after it was registered" in problems[0]


def test_verify_finds_a_missing_file_and_a_reused_id(world):
    _add(world)
    world["result"].unlink()
    assert any("missing" in p for p in rr.verify(world["register"], root=world["repo"]))
    line = world["register"].read_text(encoding="utf-8").splitlines()[0]
    with open(world["register"], "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    assert any("used twice" in p for p in rr.verify(world["register"], root=world["repo"]))


def test_render_totals_the_registered_cost(world):
    _add(world, actual_usd=0.04)
    _add(world, actual_usd=0.10)
    assert "Total actual cost registered: $0.1400" in rr.render(world["register"])


def test_a_register_line_that_is_not_json_is_reported_not_skipped(world):
    world["register"].parent.mkdir(parents=True, exist_ok=True)
    world["register"].write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(rr.RegisterError, match="not JSON"):
        rr.read_entries(world["register"])
