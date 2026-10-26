"""
Round 101C: "is there a newer Delentia?" and "update it" for a person who installed the program, not a developer.

What it does, and what it deliberately does not:

  * CHECK: one small GET to the public package index (https://pypi.org/pypi/delentia-os/json) at most once every 24 hours, remembered in a file next to the other settings. The request carries no account, no
    machine name, no data of yours; the server sees the address of your network and the program's name and version in the User-Agent, like any `pip install`. Turn it off with `delentia update off`,
    `DELENTIA_UPDATE_CHECK=off`, or `DELENTIA_OFFLINE=1`. A network failure is never an error: the answer is "unknown".
  * NOTIFY: the Desk shows a banner, `delentia desk` / `delentia serve` print one line, and nothing else happens.
  * APPLY (`delentia update --apply`, or the "Update Delentia" shortcut the Windows installer makes): downloads that exact version's file, checks its SHA-256 against the digest the index published for it, and only then
    installs it with pip. A person must confirm at the terminal; the command refuses to run for the agent (it is in the sandbox's refused commands, and refuses when it sees DELENTIA_AGENT_SHELL). A program replacing itself
    while it runs is not safe on Windows (files in use), so the command asks you to close the agent first and never restarts anything on its own.

Limit to say aloud: the digest comes from the same index as the file, so it catches a damaged or swapped download, not a compromised index. Releases are published from CI with a token only the maintainer holds;
publishing with provenance (attestations) is a later step.
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PACKAGE = "delentia-os"
DEFAULT_INDEX = "https://pypi.org/pypi/delentia-os/json"
INDEX_ENV = "DELENTIA_UPDATE_INDEX_URL"
SWITCH_ENV = "DELENTIA_UPDATE_CHECK"
OFFLINE_ENV = "DELENTIA_OFFLINE"
TTL_SECONDS = 24 * 3600
TIMEOUT_SECONDS = 4.0
RELEASES_URL = "https://github.com/delentia-labs/Delentia-OS/releases"
MAX_BODY = 3_000_000
_VERSION = re.compile(r"^(\d+(?:\.\d+){0,3})((?:a|b|rc)\d+)?$")


class UpdateError(RuntimeError):
    """A refusal or failure with a reason a person can read."""


# ---------------------------------------------------------------------------------------------------------------------------------- versions
def parse_version(text: str) -> Optional[Tuple[Tuple[int, ...], int, int]]:
    """(release numbers padded to 4, stage, number) where a pre-release sorts before the final release; None for anything this function does not understand (it is then never offered)."""
    match = _VERSION.match(str(text or "").strip())
    if not match:
        return None
    numbers = tuple(int(p) for p in match.group(1).split("."))
    numbers = numbers + (0,) * (4 - len(numbers))
    pre = match.group(2)
    if not pre:
        return numbers, 3, 0
    stage = {"a": 0, "b": 1, "rc": 2}[re.match(r"[a-z]+", pre).group(0)]       # type: ignore[union-attr]
    return numbers, stage, int(re.search(r"\d+", pre).group(0))                 # type: ignore[union-attr]


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def current_version() -> str:
    from rct_control_plane._version import PACKAGE_VERSION
    return PACKAGE_VERSION


# ---------------------------------------------------------------------------------------------------------------------------------- settings and cache
def settings_dir() -> Path:
    from rct_control_plane import data_home
    return data_home.data_home() or (Path.home() / ".delentia")


def _file() -> Path:
    return settings_dir() / "update_check.json"


def _read() -> Dict[str, Any]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: Dict[str, Any]) -> None:
    try:
        path = _file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass                                                    # a read-only home just means no memory of the last check


def enabled() -> bool:
    if (os.environ.get(OFFLINE_ENV) or "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    switch = (os.environ.get(SWITCH_ENV) or "").strip().lower()
    if switch in ("off", "0", "false", "no"):
        return False
    if switch in ("on", "1", "true", "yes"):
        return True
    return bool(_read().get("enabled", True))


def set_enabled(value: bool) -> None:
    data = _read()
    data["enabled"] = bool(value)
    _write(data)


def index_url() -> str:
    url = (os.environ.get(INDEX_ENV) or "").strip() or DEFAULT_INDEX
    if not (url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", url)):
        raise UpdateError("the update index must be an https address (or a loopback address for tests)")
    return url


# ---------------------------------------------------------------------------------------------------------------------------------- the check
def fetch_latest(url: Optional[str] = None, opener: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """What the index says about the newest stable release: version, the file to download with its SHA-256, and when it was published. Raises UpdateError."""
    target = url or index_url()
    request = urllib.request.Request(target, headers={"User-Agent": f"delentia-os/{current_version()} update-check", "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS) as response:                      # noqa: S310 - https or loopback, see index_url
            body = response.read(MAX_BODY + 1)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise UpdateError(f"the update index could not be reached ({type(exc).__name__})") from exc
    if len(body) > MAX_BODY:
        raise UpdateError("the update index answered with something too large")
    try:
        data = json.loads(body.decode("utf-8"))
        version = data["info"]["version"]
        if not isinstance(version, str):
            raise TypeError("the version is not text")
        files = data.get("urls") or []
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise UpdateError("the update index answered in a form this program does not understand") from exc
    if parse_version(version) is None:
        raise UpdateError(f"the newest release is called {version!r}, which this program does not know how to compare")
    wheel = next((f for f in files if isinstance(f, dict) and str(f.get("filename", "")).endswith(".whl") and not f.get("yanked")), None)
    return {"version": version, "file": ({"filename": str(wheel["filename"]), "url": str(wheel["url"]), "sha256": str((wheel.get("digests") or {}).get("sha256", "")).lower(),
                                          "size": int(wheel.get("size") or 0)} if wheel else None),
            "published": (wheel or {}).get("upload_time_iso_8601") if wheel else None}


def check(force: bool = False, now: Optional[float] = None, fetch: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The state a banner needs. Never raises. `status` is one of: disabled, unknown, current, available."""
    current = current_version()
    base = {"current": current, "enabled": enabled(), "releases_url": RELEASES_URL}
    if not base["enabled"]:
        return {**base, "status": "disabled", "latest": None, "checked_at": None}
    clock = time.time() if now is None else now
    saved = _read()
    cached = saved.get("last") if isinstance(saved.get("last"), dict) else None
    if cached and not force and clock - float(cached.get("checked_at", 0)) < TTL_SECONDS and cached.get("for_version") == current:
        latest, checked_at, error = cached.get("latest"), float(cached["checked_at"]), None
    else:
        try:
            got = (fetch or fetch_latest)()
            latest, checked_at, error = got, clock, None
            saved["last"] = {"latest": got, "checked_at": clock, "for_version": current}
        except UpdateError as exc:
            latest, error = (cached or {}).get("latest"), str(exc)
            saved["last"] = {**(cached or {}), "latest": latest, "checked_at": clock, "for_version": current, "error": error}
            checked_at = clock
        _write(saved)
    if not latest:
        return {**base, "status": "unknown", "latest": None, "checked_at": checked_at, "error": error}
    available = is_newer(str(latest["version"]), current)
    return {**base, "status": "available" if available else "current", "latest": latest, "checked_at": checked_at, "error": error}


