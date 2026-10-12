"""
Round 54: the owner's policy for A in F = D^I x A. Pure evaluation: precedence, roles, denied paths, signatures,
validation, persistence, and the starter templates against the real tool list.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest

from rct_control_plane import fdia_policy as fp


def policy(rules=None, **extra):
    data = {"rules": rules or [], **extra}
    parsed, errors = fp.validate_policy(data)
    assert parsed is not None, errors
    return parsed


READ = {"rule_id": "R-READ", "intent_patterns": ["read_*", "search_*", "recall"], "action_type": "ALLOW"}
WRITE = {"rule_id": "R-WRITE", "intent_patterns": ["write_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
         "human_approver_role": ["Chief_Architect"], "denied_paths": [".env", ".git/*", "*.pem"]}
COND = {"rule_id": "R-COND", "intent_patterns": ["patch_*"], "action_type": "CONDITIONAL", "denied_paths": ["secrets/*"]}


# ------------------------------------------------------------------ the equation's A

def test_allow_gives_a_of_one_and_names_the_rule():
    result = fp.evaluate(policy([READ]), "delentia_read_repo_file", {"relative_path": "README.md"})
    assert result.A == 1.0 and result.rule_id == "R-READ" and not result.needs_signature


def test_short_and_full_tool_names_both_match():
    p = policy([READ])
    assert fp.evaluate(p, "delentia_read_repo_file").A == 1.0
    assert fp.evaluate(p, "read_repo_file").A == 1.0
    assert fp.evaluate(p, "DELENTIA_READ_REPO_FILE").A == 1.0
    assert fp.evaluate(policy([{"rule_id": "R", "intent_patterns": ["delentia_recall"]}]), "delentia_recall").A == 1.0


def test_zero_trust_an_unregistered_tool_has_no_a_and_cannot_be_signed_for():
    result = fp.evaluate(policy([READ]), "delentia_crawl_url", {"url": "https://example.org"})
    assert result.A == 0.0 and result.rule_id == "ZERO_TRUST_FALLBACK" and not result.needs_signature


def test_fallback_a_can_be_opened_by_the_owner():
    result = fp.evaluate(policy([READ], default_fallback_A=1), "delentia_crawl_url")
    assert result.A == 1.0 and result.rule_id == "FALLBACK_ALLOW"


def test_require_signature_is_a_pause_not_a_block_until_signed():
    p = policy([WRITE])
    paused = fp.evaluate(p, "delentia_write_repo_file", {"relative_path": "notes.md"})
    assert paused.A == 0.0 and paused.needs_signature and paused.approver_roles == ["Chief_Architect"]
    signed = fp.evaluate(p, "delentia_write_repo_file", {"relative_path": "notes.md"}, approved=True)
    assert signed.A == 1.0 and not signed.needs_signature


def test_a_signature_never_lifts_a_denied_path_the_owner_forbade():
    p = policy([WRITE])
    for target in (".env", "app/.env", ".env.local", ".git/config", "repo/.git/hooks/pre-commit", "certs/server.pem", "C:\\proj\\.git\\config"):
        result = fp.evaluate(p, "delentia_write_repo_file", {"relative_path": target}, approved=True)
        assert result.A == 0.0, target
        assert "restricted path" in result.reason


@pytest.mark.parametrize("target", ["environment.py", "docs/gitignore.md", "src/pemfile.txt", "notes.md", "my.environment/x"])
def test_denied_paths_do_not_overblock_lookalikes(target):
    assert fp.evaluate(policy([WRITE]), "delentia_write_repo_file", {"relative_path": target}, approved=True).A == 1.0


def test_denied_path_inside_a_shell_command_is_found():
    p = policy([{"rule_id": "R-SH", "intent_patterns": ["run_sandboxed_command"], "action_type": "CONDITIONAL", "denied_paths": [".env", "/etc/*"]}])
    assert fp.evaluate(p, "delentia_run_sandboxed_command", {"command": "cat .env"}).A == 0.0
    assert fp.evaluate(p, "delentia_run_sandboxed_command", {"command": "cat /etc/passwd"}).A == 0.0
    assert fp.evaluate(p, "delentia_run_sandboxed_command", {"command": "echo hello"}).A == 1.0


def test_most_restrictive_matching_rule_wins_whatever_the_order():
    allow_all = {"rule_id": "R-ALL", "intent_patterns": ["*"], "action_type": "ALLOW"}
    for order in ([allow_all, WRITE], [WRITE, allow_all]):
        result = fp.evaluate(policy(order), "delentia_write_repo_file", {"relative_path": "a.md"})
        assert result.rule_id == "R-WRITE" and result.needs_signature
    # the bypass the TypeScript engine had: an action named like a reader that is really destructive
    destructive = {"rule_id": "R-DROP", "intent_patterns": ["*drop_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}
    sneaky = fp.evaluate(policy([READ, destructive]), "read_then_drop_table", {})
    assert sneaky.rule_id == "R-DROP" and sneaky.needs_signature


def test_blocked_patterns_win_even_when_a_rule_allows_and_even_when_signed():
    p = policy([{"rule_id": "R-ALL", "intent_patterns": ["*"], "action_type": "ALLOW"}], blocked_action_patterns=["*export_credentials*"])
    for approved in (False, True):
        result = fp.evaluate(p, "delentia_export_credentials", {}, approved=approved)
        assert result.A == 0.0 and result.rule_id == "BLOCKED_ACTION_PATTERN"


# ------------------------------------------------------------------ roles

def test_roles_come_from_the_identity_the_server_attached():
    rule = {"rule_id": "R-DEPLOY", "intent_patterns": ["create_worktree"], "action_type": "ALLOW", "allowed_roles": ["devops"]}
    p = policy([rule], roles={"default_role": "developer", "principals": {"alice": "devops"}})
    assert fp.evaluate(p, "delentia_create_worktree", {}, principal="alice").A == 1.0
    denied = fp.evaluate(p, "delentia_create_worktree", {}, principal="bob")
    assert denied.A == 0.0 and denied.rule_id == "ROLE_DENIED" and denied.role == "developer"
    assert fp.evaluate(p, "delentia_create_worktree", {}, principal="").A == 0.0


def test_a_wildcard_role_admits_everyone():
    p = policy([{"rule_id": "R", "intent_patterns": ["*"], "allowed_roles": ["*"]}])
    assert fp.evaluate(p, "delentia_recall", {}, principal="anyone").A == 1.0


# ------------------------------------------------------------------ dual sign-off

def test_dual_signoff_by_rule_or_by_list_needs_two_signatures():
    ruled = policy([{"rule_id": "R-DEP", "intent_patterns": ["deploy_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 2}])
    assert fp.evaluate(ruled, "deploy_to_production", {}).required_signatures == 2
    listed = policy([{"rule_id": "R-DEP", "intent_patterns": ["deploy_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}],
                    require_human_dual_signoff=["deploy_to_production"])
    assert fp.evaluate(listed, "deploy_to_production", {}).required_signatures == 2
    assert fp.evaluate(listed, "deploy_to_staging", {}).required_signatures == 1
    only_list = policy([], require_human_dual_signoff=["shutdown_service"])
    assert fp.evaluate(only_list, "shutdown_service", {}).needs_signature
    assert fp.evaluate(only_list, "shutdown_service", {}, approved=True).A == 1.0


def test_conditional_without_a_violation_is_allowed_and_with_one_is_not():
    p = policy([COND])
    assert fp.evaluate(p, "delentia_patch_repo_file", {"relative_path": "src/a.py"}).A == 1.0
    assert fp.evaluate(p, "delentia_patch_repo_file", {"relative_path": "secrets/db.txt"}).A == 0.0


def test_jury_tier_travels_with_the_evaluation():
    p = policy([{"rule_id": "R-J", "intent_patterns": ["run_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "jury_tier": "tier_4"}])
    assert fp.evaluate(p, "delentia_run_sandboxed_command", {}).jury_tier == "tier_4"


# ------------------------------------------------------------------ validation

@pytest.mark.parametrize("data,fragment", [
    ([], "JSON object"),
    ({"rules": "x"}, "rules must be a list"),
    ({"rules": [{"rule_id": "bad id!", "intent_patterns": ["a"]}]}, "rule_id"),
    ({"rules": [{"rule_id": "A", "intent_patterns": []}]}, "at least one pattern"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "action_type": "MAYBE"}]}, "action_type"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"]}, {"rule_id": "A", "intent_patterns": ["b"]}]}, "used twice"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "assigned_A": 2}]}, "assigned_A"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "required_signatures": 9}]}, "required_signatures"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "required_signatures": 2}]}, "REQUIRE_HUMAN_SIGNATURE"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "jury_tier": "tier_99"}]}, "jury_tier"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["x" * 500]}]}, "longer than"),
    ({"rules": [{"rule_id": "A", "intent_patterns": ["a"], "allowed_roles": ["<script>"]}]}, "not allowed"),
    ({"custom_safety_threshold": 3}, "custom_safety_threshold"),
    ({"default_fallback_A": -1}, "default_fallback_A"),
    ({"jury_by_risk": {"HIGH": "tier_4"}}, "jury_by_risk"),
    ({"roles": {"default_role": "!!"}}, "default_role"),
    ({"rules": [{"rule_id": f"R{i}", "intent_patterns": ["a"]} for i in range(250)]}, "too many rules"),
])
def test_invalid_policies_are_refused_with_a_reason(data, fragment):
    parsed, errors = fp.validate_policy(data)
    assert parsed is None and any(fragment in e for e in errors), errors


def test_unknown_fields_are_ignored_like_the_typescript_schema():
    parsed, errors = fp.validate_policy({"rules": [], "schema": "https://delentia.com/schemas/fdia-policy-v1.json", "organization_id": "x"})
    assert parsed is not None and not errors


def test_the_bundled_typescript_policy_loads_unchanged():
    path = fp.Path(__file__).resolve().parents[3] / "delentia-mcp" / "ecosystem" / "packages" / "shared" / "src" / "fdia-policy.json"
    if not path.exists():
        pytest.skip("sibling TypeScript checkout not present")
    parsed, errors = fp.validate_policy(json.loads(path.read_text(encoding="utf-8")))
    assert parsed is not None, errors
    assert fp.evaluate(parsed, "delentia_read_repo_file", {}).A == 1.0
    assert fp.evaluate(parsed, "delete_everything", {}).needs_signature


# ------------------------------------------------------------------ persistence

def test_save_and_load_roundtrip_keeps_the_digest(tmp_path):
    original = policy([READ, WRITE], roles={"default_role": "dev", "principals": {"alice": "ops"}}, jury_by_risk={"SYSTEMIC": "tier_4"})
    target = tmp_path / "p.json"
    fp.save_policy(original, target)
    loaded = fp.load_policy(target)
    assert loaded is not None and loaded.digest() == original.digest()
    assert loaded.role_for("alice") == "ops" and loaded.role_for("zed") == "dev"


def test_digest_changes_with_any_rule_change():
    a, b = policy([READ]), policy([dict(READ, intent_patterns=["read_*"])])
    assert a.digest() != b.digest()


def test_no_file_means_no_policy_and_a_broken_file_raises(tmp_path):
    assert fp.load_policy(tmp_path / "missing.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read"):
        fp.load_policy(broken)
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"rules": [{"rule_id": "!"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        fp.load_policy(invalid)


def test_environment_variable_chooses_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "x.json"))
    assert fp.policy_path() == tmp_path / "x.json"


# ------------------------------------------------------------------ the starters against the real tools

@pytest.fixture(scope="module")
def real_tool_names():
    import asyncio
    from rct_control_plane.mcp_server import mcp
    tools = asyncio.run(mcp.list_tools())
    return [t.name for t in tools]


@pytest.mark.parametrize("name", ["balanced", "strict"])
def test_every_real_tool_is_classified_by_the_starter_templates(name, real_tool_names):
    assert len(real_tool_names) >= 30
    parsed, errors = fp.validate_policy(fp.template(name, real_tool_names))
    assert parsed is not None, errors
    unregistered = [t for t in real_tool_names if fp.evaluate(parsed, t, {}).rule_id == "ZERO_TRUST_FALLBACK"]
    assert unregistered == []


def test_starters_ask_for_a_signature_on_shell_and_file_writes_and_allow_reads(real_tool_names):
    parsed, _ = fp.validate_policy(fp.template("balanced", real_tool_names))
    assert fp.evaluate(parsed, "delentia_run_sandboxed_command", {"command": "ls"}).needs_signature
    assert fp.evaluate(parsed, "delentia_write_repo_file", {"relative_path": "a.md"}).needs_signature
    assert fp.evaluate(parsed, "delentia_write_repo_file", {"relative_path": ".env"}, approved=True).A == 0.0
    assert fp.evaluate(parsed, "delentia_read_repo_file", {"relative_path": "a.md"}).A == 1.0
    strict, _ = fp.validate_policy(fp.template("strict", real_tool_names))
    assert fp.evaluate(strict, "delentia_run_sandboxed_command", {"command": "ls"}).jury_tier == "tier_4"
    assert strict.custom_safety_threshold > parsed.custom_safety_threshold


def test_the_other_actions_rule_does_not_repeat_tools_that_have_their_own_rule(real_tool_names):
    data = fp.template("balanced", real_tool_names)
    other = next(r for r in data["rules"] if r["rule_id"] == "R-OTHER-ACTIONS")["intent_patterns"]
    for special in ("run_sandboxed_command", "synthesize_function", "write_repo_file", "patch_repo_file", "save_exchange_file"):
        assert f"delentia_{special}" not in other
    assert "delentia_crawl_url" in other and "delentia_spawn_subagents" in other


def test_starters_keep_a_shell_command_away_from_secrets_even_when_signed(real_tool_names):
    parsed, _ = fp.validate_policy(fp.template("balanced", real_tool_names))
    assert fp.evaluate(parsed, "delentia_run_sandboxed_command", {"command": "cat .env"}, approved=True).A == 0.0
    assert fp.evaluate(parsed, "delentia_run_sandboxed_command", {"command": "cat /etc/passwd"}, approved=True).A == 0.0
    assert fp.evaluate(parsed, "delentia_run_sandboxed_command", {"command": "echo hello"}, approved=True).A == 1.0


def test_round65_the_careful_starter_asks_for_everything_that_reaches_beyond_the_machine(real_tool_names):
    """scripts/calibrate_fdia_round65.py: under the balanced starter 16 of 52 should-ask requests still ran (fetching an unnamed address, subagents, delegation, imported state,
    schedules, web search). The careful starter asks for those too; reading and remembering stay free."""
    careful, errors = fp.validate_policy(fp.template("careful", real_tool_names))
    assert careful is not None, errors
    for tool in ("delentia_crawl_url", "delentia_web_search", "delentia_browse_page", "delentia_spawn_subagents", "delentia_delegate", "delentia_import_session_state",
                 "delentia_schedule_self_evolution", "delentia_create_worktree"):
        if tool in real_tool_names:
            assert fp.evaluate(careful, tool, {}).needs_signature, tool
    assert fp.evaluate(careful, "delentia_read_repo_file", {"relative_path": "a.md"}).A == 1.0
    assert fp.evaluate(careful, "delentia_recall", {"query": "x"}).A == 1.0
    balanced, _ = fp.validate_policy(fp.template("balanced", real_tool_names))
    assert not fp.evaluate(balanced, "delentia_web_search", {"query": "x"}).needs_signature          # the balanced starter is unchanged
    reach = next(r for r in fp.template("careful", real_tool_names)["rules"] if r["rule_id"] == "R-REACH")["intent_patterns"]
    other = next(r for r in fp.template("careful", real_tool_names)["rules"] if r["rule_id"] == "R-OTHER-ACTIONS")["intent_patterns"]
    assert not set(reach) & set(other)
