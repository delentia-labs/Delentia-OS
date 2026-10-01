"""
Round 53: the SignedAI jury runner with in-process signers. The rules under test are the ones that make a jury
honest: abstentions never raise the ratio, one model voting six times is not a consensus, a dead or slow member
abstains, the chairman decides tier 8, and a signed verdict cannot be edited.
"""
import asyncio
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signedai.core.registry import SignedAIRegistry, SignedAITier
from signedai.runner import JuryRunner, SignerEndpoint, parse_vote, verify_verdict

AGREE = json.dumps({"vote": "agree", "reason": "fine"})
DISAGREE = json.dumps({"vote": "disagree", "reason": "unsafe"})


def signer(reply, model, delay=0.0, error=None):
    async def ask(system_prompt, prompt):
        assert "independent member" in system_prompt and "PROPOSAL:" in prompt
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return reply
    return SignerEndpoint(ask=ask, model=model)


def jury(tier, replies, **kwargs):
    """replies: one reply (or SignerEndpoint) per signer of the tier, each from its own model."""
    config = SignedAIRegistry.get_tier(tier)
    endpoints = {}
    for i, (role, reply) in enumerate(zip(config.signers, replies, strict=False)):
        endpoints[role] = reply if isinstance(reply, SignerEndpoint) else signer(reply, f"model-{i}")
    return JuryRunner(endpoints, **kwargs)


def run(runner, tier, key=None):
    return asyncio.run(runner.run(tier, "Is the plan safe?", "drop the staging table", signing_key=key))


# ------------------------------------------------------------------ parsing

@pytest.mark.parametrize("reply,vote", [
    (AGREE, "agree"), (DISAGREE, "disagree"),
    ('Sure: {"vote": "agree", "reason": "ok"} thanks', "agree"),
    ("agree - looks right", "agree"), ("Disagree. It deletes data.", "disagree"),
    ('{"vote": "AGREE"}', "agree"),
])
def test_parse_vote_reads_what_was_asked_for(reply, vote):
    assert parse_vote(reply).vote == vote


@pytest.mark.parametrize("reply", [
    "", "   ", "I think so", "yes", "not sure, but probably agree", "{broken", '{"vote": "maybe"}', '{"verdict": "agree"}', "[1, 2]",
    "I do not agree", "can't say if I agree",
])
def test_anything_that_is_not_a_clear_vote_is_an_abstain_never_an_agree(reply):
    assert parse_vote(reply).vote == "abstain"


# ------------------------------------------------------------------ consensus

def test_unanimous_independent_jury_reaches_consensus():
    verdict = run(jury(SignedAITier.TIER_4, [AGREE] * 4), SignedAITier.TIER_4)
    assert verdict.consensus_reached and verdict.votes_for == 4 and verdict.independent and verdict.distinct_models == 4
    assert verdict.confidence == 1.0 and not verdict.reasons_not_reached


def test_three_of_four_passes_tier_4_two_of_four_does_not():
    assert run(jury(SignedAITier.TIER_4, [AGREE, AGREE, AGREE, DISAGREE]), SignedAITier.TIER_4).consensus_reached
    two = run(jury(SignedAITier.TIER_4, [AGREE, AGREE, DISAGREE, DISAGREE]), SignedAITier.TIER_4)
    assert not two.consensus_reached and "2 agree, 3 needed" in two.reasons_not_reached[0]


def test_abstentions_cannot_raise_the_ratio_into_a_pass():
    # 3 agree, 0 disagree, 3 abstain in tier 6 (4 agrees required): ratio over votes cast is 100%, but it fails.
    verdict = run(jury(SignedAITier.TIER_6, [AGREE, AGREE, AGREE, "no idea", "", "{"]), SignedAITier.TIER_6)
    assert verdict.abstained == 3 and verdict.confidence == 1.0 and not verdict.consensus_reached
    assert any("abstained" in r for r in verdict.reasons_not_reached)


def test_a_member_that_raises_or_times_out_abstains_and_the_rest_still_vote():
    runner = jury(SignedAITier.TIER_4, [
        AGREE, AGREE, AGREE, signer(AGREE, "slow", delay=2.0)], timeout_s=0.2)
    verdict = run(runner, SignedAITier.TIER_4)
    slow = [v for v in verdict.votes if v.model == "slow"][0]
    assert slow.vote == "abstain" and slow.problem == "timeout" and verdict.consensus_reached
    broken = run(jury(SignedAITier.TIER_4, [AGREE, AGREE, AGREE, signer("", "dead", error=ConnectionError("down"))]), SignedAITier.TIER_4)
    assert [v for v in broken.votes if v.model == "dead"][0].problem == "ConnectionError"


def test_a_role_with_no_endpoint_abstains_it_is_not_given_another_models_vote():
    config = SignedAIRegistry.get_tier(SignedAITier.TIER_4)
    endpoints = {config.signers[0]: signer(AGREE, "only-one")}
    verdict = run(JuryRunner(endpoints), SignedAITier.TIER_4)
    assert verdict.votes_for == 1 and verdict.abstained == 3 and not verdict.consensus_reached
    assert verdict.votes[1].problem == "no endpoint configured for this role"


# ------------------------------------------------------------------ independence

def test_one_model_voting_for_every_seat_is_not_a_consensus():
    config = SignedAIRegistry.get_tier(SignedAITier.TIER_6)
    one = signer(AGREE, "the-same-model")
    verdict = run(JuryRunner({role: one for role in config.signers}), SignedAITier.TIER_6)
    assert verdict.votes_for == 6 and verdict.distinct_models == 1
    assert not verdict.independent and not verdict.consensus_reached
    assert "distinct model" in verdict.reasons_not_reached[0]