def banner_line(state: Dict[str, Any]) -> Optional[str]:
    """One line for a terminal, or None when there is nothing to say."""
    if state.get("status") != "available" or not state.get("latest"):
        return None
    return f"A newer Delentia is available: {state['latest']['version']} (you have {state['current']}). Close the agent, then run: delentia update --apply"


# ---------------------------------------------------------------------------------------------------------------------------------- applying an update
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def apply(state: Optional[Dict[str, Any]] = None, *, from_agent_shell: Optional[bool] = None, run: Optional[Callable[[List[str]], int]] = None,
          find_links: Optional[str] = None, python: Optional[str] = None) -> Dict[str, Any]:
    """Download the checked version's file, verify its SHA-256 against the index, install it. `run` and `find_links` exist for tests and for an offline folder of wheels."""
    if (bool(os.environ.get("DELENTIA_AGENT_SHELL")) if from_agent_shell is None else from_agent_shell):
        raise UpdateError("updating the program is for the person at the keyboard; it will not run for the agent")
    state = state or check(force=True)
    if state.get("status") != "available" or not state.get("latest"):
        raise UpdateError("there is no newer version to install" if state.get("status") == "current" else "the newest version could not be determined (are you online?)")
    latest = state["latest"]
    wanted = latest.get("file") or {}
    digest = str(wanted.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("the index did not publish a SHA-256 for this release, so it will not be installed")
    version, py = str(latest["version"]), python or sys.executable
    runner = run or (lambda cmd: subprocess.run(cmd, check=False).returncode)
    with tempfile.TemporaryDirectory(prefix="delentia-update-") as tmp:
        cmd = [py, "-m", "pip", "download", "--no-deps", "--dest", tmp, f"{PACKAGE}=={version}"]
        if find_links:
            cmd[4:4] = ["--no-index", "--find-links", find_links]
        if runner(cmd) != 0:
            raise UpdateError("the download failed (pip said why above); nothing was changed")
        files = sorted(Path(tmp).glob("*.whl"))
        if len(files) != 1:
            raise UpdateError("the download did not produce exactly one file; nothing was changed")
        actual = _sha256(files[0])
        if actual != digest:
            raise UpdateError("the downloaded file does not match the SHA-256 the index published for it; it was NOT installed")
        if runner([py, "-m", "pip", "install", "--upgrade", str(files[0])]) != 0:
            raise UpdateError("the installation failed (pip said why above); the earlier version is still in place unless pip reports otherwise")
    state_now = _read()
    state_now.pop("last", None)
    _write(state_now)
    return {"installed": version, "previous": state.get("current"), "sha256": actual, "note": "Start the agent again. Nothing was restarted for you."}


def cached_state() -> Dict[str, Any]:
    """The last answer without touching the network (for a line printed at start-up that must never wait for the internet)."""
    current = current_version()
    base = {"current": current, "enabled": enabled(), "releases_url": RELEASES_URL}
    saved = _read().get("last")
    if not base["enabled"] or not isinstance(saved, dict) or not saved.get("latest") or saved.get("for_version") != current:
        return {**base, "status": "unknown", "latest": None, "checked_at": None}
    latest = saved["latest"]
    return {**base, "status": "available" if is_newer(str(latest["version"]), current) else "current", "latest": latest, "checked_at": saved.get("checked_at")}
