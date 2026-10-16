"""
Round 82, plan items T11 and T12: three kinds of rules, and which one wins.

  hard      the built-in floor (secret file names, forbidden paths, writes that always wait for a person), the owner's denied paths and blocked patterns, the taint rule
  semantic  the owner's policy rules (ALLOW / CONDITIONAL / REQUIRE_HUMAN_SIGNATURE) and the FDIA number
  quality   VERIFY, the memory nudge, the curator: they decide what is LEARNED, never what runs

Precedence is "the strictest wins, and nothing a model, a memory or a signature says lifts a hard rule". This file pins it over the full product of {three tool calls} x {four owner
policies} x {untainted, tainted episode}: the gate's outcome must equal the strictest of what each source says on its own. If any source ever started to override another, one of
the 24 rows would change.

T12 (lifecycle): the gate reads the policy in force WHEN IT DECIDES, so a change reaches a queued scheduled job, a pending approval (N2) and the warm-recall replay (N6) alike.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import itertools
import json

import pytest

from rct_control_plane import approvals, envelope
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop

run = asyncio.run
ALLOWED, ASK, BLOCKED = 0, 1, 2
NAMES = {None: ALLOWED, "pending_approval": ASK, "fdia_blocked": BLOCKED}

# What each source says on its own. The floor is the built-in behaviour with no owner policy and no taint.
CALLS = {
    "read_notes": ("delentia_read_repo_file", {"relative_path": "docs/notes.md"}),
    "write_notes": ("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "x"}),
    "write_secret": ("delentia_write_repo_file", {"relative_path": "config/prod.env", "content_text": "x"}),
}
FLOOR = {"read_notes": ALLOWED, "write_notes": ASK, "write_secret": BLOCKED}

POLICIES = {
    "none": None,
    "allow_everything": {"default_fallback_A": 1, "rules": [{"rule_id": "R-ALL", "intent_patterns": ["*"], "action_type": "ALLOW", "assigned_A": 1}]},
    "require_signature": {"default_fallback_A": 1, "rules": [{"rule_id": "R-SIG", "intent_patterns": ["*"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 1}]},
    "deny_docs": {"default_fallback_A": 1, "rules": [{"rule_id": "R-DOCS", "intent_patterns": ["*"], "action_type": "CONDITIONAL", "assigned_A": 1, "denied_paths": ["docs/*"]}]},
}
# What the owner's policy says about each call on its own (ALLOWED / ASK / BLOCKED), written by hand from the policy text above.
OWNER = {
    "none": {"read_notes": ALLOWED, "write_notes": ALLOWED, "write_secret": ALLOWED},
    "allow_everything": {"read_notes": ALLOWED, "write_notes": ALLOWED, "write_secret": ALLOWED},
    "require_signature": {"read_notes": ASK, "write_notes": ASK, "write_secret": ASK},
    "deny_docs": {"read_notes": BLOCKED, "write_notes": BLOCKED, "write_secret": ALLOWED},
}
TAINT = {False: {"read_notes": ALLOWED, "write_notes": ASK, "write_secret": ASK}, True: {"read_notes": ALLOWED, "write_notes": ASK, "write_secret": ASK}}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in (envelope.PAUSED_ENV, approvals.APPROVERS_ENV, "DELENTIA_FDIA_POLICY", "DELENTIA_FDIA_POLICY_DEFAULT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_ENVELOPE_PAUSE_FILE", str(tmp_path / "pause"))
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")          # "no owner policy" means none, not the starter default


def decide(tmp_path, monkeypatch, policy_name, call_name, tainted):
    if POLICIES[policy_name] is not None:
        path = tmp_path / f"{policy_name}.json"
        path.write_text(json.dumps({"version": "1.0.0", "policy_id": policy_name, **POLICIES[policy_name]}), encoding="utf-8")
        monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(path))
    loop = _loop(tmp_path, f"{policy_name}-{call_name}-{tainted}", kernel=_FakeKernel(), mcp=_FakeMCP())
    loop._episode_D, loop._episode_I = 1.0, 1.0
    loop._episode_data = {"parts": {}, "missing": []}
    if tainted:
        loop._episode_taint = "delentia_crawl_url"
    tool, args = CALLS[call_name]
    verdict = run(loop._pre_dispatch_gate("save the notes", tool, args))
    return NAMES[verdict["stopped_reason"] if verdict else None]


@pytest.mark.parametrize("policy_name,call_name,tainted", list(itertools.product(POLICIES, CALLS, (False, True))))
def test_the_strictest_source_wins_and_none_lifts_another(tmp_path, monkeypatch, policy_name, call_name, tainted):
    expected = max(FLOOR[call_name], OWNER[policy_name][call_name], TAINT[tainted][call_name] if tainted else ALLOWED)
    got = decide(tmp_path, monkeypatch, policy_name, call_name, tainted)
    assert got == expected, f"policy={policy_name} call={call_name} tainted={tainted}: expected {expected}, the gate said {got}"


def test_a_signature_cannot_lift_a_hard_rule(tmp_path, monkeypatch):
    """The owner's denied path stays denied after an approver signs (the gate re-evaluates with approved=True)."""
    from rct_control_plane import fdia_policy
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"version": "1.0.0", "policy_id": "hard", **POLICIES["deny_docs"]}), encoding="utf-8")
    policy = fdia_policy.load_policy(path)
    tool, args = CALLS["write_notes"]
    judged = fdia_policy.evaluate(policy, tool, args, principal="alice", approved=True, context={"goal": "save"})
    assert judged.A <= 0.0


