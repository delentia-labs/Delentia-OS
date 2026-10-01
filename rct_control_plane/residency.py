"""
Data residency for the agent runtime (Round 52).

The Regional Adapter (core/regional_adapter) decides which model fits a language and
region and, since Round 52, what a tenant's policy allows (core/regional_adapter/
sovereignty.py). This module is where that policy meets the runtime: every model call
the governed loop makes goes through ResidencyCheckedProvider, which

  1. works out where the call's endpoint processes data (hosting_for_provider),
  2. asks the policy whether this text may go there,
  3. blocks the call (the episode ends with stopped_reason "residency_blocked", and
     nothing was sent), or sends it with personal data replaced, or sends it as is,
  4. records the decision in the hash-chained audit trail: tenant, endpoint hosting,
     action, which kinds of personal data were found and how many, and a SHA-256 of
     the text. The personal data itself is never written to the audit trail.

So "the data did not leave the country" becomes something the audit chain can show,
call by call, rather than a statement in a README.

Where the policy comes from (first that exists):
  environment  DELENTIA_HOME_REGION (e.g. TH) turns enforcement on;
               DELENTIA_ALLOWED_REGIONS=TH,SG   DELENTIA_ALLOW_CROSS_BORDER=1
               DELENTIA_PII_POLICY=block|redact|allow   DELENTIA_LEGAL_BASIS=...
  file         ~/.delentia/sovereignty.json (DELENTIA_SOVEREIGNTY_CONFIG overrides the
               path); written by `delentia sovereignty set`
  neither      no enforcement: the runtime behaves as before and the Desk says that
               prompts may leave this machine when a cloud model is selected.

Limits, stated plainly: this guards the calls the governed loop makes through the
provider abstraction. Algorithms that call a model themselves (ALGO-09/11/12/32/33) talk
to the local Ollama, which is "local". The crawl tool and other network tools are not
model calls and are not covered here. A provider's own handling of data after it
arrives is a matter for the contract with that provider, not for this code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlsplit

from core.regional_adapter.sovereignty import (
    GLOBAL,
    KIND_CROSS_BORDER,
    KIND_IN_REGION,
    KIND_LOCAL,
    PII_ALLOW,
    PII_BLOCK,
    PII_REDACT,
    HostingProfile,
    ResidencyDecision,
    SovereigntyPolicy,
    evaluate_call,
    redact_text,
    validate_region,
)
from rct_control_plane.llm_provider import (
    LLMProvider,
    LLMUsage,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    ResidencyViolation,
)

HOME_REGION_ENV = "DELENTIA_HOME_REGION"
ALLOWED_REGIONS_ENV = "DELENTIA_ALLOWED_REGIONS"
ALLOW_CROSS_BORDER_ENV = "DELENTIA_ALLOW_CROSS_BORDER"
PII_POLICY_ENV = "DELENTIA_PII_POLICY"
LEGAL_BASIS_ENV = "DELENTIA_LEGAL_BASIS"
LLM_REGION_ENV = "DELENTIA_LLM_REGION"
CONFIG_ENV = "DELENTIA_SOVEREIGNTY_CONFIG"
_TRUE = ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Policy configuration
# ---------------------------------------------------------------------------

def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "sovereignty.json"


def _policy_from_env() -> Optional[SovereigntyPolicy]:
    home = (os.environ.get(HOME_REGION_ENV) or "").strip()
    if not home:
        return None
    allowed = [r for r in (os.environ.get(ALLOWED_REGIONS_ENV) or "").replace(" ", "").split(",") if r]
    return SovereigntyPolicy(
        home_region=validate_region(home), allowed_regions=[validate_region(r) for r in allowed] or [],
        allow_cross_border=(os.environ.get(ALLOW_CROSS_BORDER_ENV) or "").strip().lower() in _TRUE,
        pii_policy=(os.environ.get(PII_POLICY_ENV) or PII_BLOCK).strip().lower(),
        legal_basis=os.environ.get(LEGAL_BASIS_ENV) or "", tenant_id=os.environ.get("DELENTIA_TENANT_ID", "default"),
    )


def load_policy() -> Optional[SovereigntyPolicy]:
    """The active policy, or None when nothing is configured (no enforcement)."""
    from_env = _policy_from_env()
    if from_env is not None:
        return from_env
    path = config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SovereigntyPolicy.from_dict(data)
    except (OSError, ValueError, KeyError) as exc:
        # An unreadable policy file must not silently turn enforcement off.
        raise ValueError(f"cannot read the sovereignty policy {path}: {exc}") from exc


def save_policy(policy: SovereigntyPolicy, path: Optional[Path] = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(policy.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------------------------
# Where does a provider process data?
# ---------------------------------------------------------------------------

def _is_private_host(host: str) -> bool:
    if host in ("localhost", "::1", "[::1]") or host.endswith(".localhost"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        return a == 127 or a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)
    return False


def hosting_for_provider(provider: Any) -> HostingProfile:
    """Unknown providers are cross-border: a policy must never be satisfied by a
    provider nobody described."""
    seen = 0
    while hasattr(provider, "inner") and seen < 8:       # unwrap Metered / ResidencyChecked
        provider = provider.inner
        seen += 1
    if isinstance(provider, OllamaProvider):
        host = urlsplit(provider.llm_url).hostname or ""
        if _is_private_host(host):
            return HostingProfile(KIND_LOCAL, "LOCAL", "Ollama on this machine or network")
        declared = (os.environ.get(LLM_REGION_ENV) or "").strip()
        if declared:
            return HostingProfile(KIND_IN_REGION, validate_region(declared), f"Ollama at {host} (region declared by {LLM_REGION_ENV})")
        return HostingProfile(KIND_CROSS_BORDER, GLOBAL, f"Ollama at {host} (region not declared)")
    if isinstance(provider, OpenAICompatibleProvider):
        return HostingProfile(provider.kind, provider.region or GLOBAL, provider.operator or "OpenAI-compatible endpoint")
    if isinstance(provider, OpenRouterProvider):
        return HostingProfile(KIND_CROSS_BORDER, GLOBAL, "OpenRouter",
                              "routes to many providers; the processing country cannot be pinned")
    return HostingProfile(KIND_CROSS_BORDER, GLOBAL, type(provider).__name__, "no hosting description")


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

class ResidencyCheckedProvider(LLMProvider):
    """Wraps a provider; checks every call against the policy before it is made."""

    def __init__(self, inner: LLMProvider, policy: SovereigntyPolicy, persistence: Any = None, namespace: str = "") -> None:
        self._inner = inner
        self.policy = policy
        self._persistence = persistence
        self.namespace = namespace
        self.calls = 0
        self.blocked = 0
        self.redacted_calls = 0
        self.cross_border_calls = 0
        self.last_decision: Optional[ResidencyDecision] = None

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def model(self) -> str:
        return str(getattr(self._inner, "model", "?"))

    @property
    def last_usage(self) -> Optional[LLMUsage]:      # type: ignore[override]
        return self._inner.last_usage

    @last_usage.setter
    def last_usage(self, value: Optional[LLMUsage]) -> None:
        self._inner.last_usage = value

    @property
    def hosting(self) -> HostingProfile:
        return hosting_for_provider(self._inner)

    def summary(self) -> Dict[str, Any]:
        return {"policy": self.policy.to_dict(), "hosting": self.hosting.to_dict(), "calls": self.calls,
                "blocked": self.blocked, "redacted_calls": self.redacted_calls, "cross_border_calls": self.cross_border_calls}

    def _record(self, decision: ResidencyDecision, text: str) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.append_audit(
                entity_type="residency_decision", entity_id=f"{self.namespace}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}",
                action=decision.action, actor=self.namespace or "runtime",
                changes={**decision.to_dict(), "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "text_chars": len(text)},
            )
        except Exception:
            pass        # an audit problem must not turn a safe call into an unsafe one, nor the reverse

    def _check(self, prompt: str, system_prompt: Optional[str]) -> tuple:
        full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        decision = evaluate_call(self.policy, self.hosting, full)
        self.calls += 1
        self.cross_border_calls += 1 if decision.cross_border else 0
        self.last_decision = decision
        self._record(decision, full)
        if decision.action == "block":
            self.blocked += 1
            raise ResidencyViolation(decision.reason)
        if decision.action == "redact":
            self.redacted_calls += 1
            prompt = redact_text(prompt)[0]
            system_prompt = redact_text(system_prompt)[0] if system_prompt else system_prompt
        return prompt, system_prompt

    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                       max_tokens: int = 2048, json_mode: bool = False) -> str:
        prompt, system_prompt = self._check(prompt, system_prompt)
        return await self._inner.complete(prompt, system_prompt, temperature, max_tokens, json_mode)

    async def stream_complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7,
                              max_tokens: int = 2048) -> AsyncIterator[str]:
        prompt, system_prompt = self._check(prompt, system_prompt)
        async for chunk in self._inner.stream_complete(prompt, system_prompt, temperature, max_tokens):
            yield chunk


def guard_provider(provider: LLMProvider, persistence: Any = None, namespace: str = "",
                   policy: Optional[SovereigntyPolicy] = None) -> LLMProvider:
    """The provider the loop should use: wrapped when a policy is active, unchanged
    when none is (no enforcement configured)."""
    active = policy if policy is not None else load_policy()
    if active is None:
        return provider
    return ResidencyCheckedProvider(provider, active, persistence, namespace)


def describe(provider: Optional[LLMProvider] = None) -> Dict[str, Any]:
    """What the Desk and the CLI show: the policy (or its absence) and where the
    configured model would send data."""
    from rct_control_plane.llm_provider import get_default_provider
    policy = load_policy()
    try:
        provider = provider or get_default_provider()
        hosting = hosting_for_provider(provider)
        model = str(getattr(provider, "model", "?"))
    except Exception as exc:       # e.g. a broken model config
        hosting, model = HostingProfile(KIND_CROSS_BORDER, GLOBAL, "unknown", str(exc)), "?"
    out: Dict[str, Any] = {
        "enforced": policy is not None, "policy": policy.to_dict() if policy else None,
        "model": model, "hosting": hosting.to_dict(), "config_path": str(config_path()),
        "pii_policies": [PII_ALLOW, PII_REDACT, PII_BLOCK],
    }
    if policy is None:
        out["warning"] = ("No sovereignty policy is set, so nothing stops a prompt from leaving this machine when a cloud "
                          "model is selected. Set DELENTIA_HOME_REGION or run `delentia sovereignty set`.")
        out["would_be_allowed"] = None
    else:
        decision = evaluate_call(policy, hosting, "")
        out["would_be_allowed"] = decision.allowed
        out["reason"] = decision.reason
    return out


def recent_decisions(conn: Any, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, actor, action, changes, created_at FROM audit_trail WHERE entity_type = 'residency_decision' "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        try:
            changes = json.loads(row[3])
        except (TypeError, ValueError):
            changes = {}
        out.append({"id": row[0], "namespace": row[1], "action": row[2], "at": row[4], "reason": changes.get("reason"),
                    "hosting": changes.get("hosting"), "pii": changes.get("pii"), "cross_border": changes.get("cross_border"),
                    "text_chars": changes.get("text_chars")})
    return out
