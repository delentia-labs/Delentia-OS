"""
The logic behind the Desk's model-setup page (Round 52): choose a provider and model,
describe an OpenAI-compatible endpoint (country -> provider -> model, or "Other"), test it,
and save it. Kept out of desk_api.py so it can be tested without a web server.

Rules that hold here, and are tested:

* A credential is never written to disk. The model config stores only the NAME of the
  environment variable (model_config.validate_endpoint already refuses a pasted key). A key
  typed into the Desk is placed in THIS process's environment only (lost on restart) and is
  never echoed back, logged, or put in an error message. Only names that look like credentials
  (…_API_KEY, …_TOKEN, …_SECRET, …_KEY) and not DELENTIA_* may be set, so this cannot be used to
  change PATH, the approver list or any other setting.
* "Test connection" is a request to a URL the operator typed, so it follows the residency
  policy first: an endpoint the policy would not allow a prompt to reach is not contacted at
  all. Only http(s) is accepted, and link-local addresses (cloud metadata services) are refused.
* The test sends no prompt. It asks the endpoint which models it serves (GET <base>/models).
"""
from __future__ import annotations

import ipaddress
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx

from rct_control_plane import model_config
from rct_control_plane.model_config import ModelConfigError

KEY_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
KEY_ENV_SUFFIXES = ("_API_KEY", "_API_TOKEN", "_TOKEN", "_SECRET", "_KEY")
MAX_KEY_CHARS = 4096
PROBE_TIMEOUT_S = 10.0
MAX_MODELS_LISTED = 300


class SetupError(ValueError):
    pass


def check_key_env_name(name: str) -> str:
    name = (name or "").strip()
    if not KEY_ENV_NAME.match(name) or not name.endswith(KEY_ENV_SUFFIXES) or name.startswith("DELENTIA_"):
        raise SetupError("the key's environment variable must look like a credential name (for example TYPHOON_API_KEY) "
                         "and cannot start with DELENTIA_")
    return name


def set_session_key(env_name: str, value: str) -> str:
    """Puts `value` in this process's environment under `env_name`. Returns the (checked) name."""
    name = check_key_env_name(env_name)
    if not value or len(value) > MAX_KEY_CHARS or any(c in value for c in "\r\n\x00"):
        raise SetupError("the key is empty, too long, or contains a line break")
    os.environ[name] = value
    return name


def forget_session_key(env_name: str) -> None:
    os.environ.pop(check_key_env_name(env_name), None)


def check_probe_url(base_url: str) -> str:
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SetupError("the address must start with http:// or https://")
    host = parts.hostname.lower()
    if host in ("metadata.google.internal", "metadata"):
        raise SetupError("cloud metadata addresses are not valid model endpoints")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None                           # a hostname, not an IP literal
    if ip is not None and ip.is_link_local:
        raise SetupError("link-local addresses (169.254.x.x, fe80::) are not valid model endpoints")
    return base_url.strip().rstrip("/")


def policy_verdict(endpoint: Dict[str, str]) -> Dict[str, Any]:
    """Would the active sovereignty policy let a prompt reach an endpoint declared like this?"""
    from core.regional_adapter.sovereignty import HostingProfile, evaluate_call
    from rct_control_plane import residency
    policy = residency.load_policy()
    if policy is None:
        return {"enforced": False, "allowed": None,
                "reason": "No sovereignty policy is set, so nothing restricts where prompts go."}
    hosting = HostingProfile(endpoint["kind"], endpoint.get("region") or "XX", endpoint.get("operator", ""))
    decision = evaluate_call(policy, hosting, "")
    return {"enforced": True, "allowed": bool(decision.allowed), "reason": decision.reason}


def current_view() -> Dict[str, Any]:
    """What is selected now and what the page needs to draw: never a secret, only whether one is present."""
    selection = model_config.resolve_model_selection()
    cfg = model_config.load_model_config()
    endpoint: Optional[Dict[str, Any]] = None
    if selection.provider == "openai-compat":
        try:
            endpoint = dict(model_config.openai_compat_settings(cfg))
        except ModelConfigError:
            endpoint = None
    elif isinstance(cfg.get("openai_compat"), dict):
        endpoint = dict(cfg["openai_compat"])          # configured earlier, not the active provider
    key_env = (endpoint or {}).get("credential_env") or ("OPENROUTER_API_KEY" if selection.provider == "openrouter" else "")
    return {
        "selection": selection.to_dict(),
        "config_path": str(model_config.config_path()),
        "endpoint": endpoint,
        "credential_env": key_env or None,
        "credential_present": bool(key_env and os.environ.get(key_env)),
        "openrouter_key_present": bool(os.environ.get("OPENROUTER_API_KEY")),
        "profiles": {name: dict(p) for name, p in (cfg.get("profiles") or {}).items() if isinstance(p, dict)},
        "endpoint_verdict": policy_verdict(endpoint) if endpoint else None,
    }


