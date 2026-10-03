
"""
Round 58: tamper-EVIDENCE that does not depend on one outside party (tier A3, made concrete), and a proof anyone can check without the database.

What the audit chain already gives: every row is hashed into the one before it and signed, so an edit, a deletion or a truncation of the host's own log is detectable by
anyone who holds an earlier copy of the head. What it cannot give alone: a copy of the head that the host's owner (or an attacker with the host's root) cannot also
rewrite. That copy has to live somewhere the host cannot reach. This module publishes the signed head to SEVERAL independent witnesses and reports how recent and how widely
it is held:

  * an HTTP witness (the fdia Worker's /v1/audit/anchor, which refuses a rollback or a fork and keeps the refusal as evidence);
  * a GIT witness: an append-only file of signed heads in a git repository, committed and pushed to a remote the host cannot rewrite (a protected branch, or another
    machine). Anyone with read access can see the whole history, and a force-push shows up as a rewritten history;
  * more can be added (the shape is `publish(body)` and `fetch()`).

With two witnesses an attacker has to compromise the host AND every witness before a rewritten log looks consistent; with none, "tamper-proof" is not a claim this system
makes. `status()` says plainly what is true NOW: when the last anchor reached which witness, how many audit rows are newer than the newest anchor (the window an attacker
with root could still rewrite unnoticed), and whether the witnesses agree with this chain. Configure with DELENTIA_AUDIT_WITNESSES (a JSON list; the older
DELENTIA_AUDIT_ANCHOR_URL / _KEY_ID pair still works as one HTTP witness):

    [{"type": "http", "name": "worker", "url": "https://witness.example.org", "key_id": "host-1"},
     {"type": "git",  "name": "git-mirror", "path": "/srv/delentia-anchors", "remote": "origin", "branch": "main", "key_id": "host-1"}]

`export_proof` + scripts/verify_audit_bundle.py give the other half: a bundle of chain rows, signatures and anchors that a third party can verify with nothing but Python
and the `cryptography` package (no database, no Delentia code), which is what an auditor needs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane import audit_chain

WITNESSES_ENV = "DELENTIA_AUDIT_WITNESSES"
URL_ENV = "DELENTIA_AUDIT_ANCHOR_URL"
KEY_ID_ENV = "DELENTIA_AUDIT_ANCHOR_KEY_ID"
INTERVAL_ENV = "DELENTIA_AUDIT_ANCHOR_INTERVAL_S"
GIT_TIMEOUT_S = 40

LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_anchor_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    witness   TEXT NOT NULL,
    entries   INTEGER,
    head      TEXT,
    ok        INTEGER NOT NULL,
    detail    TEXT,
    at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anchor_log_witness ON audit_anchor_log(witness, id);
"""


class WitnessError(RuntimeError):
    pass


@dataclass
class WitnessSpec:
    type: str
    name: str
    key_id: str
    url: str = ""
    path: str = ""
    remote: str = ""
    branch: str = "main"


def specs_from_env() -> List[WitnessSpec]:
    """The configured witnesses. A broken value gives none and is reported by `status()`, never half-applied."""
    raw = (os.environ.get(WITNESSES_ENV) or "").strip()
    if raw:
        items = json.loads(raw)
        if not isinstance(items, list) or not items:
            raise WitnessError(f"{WITNESSES_ENV} must be a non-empty JSON list")
        out: List[WitnessSpec] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict) or item.get("type") not in ("http", "git") or not item.get("key_id"):
                raise WitnessError(f"{WITNESSES_ENV}[{i}] needs a type (http or git) and a key_id")
            if item["type"] == "http" and not str(item.get("url", "")).startswith(("https://", "http://127.0.0.1", "http://localhost")):
                raise WitnessError(f"{WITNESSES_ENV}[{i}]: an http witness needs an https url (plain http only for loopback)")
            if item["type"] == "git" and not item.get("path"):
                raise WitnessError(f"{WITNESSES_ENV}[{i}]: a git witness needs a path to its repository")
            out.append(WitnessSpec(type=item["type"], name=str(item.get("name") or f"{item['type']}-{i + 1}"), key_id=str(item["key_id"]), url=str(item.get("url", "")),
                                   path=str(item.get("path", "")), remote=str(item.get("remote", "")), branch=str(item.get("branch", "main"))))
        if len({s.name for s in out}) != len(out):
            raise WitnessError("witness names must be unique")
        return out
    url, key_id = (os.environ.get(URL_ENV) or "").strip(), (os.environ.get(KEY_ID_ENV) or "").strip()
    return [WitnessSpec(type="http", name="worker", key_id=key_id, url=url)] if url and key_id else []


