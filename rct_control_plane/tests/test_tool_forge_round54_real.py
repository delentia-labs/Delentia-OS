"""
Round 54: Tool Forge (ALGO-39 Genesis grown into a governed loop) and ALGO-08's readiness rule on the runtime's G scale.
Real subprocesses run the candidate code, real SQLite holds proposals, real Ed25519 approvals gate activation, a real HTTP
server stands in for the model that writes the code, and the real MCP tool registry and governed loop call the result.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, tool_forge as tf
from rct_control_plane.llm_provider import OpenAICompatibleProvider
from rct_control_plane.persistence import ControlPlanePersistence
from scripted_model import ScriptedModel
from test_governed_autonomous_loop_real import _FakeKernel, _loop, _scripted_decide

GOOD = '''
import re

def slugify(title):
    """Turn a title into a url slug."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join(words)
'''
SMOKE = 'assert slugify("Hello World") == "hello-world"\nassert slugify("  A  B  ") == "a-b"\nassert slugify("") == ""'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def forge(tmp_path):
    return tf.ToolForge(ControlPlanePersistence(db_path=str(tmp_path / "forge.db")))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    path = tmp_path / "keys" / "owner.pem"
    public = approvals.generate_approver_key(str(path))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    return str(path)


def sign(forge, approval_id, key_path, decision="APPROVED"):
    store = approvals.PendingActionStore(forge._persistence)
    record = store.get(approval_id)
    signed = approvals.sign_decision(key_path, approval_id, record.action_sha256, decision)
    return store.decide(approval_id, decision, signed["public_key_hex"], signed["signature_hex"])


def run(coro):
    return asyncio.run(coro)


def activate_slugify(forge, approver):
    proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    assert proposal.status == "VERIFIED", proposal.verification
    record = forge.request_activation(proposal.id)
    sign(forge, record.approval_id, approver)
    return proposal, forge.activate(record.approval_id)


# ------------------------------------------------------------------ the static check

def test_a_plain_pure_function_passes():
    assert tf.static_check(GOOD, "slugify") == []


@pytest.mark.parametrize("code,fragment", [
    ("import os\ndef f(x):\n    return os.getcwd()", "import os"),
    ("import subprocess\ndef f(x):\n    return 1", "import subprocess"),
    ("from os import path\ndef f(x):\n    return 1", "import from os"),
    ("from . import sibling\ndef f(x):\n    return 1", "import from"),
    ("from math import *\ndef f(x):\n    return pi", "import *"),
    ("def f(x):\n    return open('/etc/passwd').read()", "name open"),
    ("def f(x):\n    return eval(x)", "name eval"),
    ("def f(x):\n    exec(x)\n    return 1", "name exec"),
    ("def f(x):\n    return __import__('os')", "name __import__"),
    ("def f(x):\n    return getattr(x, 'real')", "name getattr"),
    ("def f(x):\n    return x.__class__", "access to __class__"),
    ("def f(x):\n    return ''.__class__.__mro__", "access to __class__"),
    ("def f(x):\n    return '{0.__class__}'.format(x)", "string containing __"),
    ("def f(x):\n    return x._private", "access to _private"),
    ("class C:\n    pass\ndef f(x):\n    return 1", "ClassDef"),
    ("def f(x):\n    global y\n    return 1", "Global"),
    ("async def f(x):\n    return 1", "AsyncFunctionDef"),
    ("def f(x):\n    yield x", "Yield"),
    ("print('hello')\ndef f(x):\n    return 1", "module level"),
    ("x = [i for i in range(10)]\ndef f(x):\n    return 1", "module level"),
    ("def other(x):\n    return 1", "does not define a function named f"),
    ("def f(x:\n    return 1", "syntax error"),
    ("", "empty"),
    ("def f(x):\n    return 1\n" + "# pad\n" * 2000, "longer than"),
])
def test_unsafe_or_malformed_code_is_refused_with_a_reason(code, fragment):
    problems = tf.static_check(code, "f")
    assert problems and any(fragment in p for p in problems), problems


@pytest.mark.parametrize("smoke,fragment", [
    ("assert slugify('a') == 'a'", "at least 2"),
    ("assert True\nassert 1 == 1", "at least 2"),
    ("x = slugify('a')\nassert x == 'a'\nassert x", "at least 2"),
    ("assert slugify('a') == 'a'\nassert slugify('b') == 'b'\nprint('hi')", "assertions only"),
    ("import os\nassert slugify('a') == 'a'\nassert slugify('b') == 'b'", "import os is not allowed"),
    ("assert slugify('a') == open('x').read()\nassert slugify('b') == 'b'", "name open"),
    ("assert slugify('a'", "syntax error"),
])
def test_a_smoke_test_must_really_test(smoke, fragment):
    problems = tf.smoke_check(smoke, "slugify")
    assert problems and any(fragment in p for p in problems), problems


def test_a_proper_smoke_test_passes():
    assert tf.smoke_check(SMOKE, "slugify") == []


# ------------------------------------------------------------------ running it in its own process

def test_verify_runs_the_smoke_test_in_a_separate_process():
    result = tf.verify_code(GOOD, SMOKE, "slugify")
    assert result["passed"] and result["stage"] == "smoke_run" and "SMOKE_OK" in result["stdout"]


def test_a_failing_assertion_fails_verification():
    wrong = GOOD.replace('"-".join', '"_".join')
    result = tf.verify_code(wrong, SMOKE, "slugify")
    assert not result["passed"] and result["stage"] == "smoke_run" and "AssertionError" in result["problems"][0]


def test_code_that_never_returns_is_stopped(monkeypatch):
    monkeypatch.setattr(tf, "RUN_TIMEOUT_S", 1.0)
    loops = "def spin(n):\n    while True:\n        n += 1\n"
    result = tf.verify_code(loops, "assert spin(1) == 1\nassert spin(2) == 2", "spin")
    assert not result["passed"] and result["timed_out"] and "timed out" in result["problems"][0]


def test_the_candidate_does_not_see_the_hosts_secrets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    assert "sk-should-not-leak" not in tf._clean_env().values()


# ------------------------------------------------------------------ proposals

def test_a_verified_proposal_is_kept_with_its_hash_and_checks(forge):
    proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    saved = forge.get(proposal.id)
    assert saved.status == "VERIFIED" and saved.code_sha256 == tf.sha256(GOOD + "\n" + SMOKE) and saved.verification["code_source"] == "supplied"


def test_rejected_proposals_are_kept_never_deleted_and_cannot_be_put_forward(forge):
    bad = run(forge.propose("peek", "read a secret file", "assert peek('a') == 'a'\nassert peek('b') == 'b'", code="import os\ndef peek(x):\n    return os.environ"))
    assert bad.status == "REJECTED_STATIC_CHECK" and forge.get(bad.id) is not None
    untested = run(forge.propose("noassert", "do nothing useful", "assert True", code="def noassert(x):\n    return x"))
    assert untested.status == "REJECTED_SMOKE_CHECK"
    failing = run(forge.propose("wrongone", "return the double", "assert wrongone(2) == 4\nassert wrongone(3) == 6", code="def wrongone(x):\n    return x"))
    assert failing.status == "REJECTED_SMOKE_RUN"
    with pytest.raises(tf.ForgeError, match="only a VERIFIED proposal"):
        forge.request_activation(bad.id)
    assert {p.status for p in forge.list_proposals()} >= {"REJECTED_STATIC_CHECK", "REJECTED_SMOKE_CHECK", "REJECTED_SMOKE_RUN"}


@pytest.mark.parametrize("name", ["", "ab", "Slug", "9lives", "has space", "x" * 60, "../up"])
def test_bad_tool_names_are_refused(forge, name):
    with pytest.raises(tf.ForgeError, match="tool name"):
        run(forge.propose(name, "spec", SMOKE, code=GOOD))


# ------------------------------------------------------------------ the model writes the code (over HTTP)

def test_the_model_writes_the_code_and_it_is_checked_before_it_runs(forge):
    def policy(request):
        match = re.search(r"named exactly `(\w+)`", request.prompt)
        assert match and "standard library" in request.prompt
        return "```python\n" + GOOD.replace("slugify", match.group(1)) + "\n```"

    with ScriptedModel(policy) as model:
        provider = OpenAICompatibleProvider(base_url=model.base_url, model="scripted-1", kind="local")
        proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, provider=provider))
        assert proposal.status == "VERIFIED" and proposal.verification["code_source"] == "model" and model.calls == 1


def test_malicious_model_output_never_reaches_a_process(forge, tmp_path):
    marker = tmp_path / "pwned.txt"
    evil = f"import os\ndef slugify(title):\n    open({str(marker)!r}, 'w').write('x')\n    return title"
    with ScriptedModel(lambda request: evil) as model:
        provider = OpenAICompatibleProvider(base_url=model.base_url, model="scripted-1", kind="local")
        proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, provider=provider))
    assert proposal.status == "REJECTED_STATIC_CHECK" and not marker.exists()


# ------------------------------------------------------------------ the human signs the exact code

def test_nothing_is_active_until_a_trusted_key_signs_and_a_second_activation_is_refused(forge, approver, tmp_path):
    proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    record = forge.request_activation(proposal.id)
    assert forge.get(proposal.id).status == "AWAITING_APPROVAL" and forge.active_tool("slugify") is None
    with pytest.raises(approvals.ApprovalError, match="not APPROVED"):
        forge.activate(record.approval_id)
    intruder = tmp_path / "keys" / "intruder.pem"
    approvals.generate_approver_key(str(intruder))
    with pytest.raises(approvals.ApprovalError, match="trusted"):
        sign(forge, record.approval_id, str(intruder))
    sign(forge, record.approval_id, approver)
    result = forge.activate(record.approval_id)
    assert forge.active_tool("slugify")["code_sha256"] and os.path.exists(result["file"]) and forge.get(proposal.id).status == "ACTIVE"
    with pytest.raises(approvals.ApprovalError, match="already executed"):
        forge.activate(record.approval_id)


def test_a_rejected_activation_installs_nothing(forge, approver):
    proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    record = forge.request_activation(proposal.id)
    assert sign(forge, record.approval_id, approver, "REJECTED").status == "REJECTED"
    with pytest.raises(approvals.ApprovalError, match="REJECTED"):
        forge.activate(record.approval_id)
    assert forge.active_tool("slugify") is None


def test_a_signature_for_one_proposal_cannot_install_another(forge, approver):
    first = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    record = forge.request_activation(first.id)
    sign(forge, record.approval_id, approver)
    swapped = GOOD.replace('"-".join', '"+".join')               # the stored proposal changes after it was signed
    with forge._persistence._connect() as conn:
        conn.execute("UPDATE forge_proposals SET code = ? WHERE id = ?", (swapped, first.id))
    with pytest.raises(approvals.ApprovalError, match="no longer matches what was signed"):
        forge.activate(record.approval_id)
    assert forge.active_tool("slugify") is None


def test_the_approval_record_binds_the_hash_of_code_and_test(forge):
    proposal = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    record = forge.request_activation(proposal.id)
    assert record.tool_name == tf.ACTIVATE_TOOL and record.tool_args["code_sha256"] == proposal.code_sha256


# ------------------------------------------------------------------ using it

def test_an_active_tool_runs_in_its_own_process_and_counts_its_calls(forge, approver):
    activate_slugify(forge, approver)
    first = forge.run("slugify", {"title": "Hello Brave New World"})
    assert first == {"ok": True, "result": "hello-brave-new-world"}
    forge.run("slugify", {"title": "x"})
    assert forge.list_tools()[0]["calls"] == 2
    assert forge.run("slugify", {"wrong_argument": 1})["ok"] is False
    assert forge.run("nothing_here", {})["available"] == ["slugify"]


def test_tampering_with_the_installed_file_is_caught_on_the_next_call(forge, approver):
    _, result = activate_slugify(forge, approver)
    with open(result["file"], "a", encoding="utf-8") as handle:
        handle.write("\nimport os\n")
    outcome = forge.run("slugify", {"title": "a"})
    assert outcome["ok"] is False and "does not match the code a human signed" in outcome["error"]


def test_a_tool_that_runs_too_long_is_stopped(forge, approver, monkeypatch):
    slow = "def slowpoke(n):\n    total = 0\n    while True:\n        total += n\n"
    proposal = run(forge.propose("slowpoke", "never returns", "assert slowpoke.__name__ == 'x'\nassert 1", code=slow))
    assert proposal.status.startswith("REJECTED")                # a smoke test cannot even be written for it
    forge_dir_file = tf.forge_dir() / "slowpoke.py"
    forge_dir_file.write_text(slow, encoding="utf-8")
    with forge._persistence._connect() as conn:
        conn.execute("INSERT INTO forged_tools VALUES ('slowpoke', 'x', ?, ?, 'spin', 'a', 1, 0, 0)", (tf.sha256(slow), str(forge_dir_file)))
    monkeypatch.setattr(tf, "RUN_TIMEOUT_S", 1.0)
    assert "ran longer" in forge.run("slowpoke", {"n": 1})["error"]


def test_a_tool_can_be_turned_off_and_stays_on_record(forge, approver):
    activate_slugify(forge, approver)
    assert forge.deactivate("slugify") and forge.run("slugify", {"title": "a"})["ok"] is False
    assert [t["name"] for t in forge.list_tools(include_disabled=True)] == ["slugify"] and forge.list_tools() == []
    assert forge.deactivate("slugify") is False


def test_an_active_name_cannot_be_proposed_again(forge, approver):
    activate_slugify(forge, approver)
    with pytest.raises(tf.ForgeError, match="already active"):
        run(forge.propose("slugify", "again", SMOKE, code=GOOD))


def test_results_that_are_not_json_become_text_not_a_crash(forge, approver):
    code = "def tagset(text):\n    return set(text.split())"
    proposal = run(forge.propose("tagset", "unique words", "assert len(tagset('a b a')) == 2\nassert len(tagset('')) == 0", code=code))
    record = forge.request_activation(proposal.id)
    sign(forge, record.approval_id, approver)
    forge.activate(record.approval_id)
    assert forge.run("tagset", {"text": "z"})["ok"] is True


# ------------------------------------------------------------------ the gap evidence

def seed(persistence, goal, *, finished=1, aligned=0, user="alice", warm=0, count=1):
    experiment = f"exp-{abs(hash(goal)) % 10**8}"
    persistence.save_experiment(experiment, name=goal, description="test")
    for i in range(count):
        persistence.save_experiment_run(f"run-{abs(hash((goal, user, i, warm, aligned))) % 10**10}", experiment, algorithm_id="governed_loop/test",
                                        metrics={"finished": finished, "aligned_with_intent": aligned, "warm_recall": warm},
                                        jitna_state={"namespace": user})


def test_repeated_unmet_goals_are_grouped_into_a_gap(tmp_path):
    p = ControlPlanePersistence(db_path=str(tmp_path / "gaps.db"))
    seed(p, "Convert this temperature from celsius to fahrenheit", count=2)
    seed(p, "Please convert the temperature from fahrenheit to celsius", user="bob", count=1)
    seed(p, "Summarise the release notes", count=1)
    seed(p, "Read the readme", aligned=1, count=5)
    seed(p, "Translate the invoice", warm=1, count=4)
    gaps = tf.find_gaps(p)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["count"] == 3 and gap["users"] == 2 and len(gap["goals"]) == 2 and "temperature" in gap["keywords"] and gap["gap_id"].startswith("gap-")


def test_min_count_and_an_empty_history_are_handled(tmp_path):
    p = ControlPlanePersistence(db_path=str(tmp_path / "gaps2.db"))
    assert tf.find_gaps(p) == []
    seed(p, "Count the vowels in this sentence", count=1)
    assert tf.find_gaps(p) == [] and len(tf.find_gaps(p, min_count=1)) == 1


# ------------------------------------------------------------------ the agent uses an activated tool (real MCP, real loop)

def test_the_forged_tools_are_in_the_registry_and_behind_the_risky_gate():
    from rct_control_plane.governed_autonomous_loop import RISKY_TOOLS
    from rct_control_plane.mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"delentia_list_forged_tools", "delentia_run_forged_tool"} <= names
    assert "delentia_run_forged_tool" in RISKY_TOOLS and "delentia_list_forged_tools" not in RISKY_TOOLS


def test_the_governed_loop_calls_an_activated_tool_through_the_real_registry(tmp_path, approver, monkeypatch):
    from rct_control_plane.mcp_server import _kernel, mcp
    forge = tf.ToolForge(_kernel._persistence)
    name = "slugify_" + os.urandom(3).hex()
    code = GOOD.replace("slugify", name)
    smoke = SMOKE.replace("slugify", name)
    proposal = run(forge.propose(name, "turn a title into a url slug", smoke, code=code))
    record = forge.request_activation(proposal.id)
    sign(forge, record.approval_id, approver)
    forge.activate(record.approval_id)
    decisions = [
        {"action": "call_tool", "tool_name": "delentia_run_forged_tool", "tool_args": {"tool_name": name, "tool_args": {"title": "Agents Make Tools"}},
         "reasoning": "the slug tool exists", "final_answer": None},
        {"action": "finish", "reasoning": "done", "final_answer": "<answer that restates the goal>", "tool_name": None, "tool_args": {}},
    ]
    fake, _ = _scripted_decide(decisions)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "forge-loop", kernel=_FakeKernel(), mcp=mcp)
    real_assess = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real_assess(goal, clarity, compile_result)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    result = asyncio.run(loop.run("Make a url slug out of the title Agents Make Tools"))
    assert result["stopped_reason"] == "llm_finished"
    step = result["steps"][0]
    assert step["tool_name"] == "delentia_run_forged_tool" and step["tool_result"] == {"ok": True, "result": "agents-make-tools"}


# ------------------------------------------------------------------ ALGO-08: readiness on the runtime's G scale

from rct_control_plane import algo_08_self_evolving as a8  # noqa: E402
from rct_control_plane.algo_10_delta_memory import DocumentStatus, DocumentType, RCTDBClient, VaultDocument  # noqa: E402
from rct_control_plane.mee_engine import MEESession  # noqa: E402


def orchestrator(g_initial=1.0, deltas=(), gap_finder=None):
    session = MEESession("t", g_initial=g_initial)
    for delta in deltas:
        session.step(delta)
    return a8.SelfEvolvingOrchestrator(session, RCTDBClient(mock_mode=True), gap_finder=gap_finder), session


def test_the_threshold_is_the_same_ratio_on_both_scales():
    assert a8.SPAWN_GROWTH_RATIO == pytest.approx(70 / 65)
    legacy, legacy_session = orchestrator(g_initial=65.0, deltas=[0.6] * 5)
    runtime, runtime_session = orchestrator(g_initial=1.0, deltas=[0.6] * 5)
    assert legacy_session.total_growth_ratio == pytest.approx(runtime_session.total_growth_ratio)
    assert legacy.readiness()["ready"] and runtime.readiness()["ready"]
    assert legacy_session.g > 70                                       # what the old rule asked of a session that started at 65


def test_the_old_rule_could_never_be_met_by_a_session_that_starts_at_one():
    session = MEESession("old", g_initial=1.0)
    for _ in range(60):
        session.step(0.6)
    assert session.g < 70, "even 60 verified episodes leave the runtime's G far below the old absolute threshold of 70"


def test_not_enough_growth_steps_or_ratio_or_evenness_each_say_why():
    fresh, _ = orchestrator()
    reasons = " | ".join(fresh.readiness()["reasons"])
    assert "growth ratio" in reasons and "of 5 growth steps" in reasons
    flat, _ = orchestrator(deltas=[0.01] * 6)
    assert any("recent average growth" in r for r in flat.readiness()["reasons"])
    uneven, _ = orchestrator(deltas=[0.9, -0.2, 0.9, -0.2, 0.9, 0.9])
    assert any("too uneven" in r for r in uneven.readiness()["reasons"])
    locked, _ = orchestrator(deltas=[0.6] * 6)
    locked.state.safety_locked = True
    assert "safety lock is on" in locked.readiness()["reasons"]


def test_a_fresh_process_is_not_made_to_wait_an_hour_but_a_recent_evolution_is():
    ready, _ = orchestrator(deltas=[0.6] * 6)
    assert ready.readiness()["ready"] and ready.readiness()["measured"]["seconds_since_last_evolution"] is None
    ready.state.last_evolution = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert any("cooldown" in r for r in ready.readiness()["reasons"])
    ready.state.last_evolution = datetime.now(timezone.utc) - timedelta(seconds=a8.COOLDOWN_SECONDS + 5)
    assert ready.readiness()["ready"]


def test_the_cycle_reports_evidence_not_a_fabricated_algorithm():
    docs = RCTDBClient(mock_mode=True)
    for i in range(10):
        docs.add_mock_document(VaultDocument(uid=f"d{i}", vault="v", section_id="s", section_name="S", slug=f"d{i}", title=f"Doc {i}",
                                             doc_type=DocumentType.SPEC, status=DocumentStatus.ACTIVE, version="1",
                                             created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
    gaps = [{"gap_id": "gap-1", "goals": ["convert celsius"], "count": 3}]
    orch = a8.SelfEvolvingOrchestrator(MEESession("cycle", g_initial=1.0), docs, gap_finder=lambda: gaps)
    outcomes = [asyncio.run(orch.evolve_cycle()) for _ in range(7)]
    ready = [o for o in outcomes if o["status"] == "evolution_ready"]
    assert ready, [o["status"] for o in outcomes]
    first = ready[0]
    assert first["gaps"] == gaps and "forge propose" in first["next_step"] and "new_algorithm" not in first
    assert orch.get_evolution_status()["last_evolution"] is not None
    after = asyncio.run(orch.evolve_cycle())
    assert after["status"] == "no_evolution" and "cooldown" in after["reason"]


def test_a_broken_gap_finder_does_not_break_the_cycle():
    def broken():
        raise RuntimeError("db down")

    orch, _ = orchestrator(deltas=[0.6] * 6, gap_finder=broken)
    assert orch._find_gaps() == []


def test_no_gap_finder_means_no_gaps():
    orch, _ = orchestrator()
    assert orch._find_gaps() == []


def test_the_real_kernel_hands_its_persistence_to_the_gap_finder(shared_kernel):
    status = asyncio.run(shared_kernel.algo_08_self_evolving())
    assert status["status"] in ("no_evolution", "evolution_ready", "error") and "readiness" in status


def test_a_swapped_proposal_that_still_passes_its_test_is_refused_too(forge, approver):
    first = run(forge.propose("slugify", "turn a title into a url slug", SMOKE, code=GOOD))
    record = forge.request_activation(first.id)
    sign(forge, record.approval_id, approver)
    quietly_different = GOOD.replace('"""Turn a title into a url slug."""', '"""Turn a title into a url slug, differently."""')
    assert tf.verify_code(quietly_different, SMOKE, "slugify")["passed"]
    with forge._persistence._connect() as conn:
        conn.execute("UPDATE forge_proposals SET code = ? WHERE id = ?", (quietly_different, first.id))
    with pytest.raises(approvals.ApprovalError, match="no longer matches what was signed"):
        forge.activate(record.approval_id)