def test_allow_shared_model_opts_out_and_says_so_in_the_record():
    config = SignedAIRegistry.get_tier(SignedAITier.TIER_4)
    one = signer(AGREE, "the-same-model")
    verdict = run(JuryRunner({role: one for role in config.signers}, allow_shared_model=True), SignedAITier.TIER_4)
    assert verdict.consensus_reached and verdict.allow_shared_model and verdict.record()["allow_shared_model"] is True


def test_tier_s_is_one_signer_by_design_and_is_not_blocked_by_independence():
    config = SignedAIRegistry.get_tier(SignedAITier.TIER_S)
    verdict = run(JuryRunner({config.signers[0]: signer(AGREE, "m")}), SignedAITier.TIER_S)
    assert verdict.consensus_reached and len(verdict.votes) == 1


def test_the_signers_are_asked_at_the_same_time_and_see_only_the_question():
    seen = []

    async def ask(system_prompt, prompt):
        seen.append(prompt)
        await asyncio.sleep(0.3)
        return AGREE

    config = SignedAIRegistry.get_tier(SignedAITier.TIER_4)
    runner = JuryRunner({role: SignerEndpoint(ask=ask, model=f"m{i}") for i, role in enumerate(config.signers)})
    import time
    started = time.perf_counter()
    run(runner, SignedAITier.TIER_4)
    assert time.perf_counter() - started < 0.9                       # four 0.3 s members, not 1.2 s in a row
    assert len(set(seen)) == 1 and "agree" not in seen[0].lower().split("proposal:")[1]


# ------------------------------------------------------------------ chairman

def test_tier_8_chairman_can_veto_a_unanimous_rest():
    tier = SignedAITier.TIER_8
    config = SignedAIRegistry.get_tier(tier)
    assert config.chairman_veto
    against = run(jury(tier, [DISAGREE] + [AGREE] * (len(config.signers) - 1)), tier)
    assert against.chairman_vetoed and not against.consensus_reached
    assert against.reasons_not_reached[0] == "the chairman voted against"


def test_a_chairman_agree_cannot_force_a_pass_over_a_disagreeing_jury():
    tier = SignedAITier.TIER_8
    config = SignedAIRegistry.get_tier(tier)
    verdict = run(jury(tier, [AGREE] + [DISAGREE] * (len(config.signers) - 1)), tier)
    assert not verdict.chairman_vetoed and not verdict.consensus_reached and verdict.votes_for == 1


def test_tier_8_with_a_silent_chairman_is_decided_by_the_counts():
    tier = SignedAITier.TIER_8
    config = SignedAIRegistry.get_tier(tier)
    verdict = run(jury(tier, ["no idea"] + [AGREE] * (len(config.signers) - 1)), tier)
    assert not verdict.chairman_vetoed and verdict.abstained == 1


# ------------------------------------------------------------------ the verdict record

def test_unsigned_verdict_verifies_by_digest_and_detects_edits():
    verdict = run(jury(SignedAITier.TIER_4, [AGREE] * 4), SignedAITier.TIER_4).to_dict()
    assert verify_verdict(verdict) == {"ok": True, "problems": [], "signed": False}
    tampered = json.loads(json.dumps(verdict))
    tampered["votes"][0]["vote"] = "disagree"
    result = verify_verdict(tampered)
    assert not result["ok"] and "digest does not match the record" in result["problems"]


def test_signed_verdict_verifies_and_every_kind_of_edit_is_caught():
    key = Ed25519PrivateKey.generate()
    verdict = run(jury(SignedAITier.TIER_4, [AGREE, AGREE, DISAGREE, DISAGREE]), SignedAITier.TIER_4, key).to_dict()
    assert verify_verdict(verdict, verdict["public_key"])["ok"]
    flipped = dict(verdict, consensus_reached=True)
    assert not verify_verdict(flipped)["ok"]
    # an attacker who recomputes the digest still cannot re-sign, and the tier rule check still sees the lie
    import hashlib
    from signedai.runner import canonical
    forged = {k: v for k, v in flipped.items() if k not in ("digest", "signature", "public_key")}
    forged_full = dict(forged, digest=hashlib.sha256(canonical(forged)).hexdigest(), signature=verdict["signature"], public_key=verdict["public_key"])
    problems = verify_verdict(forged_full)["problems"]
    assert "signature does not verify" in problems and "consensus claimed with fewer agrees than the tier requires" in problems
    other = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    assert "signed by a different key than expected" in verify_verdict(verdict, other)["problems"]


def test_a_key_was_expected_but_the_verdict_is_unsigned():
    verdict = run(jury(SignedAITier.TIER_4, [AGREE] * 4), SignedAITier.TIER_4).to_dict()
    assert "unsigned, but a key was expected" in verify_verdict(verdict, "ab" * 32)["problems"]


def test_the_proposal_is_bound_by_hash_not_stored():
    verdict = run(jury(SignedAITier.TIER_4, [AGREE] * 4), SignedAITier.TIER_4)
    assert len(verdict.proposal_sha256) == 64 and "drop the staging table" not in json.dumps(verdict.to_dict())


def test_reasons_are_capped_so_a_member_cannot_flood_the_record():
    reply = json.dumps({"vote": "agree", "reason": "x" * 100_000})
    assert len(parse_vote(reply).reason) == 400
