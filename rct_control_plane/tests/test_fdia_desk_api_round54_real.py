"""
Round 54: the Desk endpoints and the CLI for the owner's policy, through the real FastAPI app and the real
click commands. The state they read and write is the policy file, the audit trail and the approvers file.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from rct_control_plane import approvals, fdia_policy as fp
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_JURY_CONFIG", str(tmp_path / "jury.json"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    with TestClient(create_app()) as c:
        yield c


def state(client):
    response = client.get("/v1/desk/fdia")
    assert response.status_code == 200
    return response.json()


def test_state_without_a_policy_says_so_and_lists_every_tool_with_its_built_in_gate(client):
    data = state(client)
    assert data["policy"] is None and data["exists"] is False and data["digest"] is None
    assert data["built_in"]["threshold"] == 0.5
    names = {t["name"]: t["built_in"] for t in data["tools"]}
    assert len(names) >= 30
    assert names["delentia_write_repo_file"] == "always a signature"
    assert names["delentia_run_sandboxed_command"] == "FDIA gate"
    assert names["delentia_recall"] == "open"
    assert data["jury"]["configured"] is False
    assert "supported" not in json.dumps(data["limits"]) and "tier_4" in data["limits"]["jury_tiers"]


@pytest.mark.parametrize("name", ["balanced", "strict"])
def test_templates_validate_and_classify_every_real_tool(client, name):
    template = client.get(f"/v1/desk/fdia/template/{name}").json()["policy"]
    checked = client.post("/v1/desk/fdia/validate", json={"policy": template}).json()
    assert checked["valid"] and checked["errors"] == [] and len(checked["digest"]) == 64
    assert client.get("/v1/desk/fdia/template/nonsense").status_code == 404


def test_validate_returns_every_problem_without_saving(client):
    bad = {"rules": [{"rule_id": "!", "intent_patterns": []}, {"rule_id": "B", "intent_patterns": ["x"], "assigned_A": 5}]}
    result = client.post("/v1/desk/fdia/validate", json={"policy": bad}).json()
    assert not result["valid"] and len(result["errors"]) >= 3
    assert state(client)["exists"] is False


def test_save_writes_the_file_audits_the_change_and_the_state_reflects_it(client, tmp_path):
    template = client.get("/v1/desk/fdia/template/balanced").json()["policy"]
    saved = client.put("/v1/desk/fdia/policy", json={"policy": template})
    assert saved.status_code == 200 and saved.json()["rules"] == len(template["rules"])
    assert (tmp_path / "policy.json").exists()
    data = state(client)
    assert data["exists"] and data["digest"] == saved.json()["digest"] and data["error"] == ""
    again = client.put("/v1/desk/fdia/policy", json={"policy": {**template, "custom_safety_threshold": 0.7}})
    from rct_control_plane.mcp_server import _kernel
    with _kernel._persistence._connect() as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type='fdia_policy' ORDER BY id DESC LIMIT 2")]
    assert rows[0]["digest_before"] == saved.json()["digest"] and rows[0]["digest_after"] == again.json()["digest"]


def test_an_invalid_policy_is_refused_and_the_old_file_stays(client, tmp_path):
    template = client.get("/v1/desk/fdia/template/balanced").json()["policy"]
    first = client.put("/v1/desk/fdia/policy", json={"policy": template}).json()["digest"]
    refused = client.put("/v1/desk/fdia/policy", json={"policy": {"rules": [{"rule_id": "x y", "intent_patterns": ["a"]}]}})
    assert refused.status_code == 400 and "invalid" in refused.json()["detail"]
    assert state(client)["digest"] == first


def test_disable_archives_the_file_instead_of_deleting_it(client, tmp_path):
    template = client.get("/v1/desk/fdia/template/balanced").json()["policy"]
    client.put("/v1/desk/fdia/policy", json={"policy": template})
    archived = client.post("/v1/desk/fdia/policy/disable").json()["archived_as"]
    assert os.path.exists(archived) and not (tmp_path / "policy.json").exists()
    assert state(client)["policy"] is None
    assert client.post("/v1/desk/fdia/policy/disable").status_code == 404


def test_a_broken_file_is_reported_not_hidden(client, tmp_path):
    (tmp_path / "policy.json").write_text("{nope", encoding="utf-8")
    data = state(client)
    assert data["exists"] and data["policy"] is None and "cannot read" in data["error"]


def test_evaluate_a_draft_without_saving_it(client):
    draft = {"rules": [{"rule_id": "R-W", "intent_patterns": ["write_*"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
                        "human_approver_role": ["Chief_Architect"], "denied_paths": [".env"]}], "default_fallback_A": 1}
    waits = client.post("/v1/desk/fdia/evaluate", json={"policy": draft, "tool_name": "delentia_write_repo_file",
                                                        "tool_args": {"relative_path": "notes.md"}, "D": 0.9, "I": 1.0}).json()
    assert waits["outcome"] == "waits for signature" and waits["approver_roles"] == ["Chief_Architect"] and waits["F"] == 0.9
    blocked = client.post("/v1/desk/fdia/evaluate", json={"policy": draft, "tool_name": "delentia_write_repo_file",
                                                          "tool_args": {"relative_path": ".env"}, "approved": True}).json()
    assert blocked["outcome"] == "blocked" and blocked["A"] == 0.0
    weak = client.post("/v1/desk/fdia/evaluate", json={"policy": draft, "tool_name": "delentia_write_repo_file",
                                                       "tool_args": {"relative_path": "a.md"}, "D": 0.3, "I": 1.0}).json()
    assert weak["outcome"] == "blocked (F below threshold)"
    assert state(client)["exists"] is False


def test_evaluate_with_no_policy_describes_the_built_in_gate(client):
    result = client.post("/v1/desk/fdia/evaluate", json={"tool_name": "delentia_recall", "D": 0.8, "I": 1.0}).json()
    assert result["policy"] is None and result["F"] == 0.8 and "no policy" in result["outcome"]


@pytest.mark.parametrize("payload,fragment", [
    ({}, "tool_name"), ({"tool_name": "x", "tool_args": "no"}, "tool_args"),
    ({"tool_name": "x", "D": "high"}, "numbers"), ({"tool_name": "x", "policy": {"rules": "z"}}, "invalid"),
])
def test_evaluate_rejects_bad_input(client, payload, fragment):
    response = client.post("/v1/desk/fdia/evaluate", json=payload)
    assert response.status_code == 400 and fragment in response.json()["detail"]


def test_approvers_are_listed_with_roles_but_never_with_full_keys(client, tmp_path):
    path = tmp_path / "keys" / "a.pem"
    public = approvals.generate_approver_key(str(path))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "alice", "public_key_hex": public, "role": "Security_Admin"}]), encoding="utf-8")
    approvers = state(client)["approvers"]
    assert approvers == [{"name": "alice", "role": "Security_Admin", "key_prefix": public[:12]}]
    assert public not in json.dumps(state(client))


def test_a_foreign_web_page_cannot_change_the_policy(client):
    template = client.get("/v1/desk/fdia/template/balanced").json()["policy"]
    response = client.put("/v1/desk/fdia/policy", json={"policy": template}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 401
    assert state(client)["exists"] is False


# ------------------------------------------------------------------ the CLI

def test_cli_template_validate_show_and_test(tmp_path, monkeypatch):
    target = tmp_path / "policy.json"
    monkeypatch.setenv(fp.POLICY_ENV, str(target))
    runner = CliRunner()
    assert runner.invoke(cli, ["fdia", "show"]).output.startswith("No policy")
    made = runner.invoke(cli, ["fdia", "template", "balanced", "--out", str(target)])
    assert made.exit_code == 0 and target.exists()
    again = runner.invoke(cli, ["fdia", "template", "balanced", "--out", str(target)])
    assert again.exit_code == 1 and "refusing to overwrite" in again.output
    assert "valid:" in runner.invoke(cli, ["fdia", "validate", str(target)]).output
    shown = runner.invoke(cli, ["fdia", "show"])
    assert shown.exit_code == 0 and "R-WRITE-FILES" in shown.output
    waits = json.loads(runner.invoke(cli, ["fdia", "test", "delentia_write_repo_file", "--args", '{"relative_path": "n.md"}']).output)
    assert waits["outcome"] == "waits for signature" and waits["rule_id"] == "R-WRITE-FILES"
    blocked = json.loads(runner.invoke(cli, ["fdia", "test", "delentia_write_repo_file", "--args", '{"relative_path": ".env"}', "--approved"]).output)
    assert blocked["outcome"] == "blocked"
    low = json.loads(runner.invoke(cli, ["fdia", "test", "delentia_run_sandboxed_command", "--args", '{"command": "ls"}', "--D", "0.2"]).output)
    assert low["outcome"] == "waits for signature" or "below" in low["outcome"]


def test_cli_validate_lists_the_problems(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rules": [{"rule_id": "x y", "intent_patterns": []}]}), encoding="utf-8")
    result = CliRunner().invoke(cli, ["fdia", "validate", str(bad)])
    assert result.exit_code == 1 and "rule_id" in result.output and "pattern" in result.output


def test_cli_keygen_records_the_role_in_the_approvers_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    result = CliRunner().invoke(cli, ["approvals", "keygen", "--out", str(tmp_path / "k" / "sec.pem"), "--trust", "sec", "--role", "Security_Admin"])
    assert result.exit_code == 0
    entries = json.loads((tmp_path / "approvers.json").read_text(encoding="utf-8"))
    assert entries[0]["role"] == "Security_Admin" and approvals.trusted_approver_roles()[entries[0]["public_key_hex"]] == "Security_Admin"
