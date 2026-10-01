"""
Round 54: the owner's policy for A inside the real governed loop - real Ed25519 approvers with roles, real SQLite,
real HTTP jury members; the model's decisions are scripted and the tools are recorded. Nothing is mocked inside
the gate, the approval store or the jury.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
from contextlib import ExitStack

import pytest

from rct_control_plane import approvals, fdia_policy as fp
from rct_control_plane.approvals import ApprovalError
from scripted_model import ScriptedModel
from signedai.core.registry import SignedAIRegistry, SignedAITier
import rct_control_plane.autonomous_loop as autonomous_loop_module
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop, _scripted_decide


@pytest.fixture
def decide_sequence(monkeypatch):
    """decide_sequence([...]) scripts the model's next decisions (a trailing 'finish' repeats)."""
    def apply(sequence):
        fake, calls = _scripted_decide(sequence)
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
        return calls
    return apply


class Tools(_FakeMCP):
    NAMES = ["delentia_read_repo_file", "delentia_run_sandboxed_command", "delentia_write_repo_file",
             "delentia_recall", "delentia_crawl_url", "delentia_create_worktree"]

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in self.NAMES]


def call(tool, args=None, why="r"):
    return {"action": "call_tool", "tool_name": tool, "tool_args": args or {}, "reasoning": why, "final_answer": None}


FINISH = {"action": "finish", "reasoning": "done", "final_answer": "<answer that restates the goal>", "tool_name": None, "tool_args": {}}

