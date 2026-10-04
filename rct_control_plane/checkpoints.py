"""
Round 57: a way back after the agent has written to a file.

A write or patch of a repository file already needs a human signature (the strongest gate the runtime has), but a signed write can still be a mistake: the
signer approved the text they were shown, not every consequence. Hermes keeps automatic snapshots before file modifications and a /rollback; this is the
same idea built on what the runtime already has:

  * before `delentia_write_repo_file` / `delentia_patch_repo_file` changes a file, its previous content is stored (content-addressed, so the same
    content is stored once) and a row records the path, the hash before and, once the write is done, the hash after;
  * `rollback` restores the previous content ONLY if the file still holds exactly what the agent wrote (a person's later edit is never overwritten, unless
    `force`), and rolling back is itself checkpointed, so it can be undone;
  * a file the agent created is, on rollback, moved out of the way (its content is kept as a checkpoint), never silently erased (Zero-Delete);
  * nothing is ever deleted by the runtime (Zero-Delete): the space they use is reported by `status`, and clearing old ones is a person's decision made outside this
    code; a file over the size limit is written but recorded as UNPROTECTED, so the list never claims a safety it does not have.

On by default; DELENTIA_CHECKPOINTS=0 turns it off. This protects files written through the agent's file tools. It does not protect what a shell command changes
(the sandboxed shell has its own approval and is not a file tool).
"""
from __future__ import annotations

import difflib
import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane import data_home

