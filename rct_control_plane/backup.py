"""
Round 60 (D8): backup and restore of the runtime's own state.

A host that loses its disk loses the audit chain, the approvals, the memory, the skills, the owner's policy and every task. This module makes ONE zip of that state and puts it back:

  * what goes in: every SQLite database in the data home (copied with SQLite's online backup API, so a running server gives a consistent file, never a half-written one), the owner's JSON
    configuration (`model.json`, `approvers.json`, `fdia_policy.json`, `mcp_servers.json`, `search.json`, `webhooks.json`, `jury.json`, the sovereignty policy, `AGENTS.md`/`SOUL.md`),
    and the PAUSED file if there is one. A `manifest.json` lists every file with its SHA-256 and the backup's own creation time;
  * what stays OUT unless you say so: private keys (`*.pem`, anything under a `keys` folder), API token files and `.env` files. A backup you can mail to yourself must not be a way to lose the
    signing key; `--include-keys` exists for the person who has decided otherwise and says so in the manifest;
  * restore: every entry is checked against the manifest BEFORE anything is written (a changed byte or an extra file fails the whole restore), names are confined to the target folder (no
    absolute paths, no `..`), an existing file is never overwritten unless `--force`, and then the old file is moved aside to `<name>.before-restore-<time>`, not deleted;
  * the audit chain in a restored database still verifies (it is the same bytes), and anything written after the backup was taken is, of course, not in it.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

FORMAT = "delentia-backup-1"
CONFIG_NAMES = {"model.json", "approvers.json", "fdia_policy.json", "mcp_servers.json", "search.json", "webhooks.json", "jury.json", "sovereignty.json", "AGENTS.md", "SOUL.md",
                ".delentia.md", "PAUSED"}
SECRET_PARTS = ("api_tokens", "token", "secret", ".env", "credentials")


class BackupError(ValueError):
    pass


def _is_secret(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith((".pem", ".key")) or "keys" in {p.lower() for p in path.parts} or any(part in lowered for part in SECRET_PARTS)


def _sources(include_keys: bool) -> List[Dict[str, Any]]:
    from rct_control_plane.data_home import data_home
    roots: List[Path] = []
    home = data_home()
    if home is not None and home.exists():
        roots.append(home)
    user_dir = Path.home() / ".delentia"
    if user_dir.exists() and user_dir not in roots:
        roots.append(user_dir)
    found: List[Dict[str, Any]] = []
    seen: set = set()
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path in seen:
                continue
            rel = path.relative_to(root)
            is_db = path.suffix == ".db" and len(rel.parts) == 1
            is_key = _is_secret(rel)
            is_config = path.name in CONFIG_NAMES and len(rel.parts) <= 2 and not is_key
            if is_db:
                kind = "database"
            elif is_config:
                kind = "config"
            elif is_key and include_keys and (path.suffix == ".pem" or {"keys", "memory_keys"} & {p.lower() for p in rel.parts}):      # Round 67: with the memory keys a restored backup can read the sealed memory log
                kind = "key"
            else:
                continue
            seen.add(path)
            found.append({"path": path, "name": f"{'home' if root == home else 'user'}/{rel.as_posix()}", "kind": kind})
    return found


def create_backup(out: str, include_keys: bool = False) -> Dict[str, Any]:
    out_path = Path(out)
    if out_path.exists():
        raise BackupError(f"{out_path} already exists; a backup is never overwritten")
    sources = _sources(include_keys)
    if not sources:
        raise BackupError("nothing to back up: no databases or configuration were found in the data home")
    entries: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="delentia-backup-") as tmp, zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for src in sources:
            path = src["path"]
            if src["kind"] == "database":
                copy = Path(tmp) / hashlib.sha256(src["name"].encode()).hexdigest()
                live = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    dest = sqlite3.connect(str(copy))
                    try:
                        live.backup(dest)
                    finally:
                        dest.close()
                finally:
                    live.close()
                data = copy.read_bytes()
            else:
                data = path.read_bytes()
            z.writestr(src["name"], data)
            entries.append({"name": src["name"], "kind": src["kind"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        manifest = {"format": FORMAT, "created_at": time.time(), "includes_keys": bool(include_keys), "files": entries}
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return {"path": str(out_path), "files": len(entries), "bytes": out_path.stat().st_size, "includes_keys": bool(include_keys),
            "keys_note": None if include_keys else "private keys, token files and .env files were left out on purpose"}


def _read_manifest(z: zipfile.ZipFile) -> Dict[str, Any]:
    try:
        manifest = json.loads(z.read("manifest.json"))
    except (KeyError, ValueError) as exc:
        raise BackupError("this is not a Delentia backup (no readable manifest.json)") from exc
    if manifest.get("format") != FORMAT:
        raise BackupError(f"unknown backup format {manifest.get('format')!r}")
    return manifest


def verify_backup(path: str) -> Dict[str, Any]:
    """Checks every file against the manifest and that nothing is in the zip that the manifest does not list. Raises BackupError on any difference."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(f"cannot open the backup: {type(exc).__name__}") from exc
    with z:
        manifest = _read_manifest(z)
        listed = {e["name"]: e for e in manifest["files"]}
        names = set(z.namelist()) - {"manifest.json"}
        extra = sorted(names - set(listed))
        if extra:
            raise BackupError(f"the zip holds files the manifest does not list: {extra[:5]}")
        for name, entry in listed.items():
            if name not in names:
                raise BackupError(f"the manifest lists {name} but the zip does not hold it")
            if hashlib.sha256(z.read(name)).hexdigest() != entry["sha256"]:
                raise BackupError(f"{name} does not match its recorded SHA-256 (the backup was changed or damaged)")
    return {"files": len(listed), "created_at": manifest["created_at"], "includes_keys": manifest.get("includes_keys", False)}


def _target(base: Path, name: str) -> Path:
    if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name.split("/")[0]:
        raise BackupError(f"unsafe name in the backup: {name!r}")
    parts = name.split("/", 1)
    if len(parts) != 2 or parts[0] not in ("home", "user"):
        raise BackupError(f"unexpected name in the backup: {name!r}")
    dest = (base / parts[0] / parts[1]).resolve()
    if not dest.is_relative_to(base.resolve()):
        raise BackupError(f"unsafe name in the backup: {name!r}")
    return dest


def restore_backup(path: str, to: str, force: bool = False) -> Dict[str, Any]:
    """Puts the files under `to/home/...` and `to/user/...` (the caller decides where those belong; nothing is written outside `to`)."""
    verify_backup(path)                                           # the whole backup is checked before the first byte is written
    base = Path(to)
    with zipfile.ZipFile(path) as z:
        manifest = _read_manifest(z)
        plan = [(e, _target(base, e["name"])) for e in manifest["files"]]
        clashes = [str(dest) for _, dest in plan if dest.exists()]
        if clashes and not force:
            raise BackupError(f"{len(clashes)} file(s) already exist (for example {clashes[0]}); restore into an empty folder, or use --force to move them aside first")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        moved = 0
        for entry, dest in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                os.replace(dest, dest.with_name(dest.name + f".before-restore-{stamp}"))
                moved += 1
            dest.write_bytes(z.read(entry["name"]))
    return {"restored": len(plan), "moved_aside": moved, "to": str(base)}
