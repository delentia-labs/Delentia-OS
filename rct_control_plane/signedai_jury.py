"""
Real SignedAI jury over the control plane's model providers (Round 53).

`signedai.runner.JuryRunner` asks signers; this module turns a small JSON file into signers:

  {"roles": {
     "supreme_architect": {"provider": "openai-compat", "model": "gpt-x", "base_url": "https://...",
                           "kind": "cross_border", "credential_env": "MY_KEY_VAR"},
     "regional_thai":     {"provider": "openai-compat", "model": "typhoon-v2", "base_url": "https://api.example.th/v1",
                           "kind": "in_region", "region": "TH", "operator": "Example TH"},
     "humanizer":         {"provider": "ollama", "model": "qwen2.5:7b"}}}

A key is NEVER in the file: `credential_env` names the environment variable. Every signer goes through the
same wrappers as the agent's own model: the sovereignty policy (a jury member in a region the policy forbids
is not called, it abstains) and the provider circuit breaker (a dead member stops being retried).
Roles without an entry abstain ("no endpoint configured"), they are never silently given another model's vote.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from signedai.core.registry import HexaCoreRole, SignedAITier
from signedai.runner import JuryRunner, JuryVerdict, SignerEndpoint

from rct_control_plane.llm_provider import LLMProvider, OllamaProvider, OpenAICompatibleProvider, OpenRouterProvider

MAX_TOKENS = 400
CONFIG_ENV = "DELENTIA_JURY_CONFIG"


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "jury.json"


def provider_from_entry(entry: Dict[str, Any]) -> LLMProvider:
    kind = str(entry.get("provider", "")).strip().lower()
    model = str(entry.get("model", "")).strip()
    if not model:
        raise ValueError("a jury entry needs a model")
    if "api_key" in entry or "key" in entry or "token" in entry:
        raise ValueError("keys do not belong in the jury file: use credential_env to name an environment variable")
    if kind == "openai-compat":
        if not entry.get("base_url"):
            raise ValueError("openai-compat needs base_url")
        return OpenAICompatibleProvider(
            base_url=str(entry["base_url"]), model=model, credential_env=entry.get("credential_env"),
            kind=str(entry.get("kind", "cross_border")), region=str(entry.get("region", "")),
            operator=str(entry.get("operator", "")))
    if kind == "openrouter":
        return OpenRouterProvider(model=model)
    if kind == "ollama":
        return OllamaProvider(model=model)
    raise ValueError(f"unknown provider {kind!r} (openai-compat, openrouter, ollama)")


def endpoint_for(provider: LLMProvider, persistence: Any = None, namespace: str = "jury") -> SignerEndpoint:
    from rct_control_plane import provider_breaker, residency
    guarded = provider_breaker.wrap(residency.guard_provider(provider, persistence, namespace))

    async def ask(system_prompt: str, prompt: str) -> str:
        return await guarded.complete(prompt, system_prompt=system_prompt, temperature=0.0, max_tokens=MAX_TOKENS, json_mode=True)

    return SignerEndpoint(ask=ask, model=f"{type(provider).__name__}:{getattr(provider, 'model', '')}")


def endpoints_from_config(config: Dict[str, Any], persistence: Any = None) -> Dict[HexaCoreRole, SignerEndpoint]:
    endpoints: Dict[HexaCoreRole, SignerEndpoint] = {}
    for role_name, entry in (config.get("roles") or {}).items():
        try:
            role = HexaCoreRole(role_name)
        except ValueError:
            raise ValueError(f"unknown role {role_name!r}; roles: {', '.join(r.value for r in HexaCoreRole)}") from None
        endpoints[role] = endpoint_for(provider_from_entry(entry), persistence)
    return endpoints


def load_config(path: Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("the jury file must be a JSON object")
    return data


async def run_jury(config: Dict[str, Any], tier: str, question: str, proposal: str, signing_key: Optional[Any] = None,
                   timeout_s: float = 60.0, allow_shared_model: bool = False, persistence: Any = None) -> JuryVerdict:
    runner = JuryRunner(endpoints_from_config(config, persistence), timeout_s=timeout_s, allow_shared_model=allow_shared_model)
    return await runner.run(SignedAITier(tier), question, proposal, signing_key=signing_key)
