"""
Audit notary: tier A2 for the agent runtime (Round 50).

A1 (audit_chain.py) signs audit rows with a key the agent's own process can
load, and the local shell sandbox is not a jail, so a compromised agent could
read that key and sign whatever it likes about itself. Tier A2 moves signing
into a separate process the agent can only *append to*:

    agent process  --(HTTP on 127.0.0.1, append only)-->  notary process
                                                          |- holds the signing key
                                                          |- own SQLite file
                                                          '- assigns seq, chains, signs

- The notary assigns the sequence number and previous hash itself, so the
  agent cannot insert, reorder or rewrite history, and never sees the key.
- Records carry hashes only (tool arguments, results, goals), never raw data,
  so personal data stays off the chain (PDPA; see CLAUDE.md).
- GovernedAutonomousLoop notarises at the dispatch chokepoint: before a tool
  runs (fail closed: no receipt, no call) and after it returns (result hash).

What A2 does not do: the dispatch gate still runs in the agent's process, so
code already inside it can lie about *future* calls; and whoever controls the
notary's host can rewrite the notary's file. Run the notary as a different OS
user (or on another machine) and anchor its head outside (tier A3,
`delentia notary anchor`) for those.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

NOTARY_URL_ENV = "DELENTIA_NOTARY_URL"
NOTARY_TOKEN_ENV = "DELENTIA_NOTARY_TOKEN"
NOTARY_KEY_ENV = "DELENTIA_NOTARY_KEY"
GENESIS = "0" * 64
MAX_RECORD_BYTES = 16 * 1024
_REPO_ROOT = Path(__file__).resolve().parent.parent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notary_log (
    seq        INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    record     TEXT NOT NULL,
    hash       TEXT NOT NULL,
    signature  TEXT NOT NULL,
    key_id     TEXT NOT NULL
);
"""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: Any) -> str:
    """SHA-256 of a value's canonical JSON (strings are hashed as-is)."""
    text = data if isinstance(data, str) else canonical(data)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry_hash(seq: int, ts: str, prev_hash: str, record_json: str) -> str:
    return hashlib.sha256(canonical([seq, ts, prev_hash, record_json]).encode("utf-8")).hexdigest()


