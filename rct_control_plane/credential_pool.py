"""
Round 72: several keys for one provider (Hermes: credential pool), with the rules this runtime keeps for keys.

An agent that is always on will, sooner or later, meet a key that is out of credit, rate limited or revoked. With one key that is an outage; with a pool the
next key takes the call. The pool is a LIST OF ENVIRONMENT VARIABLE NAMES, never of keys:

    ~/.delentia/credential_pool.json  (or the file named by DELENTIA_CREDENTIAL_POOL)
    {"openrouter": {"strategy": "fill_first", "keys": ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_BACKUP"]}}

    shorthand, no file:  DELENTIA_CREDENTIAL_POOL_OPENROUTER="OPENROUTER_API_KEY,OPENROUTER_API_KEY_BACKUP"

Rules that make it safe to have more keys:
  * a value is never stored: only names, and a name must look like a secret's name (it contains KEY, TOKEN, SECRET, ...), which is exactly what the shell sandbox
    strips from the environment of a command the agent runs - a key added to the pool is hidden from the agent's shell by the same rule as the first one;
  * an entry that does not look like a variable name (a pasted key, for instance) is refused and its text is NOT repeated in the error;
  * a key is never written to a log, an audit row, a status page or an exception: every record names the key by its LABEL (the variable's name);
  * the pool changes WHICH key of the same provider signs a call; it can never change the provider, so the sovereignty policy, the budget and the circuit breaker
    that were judged for the provider apply unchanged;
  * what a refusal means: 401/403 = the key is dead for this process (disabled until restart); 402 = out of credit (a day); 429 = rate limited (the provider's
    Retry-After, else DELENTIA_CREDENTIAL_COOLDOWN seconds, default 300). A 5xx or a network error says nothing about a key and moves nothing;
  * every move (cooldown, disabled, all keys unavailable) is written to the audit trail as `credential_pool`, with the label and the status and nothing else.

The pool is the owner's own keys. It is not a way around a provider's limits on one account's use; using it that way is a matter between the owner and the provider.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

POOL_FILE_ENV = "DELENTIA_CREDENTIAL_POOL"
SHORTHAND_PREFIX = "DELENTIA_CREDENTIAL_POOL_"
COOLDOWN_ENV = "DELENTIA_CREDENTIAL_COOLDOWN"
STRATEGIES = ("fill_first", "round_robin", "least_used")
PROVIDERS = ("openrouter", "openai-compat")
ROTATE_STATUSES = (401, 402, 403, 429)
DEFAULT_RATE_LIMIT_COOLDOWN = 300.0
OUT_OF_CREDIT_COOLDOWN = 24 * 3600.0
MAX_KEYS_PER_PROVIDER = 8
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_LOOKS_SECRET = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|SIGNING|PRIVATE|APPROVER)", re.IGNORECASE)      # same words as sandbox._SECRET_ENV_NAME


class PoolConfigError(ValueError):
    pass


class NoCredentialAvailable(RuntimeError):
    """Every key of the pool is cooling down, disabled or missing. The message names labels and seconds, never a key."""


def pool_path() -> Path:
    override = os.environ.get(POOL_FILE_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "credential_pool.json"


def valid_name(entry: Any) -> bool:
    return isinstance(entry, str) and bool(_NAME.match(entry)) and bool(_LOOKS_SECRET.search(entry))


def _clean(provider: str, spec: Any) -> Dict[str, Any]:
    if provider not in PROVIDERS:
        raise PoolConfigError(f"unknown provider {provider!r}; use one of {', '.join(PROVIDERS)}")
    if isinstance(spec, list):
        spec = {"keys": spec}
    if not isinstance(spec, dict):
        raise PoolConfigError(f"the entry for {provider} must be an object with a 'keys' list")
    keys = spec.get("keys")
    if not isinstance(keys, list) or not keys:
        raise PoolConfigError(f"{provider}: 'keys' must be a non-empty list of environment variable names")
    if len(keys) > MAX_KEYS_PER_PROVIDER:
        raise PoolConfigError(f"{provider}: at most {MAX_KEYS_PER_PROVIDER} keys")
    out: List[str] = []
    for index, entry in enumerate(keys, 1):
        if not valid_name(entry):                       # the entry itself is NOT echoed: it may be a key somebody pasted by mistake
            raise PoolConfigError(f"{provider}: entry #{index} is not an environment variable name (UPPER_CASE with KEY, TOKEN, SECRET... in it); the pool holds names, never keys")
        if entry in out:
            raise PoolConfigError(f"{provider}: entry #{index} repeats an earlier name")
        out.append(entry)
    strategy = str(spec.get("strategy") or "fill_first")
    if strategy not in STRATEGIES:
        raise PoolConfigError(f"{provider}: strategy must be one of {', '.join(STRATEGIES)}")
    return {"strategy": strategy, "keys": out}


def load_config() -> Dict[str, Dict[str, Any]]:
    """{provider: {"strategy", "keys"}}. A file that exists but cannot be used raises PoolConfigError (it is not silently ignored: a half-applied pool is worse than none)."""
    config: Dict[str, Dict[str, Any]] = {}
    path = pool_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PoolConfigError(f"the credential pool file cannot be read: {type(exc).__name__}") from exc
        if not isinstance(raw, dict):
            raise PoolConfigError("the credential pool file must hold a JSON object")
        for provider, spec in raw.items():
            if str(provider).endswith(".cleared"):          # `delentia credentials clear` moves an entry aside under this name; it is kept (Zero-Delete) and not used
                continue
            config[str(provider)] = _clean(str(provider), spec)
    for provider in PROVIDERS:
        short = os.environ.get(SHORTHAND_PREFIX + provider.upper().replace("-", "_"))
        if short and short.strip():
            config[provider] = _clean(provider, {"keys": [p.strip() for p in short.split(",") if p.strip()]})
    return config


# ---- state (per process): which key is cooling down or dead ----------------------------------------------------------------------------------------------------
_lock = threading.RLock()
_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
_round_robin: Dict[str, int] = {}
_sink: Optional[Callable[[Dict[str, Any]], None]] = None
_events: List[Dict[str, Any]] = []


def reset() -> None:
    """Forget cooldowns, disabled keys and counters (a restart does the same; tests use it)."""
    with _lock:
        _state.clear()
        _round_robin.clear()
        _events.clear()


def bind_audit(persistence: Any, namespace: str = "") -> None:
    """Send every pool event to the audit trail. Called by the governed loop when it builds its provider; the last binding wins (one process, one audit store)."""
    global _sink
    if persistence is None:
        return

    def write(event: Dict[str, Any]) -> None:
        persistence.append_audit(entity_type="credential_pool", entity_id=f"{event['provider']}-{event['label']}", action=event["kind"], actor=namespace or "runtime", changes=event)
    _sink = write


def _emit(kind: str, provider: str, label: str, **detail: Any) -> None:
    event = {"kind": kind, "provider": provider, "label": label, "at": round(time.time(), 3), **detail}
    with _lock:
        _events.append(event)
        del _events[:-200]
    if _sink is not None:
        try:
            _sink(event)
        except Exception:                                   # noqa: BLE001 - reporting a move must never decide whether the call is made
            pass


def _slot(provider: str, label: str) -> Dict[str, Any]:
    return _state.setdefault((provider, label), {"cooldown_until": 0.0, "disabled": False, "uses": 0, "last_status": None})


def _cooldown_seconds(status: int, retry_after: Optional[float]) -> float:
    if status == 402:
        return OUT_OF_CREDIT_COOLDOWN
    if retry_after is not None and retry_after > 0:
        return min(float(retry_after), 24 * 3600.0)
    try:
        return max(1.0, float(os.environ.get(COOLDOWN_ENV, DEFAULT_RATE_LIMIT_COOLDOWN)))
    except ValueError:
        return DEFAULT_RATE_LIMIT_COOLDOWN


class Lease:
    """One key for one call. `value` is read from the environment when the lease is taken. Report what the provider answered with `report`."""

    def __init__(self, provider: str, label: str, value: str) -> None:
        self.provider, self.label, self.value = provider, label, value

    def report(self, status: int, retry_after: Optional[float] = None) -> None:
        with _lock:
            slot = _slot(self.provider, self.label)
            slot["last_status"] = int(status)
            extra: Dict[str, Any]
            if status in (401, 403):
                slot["disabled"] = True
                kind, extra = "disabled", {"status": int(status)}
            elif status in (402, 429):
                seconds = _cooldown_seconds(int(status), retry_after)
                slot["cooldown_until"] = time.time() + seconds
                kind, extra = "cooldown", {"status": int(status), "seconds": round(seconds, 1)}
            else:
                if 200 <= int(status) < 400:
                    slot["uses"] += 1
                return
        _emit(kind, self.provider, self.label, **extra)

    def __repr__(self) -> str:                              # a lease is printed in tracebacks; it must never show the key
        return f"Lease({self.provider}:{self.label})"


def configured(provider: str) -> bool:
    try:
        return provider in load_config()
    except PoolConfigError:
        return True                                         # a broken pool file is a pool that cannot be used: callers must not fall back to some other key silently


def _usable(provider: str, label: str, now: float) -> str:
    """'ready' | 'cooling' | 'disabled' | 'missing'"""
    if not os.environ.get(label):
        return "missing"
    slot = _state.get((provider, label))
    if slot is None:
        return "ready"
    if slot["disabled"]:
        return "disabled"
    return "cooling" if slot["cooldown_until"] > now else "ready"


def acquire(provider: str, skip: Tuple[str, ...] = ()) -> Optional[Lease]:
    """A lease on the next usable key, or None when this provider has no pool. Raises NoCredentialAvailable when it has one and no key can be used now,
    and PoolConfigError when the pool file is broken."""
    config = load_config().get(provider)
    if config is None:
        return None
    now = time.time()
    with _lock:
        ready = [label for label in config["keys"] if label not in skip and _usable(provider, label, now) == "ready"]
        if not ready:
            states = {label: _usable(provider, label, now) for label in config["keys"]}
            waits = [max(0.0, _state[(provider, l)]["cooldown_until"] - now) for l in config["keys"] if states[l] == "cooling"]
            detail = ", ".join(f"{l}: {s}" for l, s in states.items())
            _emit("exhausted", provider, "*", states=states)
            raise NoCredentialAvailable(f"no key of the {provider} pool can be used ({detail})" + (f"; the first is ready again in {min(waits):.0f} s" if waits else ""))
        strategy = config["strategy"]
        if strategy == "round_robin":
            index = _round_robin.get(provider, 0) % len(ready)
            _round_robin[provider] = _round_robin.get(provider, 0) + 1
            label = ready[index]
        elif strategy == "least_used":
            label = min(ready, key=lambda l: (_slot(provider, l)["uses"], config["keys"].index(l)))
        else:
            label = ready[0]
    return Lease(provider, label, os.environ[label])


def available(provider: str, default_env: str = "") -> bool:
    """Is there any key that could sign a call right now? With a pool: a ready one. Without: the single variable `default_env`."""
    try:
        config = load_config().get(provider)
    except PoolConfigError:
        return False
    if config is None:
        return bool(default_env and os.environ.get(default_env))
    now = time.time()
    with _lock:
        return any(_usable(provider, label, now) == "ready" for label in config["keys"])


class KeyRing:
    """What a provider uses for one call: `take()` a key, send, then `refused(status, retry_after)` if the answer was 401/402/403/429 (True = another key is
    worth a try), `succeeded()` otherwise. With no pool for the provider it is the one key it was given and `refused` is always False."""

    def __init__(self, provider: str, explicit: Optional[str], env_name: Optional[str]) -> None:
        self._provider, self._explicit, self._env = provider, explicit, env_name
        self._lease: Optional[Lease] = None
        self._tried: Tuple[str, ...] = ()
        self._pooled = explicit is None and configured(provider)

    def take(self) -> Optional[str]:
        if self._explicit is not None:
            return self._explicit
        if not self._pooled:
            return os.environ.get(self._env) if self._env else None
        self._lease = acquire(self._provider, self._tried)
        if self._lease is None:
            return os.environ.get(self._env) if self._env else None
        self._tried += (self._lease.label,)
        return self._lease.value

    @property
    def label(self) -> Optional[str]:
        return self._lease.label if self._lease else self._env

    def refused(self, status: int, retry_after: Optional[float] = None) -> bool:
        if self._lease is None or status not in ROTATE_STATUSES:
            return False
        self._lease.report(status, retry_after)
        try:
            config = load_config().get(self._provider) or {"keys": []}
        except PoolConfigError:
            return False
        now = time.time()
        with _lock:
            return any(l not in self._tried and _usable(self._provider, l, now) == "ready" for l in config["keys"])

    def succeeded(self, status: int = 200) -> None:
        if self._lease is not None:
            self._lease.report(status)


def retry_after_seconds(headers: Any) -> Optional[float]:
    try:
        value = headers.get("retry-after") if headers is not None else None
        return float(value) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def status(include_error_text: bool = False) -> Dict[str, Any]:
    """For the CLI, the Desk and the Governance page: labels and states, never a value. The reason a broken pool file was refused is spelled out only when `include_error_text` is set (the CLI on the host); the HTTP pages say that it is broken and where to look."""
    try:
        config = load_config()
        error = None
    except PoolConfigError as exc:
        config, error = {}, (str(exc) if include_error_text else "the credential pool file is not usable; run `delentia credentials status` on the host for the reason")
    now = time.time()
    out: Dict[str, Any] = {"file": str(pool_path()), "providers": {}, "error": error, "recent_events": list(_events[-20:])}
    with _lock:
        for provider, spec in config.items():
            keys = []
            for label in spec["keys"]:
                slot = _state.get((provider, label)) or {}
                state = _usable(provider, label, now)
                keys.append({"label": label, "state": state, "uses": slot.get("uses", 0), "last_status": slot.get("last_status"),
                             "cooldown_seconds": round(max(0.0, slot.get("cooldown_until", 0.0) - now), 1) if state == "cooling" else 0})
            out["providers"][provider] = {"strategy": spec["strategy"], "keys": keys}
    return out


def save_config(provider: str, names: List[str], strategy: str = "fill_first") -> Path:
    """Write the pool for one provider (names only). Existing entries of other providers are kept."""
    clean = _clean(provider, {"keys": names, "strategy": strategy})
    path = pool_path()
    current: Dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            current = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            raise PoolConfigError("the existing credential pool file cannot be read; fix or move it first") from None
    current[provider] = clean
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