def test_quality_checks_decide_what_is_learned_never_what_runs(tmp_path, monkeypatch):
    """VERIFY's verdict is not an input of the gate: the same call gets the same decision whatever the last answer was judged to be."""
    first = decide(tmp_path, monkeypatch, "none", "write_notes", False)
    loop = _loop(tmp_path, "quality", kernel=_FakeKernel(), mcp=_FakeMCP())
    loop._last_verification = {"aligned": False, "similarity_score": 0.0}
    loop._episode_D, loop._episode_I = 1.0, 1.0
    loop._episode_data = {"parts": {}, "missing": []}
    tool, args = CALLS["write_notes"]
    verdict = run(loop._pre_dispatch_gate("save the notes", tool, args))
    assert NAMES[verdict["stopped_reason"] if verdict else None] == first


def test_a_policy_change_reaches_the_next_decision_without_a_restart(tmp_path, monkeypatch):
    """T12: the gate reads the policy in force when it decides. The same loop object answers differently after the owner edits the file."""
    path = tmp_path / "live.json"
    path.write_text(json.dumps({"version": "1.0.0", "policy_id": "v1", **POLICIES["allow_everything"]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(path))
    loop = _loop(tmp_path, "live", kernel=_FakeKernel(), mcp=_FakeMCP())
    loop._episode_D, loop._episode_I = 1.0, 1.0
    loop._episode_data = {"parts": {}, "missing": []}
    tool, args = CALLS["read_notes"]
    assert run(loop._pre_dispatch_gate("read", tool, args)) is None
    path.write_text(json.dumps({"version": "1.0.1", "policy_id": "v2", **POLICIES["deny_docs"]}), encoding="utf-8")
    after = run(loop._pre_dispatch_gate("read", tool, args))
    assert after is not None and after["stopped_reason"] == "fdia_blocked"


def test_a_queued_scheduled_job_runs_under_the_policy_at_run_time_not_at_creation(tmp_path, monkeypatch):
    import time

    import rct_control_plane.autonomous_loop as autonomous_loop_module
    import rct_control_plane.mcp_server as mcp_server
    from rct_control_plane.cron_jobs import CronService
    from rct_control_plane.persistence import ControlPlanePersistence
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    monkeypatch.setattr(mcp_server, "REPO_ROOT", repo)

    class Kernel(_FakeKernel):
        def __init__(self, persistence):
            super().__init__()
            self._persistence = persistence
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "c.db"))
    kernel = Kernel(persistence)
    monkeypatch.setattr(mcp_server, "_kernel", kernel)

    async def hijacked(goal, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "docs/notes.md"}, "reasoning": "r"}
        return {"action": "finish", "reasoning": "d", "final_answer": "Done.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", hijacked)
    (repo / "docs" / "notes.md").write_text("hello", encoding="utf-8")
    service = CronService(persistence)
    job = service.create("sched", "read the notes", "every day at 9:00", now=time.time() - 86400)      # created while no policy forbade anything
    path = tmp_path / "later.json"
    path.write_text(json.dumps({"version": "1.0.1", "policy_id": "later", **POLICIES["deny_docs"]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(path))                                                # ... and the owner forbids docs/ before it runs
    done = run(service.run_job(kernel, service.get(job["id"]), None, time.time()))
    assert done["last_status"] == "fdia_blocked"