async def probe_endpoint(endpoint: Dict[str, Any], api_key: Optional[str] = None,
                         client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """GET <base_url>/models with the key (if any). No prompt is sent. The policy is checked
    first; a blocked endpoint is not contacted."""
    try:
        clean = model_config.validate_endpoint({**endpoint, "credential_env": endpoint.get("credential_env") or ""})
        clean["base_url"] = check_probe_url(clean["base_url"])
    except (ModelConfigError, SetupError) as exc:
        return {"contacted": False, "reachable": False, "error": str(exc), "models": [], "verdict": None}
    verdict = policy_verdict(clean)
    if verdict["enforced"] and not verdict["allowed"]:
        return {"contacted": False, "reachable": False, "models": [], "verdict": verdict,
                "error": f"Not contacted: the data-location policy would not let a prompt reach this endpoint. {verdict['reason']}"}
    key = api_key or (os.environ.get(clean["credential_env"]) if clean.get("credential_env") else None)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    own = client is None
    http = client or httpx.AsyncClient(timeout=PROBE_TIMEOUT_S, follow_redirects=False)
    try:
        response = await http.get(f"{clean['base_url']}/models", headers=headers)
    except httpx.TimeoutException:
        return {"contacted": True, "reachable": False, "models": [], "verdict": verdict, "error": "timed out after "
                f"{PROBE_TIMEOUT_S:.0f} s"}
    except httpx.HTTPError as exc:
        # Only the kind of failure, never the exception text: it can carry the URL and headers.
        return {"contacted": True, "reachable": False, "models": [], "verdict": verdict,
                "error": f"could not connect ({type(exc).__name__})"}
    finally:
        if own:
            await http.aclose()
    out: Dict[str, Any] = {"contacted": True, "status": response.status_code, "verdict": verdict,
                           "key_sent": bool(key), "models": [], "reachable": response.status_code < 400, "error": None}
    if response.status_code in (401, 403):
        out["error"] = "the endpoint answered but refused the key (HTTP %d)" % response.status_code if key else \
            "the endpoint requires a key (HTTP %d)" % response.status_code
        out["reachable"] = True
        return out
    if response.status_code >= 400:
        out["error"] = f"the endpoint answered HTTP {response.status_code}"
        return out
    try:
        body = response.json()
        items = body.get("data") if isinstance(body, dict) else body
        ids = [str(m.get("id")) for m in (items or []) if isinstance(m, dict) and m.get("id")]
        out["models"] = sorted(set(ids))[:MAX_MODELS_LISTED]
    except ValueError:
        out["error"] = "the endpoint answered, but not with an OpenAI-style model list"
    return out


def apply_selection(provider: str, model: str, endpoint: Optional[Dict[str, Any]] = None, profile: Optional[str] = None,
                    api_key: Optional[str] = None) -> Dict[str, Any]:
    """Saves the choice (never a key) and, when a key was typed, keeps it in memory for this process."""
    provider = (provider or "").strip().lower()
    clean_endpoint: Optional[Dict[str, str]] = None
    key_env: Optional[str] = None
    if provider == "openai-compat":
        if endpoint is None:
            raise SetupError("an OpenAI-compatible provider needs its endpoint (address and where it processes data)")
        clean_endpoint = model_config.validate_endpoint(endpoint)
        key_env = clean_endpoint.get("credential_env")
    elif provider == "openrouter":
        key_env = "OPENROUTER_API_KEY"
    if api_key:
        if not key_env:
            raise SetupError("a key was given but no environment variable name to keep it under")
        set_session_key(key_env, api_key)
    path = model_config.save_model_selection(provider, model, profile=(profile or None), endpoint=clean_endpoint)
    view = current_view()
    view["saved"] = str(path)
    view["key_kept_in_memory"] = bool(api_key)
    view["key_note"] = ("The key is held in this server's memory only and is gone when it restarts. To keep it, set the "
                        f"environment variable {key_env} where the server starts.") if api_key else None
    return view
