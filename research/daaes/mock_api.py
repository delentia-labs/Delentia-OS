"""
The mock order API of TC-010: a SEPARATE PROCESS with its own durable receipt table, so killing the agent process never touches it.

    python -m research.daaes.mock_api --db <file.sqlite> --markers <dir> --port-file <file>

POST /commit    {operation_id, business_key, payload}
                  first time        -> the effect is committed, a receipt is stored, 200 {"status":"committed","replayed":false,"receipt":{...}}
                  same id, same payload -> no new effect, 200 {"replayed":true,"receipt":<the stored one>}   (idempotency key honoured)
                  same id, other payload -> 409 (key reuse with a different payload)
                header X-Hold-Ms: after committing, the reply is held for that long (the "in flight" window): the file `api_committed_holding` appears in the markers folder
GET  /receipt/<operation_id>   200 receipt | 404
GET  /effects                  every committed effect (the oracle reads the database directly, not this)

Tables: effects (one row per committed operation: the business effect), attempts (one row per request, replays included: the cost of recovery).
The oracle's definition of a DUPLICATE EFFECT is more than one effect row for the same business_key, whatever their operation ids are.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        conn = sqlite3.connect(path)
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS effects (seq INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT UNIQUE NOT NULL, business_key TEXT NOT NULL, payload_hash TEXT NOT NULL, committed_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT, outcome TEXT NOT NULL, at REAL NOT NULL);
        """)
        conn.commit()
        conn.close()

    def commit(self, operation_id: str, business_key: str, payload: Any) -> Dict[str, Any]:
        with self.lock:
            conn = sqlite3.connect(self.path)
            try:
                h = payload_hash(payload)
                row = conn.execute("SELECT seq, payload_hash, committed_at, business_key FROM effects WHERE operation_id = ?", (operation_id,)).fetchone()
                if row:
                    if row[1] != h:
                        conn.execute("INSERT INTO attempts (operation_id, outcome, at) VALUES (?, 'conflict', ?)", (operation_id, time.time()))
                        conn.commit()
                        return {"http": 409, "error": "idempotency key reused with a different payload"}
                    conn.execute("INSERT INTO attempts (operation_id, outcome, at) VALUES (?, 'replayed', ?)", (operation_id, time.time()))
                    conn.commit()
                    return {"http": 200, "status": "committed", "replayed": True, "receipt": {"operation_id": operation_id, "seq": row[0], "payload_hash": row[1], "business_key": row[3]}}
                now = time.time()
                cur = conn.execute("INSERT INTO effects (operation_id, business_key, payload_hash, committed_at) VALUES (?, ?, ?, ?)", (operation_id, business_key, h, now))
                conn.execute("INSERT INTO attempts (operation_id, outcome, at) VALUES (?, 'committed', ?)", (operation_id, now))
                conn.commit()
                return {"http": 200, "status": "committed", "replayed": False, "receipt": {"operation_id": operation_id, "seq": cur.lastrowid, "payload_hash": h, "business_key": business_key}}
            finally:
                conn.close()

    def receipt(self, operation_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.path)
        try:
            row = conn.execute("SELECT seq, payload_hash, business_key FROM effects WHERE operation_id = ?", (operation_id,)).fetchone()
            conn.execute("INSERT INTO attempts (operation_id, outcome, at) VALUES (?, 'lookup', ?)", (operation_id, time.time()))
            conn.commit()
            return {"operation_id": operation_id, "seq": row[0], "payload_hash": row[1], "business_key": row[2]} if row else None
        finally:
            conn.close()


def make_handler(store: Store, markers: Path) -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, code: int, body: Dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass                                            # the client was killed while waiting: the effect is already committed, which is the point

        def do_POST(self) -> None:
            if self.path != "/commit":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            result = store.commit(body["operation_id"], body["business_key"], body["payload"])
            hold = int(self.headers.get("X-Hold-Ms") or 0)
            if result["http"] == 200 and not result["replayed"] and hold > 0:
                (markers / "api_committed_holding").write_text(body["operation_id"], encoding="utf-8")
                time.sleep(hold / 1000.0)
            code = result.pop("http")
            self._send(code, result)

        def do_GET(self) -> None:
            if self.path.startswith("/receipt/"):
                found = store.receipt(self.path.split("/", 2)[2])
                return self._send(200, found) if found else self._send(404, {"error": "no receipt"})
            if self.path == "/health":
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--markers", required=True)
    parser.add_argument("--port-file", required=True)
    args = parser.parse_args()
    markers = Path(args.markers)
    markers.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Store(args.db), markers))
    Path(args.port_file).write_text(str(server.server_address[1]), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
