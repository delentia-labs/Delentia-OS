"""
Round 53: a real jury. Every member is a separate HTTP server that speaks the OpenAI protocol (the way a
national model is plugged in), reached through the real provider, sovereignty guard and circuit breaker; the
verdict goes through the real CLI. Only the members' opinions are scripted.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
from contextlib import ExitStack

import pytest
from click.testing import CliRunner

from rct_control_plane import signedai_jury
from rct_control_plane.cli import cli
from scripted_model import ScriptedModel
from signedai.core.registry import SignedAIRegistry, SignedAITier

AGREE = json.dumps({"vote": "agree", "reason": "looks right"})
DISAGREE = json.dumps({"vote": "disagree", "reason": "it deletes data"})


def opinion(reply):
    return lambda req: reply


def jury_config(models, kinds=None, regions=None):
    roles = SignedAIRegistry.get_tier(SignedAITier.TIER_4).signers
    out = {}
    for i, (role, model) in enumerate(zip(roles, models, strict=False)):
        out[role.value] = {"provider": "openai-compat", "model": model.model_id, "base_url": model.base_url,
                           "kind": (kinds or {}).get(i, "local"), "region": (regions or {}).get(i, ""), "operator": f"member-{i}"}
    return {"roles": out}


@pytest.fixture
def members(monkeypatch):
    for var in ("DELENTIA_HOME_REGION", "DELENTIA_ALLOWED_REGIONS", "DELENTIA_ALLOW_CROSS_BORDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", os.path.join(os.environ.get("TEMP", "."), "no-such-policy.json"))
    with ExitStack() as stack:
        def make(*replies):
            return [stack.enter_context(ScriptedModel(opinion(r), model_id=f"member-{i}")) for i, r in enumerate(replies)]
        yield make


def test_four_real_servers_vote_and_the_verdict_is_signed(members):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from signedai.runner import verify_verdict
    servers = members(AGREE, AGREE, AGREE, DISAGREE)
    key = Ed25519PrivateKey.generate()
    verdict = asyncio.run(signedai_jury.run_jury(jury_config(servers), "tier_4", "Is it safe?", "rotate the log files", signing_key=key))
    assert verdict.consensus_reached and (verdict.votes_for, verdict.votes_against) == (3, 1) and verdict.independent
    assert all(s.calls == 1 for s in servers)                                   # each member asked once, independently
    assert verify_verdict(verdict.to_dict(), verdict.public_key)["ok"]
    assert "rotate the log files" in servers[0].requests[0].prompt


def test_a_dissenting_majority_blocks(members):
    servers = members(AGREE, DISAGREE, DISAGREE, DISAGREE)
    verdict = asyncio.run(signedai_jury.run_jury(jury_config(servers), "tier_4", "Is it safe?", "format the disk"))
    assert not verdict.consensus_reached and verdict.votes_for == 1


def test_a_member_that_is_down_abstains(members):
    servers = members(AGREE, AGREE, AGREE, AGREE)
    servers[3].fail_next = 1000
    verdict = asyncio.run(signedai_jury.run_jury(jury_config(servers), "tier_4", "Q?", "P", timeout_s=20))
    assert verdict.votes_for == 3 and verdict.abstained == 1 and verdict.consensus_reached
    assert verdict.votes[3].vote == "abstain" and verdict.votes[3].problem


def test_the_sovereignty_policy_stops_a_member_in_a_forbidden_region_from_being_asked(members, monkeypatch):
    servers = members(AGREE, AGREE, AGREE, AGREE)
    monkeypatch.setenv("DELENTIA_HOME_REGION", "TH")
    config = jury_config(servers, kinds={3: "cross_border"})                    # the fourth member is outside the allowed regions
    verdict = asyncio.run(signedai_jury.run_jury(config, "tier_4", "Q?", "P"))
    assert servers[3].calls == 0                                                # nothing was sent to it
    assert verdict.votes[3].vote == "abstain" and verdict.votes[3].problem == "ResidencyViolation"
    assert verdict.votes_for == 3 and verdict.consensus_reached                 # the other three are in the allowed set


def test_a_key_in_the_file_is_refused(members):
    config = jury_config(members(AGREE, AGREE, AGREE, AGREE))
    first = next(iter(config["roles"].values()))
    first["api_key"] = "sk-should-not-be-here"
    with pytest.raises(ValueError, match="credential_env"):
        signedai_jury.endpoints_from_config(config)


@pytest.mark.parametrize("entry,message", [
    ({"provider": "openai-compat", "model": "m"}, "base_url"),
    ({"provider": "carrier-pigeon", "model": "m"}, "unknown provider"),
    ({"provider": "ollama"}, "needs a model"),
])
def test_bad_entries_are_refused_with_a_reason(entry, message):
    with pytest.raises(ValueError, match=message):
        signedai_jury.provider_from_entry(entry)


def test_an_unknown_role_is_refused_and_lists_the_real_ones():
    with pytest.raises(ValueError, match="supreme_architect"):
        signedai_jury.endpoints_from_config({"roles": {"emperor": {"provider": "ollama", "model": "m"}}})


# ------------------------------------------------------------------ the CLI

def write_config(tmp_path, servers):
    path = tmp_path / "jury.json"
    path.write_text(json.dumps(jury_config(servers)), encoding="utf-8")
    return str(path)


def test_cli_run_prints_a_verdict_and_verify_accepts_it_and_rejects_an_edit(members, tmp_path):
    from rct_control_plane import audit_chain
    servers = members(AGREE, AGREE, AGREE, AGREE)
    key_path = tmp_path / "jury-key.pem"
    public_hex = audit_chain.generate_signing_key(str(key_path))
    out = tmp_path / "verdict.json"
    result = CliRunner().invoke(cli, ["jury", "run", "--config", write_config(tmp_path, servers), "--tier", "tier_4",
                                      "--question", "Is it safe?", "--proposal", "add an index", "--sign-key", str(key_path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8"))["public_key"] == public_hex
    ok = CliRunner().invoke(cli, ["jury", "verify", str(out), "--pubkey", public_hex])
    assert ok.exit_code == 0 and '"ok": true' in ok.output
    data = json.loads(out.read_text(encoding="utf-8"))
    data["votes"][0]["vote"] = "disagree"
    out.write_text(json.dumps(data), encoding="utf-8")
    bad = CliRunner().invoke(cli, ["jury", "verify", str(out), "--pubkey", public_hex])
    assert bad.exit_code == 1 and "digest does not match" in bad.output


def test_cli_exits_2_when_there_is_no_consensus_and_1_on_bad_input(members, tmp_path):
    servers = members(AGREE, DISAGREE, DISAGREE, DISAGREE)
    base = ["jury", "run", "--config", write_config(tmp_path, servers), "--tier", "tier_4", "--question", "Q?"]
    assert CliRunner().invoke(cli, base + ["--proposal", "format the disk"]).exit_code == 2
    assert CliRunner().invoke(cli, base).exit_code == 1                              # neither --proposal nor --proposal-file
    assert CliRunner().invoke(cli, base + ["--proposal", "a", "--proposal-file", write_config(tmp_path, servers)]).exit_code == 1
