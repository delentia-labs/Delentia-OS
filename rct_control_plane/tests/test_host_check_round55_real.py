"""
Round 55: `delentia host-check`. Each check is exercised with the configuration that should make it pass and the one that should make it
fail, using real files (real Ed25519 keys, real token files, real config files), not mocks of the checks.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest
from click.testing import CliRunner

from rct_control_plane import approvals, audit_chain, host_check as hc
from rct_control_plane.cli import cli


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".delentia").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "data"))
    for var in list(os.environ):
        if var.startswith(("DELENTIA_", "TELEGRAM_", "DISCORD_", "SLACK_", "LINE_", "WHATSAPP_", "SIGNAL_", "BRAVE_")) and var != "DELENTIA_HOME":
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", str(tmp_path / "sov.json"))
    monkeypatch.setenv("DELENTIA_MCP_SERVERS", str(tmp_path / "mcp.json"))
    monkeypatch.setenv("DELENTIA_SEARCH_CONFIG", str(tmp_path / "search.json"))
    return tmp_path


def by_id(checks, check_id):
    return next(c for c in checks if c.id == check_id)


def status(check_id, public=True):
    return by_id(hc.run_checks(public=public), check_id).status


# ------------------------------------------------------------------ authentication

def test_no_token_fails_on_a_host_and_only_warns_locally():
    assert status("H01", public=True) == hc.FAIL
    assert status("H01", public=False) == hc.WARN


def test_a_short_shared_token_fails_and_a_long_one_passes(monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKEN", "short")
    assert status("H01") == hc.FAIL
    monkeypatch.setenv("DELENTIA_API_TOKEN", "x" * 32)
    assert status("H01") == hc.PASS and status("H02") == hc.WARN          # works, but roles are only labels


def test_per_person_tokens_pass_and_an_unusable_file_is_a_failure(clean, monkeypatch):
    from rct_control_plane import api_tokens
    api_tokens.create("alice")
    assert status("H01") == hc.PASS and status("H02") == hc.PASS
    (clean / "tokens.json").write_text("{broken", encoding="utf-8")
    api_tokens._cache.clear()
    assert status("H01") == hc.FAIL


# ------------------------------------------------------------------ approvers and keys

def test_no_approver_warns_and_a_private_key_in_the_approvers_file_fails(clean, monkeypatch):
    assert status("H03") == hc.WARN
    public = approvals.generate_approver_key(str(clean / "keys" / "a.pem"))
    (clean / "approvers.json").write_text(json.dumps([{"name": "a", "public_key_hex": public}]), encoding="utf-8")
    assert status("H03") == hc.PASS and status("H04") == hc.PASS
    (clean / "approvers.json").write_text(json.dumps([{"name": "a", "public_key_hex": public, "private_key": "-----BEGIN PRIVATE KEY-----"}]), encoding="utf-8")
    assert status("H04") == hc.FAIL


def test_the_audit_key_must_exist_load_and_live_outside_the_repository(clean, monkeypatch):
    assert status("H05") == hc.WARN
    key = clean / "keys" / "audit.pem"
    audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    audit_chain._signer_cache.clear()
    assert status("H05") == hc.PASS
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(clean / "missing.pem"))
    assert status("H05") == hc.FAIL
    inside = hc.Path(hc.__file__).resolve().parent.parent / "audit_test_key_do_not_commit.pem"
    try:
        audit_chain.generate_signing_key(str(inside)) if False else inside.write_bytes(key.read_bytes())
        monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(inside))
        assert status("H05") == hc.FAIL
    finally:
        if inside.exists():
            inside.unlink()


def test_notary_and_anchoring_are_warnings_until_configured(monkeypatch):
    assert status("H06") == hc.WARN and status("H07") == hc.WARN
    monkeypatch.setenv("DELENTIA_NOTARY_URL", "http://127.0.0.1:9")
    assert status("H06") == hc.PASS
    monkeypatch.setenv("DELENTIA_AUDIT_ANCHOR_URL", "https://witness.example")
    monkeypatch.setenv("DELENTIA_AUDIT_ANCHOR_KEY_ID", "delentia-os-1")
    assert status("H07") == hc.WARN                                    # no signing key: nothing could be anchored


def test_anchoring_passes_only_with_two_independent_kinds_of_witness(monkeypatch, tmp_path):
    key = tmp_path / "audit.pem"
    audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    http = {"type": "http", "name": "worker", "url": "https://witness.example", "key_id": "h1"}
    git = {"type": "git", "name": "ledger", "path": str(tmp_path / "ledger"), "key_id": "h1"}
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", json.dumps([http]))
    assert status("H07") == hc.WARN and "one party" in by_id(hc.run_checks(), "H07").detail
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", json.dumps([http, {**http, "name": "second"}]))
    assert status("H07") == hc.WARN and "one failure mode" in by_id(hc.run_checks(), "H07").detail
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", json.dumps([http, git]))
    assert status("H07") == hc.PASS
    monkeypatch.setenv("DELENTIA_AUDIT_WITNESSES", "not json")
    assert status("H07") == hc.FAIL


def test_probe_reports_a_dead_notary_as_a_failure(monkeypatch):
    monkeypatch.setenv("DELENTIA_NOTARY_URL", "http://127.0.0.1:9")
    checks = hc.run_checks(probe=True)
    assert by_id(checks, "H06").status == hc.FAIL and "fail closed" in by_id(checks, "H06").detail


# ------------------------------------------------------------------ channels

def test_a_channel_with_credentials_is_judged_by_its_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    assert status("H08-telegram") == hc.WARN                               # nobody can send
    monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", "*")
    assert status("H08-telegram") == hc.FAIL                               # everybody can
    monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", "123,456")
    assert status("H08-telegram") == hc.PASS


def test_a_webhook_channel_without_its_signature_secret_fails(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    monkeypatch.setenv("DELENTIA_WHATSAPP_ALLOWED_SENDERS", "66811111111")
    assert status("H08-whatsapp") == hc.FAIL
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "s")
    assert status("H08-whatsapp") == hc.PASS


def test_trusting_unverified_email_fails_on_a_host(monkeypatch):
    monkeypatch.setenv("DELENTIA_EMAIL_TRUST_UNVERIFIED", "1")
    assert status("H08-email-auth", public=True) == hc.FAIL and status("H08-email-auth", public=False) == hc.WARN


# ------------------------------------------------------------------ exposure, model, data

def test_cors_wildcard_and_open_private_fetch_are_flagged(monkeypatch):
    assert status("H09") == hc.PASS
    monkeypatch.setenv("DELENTIA_CORS_ORIGINS", "https://a.example,*")
    assert status("H09") == hc.FAIL
    monkeypatch.setenv("DELENTIA_CRAWL_ALLOW_PRIVATE", "1")
    assert status("H11") == hc.WARN


def test_a_paid_model_without_a_cap_warns_and_a_local_model_passes(monkeypatch):
    assert status("H13") == hc.PASS and status("H14") == hc.INFO
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", "qwen/qwen3-235b-a22b")
    assert status("H13") == hc.WARN and status("H14") == hc.WARN
    monkeypatch.setenv("DELENTIA_EPISODE_BUDGET_USD", "0.20")
    assert status("H13") == hc.PASS


def test_a_broken_owner_policy_is_a_failure_and_no_policy_a_warning(clean):
    assert status("H15") == hc.WARN
    (clean / "policy.json").write_text("{not json", encoding="utf-8")
    assert status("H15") == hc.FAIL


# ------------------------------------------------------------------ configuration files

def test_a_pasted_key_in_a_config_file_fails(clean, monkeypatch):
    assert status("H16") == hc.PASS
    (clean / "model.json").write_text(json.dumps({"provider": "openrouter", "api_key": "sk-or-v1-" + "ab12cd34" * 8}), encoding="utf-8")
    checks = hc.run_checks()
    assert by_id(checks, "H16").status == hc.FAIL and "sk-or-v1" not in by_id(checks, "H16").detail      # the report never repeats the secret


def test_mcp_and_search_configuration_problems_are_reported(clean, monkeypatch):
    (clean / "mcp.json").write_text(json.dumps({"servers": {"notes": {"command": "python", "token": "abc"}}}), encoding="utf-8")
    assert status("H17") == hc.FAIL
    (clean / "mcp.json").write_text(json.dumps({"servers": {"notes": {"command": "python"}, "remote": {"url": "https://m.example/mcp"}}}), encoding="utf-8")
    checks = hc.run_checks()
    assert by_id(checks, "H17").status == hc.WARN and "not pinned" in by_id(checks, "H17").detail and "no declared region" in by_id(checks, "H17").detail
    monkeypatch.setenv("DELENTIA_SEARCH_PROVIDER", "bing")
    assert status("H18") == hc.FAIL


def test_the_data_directory_must_be_writable():
    assert status("H19") == hc.PASS


# ------------------------------------------------------------------ the command

def test_one_broken_check_does_not_hide_the_rest(monkeypatch):
    monkeypatch.setattr(hc, "check_approvers", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    checks = hc.run_checks()
    assert any(c.id == "H03" and c.status == hc.FAIL and "boom" in c.detail for c in checks) and any(c.id == "H09" for c in checks)


def test_the_command_exits_one_on_a_failure_and_prints_the_fix():
    result = CliRunner().invoke(cli, ["host-check"])
    assert result.exit_code == 1 and "H01" in result.output and "-> set DELENTIA_API_TOKEN" in result.output


def test_a_fully_configured_host_passes_with_only_notes(clean, monkeypatch):
    from rct_control_plane import api_tokens
    api_tokens.create("alice")
    public = approvals.generate_approver_key(str(clean / "keys" / "a.pem"))
    (clean / "approvers.json").write_text(json.dumps([{"name": "a", "public_key_hex": public, "role": "Security_Admin"}]), encoding="utf-8")
    key = clean / "keys" / "audit.pem"
    audit_chain.generate_signing_key(str(key))
    audit_chain._signer_cache.clear()
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    monkeypatch.setenv("DELENTIA_NOTARY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("DELENTIA_AUDIT_ANCHOR_URL", "https://w.example")
    monkeypatch.setenv("DELENTIA_AUDIT_ANCHOR_KEY_ID", "delentia-os-1")
    (clean / "policy.json").write_text(json.dumps({"rules": [{"rule_id": "R", "intent_patterns": ["read_*"], "action_type": "ALLOW"}]}), encoding="utf-8")
    result = CliRunner().invoke(cli, ["host-check", "--json"])
    data = json.loads(result.output)
    assert result.exit_code == 0 and data["ready_for_a_public_host"] is True
    assert not [c for c in data["checks"] if c["status"] == "FAIL"]


def test_strict_turns_warnings_into_a_failing_exit(monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKEN", "x" * 32)
    assert CliRunner().invoke(cli, ["host-check"]).exit_code == 0
    assert CliRunner().invoke(cli, ["host-check", "--strict"]).exit_code == 1
