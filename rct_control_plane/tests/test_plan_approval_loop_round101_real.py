"""
Round 101: plan-first approval inside the real governed loop (the Architect's answers Q1-Q5 of the plan-approval note, 2026-10-25).

Real Ed25519 approvers, real SQLite, the real gate and approval store; the model's decisions are scripted and the tools are recorded. What these tests pin:
  * with `plan_first` on, an action of a listed kind is never dispatched before the person confirms: it becomes a step of ONE pending plan;
  * one signature over the plan digest runs exactly the recorded steps, in order, each judged again by the rules no signature can lift;
  * a plan altered after it was made, a missing signature, a changed policy, a halt in the middle - nothing beyond the first problem runs;
  * a hard refusal (a denied path) is still a refusal, not a plan step;
  * with the feature off the loop behaves as before;
  * Q1: a small edit of a file the request names runs without a signature only when the owner's policy says so and every condition holds.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import sqlite3

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, fdia_policy as fp, plan_approval
from rct_control_plane.approvals import ApprovalError
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop, _scripted_decide

FINISH = {"action": "finish", "reasoning": "done", "final_answer": "<answer that restates the goal>", "tool_name": None, "tool_args": {}}
READ = {"rule_id": "R-READ", "intent_patterns": ["read_*", "recall"], "action_type": "ALLOW"}
WRITE_RULE = {"rule_id": "R-WRITE", "intent_patterns": ["write_repo_file", "patch_repo_file"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}
CRON_RULE = {"rule_id": "R-CRON", "intent_patterns": ["cron_delete"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}
CRAWL_RULE = {"rule_id": "R-CRAWL", "intent_patterns": ["crawl_url"], "action_type": "ALLOW"}


class Tools(_FakeMCP):
    NAMES = ["delentia_read_repo_file", "delentia_write_repo_file", "delentia_cron_delete", "delentia_recall", "delentia_crawl_url", "delentia_run_sandboxed_command"]

    def __init__(self, failing=()):
        super().__init__()
        self.failing = set(failing)

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in self.NAMES]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        from test_governed_autonomous_loop_real import _FakeToolResult
        if name in self.failing:
            return _FakeToolResult('{"error": "the service refused"}')
        return _FakeToolResult('{"ok": true}')


def call(tool, args=None, why="r"):
    return {"action": "call_tool", "tool_name": tool, "tool_args": args or {}, "reasoning": why, "final_answer": None}


WRITE = call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"})
CRON = call("delentia_cron_delete", {"job_id": "job-7"})
READ_CALL = call("delentia_read_repo_file", {"relative_path": "docs/notes.md"})


def make_policy(rules=None, **extra):
    parsed, errors = fp.validate_policy({"rules": rules or [READ, WRITE_RULE, CRON_RULE, CRAWL_RULE], **extra})
    assert parsed is not None, errors
    return parsed


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_JURY_CONFIG", str(tmp_path / "jury.json"))
    for var in ("DELENTIA_HOME_REGION", "DELENTIA_ALLOWED_REGIONS", "DELENTIA_ALLOW_CROSS_BORDER", "DELENTIA_PARALLEL_TOOLS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", str(tmp_path / "none.json"))


@pytest.fixture
def decide(monkeypatch):
    def apply(sequence):
        fake, calls = _scripted_decide(sequence)
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
        return calls
    return apply


@pytest.fixture
def approver(tmp_path):
    key = tmp_path / "keys" / "owner.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "owner", "public_key_hex": public}]), encoding="utf-8")
    return str(key)


def mk(tmp_path, name, mcp, policy, **kwargs):
    loop = _loop(tmp_path, name, kernel=_FakeKernel(), mcp=mcp, policy=policy, **kwargs)
    real = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real(goal, clarity, compile_result)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    return loop


def sign(store, action, key):
    signed = approvals.sign_decision(key, action.approval_id, action.action_sha256, "APPROVED")
    return store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


def run(loop, goal="Clean up the old job and update the notes"):
    return asyncio.run(loop.run(goal))


def dispatched_names(mcp):
    return [n for n, _a in mcp.dispatched]


# ------------------------------------------------------------------ the plan is proposed, nothing runs
def test_effects_of_a_planned_kind_become_one_pending_plan_and_nothing_effectful_runs(tmp_path, decide):
    decide([READ_CALL, CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan1", mcp, make_policy(plan_first=["delete", "document_edit"]))
    result = run(loop)
    assert result["stopped_reason"] == "pending_approval"
    assert dispatched_names(mcp) == ["delentia_read_repo_file"], "reads run normally; the two effects must not have run"
    last = result["steps"][-1]
    assert last["tool_name"] == plan_approval.PLAN_TOOL
    plan = last["tool_args"]["plan"]
    assert [s["tool"] for s in plan["steps"]] == ["delentia_cron_delete", "delentia_write_repo_file"]
    assert [s["kind"] for s in plan["steps"]] == ["delete", "document_edit"]
    assert plan_approval.plan_digest_ok(plan)
    assert result["approval_id"] and result["plan_approval"]["steps"] == 2
    proposed = [s["tool_result"] for s in result["steps"] if isinstance(s.get("tool_result"), dict) and s["tool_result"].get("proposed")]
    assert [p["plan_step"] for p in proposed] == [1, 2]


def test_the_pending_action_is_the_plan_and_binds_the_policy_and_workspace(tmp_path, decide):
    decide([CRON, FINISH])
    mcp = Tools()
    policy = make_policy(plan_first=["delete"])
    loop = mk(tmp_path, "plan2", mcp, policy)
    result = run(loop)
    action = loop._pending_actions().get(result["approval_id"])
    assert action.tool_name == plan_approval.PLAN_TOOL
    assert action.policy_digest == policy.digest()
    assert action.workspace == loop._workspace_id()


def test_one_signature_runs_the_steps_exactly_once_in_order(tmp_path, decide, approver):
    decide([CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan3", mcp, make_policy(plan_first=["delete", "document_edit"]))
    result = run(loop)
    store = loop._pending_actions()
    action = store.get(result["approval_id"])
    sign(store, action, approver)
    outcome = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert dispatched_names(mcp) == ["delentia_cron_delete", "delentia_write_repo_file"]
    recorded = [step["args"] for step in action.tool_args["plan"]["steps"]]
    assert [args for _n, args in mcp.dispatched] == recorded, "what ran is byte for byte what was confirmed"
    assert mcp.dispatched[0][1]["job_id"] == "job-7" and mcp.dispatched[1][1]["relative_path"] == "docs/notes.md"
    assert outcome["executed_result"]["executed"] == 2 and outcome["executed_result"]["halted"] is None
    with pytest.raises(ApprovalError):
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))           # at most once
    assert len(mcp.dispatched) == 2


def test_resume_without_a_signature_runs_nothing(tmp_path, decide):
    decide([CRON, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan4", mcp, make_policy(plan_first=["delete"]))
    result = run(loop)
    with pytest.raises(ApprovalError):
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert mcp.dispatched == []


# ------------------------------------------------------------------ tampering
def test_a_plan_edited_in_the_database_is_refused(tmp_path, decide, approver):
    decide([CRON, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan5", mcp, make_policy(plan_first=["delete"]))
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), approver)
    db = str(tmp_path / "plan5.db")
    with sqlite3.connect(db) as conn:
        raw = conn.execute("SELECT tool_args_json FROM pending_actions WHERE approval_id = ?", (result["approval_id"],)).fetchone()[0]
        edited = raw.replace("job-7", "job-ALL")
        assert edited != raw
        conn.execute("UPDATE pending_actions SET tool_args_json = ? WHERE approval_id = ?", (edited, result["approval_id"]))
    with pytest.raises(ApprovalError):
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert mcp.dispatched == []


def test_a_plan_whose_digest_does_not_match_its_content_runs_nothing(tmp_path, decide):
    decide([FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan6", mcp, make_policy(plan_first=["delete"]))
    plan = plan_approval.build_plan("g", [{"tool_name": "delentia_cron_delete", "tool_args": {"job_id": "job-7"}}])
    plan["steps"][0]["args"] = {"job_id": "job-ALL"}                                  # edited after the digest was made
    action = type("A", (), {"tool_args": {"plan": plan}, "goal": "g"})()
    A, reason, summary = asyncio.run(loop._execute_plan(action))
    assert A == 0.0 and "digest" in reason and mcp.dispatched == [] and summary["executed"] == 0


def test_changing_the_policy_after_the_plan_was_made_stops_the_resume(tmp_path, decide, approver):
    decide([CRON, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan7", mcp, make_policy(plan_first=["delete"]))
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), approver)
    loop._policy_override = make_policy(plan_first=["delete", "publish"])             # the owner changed the policy in between
    with pytest.raises(ApprovalError):
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert mcp.dispatched == []


# ------------------------------------------------------------------ halting and hard refusals
def test_the_first_failing_step_ends_the_run_and_later_steps_do_not_run(tmp_path, decide, approver):
    decide([CRON, WRITE, FINISH])
    mcp = Tools(failing={"delentia_cron_delete"})
    loop = mk(tmp_path, "plan8", mcp, make_policy(plan_first=["delete", "document_edit"]))
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), approver)
    outcome = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert dispatched_names(mcp) == ["delentia_cron_delete"], "the write must not run after the delete failed"
    assert outcome["executed_result"]["halted"] and outcome["executed_result"]["executed"] == 1


def test_a_denied_path_is_a_refusal_not_a_plan_step(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": ".env", "content_text": "x=1"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan9", mcp, make_policy(plan_first=["document_edit"]))
    result = run(loop)
    assert result["stopped_reason"] == "fdia_blocked"
    assert mcp.dispatched == [] and "plan_approval" not in result


def test_proposals_are_discarded_when_the_episode_ends_for_another_reason(tmp_path, decide):
    decide([CRON, call("delentia_write_repo_file", {"relative_path": ".env", "content_text": "x=1"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "plan10", mcp, make_policy(plan_first=["delete", "document_edit"]))
    result = run(loop)
    assert result["stopped_reason"] == "fdia_blocked"
    assert result["plan_discarded"]["steps"] == 1
    assert mcp.dispatched == []


# ------------------------------------------------------------------ off means unchanged
def test_without_plan_first_the_first_effect_stops_for_its_own_signature_as_before(tmp_path, decide):
    decide([CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "off1", mcp, make_policy())
    result = run(loop)
    assert result["stopped_reason"] == "pending_approval"
    assert result["steps"][-1]["tool_name"] == "delentia_cron_delete"
    assert "plan_approval" not in result and mcp.dispatched == []
    assert loop._pending_actions().get(result["approval_id"]).tool_name == "delentia_cron_delete"


def test_a_kind_the_owner_did_not_list_is_not_planned(tmp_path, decide):
    decide([CRON, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "off2", mcp, make_policy(plan_first=["publish"]))
    result = run(loop)
    assert result["steps"][-1]["tool_name"] == "delentia_cron_delete"                  # asked for its own signature, the old way


# ------------------------------------------------------------------ batches
def test_an_effect_inside_a_batch_is_refused_and_nothing_in_the_batch_runs(tmp_path, decide, monkeypatch):
    monkeypatch.setenv("DELENTIA_PARALLEL_TOOLS", "1")
    batch = {"action": "call_tools", "reasoning": "r", "final_answer": None, "tool_name": None, "tool_args": {},
             "calls": [{"id": "a", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "docs/notes.md"}},
                       {"id": "b", "tool_name": "delentia_cron_delete", "tool_args": {"job_id": "job-7"}}]}
    decide([batch, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "batch1", mcp, make_policy(plan_first=["delete"]))
    run(loop)
    assert mcp.dispatched == []


# ------------------------------------------------------------------ the invariant, over several kinds at once
def test_no_effect_of_a_planned_kind_is_dispatched_before_the_confirmation(tmp_path, decide):
    kinds = ["delete", "document_edit"]
    decide([CRON, WRITE, CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "inv1", mcp, make_policy(plan_first=kinds))
    run(loop)
    assert [n for n in dispatched_names(mcp) if n in ("delentia_cron_delete", "delentia_write_repo_file")] == []


def test_mutation_if_the_interception_is_defeated_the_invariant_test_would_fail(tmp_path, decide, monkeypatch):
    """The test above is only worth something if it can fail: with the interception removed the effect IS dispatched or stops by the old way, never planned."""
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop

    async def defeated(self, goal, tool_name, tool_args, reasoning=""):
        return None

    monkeypatch.setattr(GovernedAutonomousLoop, "_plan_intercept", defeated)
    decide([CRON, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "mut1", mcp, make_policy(plan_first=["delete"]))
    result = run(loop)
    assert "plan_approval" not in result


# ------------------------------------------------------------------ Q1: a small edit of a named file
def policy_small(**kw):
    return make_policy(small_edit_autorun=True, **kw)


def test_a_small_edit_of_the_named_file_runs_without_a_signature_when_the_policy_says_so(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "small1", mcp, policy_small())
    result = run(loop, goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "llm_finished"
    assert dispatched_names(mcp) == ["delentia_write_repo_file"]
    with loop._persistence._connect() as conn:
        rows = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type='governed_loop_plan'")]
    assert "small_edit_autorun" in rows


def test_without_the_policy_flag_the_same_edit_still_asks(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small2", mcp, make_policy()), goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "pending_approval" and mcp.dispatched == []


def test_a_file_the_request_does_not_name_still_asks(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": "docs/other.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small3", mcp, policy_small()), goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "pending_approval" and mcp.dispatched == []


def test_after_reading_outside_text_the_edit_asks_again(tmp_path, decide):
    decide([call("delentia_crawl_url", {"url": "https://example.com/page"}), call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small4", mcp, policy_small()), goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "pending_approval"
    assert "delentia_write_repo_file" not in dispatched_names(mcp)


def test_a_denied_path_is_not_lifted_by_the_flag(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": ".env", "content_text": "x=1"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small5", mcp, policy_small()), goal="Fix the typo in .env")
    assert result["stopped_reason"] == "fdia_blocked" and mcp.dispatched == []


def test_no_checkpoint_no_autorun(tmp_path, decide, monkeypatch):
    monkeypatch.setenv("DELENTIA_CHECKPOINTS", "off")
    from rct_control_plane import checkpoints
    assert not checkpoints.enabled()
    decide([call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small6", mcp, policy_small()), goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "pending_approval" and mcp.dispatched == []


def test_a_small_edit_is_not_made_a_plan_step_when_the_flag_applies(tmp_path, decide):
    decide([call("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "small7", mcp, make_policy(small_edit_autorun=True, plan_first=["document_edit"])), goal="Fix the typo in docs/notes.md")
    assert result["stopped_reason"] == "llm_finished" and "plan_approval" not in result
    assert dispatched_names(mcp) == ["delentia_write_repo_file"]


# ------------------------------------------------------------------ the history names what loosens
def test_the_policy_history_names_plan_first_and_autorun_changes_as_loosening():
    from rct_control_plane import fdia_policy_history as hist
    strict = make_policy(plan_first=["delete", "publish"]).to_dict()
    fewer = make_policy(plan_first=["delete"]).to_dict()
    assert any("publish" in line for line in hist.loosened(strict, fewer))
    assert not hist.loosened(fewer, strict), "adding a kind is stricter, not looser"
    off = make_policy().to_dict()
    on = make_policy(small_edit_autorun=True).to_dict()
    assert any("without a signature" in line for line in hist.loosened(off, on))
    assert not hist.loosened(on, off)


# ------------------------------------------------------------------ what a chat channel is told
def test_a_chat_channel_is_shown_the_plan_the_id_and_that_nothing_ran(tmp_path, decide):
    from rct_control_plane.gateways.common import reply_text_for
    decide([CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "chat1", mcp, make_policy(plan_first=["delete", "document_edit"]))
    result = run(loop)
    text = reply_text_for(result)
    assert "delentia_cron_delete" in text and "delentia_write_repo_file" in text
    assert result["approval_id"] in text and "Nothing has run" in text
    assert mcp.dispatched == []


def test_without_a_plan_the_chat_reply_is_what_it_was(tmp_path, decide):
    from rct_control_plane.gateways.common import reply_text_for
    decide([CRON, FINISH])
    result = run(mk(tmp_path, "chat2", Tools(), make_policy()))
    assert "needs a human approval" in reply_text_for(result)


# ------------------------------------------------------------------ each step is recorded by the notary before it runs
@pytest.fixture
def notary_server(tmp_path):
    import threading
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from rct_control_plane import notary
    key = Ed25519PrivateKey.generate()
    store = notary.NotaryStore(str(tmp_path / "notary" / "notary.db"), key, "notary-test")
    server = notary.make_server(store, port=0, token="t101")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_notary_records_each_step_before_it_runs_and_its_result_after(tmp_path, decide, approver, notary_server):
    from rct_control_plane.notary import NotaryClient
    decide([CRON, WRITE, FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "nt1", mcp, make_policy(plan_first=["delete", "document_edit"]), notary=NotaryClient(notary_server, "t101"))
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), approver)
    asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    kinds = [r["kind"] for r in loop._episode_notary_receipts]
    tail = kinds[kinds.index("plan_step"):]
    assert tail[:4] == ["plan_step", "plan_step_result", "plan_step", "plan_step_result"], kinds
    assert len(mcp.dispatched) == 2


def test_a_notary_that_cannot_record_a_step_stops_the_run_at_that_step(tmp_path, decide, approver, notary_server):
    from rct_control_plane.notary import NotaryClient, NotaryUnavailable
    decide([CRON, WRITE, FINISH])
    mcp = Tools()
    client = NotaryClient(notary_server, "t101")
    loop = mk(tmp_path, "nt2", mcp, make_policy(plan_first=["delete", "document_edit"]), notary=client)
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), approver)
    real_append, seen = client.append, {"steps": 0}

    async def flaky(record):
        if record.get("kind") == "plan_step":
            seen["steps"] += 1
            if seen["steps"] == 2:
                raise NotaryUnavailable("down")
        return await real_append(record)

    client.append = flaky
    outcome = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert dispatched_names(mcp) == ["delentia_cron_delete"], "the second step must not run when it could not be recorded"
    assert outcome["executed_result"]["halted"] and "notary" in outcome["executed_result"]["halted"]
