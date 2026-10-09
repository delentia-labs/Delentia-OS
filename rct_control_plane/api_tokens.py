"""
One API token per person (Round 54).

With the single shared `DELENTIA_API_TOKEN` every caller is the same caller: a role in the owner's policy
(fdia_policy.py) is only a label, and `POST /v1/agent/run` let the caller CHOOSE its own namespace, which is the
identity the policy, the memory and the growth ledger all key on. This gives each person their own token. The server
learns who is calling from the token and uses that name as the identity; a namespace in the request body is ignored.

  delentia tokens create alice        prints the token ONCE; only its SHA-256 is stored
  delentia tokens list                names, created time, disabled or not (never a token)
  delentia tokens revoke alice        disables the entry; the line stays on record (Zero-Delete)

Round 62 (tenant isolation): a token belongs to a PERSON or to an OWNER. An entry may carry "owner": true (`delentia tokens create <name> --owner`,
`delentia tokens owner <name>`); the old shared token is the owner, and so is the token-less loopback of a single-user machine. In per-person mode a
person who is not an owner may call only the routes in api_auth.PERSON_ROUTES (talk to the agent, their own jobs/tasks/approvals, their own memory and
history, the OpenAI-compatible API); every other route, the whole Desk and the raw MCP gateway included, is the owner's.

File: DELENTIA_API_TOKENS_FILE or ~/.delentia/api_tokens.json. If the file has any entry the server is in per-user
mode: a request needs a token from the file (the old shared token still works if it is set, as the identity "shared",
so a migration does not lock everyone out; unset it once everyone has their own). An unreadable file locks everyone
out instead of silently falling back to nobody-is-checked.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOKENS_FILE_ENV = "DELENTIA_API_TOKENS_FILE"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")
PREFIX = "dlt_"
SHARED_IDENTITY = "shared"


class TokenFileError(ValueError):
    pass


def tokens_path() -> Path:
    override = os.environ.get(TOKENS_FILE_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "api_tokens.json"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_cache: Dict[str, Tuple[float, int, List[Dict[str, Any]]]] = {}


def load_entries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every entry in the file (disabled ones too). Raises TokenFileError for a file that exists but cannot be used."""
    target = path or tokens_path()
    try:
        stat = target.stat()
    except FileNotFoundError:
        return []
    cached = _cache.get(str(target))
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        users = data["users"]
        if not isinstance(users, list) or not all(isinstance(u, dict) and NAME.match(str(u.get("name", ""))) and re.fullmatch(r"[0-9a-f]{64}", str(u.get("token_sha256", ""))) for u in users):
            raise ValueError("each user needs a valid name and a 64-character token_sha256")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TokenFileError(f"cannot use the API tokens file {target}: {exc}") from exc
    _cache[str(target)] = (stat.st_mtime, stat.st_size, users)
    return users


def per_user_mode() -> bool:
    """True when the file exists and holds any entry, or exists but is unusable (then nobody gets in)."""
    try:
        return bool(load_entries())
    except TokenFileError:
        return True


def identify(token: str) -> Optional[str]:
    """The name for this token, or None. Constant-time over every entry; an unusable file identifies nobody."""
    if not token:
        return None
    try:
        entries = load_entries()
    except TokenFileError:
        return None
    digest = hash_token(token)
    found: Optional[str] = None
    for entry in entries:
        if hmac.compare_digest(digest, entry["token_sha256"]) and not entry.get("disabled"):
            found = entry["name"]
    return found


def _write(path: Path, users: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".api_tokens.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"users": users}, handle, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _cache.pop(str(path), None)


def is_owner(identity: str, path: Optional[Path] = None) -> bool:
    """May this identity use the owner's routes? The shared token and the token-less loopback ("") are the owner; a named person only with "owner": true."""
    if not identity or identity == SHARED_IDENTITY:
        return True
    try:
        return any(e["name"] == identity and bool(e.get("owner")) and not e.get("disabled") for e in load_entries(path))
    except TokenFileError:
        return False


def set_owner(name: str, value: bool = True, path: Optional[Path] = None) -> bool:
    """Marks (or unmarks) an existing person as an owner. Returns whether anything changed. Host-side only (it edits the file)."""
    target = path or tokens_path()
    users = list(load_entries(target))
    changed = False
    for user in users:
        if user["name"] == name and bool(user.get("owner")) != value:
            user["owner"] = value
            changed = True
    if changed:
        _write(target, users)
    return changed


def create(name: str, path: Optional[Path] = None, owner: bool = False) -> str:
    """Adds a person and returns their token. The token is shown to the caller once and never stored."""
    if not NAME.match(name):
        raise TokenFileError("a name is 1-64 characters: letters, digits, . _ @ -")
    if name == SHARED_IDENTITY:
        raise TokenFileError(f"{SHARED_IDENTITY!r} is reserved for the old shared token")
    target = path or tokens_path()
    users = list(load_entries(target))
    if any(u["name"] == name for u in users):
        raise TokenFileError(f"{name!r} already has an entry (revoke it first if the token is lost; the line is kept)")
    token = PREFIX + secrets.token_urlsafe(32)
    users.append({"name": name, "token_sha256": hash_token(token), "created_at": time.time(), "disabled": False, "owner": bool(owner)})
    _write(target, users)
    return token


def revoke(name: str, path: Optional[Path] = None) -> bool:
    target = path or tokens_path()
    users = list(load_entries(target))
    changed = False
    for user in users:
        if user["name"] == name and not user.get("disabled"):
            user["disabled"] = True
            user["disabled_at"] = time.time()
            changed = True
    if changed:
        _write(target, users)
    return changed
