"""
Round 110: what really happens to a subagent that runs as its own OS process (checked before any multi-agent design is built on it).

Three questions, each answered by running a REAL child (`subagent_runner` in its own process, a real git worktree, the real governed loop,
a scripted model over HTTP so no real model is needed):

  Q1. Can a child write a file?                       -> it stops at `pending_approval`; nobody is there to sign, so the file is never written.
  Q2. Does a child use the owner's policy?             -> yes: an owner rule that asks for a signature on reads reaches the child.
  Q3. What is left of a child's work after it ends?    -> nothing: the worktree is removed and its branch carries no commit.

These are CHARACTERISATION tests: they record today's behaviour. If a later round adds a step that brings a child's work back into the project
(a patch handed to a signed plan), Q1 and Q3 are expected to change and these tests must change with it, on purpose.
Source: future plan for delentia/05_SOVEREIGN_META_HARNESS_AND_MULTI_AGENT_PLAN_ANALYSIS_AND_READINESS.md, section 3.1.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

import scripted_model as sm


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


class _Store:
    def __init__(self):
        self.rows = []

    def save_architect_decision(self, **kw):
        self.rows.append(kw)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "0.1.0"\n', encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    home = tmp_path / "home"
    home.mkdir()
    with sm.ScriptedModel(sm.competent) as model:
        from rct_control_plane.model_config import save_model_selection
        cfg = tmp_path / "model.json"
        save_model_selection("openai-compat", model.model_id, path=cfg, endpoint={
            "base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-test-model"})
        for k, v in {"DELENTIA_HOME": str(home), "DELENTIA_MODEL_CONFIG": str(cfg), "DELENTIA_LLM_PROVIDER": "openai-compat",
                     "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "PYTHONIOENCODING": "utf-8",
                     "PYTHONPATH": str(Path(__file__).resolve().parents[2])}.items():
            monkeypatch.setenv(k, v)
        for k in ("DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL", "DELENTIA_NOTARY_TOKEN", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS"):
            monkeypatch.delenv(k, raising=False)
        yield repo, home


def _run(repo: Path, goals):
    from rct_control_plane.jitna_distributor import distribute_to_subagents
    return asyncio.run(distribute_to_subagents(goals, _Store(), repo_root=str(repo), timeout_seconds=240))


def test_a_child_cannot_write_and_leaves_nothing_behind(world):
    repo, _ = world
    (child,) = _run(repo, ["write a note to child_note.txt"])
    # Q1: the write waits for a signature that nobody in a child process can give
    assert child["jitna"]["response_verified"], child
    assert child["stopped_reason"] == "pending_approval", child
    assert not (repo / "child_note.txt").exists()
    # Q3: the child's worktree is gone and its branch holds no commit of its own
    assert not list((repo / ".delentia_worktrees").glob("agent_*")) if (repo / ".delentia_worktrees").exists() else True
    branches = _git(repo, "branch", "--list", "swarm/*").split()
    for b in [x for x in branches if x.startswith("swarm/")]:
        assert _git(repo, "rev-parse", b) == _git(repo, "rev-parse", "main"), f"{b} carries work"
    assert _git(repo, "status", "--porcelain") in ("", "?? .delentia_worktrees/")      # the main working tree is untouched


def test_a_child_reads_normally_without_an_owner_rule(world):
    repo, _ = world
    (child,) = _run(repo, ["Read the file pyproject.toml and tell me the project name"])
    assert child["stopped_reason"] != "pending_approval", child
    assert "sample-service" in str(child.get("final_answer")), child


def test_the_owners_policy_reaches_the_child(world, monkeypatch, tmp_path):
    repo, _ = world
    policy = tmp_path / "fdia_policy.json"
    policy.write_text(json.dumps({"rules": [{"rule_id": "R-READ-SIGN", "intent_patterns": ["read_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(policy))
    (child,) = _run(repo, ["Read the file pyproject.toml and tell me the project name"])
    # Q2: the same goal that was answered above now stops, because the owner's rule asks for a signature on reads
    assert child["stopped_reason"] == "pending_approval", child
