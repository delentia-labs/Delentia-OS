"""
Round 84, T12 policy versioning: every saved version of the owner's policy is kept next to the file, hash-chained; a decision's digest leads back to the exact text; two versions are compared rule by rule;
a loosening is named; an edit made outside the program or inside the history is seen.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest
from click.testing import CliRunner

from rct_control_plane import fdia_policy
from rct_control_plane import fdia_policy_history as fh


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")


def make(rule_action="REQUIRE_HUMAN_SIGNATURE", signatures=1, denied=("secrets/*", ".env"), extra_rule=False, threshold=0.5):
    rules = [{"rule_id": "R-READ", "intent_patterns": ["read_repo_file"], "action_type": "ALLOW", "assigned_A": 1},
             {"rule_id": "R-WRITE", "intent_patterns": ["write_repo_file"], "action_type": rule_action, "required_signatures": signatures, "denied_paths": list(denied)}]
    if extra_rule:
        rules.append({"rule_id": "R-SEARCH", "intent_patterns": ["search_repo_files"], "action_type": "ALLOW", "assigned_A": 1})
    policy, errors = fdia_policy.validate_policy({"version": "1.0.0", "policy_id": "owner", "default_fallback_A": 0, "custom_safety_threshold": threshold, "rules": rules,
                                                   "blocked_action_patterns": ["rm -rf"], "require_human_dual_signoff": [], "roles": {"default_role": "developer", "principals": {}}, "jury_by_risk": {}})
    assert policy is not None, errors
    return policy


def test_each_save_is_recorded_in_order_and_an_unchanged_save_adds_nothing():
    first, second = make(), make(extra_rule=True)
    fdia_policy.save_policy(first, actor="alice", reason="first")
    fdia_policy.save_policy(first, actor="alice", reason="again, unchanged")
    fdia_policy.save_policy(second, actor="alice", reason="allow search")
    rows = fh.history()
    assert [r["seq"] for r in rows] == [1, 2] and rows[0]["digest"] == first.digest() and rows[1]["digest"] == second.digest()
    assert rows[1]["actor"] == "alice" and rows[1]["reason"] == "allow search"
    check = fh.verify()
    assert check["ok"] and check["rows"] == 2 and check["in_sync"] is True and check["head"]


def test_a_digest_from_an_audit_row_leads_back_to_the_exact_policy_text():
    old, new = make(), make(extra_rule=True)
    fdia_policy.save_policy(old)
    fdia_policy.save_policy(new)
    found = fh.policy_for_digest(old.digest())
    assert found["seq"] == 1 and found["policy"] == old.to_dict()
    assert fh.policy_for_digest("0" * 64) is None


def test_the_diff_names_added_removed_and_changed_rules_and_changed_settings():
    before, after = make().to_dict(), make(signatures=2, extra_rule=True, threshold=0.7).to_dict()
    d = fh.diff(before, after)
    assert d["added_rules"] == ["R-SEARCH"] and d["removed_rules"] == []
    assert d["changed_rules"][0]["rule_id"] == "R-WRITE" and d["changed_rules"][0]["fields"] == ["required_signatures"]
    assert d["changed_settings"]["custom_safety_threshold"] == {"before": 0.5, "after": 0.7} and not d["same"]
    assert fh.diff(before, json.loads(json.dumps(before)))["same"]


def test_loosening_changes_are_named_and_tightening_ones_are_not():
    base = make(signatures=2).to_dict()
    assert fh.loosened(base, make(signatures=1).to_dict()) == ["rule R-WRITE asks for fewer signatures"]
    assert any("now ALLOWs" in x for x in fh.loosened(base, make(rule_action="ALLOW", signatures=1).to_dict()))
    assert any("denies fewer paths" in x for x in fh.loosened(base, make(signatures=2, denied=(".env",)).to_dict()))
    assert any("threshold is lower" in x for x in fh.loosened(base, make(signatures=2, threshold=0.2).to_dict()))
    assert fh.loosened(base, make(signatures=3, extra_rule=True, threshold=0.9).to_dict()) == []
    removed = make().to_dict()
    removed["rules"] = removed["rules"][:1]
    assert fh.loosened(make().to_dict(), removed) == ["rule R-WRITE was removed"]


def test_editing_the_history_or_the_file_outside_the_program_is_seen(tmp_path):
    fdia_policy.save_policy(make())
    fdia_policy.save_policy(make(extra_rule=True))
    assert fh.verify()["ok"]
    path = fh.history_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[0])
    forged["policy"]["rules"][1]["action_type"] = "ALLOW"              # someone rewrites what version 1 said
    path.write_text("\n".join([json.dumps(forged, sort_keys=True, ensure_ascii=False)] + lines[1:]) + "\n", encoding="utf-8")
    broken = fh.verify()
    assert not broken["ok"] and broken["broken_at"] == 1
    path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")      # the first line removed
    assert not fh.verify()["ok"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")          # restored
    assert fh.verify()["ok"] and fh.verify()["in_sync"] is True
    live = json.loads(fdia_policy.policy_path().read_text(encoding="utf-8"))
    live["rules"][1]["action_type"] = "ALLOW"                           # the policy file is edited by hand, without Delentia
    fdia_policy.policy_path().write_text(json.dumps(live), encoding="utf-8")
    assert fh.verify()["ok"] and fh.verify()["in_sync"] is False, "the chain is fine but the file in use is not the newest recorded version"


def test_a_proposal_from_an_older_version_saves_nothing():
    fdia_policy.save_policy(make())
    fdia_policy.save_policy(make(extra_rule=True))
    proposal = fh.proposal_from(1)
    assert proposal == make().to_dict() and fh.proposal_from(9) is None
    assert fh.verify()["rows"] == 2 and fdia_policy.load_policy().digest() == make(extra_rule=True).digest(), "reading an older version changed nothing"


def test_the_command_line_shows_history_diff_and_explains_a_digest():
    from rct_control_plane.cli import cli
    old, new = make(signatures=2), make(signatures=1, extra_rule=True)
    fdia_policy.save_policy(old, actor="owner", reason="start")
    fdia_policy.save_policy(new, actor="owner", reason="relax")
    run = CliRunner()
    out = run.invoke(cli, ["fdia", "history"])
    assert out.exit_code == 0 and "#1" in out.output and "#2" in out.output and "relax" in out.output and "intact" in out.output
    out = run.invoke(cli, ["fdia", "diff", "1", "2"])
    assert out.exit_code == 0 and "R-SEARCH" in out.output and "looser: rule R-WRITE asks for fewer signatures" in out.output
    out = run.invoke(cli, ["fdia", "explain", old.digest()[:12]])
    assert out.exit_code == 0 and "version #1" in out.output and "R-WRITE" in out.output
    assert run.invoke(cli, ["fdia", "explain", "deadbeef"]).exit_code == 1
    fdia_policy.policy_path().write_text(json.dumps(old.to_dict()), encoding="utf-8")        # edited outside the program: the history command says so and exits 1
    assert run.invoke(cli, ["fdia", "history"]).exit_code == 1