def load_key(path: str) -> Any:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    p = Path(path).expanduser()
    try:
        inside = p.resolve().is_relative_to(_REPO_ROOT)
    except (OSError, ValueError):
        inside = False
    if inside:
        raise ValueError(f"refusing a notary key inside the repository ({_REPO_ROOT}); the agent can read it there")
    key = load_pem_private_key(p.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("the notary key must be an Ed25519 private key")
    return key


def public_hex(private_key: Any) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class NotaryStore:
    """The notary's own append-only log. Only the notary process opens it."""

    def __init__(self, db_path: str, private_key: Any, key_id: str):
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._key = private_key
        self.key_id = key_id
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        record_json = canonical(record)
        if len(record_json.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError(f"record larger than {MAX_RECORD_BYTES} bytes; send hashes, not content")
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT seq, hash FROM notary_log ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (row[0] + 1) if row else 1
            prev_hash = row[1] if row else GENESIS
            ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            h = entry_hash(seq, ts, prev_hash, record_json)
            sig = self._key.sign(bytes.fromhex(h)).hex()
            conn.execute("INSERT INTO notary_log (seq, ts, prev_hash, record, hash, signature, key_id) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (seq, ts, prev_hash, record_json, h, sig, self.key_id))
        return {"seq": seq, "ts": ts, "hash": h, "signature": sig, "key_id": self.key_id}

    def head(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT seq, hash FROM notary_log ORDER BY seq DESC LIMIT 1").fetchone()
        return {"seq": row[0], "row_hash": row[1]} if row else None


@dataclass
class NotaryReport:
    ok: bool
    entries: int
    head_seq: Optional[int]
    head_hash: Optional[str]
    first_bad_seq: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def verify_log(db_path: str, public_key_hex: str) -> NotaryReport:
    """Anyone with the notary's public key can re-check the whole log."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    with sqlite3.connect(str(Path(db_path).expanduser())) as conn:
        rows = conn.execute("SELECT seq, ts, prev_hash, record, hash, signature FROM notary_log ORDER BY seq").fetchall()
    expected_seq, prev = 1, GENESIS
    for seq, ts, prev_hash, record, h, sig in rows:
        def fail(reason: str) -> NotaryReport:
            return NotaryReport(False, len(rows), rows[-1][0], rows[-1][4], seq, reason)
        if seq != expected_seq:
            return fail(f"sequence gap: expected {expected_seq}, found {seq} (an entry was removed)")
        if prev_hash != prev:
            return fail("broken link: prev_hash does not match the previous entry")
        if entry_hash(seq, ts, prev_hash, record) != h:
            return fail(f"entry {seq} was modified after it was written")
        try:
            verifier.verify(bytes.fromhex(sig), bytes.fromhex(h))
        except Exception:
            return fail(f"entry {seq}: signature does not verify with the given public key")
        expected_seq, prev = seq + 1, h
    head = rows[-1] if rows else None
    return NotaryReport(True, len(rows), head[0] if head else None, head[4] if head else None)


# ---------------------------------------------------------------------------
# HTTP server (loopback only) and client
# ---------------------------------------------------------------------------

def make_server(store: NotaryStore, host: str = "127.0.0.1", port: int = 8765,
                token: Optional[str] = None) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("the notary listens on loopback only; put it on another machine behind your own tunnel if needed")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # keep stderr quiet
            pass

        def _reply(self, status: int, body: Dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            if not token:
                return True
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given, f"Bearer {token}")

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                return self._reply(200, {"status": "ok", "key_id": store.key_id})
            if not self._authorised():
                return self._reply(401, {"error": "unauthorised"})
            if self.path == "/head":
                return self._reply(200, {"head": store.head(), "key_id": store.key_id})
            return self._reply(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            # Read the body (bounded) before any reply: answering with an
            # unread body makes some clients (Windows) see a connection reset
            # instead of the 401/404/413.
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(min(max(length, 0), 1024 * 1024))
            if length > len(raw):
                self.close_connection = True
            if self.path != "/append":
                return self._reply(404, {"error": "not_found"})
            if not self._authorised():
                return self._reply(401, {"error": "unauthorised"})
            if length <= 0 or length > MAX_RECORD_BYTES:
                return self._reply(413, {"error": "record missing or too large; send hashes, not content"})
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                return self._reply(400, {"error": "invalid_json"})
            if not isinstance(record, dict) or not isinstance(record.get("kind"), str):
                return self._reply(400, {"error": "record must be an object with a string 'kind'"})
            try:
                return self._reply(201, store.append(record))
            except ValueError as exc:
                return self._reply(413, {"error": str(exc)})

    return ThreadingHTTPServer((host, port), Handler)


class NotaryUnavailable(RuntimeError):
    """The notary could not be reached or refused the record."""


def token_from_env() -> Optional[str]:
    """The notary token from DELENTIA_NOTARY_TOKEN, or from the file named by DELENTIA_NOTARY_TOKEN_FILE (a Docker/Kubernetes secret is
    a file, and a secret in an environment variable shows up in `docker inspect`)."""
    value = os.getenv(NOTARY_TOKEN_ENV)
    if value:
        return value
    path = os.getenv(NOTARY_TOKEN_ENV + "_FILE")
    if path:
        text = Path(path).read_text(encoding="utf-8").strip()
        return text or None
    return None


class NotaryClient:
    """What the agent process holds: a URL (and optional token), never a key."""

    def __init__(self, url: str, token: Optional[str] = None, timeout: float = 3.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Optional["NotaryClient"]:
        url = os.getenv(NOTARY_URL_ENV)
        return cls(url, token_from_env()) if url else None

    async def append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        from rct_control_plane import http_client
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            async with http_client.async_client(timeout=self.timeout) as client:
                resp = await client.post(f"{self.url}/append", json=record, headers=headers)
        except Exception as exc:
            raise NotaryUnavailable(f"notary unreachable at {self.url}: {exc}") from exc
        if resp.status_code != 201:
            raise NotaryUnavailable(f"notary refused the record ({resp.status_code}): {resp.text[:200]}")
        receipt: Dict[str, Any] = resp.json()
        return receipt


def records_for_episode(db_path: str, namespace: str) -> List[Dict[str, Any]]:
    """Convenience for audits and tests: the decoded records of one namespace."""
    with sqlite3.connect(str(Path(db_path).expanduser())) as conn:
        rows = conn.execute("SELECT seq, record FROM notary_log ORDER BY seq").fetchall()
    out = []
    for seq, record in rows:
        rec = json.loads(record)
        if rec.get("namespace") == namespace:
            out.append({"seq": seq, **rec})
    return out


def generate_key(private_key_path: str) -> str:
    """Creates the notary key outside the repository; returns its public key hex."""
    from rct_control_plane.audit_chain import generate_signing_key
    return generate_signing_key(private_key_path)


# Tier A3 for the notary log: the same anchor protocol as audit_chain.py and
# delentia-guard ("delentia-audit-anchor:v1|key_id|entries|head|signed_at"),
# where entries = seq of the head entry. The witness must know the notary's
# public key under key_id (AUDIT_ANCHOR_KEYS_JSON on the fdia Worker).

def sign_anchor(db_path: str, key_id: str, private_key: Any, signed_at: Optional[str] = None) -> Dict[str, Any]:
    from rct_control_plane.audit_chain import anchor_message
    with sqlite3.connect(str(Path(db_path).expanduser())) as conn:
        row = conn.execute("SELECT seq, hash FROM notary_log ORDER BY seq DESC LIMIT 1").fetchone()
    if row is None:
        raise ValueError("the notary log is empty; nothing to anchor")
    when = signed_at or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    message = anchor_message(key_id, int(row[0]), row[1], when)
    return {"key_id": key_id, "entries": int(row[0]), "head": row[1], "signed_at": when,
            "signature": private_key.sign(message.encode("utf-8")).hex()}


def check_anchors(db_path: str, witness: Dict[str, Any]) -> Dict[str, Any]:
    problems = []
    anchors = witness.get("anchors") or []
    with sqlite3.connect(str(Path(db_path).expanduser())) as conn:
        for a in anchors:
            row = conn.execute("SELECT hash FROM notary_log WHERE seq = ?", (int(a["entries"]),)).fetchone()
            if row is None:
                problems.append(f"log has no entry {a['entries']}, but it was anchored at {a.get('received_at')} (truncated)")
            elif row[0] != a["head"]:
                problems.append(f"entry {a['entries']} hashes to {row[0][:12]}..., anchored {a['head'][:12]}... "
                                f"at {a.get('received_at')} (rewritten)")
    conflicts = witness.get("conflicts") or []
    if conflicts:
        problems.append(f"the witness recorded {len(conflicts)} conflicting anchor(s) (rollback/fork) for this key")
    return {"ok": not problems, "checked": len(anchors), "problems": problems}


def anchor_once(db_path: str, key_id: str, private_key: Any, url: str,
                last_entries: Optional[int] = None) -> Dict[str, Any]:
    """Publishes the head if it moved since last_entries. Never raises: the
    result says what happened, so a witness outage cannot stop the notary."""
    import httpx
    try:
        body = sign_anchor(db_path, key_id, private_key)
    except ValueError as exc:
        return {"anchored": False, "entries": last_entries, "reason": str(exc)}
    if last_entries is not None and body["entries"] <= last_entries:
        return {"anchored": False, "entries": last_entries, "reason": "head unchanged since the last anchor"}
    try:
        resp = httpx.post(f"{url.rstrip('/')}/v1/audit/anchor", json=body, timeout=20.0)
    except Exception as exc:
        return {"anchored": False, "entries": last_entries, "reason": f"witness unreachable: {exc}"}
    if resp.status_code not in (200, 201):
        return {"anchored": False, "entries": last_entries,
                "reason": f"witness refused ({resp.status_code}): {resp.text[:200]}"}
    return {"anchored": True, "entries": body["entries"], "head": body["head"]}


def start_anchor_loop(db_path: str, key_id: str, private_key: Any, url: str, every_seconds: float,
                      on_result: Optional[Any] = None) -> threading.Event:
    """Tier A3 on a schedule, run by the notary itself (it holds the key).
    Returns an Event; set it to stop the loop."""
    stop = threading.Event()

    def _loop() -> None:
        last: Optional[int] = None
        while not stop.is_set():
            result = anchor_once(db_path, key_id, private_key, url, last)
            if result.get("anchored"):
                last = result["entries"]
            if on_result is not None:
                on_result(result)
            stop.wait(every_seconds)

    threading.Thread(target=_loop, name="notary-anchor", daemon=True).start()
    return stop

