"""Round 67: owner-policy rules that look at the arguments (fdia_policy `when` / `unless`, the `argaware` starter)."""
from __future__ import annotations

import pytest

from rct_control_plane import fdia_policy as fp

TOOLS = ["delentia_run_sandboxed_command", "delentia_write_repo_file", "delentia_patch_repo_file", "delentia_save_exchange_file", "delentia_read_repo_file",
         "delentia_web_search", "delentia_describe_image", "delentia_crawl_url", "delentia_browse_page", "delentia_synthesize_function", "delentia_create_worktree",
         "delentia_spawn_subagents", "delentia_schedule_reminder"]
SHELL = "delentia_run_sandboxed_command"


@pytest.fixture(scope="module")
def policy():
    p, errors = fp.validate_policy(fp.template("argaware", TOOLS))
    assert p is not None, errors
    return p


def verdict(policy, command, tool=SHELL, key="command"):
    ev = fp.evaluate(policy, tool, {key: command})
    return "allow" if ev.A > 0 and not ev.needs_signature else ("sign" if ev.needs_signature else "block")


@pytest.mark.parametrize("command", ["ls docs", "ls -la src", "pwd", "git status", "git log --oneline -5", "git diff", "git branch --show-current", "wc -l README.md",
                                     "grep -rn TODO src", "ls src | wc -l", "python --version", "cat config/settings.yaml", "df -h", "whoami", "pip show requests"])
def test_read_only_inspection_runs_without_a_signature(policy, command):
    assert verdict(policy, command) == "allow"


# every one of these looks like an inspection command at the start
@pytest.mark.parametrize("command", [
    "ls src; rm -rf build", "ls && rm x", "cat README.md > /etc/readme", "ls | sh", "ls | wc -l | sh", "echo $(whoami)", "echo `id`", "echo $HOME", "echo %USERPROFILE%",
    "ls ../..", "ls ~", "ls -la ~", "cat /etc/hosts", "cat C:\\Windows\\win.ini", "git log --output=log.txt", "git diff --output=x", "find . -name x -delete", "git branch -D old",
    "git branch newbranch", "cat docs/guide.md | tee notes/copy.md", "PYTHONPATH=src python scripts/report.py", "lsx", "ls\nrm x", "grep -r password ~/", "echo hi > x", "cat < /etc/passwd",
    "python --version && rm x", "git status; git push", "du -sh ^", "wc -l a & rm b",
])
def test_commands_dressed_as_inspection_are_asked_about(policy, command):
    assert verdict(policy, command) in ("sign", "block"), command


@pytest.mark.parametrize("command", ["cat .env", "cat .env.local", "cat id_rsa", "cat server.pem", "cat ~/.ssh/id_rsa"])
def test_secret_names_are_blocked_not_just_asked(policy, command):
    assert verdict(policy, command) == "block"


def test_missing_command_argument_asks(policy):
    assert fp.evaluate(policy, SHELL, {}).needs_signature


def test_other_programs_ask(policy):
    for c in ("rm build/output.log", "pip install requests", "git push origin main", "chmod +x run.sh", "python scripts/report.py", "npm install", "kill -9 12"):
        assert verdict(policy, c) == "sign", c


def test_search_with_personal_data_asks_and_plain_search_runs(policy):
    assert verdict(policy, "Python asyncio tutorial", "delentia_web_search", "query") == "allow"
    assert verdict(policy, "landlord Somchai phone number", "delentia_web_search", "query") == "sign"
    assert verdict(policy, "ที่อยู่บ้านสมชาย", "delentia_web_search", "query") == "sign"


def test_image_inside_project_runs_other_paths_ask(policy):
    assert verdict(policy, "exports/chart.png", "delentia_describe_image", "path") == "allow"
    assert verdict(policy, "../x.png", "delentia_describe_image", "path") == "sign"
    assert verdict(policy, "exports/secret.pdf", "delentia_describe_image", "path") == "sign"
    assert verdict(policy, "/home/x/photo.png", "delentia_describe_image", "path") == "sign"


def test_reaching_beyond_the_machine_asks(policy):
    for tool, args in (("delentia_crawl_url", {"url": "https://example.org"}), ("delentia_browse_page", {"url": "https://example.org"}),
                       ("delentia_spawn_subagents", {"goals": ["a"]}), ("delentia_schedule_reminder", {"message": "x"})):
        assert fp.evaluate(policy, tool, args).needs_signature, tool


def test_writes_to_secrets_cannot_be_signed_for(policy):
    ev = fp.evaluate(policy, "delentia_write_repo_file", {"relative_path": ".env", "content_text": "k"}, approved=True)
    assert ev.A == 0


# --------------------------------------------------------------- the file format

def rule(**extra):
    base = {"rule_id": "R", "intent_patterns": ["run_sandboxed_command"], "action_type": "ALLOW"}
    base.update(extra)
    return {"rules": [base], "default_fallback_A": 0}


def test_conditions_are_validated():
    bad = [
        {"when": [{"arg": "command", "op": "regex", "values": ["x"]}]},                      # no regular expressions
        {"when": [{"arg": "command", "op": "prefix_in", "values": []}]},                     # needs values
        {"when": [{"arg": "bad name!", "op": "prefix_in", "values": ["ls"]}]},
        {"when": "ls"},
        {"unless": [{"arg": "command", "op": "prefix_in", "values": ["ls"]}] * 13},          # too many
        {"when": [5]},
    ]
    for extra in bad:
        policy, errors = fp.validate_policy(rule(**extra))
        assert policy is None and errors, extra


def test_an_unknown_operation_never_holds():
    assert fp._one_condition_holds({"arg": "command", "op": "nonsense", "values": ["x"]}, {"command": "x"}) is False


def test_when_and_unless_semantics():
    policy, errors = fp.validate_policy({"rules": [
        {"rule_id": "A", "intent_patterns": ["run_sandboxed_command"], "action_type": "ALLOW", "when": [{"arg": "command", "op": "prefix_in", "values": ["ls"]}]},
        {"rule_id": "B", "intent_patterns": ["run_sandboxed_command"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "unless": [{"arg": "command", "op": "prefix_in", "values": ["ls"]}]},
    ], "default_fallback_A": 0})
    assert policy is not None, errors
    assert fp.evaluate(policy, SHELL, {"command": "ls x"}).rule_id == "A"
    assert fp.evaluate(policy, SHELL, {"command": "rm x"}).rule_id == "B"


def test_no_rule_matching_after_conditions_falls_back_to_zero_trust():
    policy, _ = fp.validate_policy({"rules": [{"rule_id": "A", "intent_patterns": ["run_sandboxed_command"], "action_type": "ALLOW",
                                              "when": [{"arg": "command", "op": "prefix_in", "values": ["ls"]}]}], "default_fallback_A": 0})
    ev = fp.evaluate(policy, SHELL, {"command": "rm x"})
    assert ev.A == 0 and ev.rule_id == "ZERO_TRUST_FALLBACK"


def test_conditions_change_the_digest_and_survive_a_round_trip(tmp_path, policy):
    path = tmp_path / "p.json"
    fp.save_policy(policy, path)
    again = fp.load_policy(path)
    assert again.digest() == policy.digest()
    plain, _ = fp.validate_policy(fp.template("careful", TOOLS))
    assert plain.digest() != policy.digest()


def test_large_inputs_are_cheap():
    import time
    start = time.perf_counter()
    for _ in range(200):
        fp._one_condition_holds({"arg": "command", "op": "prefix_in_pipe", "values": fp.SAFE_SHELL_PREFIXES}, {"command": "ls | " * 800})
    assert time.perf_counter() - start < 2.0
