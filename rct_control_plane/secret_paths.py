"""
Round 61: files the agent must never READ, whoever asks.

Found by checking the agent's own read tool: `delentia_read_repo_file(".env")` returned the real `.env` of this checkout (and `delentia_search_repo_files` returned matching lines from it), because
only WRITES had a block list. A model that can read a file can put it in an answer, and a person on a chat allowlist is not necessarily the owner of the machine. This is the one list the read tool,
the search tool and the `@file` references share.

It is a name-based list, a floor and not a boundary (a copy of a key under an innocent name is not caught; the real protection for keys is keeping them off the host or under another OS user).

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import re
from pathlib import PurePath
from typing import Optional

_BLOCKED_DIRS = {".git", ".ssh", ".aws", ".gnupg", ".delentia", ".claude", ".claude-mem", ".kube", ".docker"}
_NAME = re.compile(
    r"^(?:"
    r"\.env(?:\.(?!example$|sample$|template$|dist$).+)?"           # .env, .env.local, .env.production - not .env.example
    r"|.*_secrets?(?:\..*)?|.*secrets?\.(?:json|ya?ml|toml|txt|ini)"
    r"|credentials(?:\.json)?|vault_master\.key|approvers\.json"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?"
    r"|.*\.(?:pem|key|p12|pfx|jks|keystore|kdbx|ppk|asc|gpg)"
    r"|.*\.(?:db|sqlite|sqlite3|db-wal|db-shm|db-journal)"          # the runtime's own stores hold every person's memory, goals and approvals
    r"|\.netrc|\.npmrc|\.pypirc|\.git-credentials|token(?:s)?\.json|api[_-]?tokens?\.json"
    r")$",
    re.IGNORECASE,
)


def blocked_reason(path: str) -> Optional[str]:
    """Why the agent may not read this path, or None. Works on the path as written (relative or absolute, / or \\)."""
    parts = PurePath(str(path).replace("\\", "/")).parts
    for part in parts[:-1]:
        if part.lower() in _BLOCKED_DIRS:
            return f"{part} holds credentials or history that the agent must not read"
    name = parts[-1] if parts else ""
    if len(name) > 255 or len(parts) > 64:                                # no real file name is this long; also keeps the pattern below away from adversarial input
        return "a path this long is not a file the agent may read"
    if name.lower() in _BLOCKED_DIRS:
        return f"{name} holds credentials or history that the agent must not read"
    if _NAME.match(name):
        return f"{name} looks like a credential, key or private store, which the agent must not read"
    return None