ENABLED_ENV = "DELENTIA_CHECKPOINTS"
MAX_FILE_BYTES = 10 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS repo_checkpoints (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project        TEXT NOT NULL,
    rel_path       TEXT NOT NULL,
    tool           TEXT NOT NULL,
    existed_before INTEGER NOT NULL,
    before_sha     TEXT,
    after_sha      TEXT,
    protected      INTEGER NOT NULL DEFAULT 1,
    note           TEXT,
    created_at     REAL NOT NULL,
    rolled_back_at REAL,
    rollback_of    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_project ON repo_checkpoints(project, id);
"""


def enabled() -> bool:
    return (os.environ.get(ENABLED_ENV) or "1").strip().lower() not in ("0", "false", "no", "off")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CheckpointError(ValueError):
    pass


class CheckpointStore:
    def __init__(self, persistence: Any, blob_dir: Optional[Path] = None):
        self._p = persistence
        base = data_home.data_home() or Path(str(getattr(persistence, "db_path", "."))).resolve().parent
        self._blobs = Path(blob_dir) if blob_dir else base / "checkpoints" / "blobs"
        self._blobs.mkdir(parents=True, exist_ok=True)
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ blobs

    def _put(self, data: bytes) -> str:
        digest = _sha(data)
        target = self._blobs / digest
        if not target.exists():
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        return digest

    def _get(self, digest: str) -> bytes:
        path = self._blobs / digest
        if not path.is_file():
            raise CheckpointError(f"the stored content {digest[:12]} is missing from {self._blobs}")
        data = path.read_bytes()
        if _sha(data) != digest:
            raise CheckpointError(f"the stored content {digest[:12]} no longer matches its hash: refusing to restore from it")
        return data

    # ------------------------------------------------------------------ before and after a write

    def begin(self, project_root: Path, rel_path: str, tool: str) -> Optional[int]:
        """Call BEFORE the file is changed. Returns the checkpoint id (pass it to `seal` afterwards), or None when checkpoints are off."""
        if not enabled():
            return None
        target = Path(project_root) / rel_path
        existed = target.is_file()
        before: Optional[str] = None
        protected, note = 1, None
        if existed:
            data = target.read_bytes()
            if len(data) > MAX_FILE_BYTES:
                protected, note = 0, f"UNPROTECTED: the file is {len(data)} bytes, over the {MAX_FILE_BYTES} byte limit"
            else:
                before = self._put(data)
        with self._p._connect() as conn:
            cur = conn.execute("INSERT INTO repo_checkpoints (project, rel_path, tool, existed_before, before_sha, protected, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (str(Path(project_root).resolve()), rel_path, tool, 1 if existed else 0, before, protected, note, time.time()))
            return int(cur.lastrowid or 0)

    def seal(self, checkpoint_id: Optional[int], project_root: Path, rel_path: str) -> None:
        """Call AFTER the write: records what the agent left in the file, which is what `rollback` will insist is still there."""
        if checkpoint_id is None:
            return
        target = Path(project_root) / rel_path
        after = _sha(target.read_bytes()) if target.is_file() else None
        with self._p._connect() as conn:
            conn.execute("UPDATE repo_checkpoints SET after_sha = ? WHERE id = ?", (after, checkpoint_id))

    def abandon(self, checkpoint_id: Optional[int], reason: str) -> None:
        """The write failed after `begin`: keep the row (it says what happened) but there is nothing to roll back."""
        if checkpoint_id is None:
            return
        with self._p._connect() as conn:
            conn.execute("UPDATE repo_checkpoints SET note = ?, protected = 0 WHERE id = ?", (f"write did not happen: {reason}"[:200], checkpoint_id))

    # ------------------------------------------------------------------ reading

    def list(self, project_root: Optional[Path] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM repo_checkpoints", []
        if project_root is not None:
            sql += " WHERE project = ?"
            args.append(str(Path(project_root).resolve()))
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", [*args, max(1, min(int(limit), 500))]).fetchall()
        return [dict(r) for r in rows]

    def get(self, checkpoint_id: int) -> Dict[str, Any]:
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM repo_checkpoints WHERE id = ?", (int(checkpoint_id),)).fetchone()
        if row is None:
            raise CheckpointError(f"no checkpoint {checkpoint_id}")
        return dict(row)

    def diff(self, checkpoint_id: int) -> str:
        """What the write changed: the stored previous content against what the file holds now (empty text for a file that did not exist)."""
        cp = self.get(checkpoint_id)
        before = self._get(cp["before_sha"]).decode("utf-8", "replace") if cp["before_sha"] else ""
        target = Path(cp["project"]) / cp["rel_path"]
        now = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        return "".join(difflib.unified_diff(before.splitlines(True), now.splitlines(True), f"before: {cp['rel_path']}", f"now: {cp['rel_path']}"))

    # ------------------------------------------------------------------ rolling back

    def rollback(self, checkpoint_id: int, force: bool = False) -> Dict[str, Any]:
        cp = self.get(checkpoint_id)
        if cp["rolled_back_at"]:
            raise CheckpointError(f"checkpoint {checkpoint_id} was already rolled back")
        if not cp["protected"] or (cp["existed_before"] and not cp["before_sha"]):
            raise CheckpointError(f"checkpoint {checkpoint_id} cannot be rolled back: {cp['note'] or 'no previous content was stored'}")
        project, rel = Path(cp["project"]), cp["rel_path"]
        target = (project / rel).resolve()
        if not target.is_relative_to(project):
            raise CheckpointError("the recorded path leaves the project: refusing")
        current = _sha(target.read_bytes()) if target.is_file() else None
        if current != cp["after_sha"] and not force:
            raise CheckpointError(f"{rel} no longer holds what the agent wrote (it was changed afterwards, probably by a person): refusing to overwrite it. "
                                  "Use --force to restore the earlier content anyway; the current content is kept as a checkpoint either way.")
        undo = self.begin(project, rel, "rollback") if target.is_file() else None     # the rollback is itself undoable
        if undo is not None:
            with self._p._connect() as conn:
                conn.execute("UPDATE repo_checkpoints SET rollback_of = ? WHERE id = ?", (checkpoint_id, undo))
        if cp["existed_before"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self._get(cp["before_sha"]))
            action = "restored the earlier content"
        elif target.is_file():
            target.unlink()                                                              # the content is already held by `undo`: nothing is lost
            action = "removed the file the agent created (its content is kept as a checkpoint)"
        else:
            action = "the file was already gone"
        self.seal(undo, project, rel)
        with self._p._connect() as conn:
            conn.execute("UPDATE repo_checkpoints SET rolled_back_at = ? WHERE id = ?", (time.time(), checkpoint_id))
        try:
            self._p.append_audit(entity_type="repo_checkpoint", entity_id=str(checkpoint_id), action="rollback", actor="owner",
                                 changes={"path": rel, "project": str(project), "forced": bool(force), "result": action, "undo_checkpoint": undo})
        except Exception:               # the file is already restored; an audit-store problem must not hide that
            pass
        return {"checkpoint": checkpoint_id, "path": rel, "result": action, "undo_checkpoint": undo}

    def status(self) -> Dict[str, Any]:
        total = sum(f.stat().st_size for f in self._blobs.iterdir() if f.is_file())
        with self._p._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM repo_checkpoints").fetchone()[0]
            unprotected = conn.execute("SELECT COUNT(*) FROM repo_checkpoints WHERE protected = 0").fetchone()[0]
        return {"enabled": enabled(), "checkpoints": int(n), "unprotected": int(unprotected), "stored_bytes": total, "blob_dir": str(self._blobs)}
