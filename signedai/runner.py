"""
SignedAI jury runner (Round 53).

Layer 8 of the architecture document says a board of models votes and the verdict is stamped. Until now
`signedai` only did the arithmetic of a vote (`SignedAIRegistry.calculate_consensus`, the API's `/consensus`):
nothing asked a model anything. This module runs the jury:

  1. every signer of the tier gets the same question about the same proposal, independently;
  2. each reply is parsed into agree / disagree / abstain (a reply that cannot be parsed, a timeout or an
     error is an ABSTAIN, never an agree);
  3. the registry decides with the counts it already uses (required votes AND ratio);
  4. the verdict is a canonical record with a SHA-256 digest, optionally signed with an Ed25519 key.

Rules that keep it honest:
  * Abstentions never raise the ratio: `required_votes` is an absolute count of agrees, so a tier cannot pass
    because the dissenters failed to answer.
  * A jury is only a jury if the voters are different models. If fewer than `min_distinct_models` distinct
    endpoints answered, `independent` is False and consensus is NOT reached (a single model voting six times
    is one opinion). `allow_shared_model=True` opts out and is recorded in the verdict.
  * Tier 8 keeps the chairman VETO: the first signer, when the tier has one and it voted disagree, blocks the
    verdict whatever the others said. A chairman's agree cannot force a pass over a disagreeing jury.
  * Signers are plain async callables, `signer(system_prompt, prompt) -> str`; this package keeps its stated
    independence from `rct_control_plane`. The control plane adapts its providers (`signedai_jury.py`).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from signedai.core.registry import HexaCoreRegistry, HexaCoreRole, SignedAIRegistry, SignedAITier

Signer = Callable[[str, str], Awaitable[str]]

SYSTEM_PROMPT = (
    "You are one independent member of a review jury. Judge ONLY the proposal you are given, against the "
    "question. Do not assume the other members agree. Reply with a single JSON object and nothing else: "
    '{"vote": "agree" | "disagree", "reason": "<one or two sentences>"}.'
)
MAX_REASON_CHARS = 400
VOTES = ("agree", "disagree", "abstain")


@dataclass
class SignerEndpoint:
    """One voter: who it is (for the independence check) and how to ask it."""
    ask: Signer
    model: str                       # the endpoint's model id; two roles with the same id are one opinion
    label: str = ""


@dataclass
class SignerVote:
    role: str
    model: str
    vote: str                        # agree | disagree | abstain
    reason: str = ""
    elapsed_ms: float = 0.0
    problem: str = ""                # why it abstained (timeout, error class, unparseable)


@dataclass
class JuryVerdict:
    tier: str
    question: str
    proposal_sha256: str
    votes: List[SignerVote]
    votes_for: int
    votes_against: int
    abstained: int
    consensus_reached: bool
    confidence: float
    distinct_models: int
    independent: bool
    required_votes: int
    consensus_threshold: float
    chairman_vetoed: bool
    allow_shared_model: bool
    reasons_not_reached: List[str] = field(default_factory=list)
    digest: str = ""
    signature: str = ""
    public_key: str = ""

    def record(self) -> Dict[str, Any]:
        """The canonical, signed-over part (no digest/signature fields)."""
        return {
            "tier": self.tier, "question": self.question, "proposal_sha256": self.proposal_sha256,
            "votes": [{"role": v.role, "model": v.model, "vote": v.vote, "reason": v.reason, "problem": v.problem}
                      for v in self.votes],
            "votes_for": self.votes_for, "votes_against": self.votes_against, "abstained": self.abstained,
            "consensus_reached": self.consensus_reached, "confidence": round(self.confidence, 6),
            "distinct_models": self.distinct_models, "independent": self.independent,
            "required_votes": self.required_votes, "consensus_threshold": round(self.consensus_threshold, 6),
            "chairman_vetoed": self.chairman_vetoed, "allow_shared_model": self.allow_shared_model,
            "reasons_not_reached": self.reasons_not_reached,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.record()
        data["digest"] = self.digest
        data["signature"] = self.signature
        data["public_key"] = self.public_key
        return data


def canonical(record: Dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_vote(reply: str) -> SignerVote:
    """JSON first (what we asked for), then a bare leading word; anything else is an abstain, never an agree."""
    text = (reply or "").strip()
    if not text:
        return SignerVote("", "", "abstain", problem="empty reply")
    candidates: List[str] = [text]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start:end + 1])
    for raw in candidates:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict):
            vote = str(data.get("vote", "")).strip().lower()
            reason = str(data.get("reason", ""))[:MAX_REASON_CHARS]
            if vote in ("agree", "disagree"):
                return SignerVote("", "", vote, reason)
            return SignerVote("", "", "abstain", reason, problem="vote field missing or not agree/disagree")
    word = re.match(r"\W*(agree|disagree)\b", text, flags=re.I)
    if word:
        return SignerVote("", "", word.group(1).lower(), text[:MAX_REASON_CHARS])
    return SignerVote("", "", "abstain", problem="reply is not a vote")


def build_prompt(question: str, proposal: str) -> str:
    return f"QUESTION:\n{question}\n\nPROPOSAL:\n{proposal}\n\nDoes the proposal answer the question correctly and safely?"


class JuryRunner:
    def __init__(self, endpoints: Dict[HexaCoreRole, SignerEndpoint], timeout_s: float = 60.0,
                 min_distinct_models: int = 2, allow_shared_model: bool = False):
        self.endpoints = endpoints
        self.timeout_s = timeout_s
        self.min_distinct_models = min_distinct_models
        self.allow_shared_model = allow_shared_model

    async def _one(self, role: HexaCoreRole, endpoint: Optional[SignerEndpoint], prompt: str) -> SignerVote:
        if endpoint is None:
            return SignerVote(role.value, "", "abstain", problem="no endpoint configured for this role")
        started = time.perf_counter()
        try:
            reply = await asyncio.wait_for(endpoint.ask(SYSTEM_PROMPT, prompt), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return SignerVote(role.value, endpoint.model, "abstain", problem="timeout",
                              elapsed_ms=(time.perf_counter() - started) * 1000)
        except Exception as error:                                   # a failing voter must not sink the jury
            return SignerVote(role.value, endpoint.model, "abstain", problem=type(error).__name__,
                              elapsed_ms=(time.perf_counter() - started) * 1000)
        parsed = parse_vote(reply)
        parsed.role, parsed.model = role.value, endpoint.model
        parsed.elapsed_ms = (time.perf_counter() - started) * 1000
        return parsed

    async def run(self, tier: SignedAITier, question: str, proposal: str,
                  signing_key: Optional[Any] = None) -> JuryVerdict:
        config = SignedAIRegistry.get_tier(tier)
        prompt = build_prompt(question, proposal)
        # Independent: every signer is asked at the same time and sees nothing of the others.
        votes = await asyncio.gather(*(self._one(role, self.endpoints.get(role), prompt) for role in config.signers))
        agree = sum(1 for v in votes if v.vote == "agree")
        disagree = sum(1 for v in votes if v.vote == "disagree")
        abstained = sum(1 for v in votes if v.vote == "abstain")
        answered_models = {v.model for v in votes if v.vote != "abstain" and v.model}
        independent = len(answered_models) >= min(self.min_distinct_models, len(config.signers))
        reasons: List[str] = []

        chairman_vetoed = bool(config.chairman_veto and votes and votes[0].vote == "disagree")
        outcome = SignedAIRegistry.calculate_consensus(tier, agree, disagree)
        confidence = outcome.confidence                              # the real agreement, whatever the veto does
        reached = outcome.consensus_reached and not chairman_vetoed
        if not reached:
            if chairman_vetoed:
                reasons.append("the chairman voted against")
            if agree < config.required_votes:
                reasons.append(f"{agree} agree, {config.required_votes} needed")
            if confidence < config.consensus_threshold:
                reasons.append(f"agreement {confidence:.2f} is below the {config.consensus_threshold:.2f} threshold")
        if reached and not independent and not self.allow_shared_model and len(config.signers) > 1:
            reached = False
            reasons.append(f"only {len(answered_models)} distinct model(s) answered; a jury needs "
                           f"{self.min_distinct_models} (or allow_shared_model)")
        if abstained and not reached:
            reasons.append(f"{abstained} signer(s) abstained")

        verdict = JuryVerdict(
            tier=tier.value, question=question, proposal_sha256=hashlib.sha256(proposal.encode("utf-8")).hexdigest(),
            votes=list(votes), votes_for=agree, votes_against=disagree, abstained=abstained,
            consensus_reached=reached, confidence=confidence, distinct_models=len(answered_models),
            independent=independent, required_votes=config.required_votes, consensus_threshold=config.consensus_threshold,
            chairman_vetoed=chairman_vetoed, allow_shared_model=self.allow_shared_model, reasons_not_reached=reasons,
        )
        body = canonical(verdict.record())
        verdict.digest = hashlib.sha256(body).hexdigest()
        if signing_key is not None:
            from cryptography.hazmat.primitives import serialization
            verdict.signature = signing_key.sign(body).hex()
            verdict.public_key = signing_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        return verdict


def verify_verdict(data: Dict[str, Any], expected_public_key: Optional[str] = None) -> Dict[str, Any]:
    """Re-check a verdict dictionary: digest matches the record, the vote counts match the votes, the
    outcome follows the tier's rules, and (when signed) the signature verifies. Returns {ok, problems}."""
    problems: List[str] = []
    record = {k: v for k, v in data.items() if k not in ("digest", "signature", "public_key")}
    body = canonical(record)
    if hashlib.sha256(body).hexdigest() != data.get("digest"):
        problems.append("digest does not match the record")
    votes = data.get("votes") or []
    counts = {name: sum(1 for v in votes if v.get("vote") == name) for name in VOTES}
    if (counts["agree"], counts["disagree"], counts["abstain"]) != (
            data.get("votes_for"), data.get("votes_against"), data.get("abstained")):
        problems.append("vote counts do not match the votes")
    try:
        config = SignedAIRegistry.get_tier(SignedAITier(data.get("tier")))
        if data.get("consensus_reached") and counts["agree"] < config.required_votes:
            problems.append("consensus claimed with fewer agrees than the tier requires")
    except ValueError:
        problems.append("unknown tier")
    if data.get("signature"):
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub = data.get("public_key", "")
            if expected_public_key and pub != expected_public_key:
                problems.append("signed by a different key than expected")
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(data["signature"]), body)
        except (InvalidSignature, ValueError):
            problems.append("signature does not verify")
    elif expected_public_key:
        problems.append("unsigned, but a key was expected")
    return {"ok": not problems, "problems": problems, "signed": bool(data.get("signature"))}


def role_models() -> Dict[str, str]:
    """The registry's declared model per role (informational: which ids the roster asks for)."""
    return {role.value: HexaCoreRegistry.get_model_id(role) for role in HexaCoreRole}