# ------------------------------------------------------------------ the witnesses

class HttpWitness:
    def __init__(self, spec: WitnessSpec):
        self.spec = spec

    def publish(self, body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        try:
            resp = httpx.post(f"{self.spec.url.rstrip('/')}/v1/audit/anchor", json=body, timeout=20.0)
        except Exception as exc:                                    # noqa: BLE001
            raise WitnessError(f"unreachable ({type(exc).__name__})") from exc
        if resp.status_code not in (200, 201):
            raise WitnessError(f"refused ({resp.status_code}): {resp.text[:160]}")
        return {"entries": body["entries"]}

    def fetch(self) -> Dict[str, Any]:
        import httpx
        try:
            resp = httpx.get(f"{self.spec.url.rstrip('/')}/v1/audit/anchor/{self.spec.key_id}", params={"limit": 1000}, timeout=20.0)
        except Exception as exc:                                    # noqa: BLE001
            raise WitnessError(f"unreachable ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise WitnessError(f"answered {resp.status_code}")
        data: Dict[str, Any] = resp.json()
        return data


class GitWitness:
    """An append-only file of signed heads (`anchors/<key_id>.jsonl`) in a git repository, committed and, when a remote is named, pushed. The witness is only as independent
    as the remote: protect its branch against force-pushes (or keep it on another machine the host cannot write to)."""

    def __init__(self, spec: WitnessSpec):
        self.spec = spec
        self.repo = Path(spec.path).expanduser()
        self.file = Path("anchors") / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', spec.key_id)}.jsonl"

    def _git(self, *args: str, check: bool = True) -> str:
        if shutil.which("git") is None:
            raise WitnessError("git is not installed")
        done = subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=delentia-witness", "-c", "user.email=witness@delentia.invalid", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True, timeout=GIT_TIMEOUT_S, encoding="utf-8", errors="replace")
        if check and done.returncode != 0:
            raise WitnessError(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()[:200]}")
        return done.stdout

    def _ensure_repo(self) -> None:
        self.repo.mkdir(parents=True, exist_ok=True)
        if not (self.repo / ".git").exists():
            self._git("init", "-q", "-b", self.spec.branch)

    def _committed_lines(self) -> List[Dict[str, Any]]:
        out = self._git("show", f"HEAD:{self.file.as_posix()}", check=False)
        rows = []
        for line in out.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def publish(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_repo()
        committed = self._committed_lines()
        last = committed[-1] if committed else None
        if last is not None:
            if body["entries"] < last["entries"]:
                raise WitnessError(f"rollback refused: the chain is at {body['entries']} but entry {last['entries']} was already anchored")
            if body["entries"] == last["entries"] and body["head"] != last["head"]:
                raise WitnessError(f"fork refused: entry {body['entries']} was anchored with a different head")
            if body["entries"] == last["entries"]:
                return {"entries": body["entries"], "note": "already anchored"}
        target = self.repo / self.file
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
        self._git("add", self.file.as_posix())
        self._git("commit", "-q", "-m", f"anchor {self.spec.key_id} entries={body['entries']} head={body['head'][:16]}")
        if self.spec.remote:
            self._git("push", "-q", self.spec.remote, f"HEAD:{self.spec.branch}")
        return {"entries": body["entries"]}

    def fetch(self) -> Dict[str, Any]:
        """What the witness holds NOW: from the remote's branch when there is one (a fresh `git fetch`), else the local committed file."""
        self._ensure_repo()
        ref = "HEAD"
        if self.spec.remote:
            self._git("fetch", "-q", self.spec.remote, self.spec.branch)
            ref = "FETCH_HEAD"
        text = self._git("show", f"{ref}:{self.file.as_posix()}", check=False)
        anchors, conflicts = [], []
        seen: Dict[int, str] = {}
        highest = 0
        for number, line in enumerate(text.splitlines(), 1):
            try:
                row = json.loads(line)
            except ValueError:
                conflicts.append({"line": number, "reason": "unreadable line"})
                continue
            if row["entries"] < highest:
                conflicts.append({"line": number, "reason": f"entries went back from {highest} to {row['entries']} (rollback)"})
            if row["entries"] in seen and seen[row["entries"]] != row["head"]:
                conflicts.append({"line": number, "reason": f"entry {row['entries']} anchored with two different heads (fork)"})
            seen[row["entries"]] = row["head"]
            highest = max(highest, row["entries"])
            anchors.append({**row, "received_at": row.get("signed_at")})
        return {"anchors": anchors, "conflicts": conflicts}


def make(spec: WitnessSpec) -> Any:
    return HttpWitness(spec) if spec.type == "http" else GitWitness(spec)


# ------------------------------------------------------------------ publishing

def ensure_log(conn: sqlite3.Connection) -> None:
    conn.executescript(LOG_SCHEMA)


def _log(conn: sqlite3.Connection, witness: str, entries: Optional[int], head: Optional[str], ok: bool, detail: str, now: float) -> None:
    conn.execute("INSERT INTO audit_anchor_log (witness, entries, head, ok, detail, at) VALUES (?, ?, ?, ?, ?, ?)", (witness, entries, head, 1 if ok else 0, detail[:300], now))


def anchor_all(conn: sqlite3.Connection, specs: Optional[List[WitnessSpec]] = None, private_key: Optional[Any] = None, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Sign the current head once and publish it to every witness. Never raises for a witness problem: each result says what happened, and each outcome is logged,
    so one dead witness neither stops the others nor goes unnoticed."""
    specs = specs_from_env() if specs is None else specs
    when = time.time() if now is None else now
    ensure_log(conn)
    results: List[Dict[str, Any]] = []
    for spec in specs:
        try:
            body = audit_chain.sign_anchor(conn, spec.key_id, private_key=private_key)
        except ValueError as exc:
            results.append({"witness": spec.name, "ok": False, "detail": str(exc)})
            continue
        try:
            outcome = make(spec).publish(body)
            detail = str(outcome.get("note") or "anchored")
            _log(conn, spec.name, body["entries"], body["head"], True, detail, when)
            results.append({"witness": spec.name, "ok": True, "entries": body["entries"], "detail": detail})
        except WitnessError as exc:
            _log(conn, spec.name, body["entries"], body["head"], False, str(exc), when)
            results.append({"witness": spec.name, "ok": False, "entries": body["entries"], "detail": str(exc)})
        except Exception as exc:                                        # noqa: BLE001 - a witness must never be able to crash the daemon
            _log(conn, spec.name, body["entries"], body["head"], False, type(exc).__name__, when)
            results.append({"witness": spec.name, "ok": False, "entries": body["entries"], "detail": type(exc).__name__})
    conn.commit()
    return results


# ------------------------------------------------------------------ what is true now

def _public_hex() -> Optional[str]:
    configured = (os.getenv(audit_chain.PUBKEY_ENV) or "").strip().lower()
    if configured:
        return configured
    try:
        key = audit_chain.load_signing_key()
        return audit_chain._public_hex(key) if key is not None else None
    except Exception:                                                   # noqa: BLE001
        return None


def verify_anchor_signature(anchor: Dict[str, Any], public_hex: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        message = audit_chain.anchor_message(anchor["key_id"], int(anchor["entries"]), anchor["head"], anchor["signed_at"])
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(anchor["signature"]), message.encode("utf-8"))
        return True
    except Exception:                                                   # noqa: BLE001
        return False


def check_witnesses(conn: sqlite3.Connection, specs: Optional[List[WitnessSpec]] = None) -> List[Dict[str, Any]]:
    """Ask every witness what it holds and compare it with this chain: heads that no longer match (rewritten or truncated), conflicts the witness recorded, and anchors whose
    signature does not verify with this host's public key (a forged entry at the witness)."""
    specs = specs_from_env() if specs is None else specs
    public = _public_hex()
    report: List[Dict[str, Any]] = []
    for spec in specs:
        try:
            held = make(spec).fetch()
        except WitnessError as exc:
            report.append({"witness": spec.name, "reachable": False, "ok": False, "checked": 0, "problems": [str(exc)]})
            continue
        result = audit_chain.check_anchors(conn, held)
        problems = list(result["problems"])
        if public:
            bad = [a for a in held.get("anchors", []) if "signature" in a and not verify_anchor_signature(a, public)]
            if bad:
                problems.append(f"{len(bad)} anchor(s) at the witness do not verify with this host's public key (forged or from another key)")
        report.append({"witness": spec.name, "reachable": True, "ok": not problems, "checked": result["checked"], "problems": problems,
                       "highest_anchored": max((int(a["entries"]) for a in held.get("anchors", [])), default=0)})
    return report


def status(conn: sqlite3.Connection, specs: Optional[List[WitnessSpec]] = None, now: Optional[float] = None, stale_after_s: Optional[float] = None) -> Dict[str, Any]:
    """What an auditor should be told right now about how well the log is protected, in numbers."""
    when = time.time() if now is None else now
    try:
        specs = specs_from_env() if specs is None else specs
        problem = ""
    except (WitnessError, ValueError) as exc:
        specs, problem = [], f"the witness configuration is unusable ({exc})"
    ensure_log(conn)
    head = audit_chain.chain_head(conn)
    interval = float(os.environ.get(INTERVAL_ENV) or 3600)
    limit = stale_after_s if stale_after_s is not None else interval * 2 + 60
    witnesses = []
    for spec in specs:
        ok = conn.execute("SELECT entries, at FROM audit_anchor_log WHERE witness = ? AND ok = 1 ORDER BY id DESC LIMIT 1", (spec.name,)).fetchone()
        last = conn.execute("SELECT ok, detail, at FROM audit_anchor_log WHERE witness = ? ORDER BY id DESC LIMIT 1", (spec.name,)).fetchone()
        age = when - ok[1] if ok else None
        witnesses.append({"name": spec.name, "type": spec.type, "last_anchored_entries": ok[0] if ok else None, "last_anchored_age_s": round(age, 1) if age is not None else None,
                          "fresh": bool(ok and age is not None and age <= limit), "last_attempt_ok": bool(last[0]) if last else None,
                          "last_attempt_detail": last[1] if last else None})
    fresh = [w for w in witnesses if w["fresh"]]
    newest = max((w["last_anchored_entries"] or 0 for w in witnesses), default=0)
    head_seq = int(head["seq"]) if head else 0
    return {"configured": len(specs), "problem": problem, "fresh_witnesses": len(fresh), "witnesses": witnesses, "head_seq": head_seq,
            "rows_not_yet_anchored": max(0, head_seq - newest) if specs else head_seq,
            "tamper_evident_against_host_compromise": bool(fresh),
            "independent_witnesses": len(fresh), "stale_after_s": round(limit),
            "plain": _plain(len(specs), len(fresh), head_seq, newest)}


def _plain(configured: int, fresh: int, head_seq: int, newest: int) -> str:
    if not configured:
        return "no witness is configured: a rewrite of the whole log by someone with the host's root would not be noticed"
    if not fresh:
        return "no witness has received the head recently: treat the log as tamper-EVIDENT only against edits, not against a rewrite of everything"
    window = max(0, head_seq - newest)
    text = (f"{fresh} independent witness(es) hold a recent signed head; the {window} row(s) newer than the newest anchor are the window an attacker "
            "with the host's root could still rewrite unnoticed")
    return text + ("" if fresh >= 2 else "; with only one witness, a compromise of that one party defeats it: add a second")


# ------------------------------------------------------------------ a proof anyone can check

def export_proof(conn: sqlite3.Connection, from_seq: int = 1, to_seq: Optional[int] = None, include_content: bool = True, witnesses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """A self-contained bundle: the chain rows from..to (with their content when asked), the signer's public key, the anchors known to the witnesses. Verified by
    scripts/verify_audit_bundle.py with no database and no Delentia code."""
    audit_chain.ensure_schema(conn)
    head = audit_chain.chain_head(conn)
    if head is None:
        raise ValueError("the audit chain is empty")
    last = int(to_seq or head["seq"])
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT c.seq, c.audit_id, c.prev_hash, c.row_hash, c.signature_hex, c.signer_fingerprint, t.entity_type, t.entity_id, t.action, t.actor, t.changes, t.created_at "
                        "FROM audit_chain c JOIN audit_trail t ON t.id = c.audit_id WHERE c.seq BETWEEN ? AND ? ORDER BY c.seq", (int(from_seq), last)).fetchall()
    out_rows = []
    for r in rows:
        item = {"seq": r["seq"], "audit_id": r["audit_id"], "prev_hash": r["prev_hash"], "row_hash": r["row_hash"], "signature_hex": r["signature_hex"],
                "signer_fingerprint": r["signer_fingerprint"]}
        if include_content:
            item.update({"entity_type": r["entity_type"], "entity_id": r["entity_id"], "action": r["action"], "actor": r["actor"], "changes": r["changes"], "created_at": r["created_at"]})
        out_rows.append(item)
    return {"format": "delentia-audit-bundle:v1", "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "genesis_hash": audit_chain.GENESIS_HASH,
            "signer_public_key": _public_hex(), "content_included": include_content, "from_seq": int(from_seq), "to_seq": last, "head": head,
            "rows": out_rows, "witnesses": witnesses or []}
