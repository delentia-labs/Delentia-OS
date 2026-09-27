"""
User-selectable LLM model (Round 48): Hermes-style bring-your-own-model.

Before this module, llm_provider.get_default_provider() let a user pick a
*provider* (DELENTIA_LLM_PROVIDER=ollama|openrouter) but the *model* was
hardcoded in each provider class. This module resolves both, from (highest
precedence first):

  1. explicit arguments to resolve_model_selection()
  2. env vars DELENTIA_LLM_PROVIDER / DELENTIA_LLM_MODEL
  3. the named profile's entry in the model config file
  4. the config file's top-level default
  5. built-in defaults (BUILTIN_DEFAULT_MODELS)

The config file lives OUTSIDE the repo - ~/.delentia/model.json, or the
path in DELENTIA_MODEL_CONFIG - and never holds API keys (keys stay in
env vars only). save_model_selection() refuses any key-looking field.

Listing: list_openrouter_models() reads OpenRouter's public model catalog
(no API key needed); list_ollama_models() reads the local Ollama tags.
Both take an injectable httpx client so tests never touch the network.

Model choice changes how capable the agent is, not how safe it is: the
FDIA gate and approval rules are enforced in code (governed_autonomous_loop.py),
independent of whichever model is selected here.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

SUPPORTED_PROVIDERS = ("ollama", "openrouter")

BUILTIN_DEFAULT_MODELS: Dict[str, str] = {
    "ollama": "qwen2.5:7b",
    "openrouter": "anthropic/claude-sonnet-5",
}
BUILTIN_DEFAULT_PROVIDER = "ollama"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# The agent loop's decide_next_action() uses JSON mode (response_format),
# so that is the capability a model needs today to drive the loop at all.
AGENT_REQUIRED_PARAMETER = "response_format"

_FORBIDDEN_CONFIG_KEY_PARTS = ("key", "token", "secret", "password")


class ModelConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str
    # Where each value came from - shown by `delentia model show` so a
    # user can tell why a given model is active.
    provider_source: str
    model_source: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ModelInfo:
    id: str
    context_length: Optional[int] = None
    prompt_price_per_mtok: Optional[float] = None
    completion_price_per_mtok: Optional[float] = None
    supports_json_mode: bool = False
    supports_tools: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def config_path() -> Path:
    override = os.getenv("DELENTIA_MODEL_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".delentia" / "model.json"


def load_model_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelConfigError(f"cannot read model config {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelConfigError(f"model config {p} must be a JSON object")
    return data


def _validate_provider(provider: str) -> str:
    p = provider.lower().strip()
    if p not in SUPPORTED_PROVIDERS:
        raise ModelConfigError(f"unsupported provider '{provider}' (supported: {', '.join(SUPPORTED_PROVIDERS)})")
    return p


def resolve_model_selection(
    profile: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> ModelSelection:
    cfg = config if config is not None else load_model_config()
    profile_cfg: Dict[str, Any] = {}
    if profile:
        profile_cfg = (cfg.get("profiles") or {}).get(profile) or {}

    candidates_provider = [
        (provider, "argument"),
        (os.getenv("DELENTIA_LLM_PROVIDER"), "env:DELENTIA_LLM_PROVIDER"),
        (profile_cfg.get("provider"), f"config:profiles.{profile}"),
        (cfg.get("provider"), "config"),
        (BUILTIN_DEFAULT_PROVIDER, "builtin"),
    ]
    chosen_provider, provider_source = next((v, s) for v, s in candidates_provider if v)
    chosen_provider = _validate_provider(chosen_provider)

    # A configured model only applies if it was configured for the same
    # provider - an OpenRouter model id is meaningless to Ollama.
    def _same_provider(scope: Dict[str, Any]) -> bool:
        scoped = scope.get("provider")
        return scoped is None or str(scoped).lower() == chosen_provider

    candidates_model = [
        (model, "argument"),
        (os.getenv("DELENTIA_LLM_MODEL"), "env:DELENTIA_LLM_MODEL"),
        (profile_cfg.get("model") if _same_provider(profile_cfg) else None, f"config:profiles.{profile}"),
        (cfg.get("model") if _same_provider(cfg) else None, "config"),
        (BUILTIN_DEFAULT_MODELS[chosen_provider], "builtin"),
    ]
    chosen_model, model_source = next((v, s) for v, s in candidates_model if v)
    return ModelSelection(chosen_provider, str(chosen_model), provider_source, model_source)


def save_model_selection(
    provider: str,
    model: str,
    profile: Optional[str] = None,
    path: Optional[Path] = None,
) -> Path:
    provider = _validate_provider(provider)
    if not model or not model.strip():
        raise ModelConfigError("model must be a non-empty string")
    p = path or config_path()
    cfg = load_model_config(p)
    if profile:
        cfg.setdefault("profiles", {})[profile] = {"provider": provider, "model": model.strip()}
    else:
        cfg["provider"] = provider
        cfg["model"] = model.strip()
    _assert_no_secrets(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


def _assert_no_secrets(obj: Any, trail: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(part in str(k).lower() for part in _FORBIDDEN_CONFIG_KEY_PARTS):
                raise ModelConfigError(
                    f"refusing to store '{trail}{k}' in the model config: API keys belong in env vars, not files"
                )
            _assert_no_secrets(v, f"{trail}{k}.")


def _price_per_mtok(value: Any) -> Optional[float]:
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def parse_openrouter_models(payload: Dict[str, Any]) -> List[ModelInfo]:
    models: List[ModelInfo] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        params = item.get("supported_parameters") or []
        pricing = item.get("pricing") or {}
        models.append(ModelInfo(
            id=str(item["id"]),
            context_length=item.get("context_length"),
            prompt_price_per_mtok=_price_per_mtok(pricing.get("prompt")),
            completion_price_per_mtok=_price_per_mtok(pricing.get("completion")),
            supports_json_mode=AGENT_REQUIRED_PARAMETER in params or "structured_outputs" in params,
            supports_tools="tools" in params,
        ))
    return models


def filter_models(models: List[ModelInfo], agent_capable_only: bool = True,
                  search: Optional[str] = None) -> List[ModelInfo]:
    out = models
    if agent_capable_only:
        out = [m for m in out if m.supports_json_mode]
    if search:
        needle = search.lower()
        out = [m for m in out if needle in m.id.lower()]
    return sorted(out, key=lambda m: m.id)


def list_openrouter_models(client: Optional[httpx.Client] = None, timeout: float = 20.0) -> List[ModelInfo]:
    own_client = client is None
    c = client or httpx.Client(timeout=timeout)
    try:
        resp = c.get(OPENROUTER_MODELS_URL)
        resp.raise_for_status()
        return parse_openrouter_models(resp.json())
    finally:
        if own_client:
            c.close()


def list_ollama_models(llm_url: Optional[str] = None, client: Optional[httpx.Client] = None,
                       timeout: float = 5.0) -> List[ModelInfo]:
    from rct_control_plane.llm_provider import DEFAULT_OLLAMA_URL
    url = (llm_url or os.getenv("DELENTIA_OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
    own_client = client is None
    c = client or httpx.Client(timeout=timeout)
    try:
        resp = c.get(f"{url}/api/tags")
        resp.raise_for_status()
        names = [m.get("name") for m in (resp.json().get("models") or []) if isinstance(m, dict)]
        # Ollama's JSON mode ("format": "json") works for every local model,
        # so all of them are nominally agent-capable; K.1.5 decides whether
        # one is actually good enough.
        return [ModelInfo(id=str(n), supports_json_mode=True) for n in names if n]
    finally:
        if own_client:
            c.close()


def profile_has_model_override(profile: Optional[str], config: Optional[Dict[str, Any]] = None) -> bool:
    """True when the config file names a provider/model for this profile.
    Callers use it to build a dedicated provider only when a profile
    really differs from the default, leaving every other loop on the
    default per-call resolution."""
    if not profile:
        return False
    try:
        cfg = config if config is not None else load_model_config()
    except ModelConfigError:
        return False
    entry = (cfg.get("profiles") or {}).get(profile) or {}
    return bool(entry.get("provider") or entry.get("model"))
