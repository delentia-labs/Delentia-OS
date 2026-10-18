"""
Round 86: the Hermes arm (H0) can run inside a throw-away container, which is the sandbox a real model needs.

What is checked without Docker: the command line that would be run (the only things that leave the machine's control are the workspace, this run's folder and one model endpoint; nothing of ours in the
environment; capabilities dropped; the gateway address rewritten so the container can reach it), that the test command the model is told is the container's own Python, and that a missing image
does not turn into a pass. The real container is exercised by `python -m research.daaes benchmark --provider rehearsal --arms h0 --hermes-container daaes-hermes:r86` (see the Round 86 document).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research.daaes import hermes_adapter


class _Done:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _capture(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if "rev-parse" in argv:
            return _Done(stdout=hermes_adapter.PINNED_SHA + "\n")
        return _Done(stdout='noise\nHERMES_RESULT {"final_response": "ok", "completed": true, "tool_calls": []}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_container_run_passes_only_the_workspace_and_one_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HERMES_CONTAINER", "daaes-hermes:test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-reach-the-container")
    calls = _capture(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    out = hermes_adapter.run_goal("fix it", workspace, "http://127.0.0.1:54321/v1", "gateway-token", "m", tmp_path / "run", real_model=True, sandboxed=False)
    assert out["available"] and out["result"]["completed"] is True and out["pinned_ok"] is True and out["container"] == "daaes-hermes:test"
    argv, kwargs = next((a, k) for a, k in calls if "run" in a[:2] and "--rm" in a and "rev-parse" not in a)
    joined = " ".join(argv)
    for needed in ("--cap-drop ALL", "--security-opt no-new-privileges", "--memory 3g", "--pids-limit 512", "--tmpfs"):
        assert needed in joined, needed
    assert f"{workspace}:/work" in joined and f"{tmp_path / 'run'}:/run" in joined
    assert argv.count("-v") == 3, "only the workspace, this run folder and its log folder are mounted"
    assert "env" not in kwargs or kwargs["env"] is None, "the container gets no environment of ours"
    assert "must-not-reach-the-container" not in joined
    cfg = json.loads((tmp_path / "run" / "hermes_run.json").read_text(encoding="utf-8"))
    assert cfg["base_url"] == "http://host.docker.internal:54321/v1" and cfg["workspace"] == "/work"
    assert cfg["api_key"] == "gateway-token", "the only credential is the gateway's"


def test_a_real_model_run_is_still_refused_outside_a_container_without_the_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("DELENTIA_HERMES_CONTAINER", raising=False)
    with pytest.raises(PermissionError):
        hermes_adapter.run_goal("g", tmp_path, "http://127.0.0.1:1/v1", "t", "m", tmp_path / "r", real_model=True, sandboxed=False)


def test_the_model_is_told_the_containers_python(tmp_path, monkeypatch):
    from research.daaes import tc003
    seen = {}

    def fake_run_goal(goal, *args, **kwargs):
        seen["goal"] = goal
        return {"available": False, "note": "stop here"}
    monkeypatch.setenv("DELENTIA_HERMES_CONTAINER", "daaes-hermes:test")
    monkeypatch.setattr(hermes_adapter, "run_goal", fake_run_goal)
    tc003.run_hermes("http://127.0.0.1:1/v1", "t", "m", tmp_path / "w")
    assert "python3 -m pytest -q tests" in seen["goal"] and "WindowsApps" not in seen["goal"]


def test_pinned_rule_cost_rule_text_is_what_the_loop_renders():
    """The cost model renders the same two sentences the loop does; if the loop's wording changes, the model has to be re-run."""
    from rct_control_plane import governed_autonomous_loop as G
    from research import pinned_cost_r86 as cost
    source = Path(G.__file__).read_text(encoding="utf-8")
    assert cost.HEADING in source
    assert cost.HIDDEN.split("{n}")[1] in source
