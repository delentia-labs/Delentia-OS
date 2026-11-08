"""
Round 101 (UX audit): "can I use this yet?" answered in plain checks, for the first screen a new person sees.

Two layers on purpose. `gather()` does the short, bounded reads (is the local model server up and does it have the chosen model, is a key present, can anyone approve, has anything been run).
`evaluate()` is a pure function of those facts, so every state a person can meet is a test and none needs a running model. Nothing here changes a setting and no secret is read into the answer:
a key is reported as present or absent only.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
import json
from typing import Any, Dict, List, Optional

PROBE_TIMEOUT_S = 1.5


def _ollama_models(url: str) -> Optional[List[str]]:
    """The model names a local Ollama lists, or None when it can not be reached (a bounded read; never raises)."""
    from rct_control_plane import local_net
    if not local_net.quick_connect_ok(url):
        return None
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=PROBE_TIMEOUT_S) as response:      # noqa: S310 - loopback or the owner's configured address
            body = json.loads(response.read(2_000_000))
        return sorted({str(m.get("name", "")) for m in body.get("models", []) if isinstance(m, dict) and m.get("name")})
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _ollama_installed() -> bool:
    """Is the Ollama program on this computer at all (so 'not running' and 'not installed' can be told apart)? A bounded look at the PATH and the usual install folders; never starts anything."""
    import shutil
    if shutil.which("ollama"):
        return True
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Programs", "Ollama", "ollama.exe"))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(os.path.join(base, "Ollama", "ollama.exe"))
    candidates += ["/usr/local/bin/ollama", "/usr/bin/ollama", "/opt/homebrew/bin/ollama", "/Applications/Ollama.app"]
    return any(os.path.exists(c) for c in candidates)


def gather(persistence: Any) -> Dict[str, Any]:
    from rct_control_plane import model_config, model_setup
    from rct_control_plane.approvals import trusted_approver_keys
    selection = model_config.resolve_model_selection()
    facts: Dict[str, Any] = {"provider": selection.provider, "model": selection.model, "ollama_models": None, "key_present": None,
                             "chosen": not (selection.provider_source == "builtin" and selection.model_source == "builtin")}
    if selection.provider == "ollama":
        from rct_control_plane.llm_provider import DEFAULT_OLLAMA_URL
        facts["ollama_models"] = _ollama_models(os.getenv("DELENTIA_OLLAMA_URL") or DEFAULT_OLLAMA_URL)
        if facts["ollama_models"] is None:
            facts["ollama_installed"] = _ollama_installed()
    else:
        view = model_setup.current_view()
        facts["key_present"] = bool(view.get("credential_present") or (selection.provider == "openrouter" and view.get("openrouter_key_present")))
        facts["needs_key"] = bool(view.get("credential_env"))
    try:
        keys = len(trusted_approver_keys())
    except Exception:                                           # noqa: BLE001 - an unreadable approvers file means nobody can approve: reported as zero
        keys = 0
    devices = 0
    try:
        from rct_control_plane.passkeys import PasskeyStore
        devices = len(PasskeyStore(persistence).active())
    except Exception:                                           # noqa: BLE001 - no table yet is zero devices
        devices = 0
    facts["approver_keys"], facts["approver_devices"] = keys, devices
    try:
        with persistence._connect() as conn:
            facts["episodes"] = int(conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_episode_start'").fetchone()[0])
    except Exception:                                           # noqa: BLE001
        facts["episodes"] = 0
    return facts


def _model_state(facts: Dict[str, Any]) -> Dict[str, Any]:
    provider, model = str(facts.get("provider")), str(facts.get("model"))
    if provider == "ollama":
        installed = facts.get("ollama_models")
        if installed is None:
            # nothing answers: either the program is not on this computer at all, or it is installed and not started
            state = "server_down" if facts.get("ollama_installed", True) else "not_installed"
            return {"state": state, "ok": False, "provider": provider, "model": model, "chosen": bool(facts.get("chosen", True))}
        have = model in installed or f"{model}:latest" in installed
        return {"state": "ready" if have else "model_missing", "ok": have, "provider": provider, "model": model, "installed": installed[:12]}
    if facts.get("needs_key") and not facts.get("key_present"):
        return {"state": "no_key", "ok": False, "provider": provider, "model": model}
    return {"state": "configured", "ok": True, "provider": provider, "model": model}


def evaluate(facts: Dict[str, Any]) -> Dict[str, Any]:
    model = _model_state(facts)
    approvers = int(facts.get("approver_keys") or 0) + int(facts.get("approver_devices") or 0)
    episodes = int(facts.get("episodes") or 0)
    checks = [
        {"id": "model", "essential": True, **model},
        {"id": "approver", "essential": True, "ok": approvers > 0, "state": "ready" if approvers > 0 else "nobody",
         "keys": int(facts.get("approver_keys") or 0), "devices": int(facts.get("approver_devices") or 0)},
        {"id": "first_request", "essential": False, "ok": episodes > 0, "state": "done" if episodes > 0 else "not_yet", "episodes": episodes},
    ]
    return {"ready": all(c["ok"] for c in checks if c["essential"]), "all_done": all(c["ok"] for c in checks), "checks": checks}


def report(persistence: Any) -> Dict[str, Any]:
    return evaluate(gather(persistence))
