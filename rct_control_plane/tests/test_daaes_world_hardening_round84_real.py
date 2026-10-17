"""
Round 84, what CodeQL found in the DAAES test worlds: the tools a model calls there take paths, globs and patterns from a model that is not trusted. A path may not leave the workspace, a glob may not climb out of it,
and a search pattern is literal text, never a regular expression the model wrote (a hostile pattern could stall the run).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import time

from research.daaes import tc003
from research.daaes.delentia_session import DirWorld as World


def run(world, name, args):
    result = asyncio.run(world.call_tool(name, args))
    return json.loads(result.content[0].text)


def test_a_model_cannot_read_or_write_outside_its_workspace(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("do not read", encoding="utf-8")
    world = World(tmp_path / "w")
    (tmp_path / "w" / "inside.txt").write_text("fine", encoding="utf-8")
    assert run(world, "delentia_read_repo_file", {"relative_path": "inside.txt"})["content"] == "fine"
    for bad in ("../outside.txt", "..\\outside.txt", str(secret), "sub/../../outside.txt"):
        out = run(world, "delentia_read_repo_file", {"relative_path": bad})
        assert out["ok"] is False and out["content"] == "", bad
        out = run(world, "delentia_write_repo_file", {"relative_path": bad, "content_text": "overwritten"})
        assert out["ok"] is False, bad
    assert secret.read_text(encoding="utf-8") == "do not read", "nothing outside the workspace was touched"


def test_the_search_stand_in_is_literal_and_stays_inside_the_workspace(tmp_path):
    root = tmp_path / "w"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("def total(x):\n    return x + 1\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("def total(x): return 0\n", encoding="utf-8")
    world = tc003.LiveTestWorld(root, "F0")
    assert world is not None
    hits = run(world, "delentia_search_repo_files", {"pattern": "def total"})["matches"]
    assert [h["path"] for h in hits] == ["pkg/a.py"]
    both = run(world, "delentia_search_repo_files", {"pattern": "nothing like this|return x"})["matches"]
    assert [h["line_number"] for h in both] == [2], "`|` separates alternatives"
    assert "error" in run(world, "delentia_search_repo_files", {"pattern": "def", "glob": "../*.py"}), "a glob cannot climb out"
    assert "error" in run(world, "delentia_search_repo_files", {"pattern": ""})
    started = time.time()
    run(world, "delentia_search_repo_files", {"pattern": "(a+)+$" + "a" * 5000})
    assert time.time() - started < 2.0, "a catastrophic regular expression is just text here"


def test_the_owner_policy_of_the_live_cases_has_a_rule_for_every_tool_the_world_offers(tmp_path):
    """Found by the first local-model A/B: the search tool was added to the world but not to the policy, so the zero-trust fallback (A = 0) blocked every search and Delentia's arm was judged on a handicap."""
    from rct_control_plane import fdia_policy
    policy, errors = fdia_policy.validate_policy(tc003.OWNER_POLICY)
    assert policy is not None, errors
    world = tc003.LiveTestWorld(tmp_path / "w", "F0")
    names = [t.name for t in asyncio.run(world.list_tools()) if t.name != "delentia_crawl_url"]
    assert "delentia_search_repo_files" in names and "delentia_read_repo_file" in names
    for name in names:
        verdict = fdia_policy.evaluate(policy, name, {"relative_path": "ledgercalc/core.py", "pattern": "x"}, principal="agent")
        assert verdict.rule_id, f"{name}: no rule matched, the fallback decided"
