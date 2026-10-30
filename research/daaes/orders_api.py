"""
The order service of W09 (research/W09_CRITERIA_R105.md): a SEPARATE PROCESS with its own durable ledger, so killing the agent never touches it.

    python -m research.daaes.orders_api --db <file.sqlite> --markers <dir> --port-file <file>

POST /orders   {"order": "order-1.txt"}   header Idempotency-Key (the key the governed loop issued), header X-Agent-Pid (who sent it)
                 a key it has not seen   -> the order is committed (one ledger row), 200 {"replayed": false}
                 a key it has seen        -> NO new effect, 200 {"replayed": true}
                 no key at all            -> every request is a new order (the documented limit: a service that cannot recognise a repeat repeats the effect)
GET  /health

Every request is also appended to `<markers>/requests.jsonl` (time, order, key, sender pid, replayed): the oracle needs to know what was ASKED, not only what was done.
Hold control: if `<markers>/hold.json` holds {"order": ..., "ms": ...}, the reply to the first COMMIT of that order is held for that long after the effect is committed and the file
`api_committed_holding` appears: the "in flight" window in which the supervisor kills the agent.

The ledger is the oracle's source: `effects` has one row per committed operation; a DUPLICATE EFFECT is more than one row for the same business key (the order), whatever the keys are.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from research.daaes.mock_api import Store


def make_handler(store: Store, markers: Path) -> type:
    log_lock = threading.Lock()

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
            if self.path != "/orders":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            order = str(body.get("order"))
            key = self.headers.get("Idempotency-Key")
            result = store.commit(key or f"nokey-{uuid.uuid4().hex}", order, {"order": order})
            with log_lock, open(markers / "requests.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "order": order, "key": key, "pid": self.headers.get("X-Agent-Pid"), "replayed": bool(result.get("replayed")), "http": result["http"]}) + "\n")
            hold_file = markers / "hold.json"
            if result["http"] == 200 and not result.get("replayed") and hold_file.exists():
                try:
                    hold = json.loads(hold_file.read_text(encoding="utf-8"))
                except ValueError:
                    hold = {}
                if hold.get("order") == order and int(hold.get("ms") or 0) > 0:
                    (markers / "api_committed_holding").write_text(order, encoding="utf-8")
                    time.sleep(int(hold["ms"]) / 1000.0)
            code = result.pop("http")
            self._send(code, result)

        def do_GET(self) -> None:
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