SHELL = {"rule_id": "R-SHELL", "intent_patterns": ["run_sandboxed_command"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
         "human_approver_role": ["Security_Admin"]}
READ = {"rule_id": "R-READ", "intent_patterns": ["read_*", "recall"], "action_type": "ALLOW"}


def mk(tmp_path, name, kernel=None, **kwargs):
    """A governed loop whose D is the kernel's D (1.0 unless given): the data evidence, which depends on what this
    machine's repository happens to contain, would otherwise decide whether F clears the threshold."""
    loop = _loop(tmp_path, name, kernel=kernel, **kwargs)
    forced = (kernel.D if kernel is not None else 1.0)
    real = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real(goal, clarity, compile_result)
        evidence.D = forced
        return evidence

    loop._assess_data = assess
    return loop


def make_policy(rules, **extra):
    parsed, errors = fp.validate_policy({"rules": rules, **extra})
    assert parsed is not None, errors
    return parsed


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_JURY_CONFIG", str(tmp_path / "jury.json"))
    for var in ("DELENTIA_HOME_REGION", "DELENTIA_ALLOWED_REGIONS", "DELENTIA_ALLOW_CROSS_BORDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", str(tmp_path / "none.json"))


def make_keys(tmp_path, roles):
    """Real approver keys outside the repo; returns {name: (key_path, public_hex)} and writes approvers.json."""
    out, entries = {}, []
    for name, role in roles.items():
        path = tmp_path / "keys" / f"{name}.pem"
        public = approvals.generate_approver_key(str(path))
        out[name] = (str(path), public)
        entries.append({"name": name, "public_key_hex": public, **({"role": role} if role else {})})
    (tmp_path / "approvers.json").write_text(json.dumps(entries), encoding="utf-8")
    return out


def sign(store, action, key_path, decision="APPROVED"):
    signed = approvals.sign_decision(key_path, action.approval_id, action.action_sha256, decision)
    return store.decide(action.approval_id, decision, signed["public_key_hex"], signed["signature_hex"])


def run(loop, goal="Read the project notes carefully"):
    return asyncio.run(loop.run(goal))


# ------------------------------------------------------------------ allow, zero trust, fail closed

def test_without_a_policy_nothing_changes_for_a_non_risky_tool(tmp_path, decide_sequence):
    decide_sequence([call("delentia_read_repo_file", {"relative_path": "a.md"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "nopolicy", mcp=mcp))
    assert result["stopped_reason"] == "llm_finished" and mcp.dispatched


def test_with_a_policy_an_allowed_read_runs_and_the_audit_row_names_the_rule(tmp_path, decide_sequence):
    decide_sequence([call("delentia_read_repo_file", {"relative_path": "a.md"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "allowed", mcp=mcp, policy=make_policy([READ]))
    result = run(loop)
    assert result["stopped_reason"] == "llm_finished" and len(mcp.dispatched) == 1
    with loop._persistence._connect() as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type='governed_loop_fdia_gate'")]
    assert rows[0]["policy"]["rule_id"] == "R-READ" and rows[0]["policy"]["policy_digest"]


def test_zero_trust_a_tool_the_owner_never_registered_is_refused_and_not_dispatched(tmp_path, decide_sequence):
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "zerotrust", mcp=mcp, policy=make_policy([READ])))
    assert result["stopped_reason"] == "fdia_blocked" and not mcp.dispatched
    step = result["steps"][-1]["tool_result"]
    assert step["A"] == 0.0 and "not registered" in step["reason"] and step["policy"]["rule_id"] == "ZERO_TRUST_FALLBACK"


def test_a_broken_policy_file_refuses_every_tool_including_reads(tmp_path, decide_sequence):
    (tmp_path / "policy.json").write_text("{not json", encoding="utf-8")
    decide_sequence([call("delentia_read_repo_file", {"relative_path": "a.md"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "broken", mcp=mcp))
    assert result["stopped_reason"] == "fdia_blocked" and not mcp.dispatched
    assert "fail closed" in result["steps"][-1]["tool_result"]["reason"]


def test_a_policy_file_on_disk_is_picked_up_without_restarting(tmp_path, decide_sequence):
    path = tmp_path / "policy.json"
    fp.save_policy(make_policy([READ]), path)
    mcp = Tools()
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    assert run(mk(tmp_path, "disk1", mcp=mcp))["stopped_reason"] == "fdia_blocked"
    fp.save_policy(make_policy([READ, {"rule_id": "R-WT", "intent_patterns": ["create_worktree"], "action_type": "ALLOW"}]), path)
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    assert run(mk(tmp_path, "disk2", mcp=mcp))["stopped_reason"] == "llm_finished"


# ------------------------------------------------------------------ the policy can tighten, never loosen

def test_the_policy_cannot_lift_the_built_in_write_approval(tmp_path, decide_sequence):
    allow_write = {"rule_id": "R-W", "intent_patterns": ["write_repo_file"], "action_type": "ALLOW"}
    decide_sequence([call("delentia_write_repo_file", {"relative_path": "n.md", "content_text": "x"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "floor", mcp=mcp, policy=make_policy([READ, allow_write])))
    assert result["stopped_reason"] == "pending_approval" and not mcp.dispatched


def test_the_policy_cannot_lower_the_built_in_threshold_but_can_raise_it(tmp_path, decide_sequence):
    risky = {"rule_id": "R-WT", "intent_patterns": ["create_worktree"], "action_type": "CONDITIONAL"}
    kernel = _FakeKernel(D=0.8, I=1.0)                     # F = 0.8
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    passed = run(mk(tmp_path, "thr-low", kernel=kernel, mcp=Tools(), policy=make_policy([risky], custom_safety_threshold=0.1)))
    assert passed["stopped_reason"] == "llm_finished"
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    blocked = run(mk(tmp_path, "thr-high", kernel=kernel, mcp=Tools(), policy=make_policy([risky], custom_safety_threshold=0.9)))
    assert blocked["stopped_reason"] == "fdia_blocked" and blocked["steps"][-1]["tool_result"]["threshold"] == 0.9


def test_reads_the_owner_allows_are_not_held_to_the_data_threshold(tmp_path, decide_sequence):
    decide_sequence([call("delentia_read_repo_file", {"relative_path": "a.md"}), FINISH])
    result = run(mk(tmp_path, "weakdata", kernel=_FakeKernel(D=0.1, I=1.0), mcp=Tools(), policy=make_policy([READ], custom_safety_threshold=0.9)))
    assert result["stopped_reason"] == "llm_finished"


def test_a_denied_path_stops_a_read_the_owner_otherwise_allows(tmp_path, decide_sequence):
    rule = dict(READ, action_type="CONDITIONAL", denied_paths=[".env", "*.pem"])
    decide_sequence([call("delentia_read_repo_file", {"relative_path": "config/.env"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "denied", mcp=mcp, policy=make_policy([rule])))
    assert result["stopped_reason"] == "fdia_blocked" and not mcp.dispatched
    assert "restricted path" in result["steps"][-1]["tool_result"]["reason"]


# ------------------------------------------------------------------ roles of the caller

def test_roles_follow_the_server_side_identity_not_the_request(tmp_path, decide_sequence):
    rule = {"rule_id": "R-WT", "intent_patterns": ["create_worktree"], "action_type": "ALLOW", "allowed_roles": ["devops"]}
    policy = make_policy([rule], roles={"default_role": "developer", "principals": {"alice": "devops"}})
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    assert run(mk(tmp_path, "alice", mcp=Tools(), policy=policy))["stopped_reason"] == "llm_finished"
    decide_sequence([call("delentia_create_worktree", {"branch": "x"}), FINISH])
    refused = run(mk(tmp_path, "bob", mcp=Tools(), policy=policy))
    assert refused["stopped_reason"] == "fdia_blocked" and "role 'developer'" in refused["steps"][-1]["tool_result"]["reason"]


# ------------------------------------------------------------------ signatures, roles of approvers, dual sign-off

def test_a_safe_shell_command_still_needs_a_signature_when_the_owner_says_so(tmp_path, decide_sequence):
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "shell", mcp=mcp, policy=make_policy([READ, SHELL])))
    assert result["stopped_reason"] == "pending_approval" and not mcp.dispatched
    loop_store = approvals.PendingActionStore(mk(tmp_path, "shell", mcp=mcp)._persistence)
    pending = loop_store.get(result["approval_id"])
    assert pending.policy_rule == "R-SHELL" and pending.approver_roles == ["Security_Admin"] and pending.required_signatures == 1


def test_only_an_approver_with_the_required_role_can_sign_and_the_resume_runs_once(tmp_path, decide_sequence):
    keys = make_keys(tmp_path, {"sec": "Security_Admin", "dev": "Developer", "anon": None})
    policy = make_policy([READ, SHELL])
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "roles", mcp=mcp, policy=policy)
    result = run(loop)
    store = loop._pending_actions()
    pending = store.get(result["approval_id"])
    for wrong in ("dev", "anon"):
        with pytest.raises(ApprovalError, match="needs an approver with the role Security_Admin"):
            sign(store, pending, keys[wrong][0])
    assert store.get(pending.approval_id).status == "PENDING"
    assert sign(store, pending, keys["sec"][0]).status == "APPROVED"
    decide_sequence([FINISH])
    outcome = asyncio.run(loop.resume(pending.approval_id))
    assert outcome["executed_result"] is not None
    with pytest.raises(ApprovalError, match="already executed|already"):
        asyncio.run(loop.resume(pending.approval_id))


def test_any_trusted_key_can_reject_whatever_its_role(tmp_path, decide_sequence):
    keys = make_keys(tmp_path, {"sec": "Security_Admin", "dev": "Developer"})
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    loop = mk(tmp_path, "reject", mcp=Tools(), policy=make_policy([SHELL]))
    result = run(loop)
    store = loop._pending_actions()
    assert sign(store, store.get(result["approval_id"]), keys["dev"][0], "REJECTED").status == "REJECTED"


def test_dual_signoff_needs_two_distinct_keys_and_one_key_twice_does_not_count(tmp_path, decide_sequence):
    keys = make_keys(tmp_path, {"a": "Chief_Architect", "b": "DevOps_Lead", "c": "Intern"})
    deploy = {"rule_id": "R-DEP", "intent_patterns": ["create_worktree"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
              "required_signatures": 2, "human_approver_role": ["Chief_Architect", "DevOps_Lead"]}
    decide_sequence([call("delentia_create_worktree", {"branch": "release"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "dual", mcp=mcp, policy=make_policy([deploy]))
    result = run(loop)
    store = loop._pending_actions()
    pending = store.get(result["approval_id"])
    assert pending.required_signatures == 2
    first = sign(store, pending, keys["a"][0])
    assert first.status == "PENDING" and first.signatures_collected == 1
    with pytest.raises(ApprovalError, match="already signed"):
        sign(store, pending, keys["a"][0])
    with pytest.raises(ApprovalError, match="needs an approver with the role"):
        sign(store, pending, keys["c"][0])
    with pytest.raises(ApprovalError, match="not APPROVED"):
        asyncio.run(loop.resume(pending.approval_id))
    assert not mcp.dispatched
    second = sign(store, pending, keys["b"][0])
    assert second.status == "APPROVED" and second.signatures_collected == 2
    decide_sequence([FINISH])
    assert asyncio.run(loop.resume(pending.approval_id))["tool_name"] == "delentia_create_worktree"
    assert mcp.dispatched[0][0] == "delentia_create_worktree"


def test_forging_the_second_signature_row_is_caught_at_execution(tmp_path, decide_sequence):
    keys = make_keys(tmp_path, {"a": "Chief_Architect", "b": "DevOps_Lead"})
    deploy = {"rule_id": "R-DEP", "intent_patterns": ["create_worktree"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 2}
    decide_sequence([call("delentia_create_worktree", {"branch": "release"}), FINISH])
    loop = mk(tmp_path, "forge", mcp=Tools(), policy=make_policy([deploy]))
    result = run(loop)
    store = loop._pending_actions()
    pending = store.get(result["approval_id"])
    sign(store, pending, keys["a"][0])
    with store._persistence._connect() as conn:                        # an attacker with database access fakes the second approval
        conn.execute("INSERT INTO pending_action_signatures VALUES (?, ?, ?, ?)", (pending.approval_id, keys["b"][1], "00" * 64, 1.0))
        first_sig = conn.execute("SELECT signature_hex FROM pending_action_signatures WHERE public_key = ?", (keys["a"][1],)).fetchone()[0]
        conn.execute("UPDATE pending_actions SET status = 'APPROVED', approver_public_key = ?, signature_hex = ? WHERE approval_id = ?",
                     (keys["a"][1], first_sig, pending.approval_id))
    with pytest.raises(ApprovalError, match="does not verify"):
        asyncio.run(loop.resume(pending.approval_id))


def test_a_signature_cannot_authorise_what_the_policy_now_forbids(tmp_path, decide_sequence):
    keys = make_keys(tmp_path, {"sec": "Security_Admin"})
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "tightened", mcp=mcp, policy=make_policy([SHELL]))
    result = run(loop)
    store = loop._pending_actions()
    sign(store, store.get(result["approval_id"]), keys["sec"][0])
    loop._policy_override = make_policy([SHELL], blocked_action_patterns=["*sandboxed_command*"])     # the owner changed their mind
    outcome = asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert outcome["executed_result"]["fdia_blocked"] and not mcp.dispatched


# ------------------------------------------------------------------ the jury, by action

def jury_config(models):
    roles = SignedAIRegistry.get_tier(SignedAITier.TIER_4).signers
    return {"roles": {role.value: {"provider": "openai-compat", "model": m.model_id, "base_url": m.base_url, "kind": "local",
                                   "operator": f"member-{i}"} for i, (role, m) in enumerate(zip(roles, models, strict=False))}}


AGREE = json.dumps({"vote": "agree", "reason": "fine"})
DISAGREE = json.dumps({"vote": "disagree", "reason": "it looks dangerous"})
JURY_SHELL = dict(SHELL, jury_tier="tier_4")


@pytest.fixture
def members():
    with ExitStack() as stack:
        def make(*replies):
            return [stack.enter_context(ScriptedModel(lambda req, r=r: r, model_id=f"member-{i}")) for i, r in enumerate(replies)]
        yield make


def test_the_jury_agrees_then_the_action_still_waits_for_the_human_and_the_verdict_is_in_the_audit(tmp_path, decide_sequence, members):
    servers = members(AGREE, AGREE, AGREE, DISAGREE)
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    loop = mk(tmp_path, "jury-ok", mcp=Tools(), policy=make_policy([JURY_SHELL]), jury_config=jury_config(servers))
    result = run(loop)
    assert result["stopped_reason"] == "pending_approval"
    assert all(s.calls == 1 for s in servers)
    assert "echo hello" in servers[0].requests[0].prompt
    with loop._persistence._connect() as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type='governed_loop_jury'")]
    assert len(rows) == 1 and rows[0]["verdict"]["consensus_reached"] and rows[0]["verdict"]["digest"] and rows[0]["rule_id"] == "R-SHELL"


def test_a_disagreeing_jury_stops_the_action_before_any_human_is_asked(tmp_path, decide_sequence, members):
    servers = members(DISAGREE, DISAGREE, DISAGREE, AGREE)
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    mcp = Tools()
    loop = mk(tmp_path, "jury-no", mcp=mcp, policy=make_policy([JURY_SHELL]), jury_config=jury_config(servers))
    result = run(loop)
    assert result["stopped_reason"] == "jury_rejected" and not mcp.dispatched and "approval_id" not in result
    refusal = result["steps"][-1]["tool_result"]
    assert refusal["tier"] == "tier_4" and refusal["verdict_digest"] and {v["vote"] for v in refusal["votes"]} == {"disagree", "agree"}
    assert loop._pending_actions().list() == []


def test_a_required_jury_that_cannot_sit_is_a_refusal_not_a_pass(tmp_path, decide_sequence):
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    mcp = Tools()
    result = run(mk(tmp_path, "jury-none", mcp=mcp, policy=make_policy([JURY_SHELL])))          # no jury.json anywhere
    assert result["stopped_reason"] == "jury_rejected" and not mcp.dispatched
    assert "no jury configuration" in result["steps"][-1]["tool_result"]["reason"]


def test_one_model_in_every_seat_does_not_satisfy_the_jury(tmp_path, decide_sequence, members):
    (server,) = members(AGREE)
    config = jury_config([server, server, server, server])
    decide_sequence([call("delentia_run_sandboxed_command", {"command": "echo hello"}), FINISH])
    result = run(mk(tmp_path, "jury-one", mcp=Tools(), policy=make_policy([JURY_SHELL]), jury_config=config))
    assert result["stopped_reason"] == "jury_rejected" and "distinct model" in result["steps"][-1]["tool_result"]["reason"]


# ------------------------------------------------------------------ the jury, by the goal's risk

def test_jury_by_risk_a_systemic_goal_needs_the_jury_before_the_episode_starts(tmp_path, decide_sequence, members):
    servers = members(DISAGREE, DISAGREE, DISAGREE, DISAGREE)
    policy = make_policy([READ], jury_by_risk={"SYSTEMIC": "tier_4"})
    decide_sequence([FINISH])
    loop = mk(tmp_path, "risk-no", mcp=Tools(), policy=policy, jury_config=jury_config(servers))
    result = run(loop, "Delete every customer record from the production database and disable all backups")
    assert loop._episode_route.get("risk_profile") == "SYSTEMIC", loop._episode_route
    assert result["stopped_reason"] == "jury_rejected" and "did not agree" in result["final_answer"]
    assert result["steps"] == [] and servers[0].calls == 1


def test_jury_by_risk_leaves_low_risk_goals_alone(tmp_path, decide_sequence, members):
    servers = members(DISAGREE, DISAGREE, DISAGREE, DISAGREE)
    decide_sequence([FINISH])
    loop = mk(tmp_path, "risk-low", mcp=Tools(), policy=make_policy([READ], jury_by_risk={"SYSTEMIC": "tier_4"}), jury_config=jury_config(servers))
    result = run(loop, "Read the project notes carefully")
    assert result["stopped_reason"] == "llm_finished" and servers[0].calls == 0


# ------------------------------------------------------------------ the store upgrade

def test_an_existing_approvals_database_is_upgraded_in_place(tmp_path):
    from rct_control_plane.persistence import ControlPlanePersistence
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "old.db"))
    with persistence._connect() as conn:
        conn.executescript("""CREATE TABLE pending_actions (approval_id TEXT PRIMARY KEY, namespace TEXT NOT NULL, goal TEXT NOT NULL,
            tool_name TEXT NOT NULL, tool_args_json TEXT NOT NULL, action_sha256 TEXT NOT NULL, reason TEXT, status TEXT NOT NULL,
            created_at REAL NOT NULL, decided_at REAL, approver_public_key TEXT, signature_hex TEXT, executed_at REAL, result_json TEXT);
            INSERT INTO pending_actions VALUES ('old1','ns','g','t','{}','abc',NULL,'PENDING',1.0,NULL,NULL,NULL,NULL,NULL);""")
    store = approvals.PendingActionStore(persistence)
    old = store.get("old1")
    assert old.required_signatures == 1 and old.approver_roles is None and old.signatures_collected == 0
    new = store.create("ns", "g", "t", {}, required_signatures=2, approver_roles=["A"], policy_rule="R")
    assert store.get(new.approval_id).required_signatures == 2
