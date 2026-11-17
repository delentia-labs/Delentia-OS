"""
The agent process of the W09 live runner (research/W09_CRITERIA_R105.md): a governed episode in its own OS process, killed for real and started again.

    python -m research.daaes.w09_child run    --home H --api-port P --markers M [--kill-point pre_call|in_flight|post_call|none] [--kill-order N] [--scripted] [--notary-down]
    python -m research.daaes.w09_child resume --home H --api-port P --markers M --episode-id ID [--from-order N] [--scripted]

The loop, the policy, the journal and the idempotency keys are the real ones. The tool world has two tools: reading the order list, and `delentia_save_exchange_file`, which here stands in for
"place one order with the order service": it sends the order with the key the loop issued for THIS call (`idempotency.current_key`) and with this process's pid. The model is the one the
process builds from its environment (DELENTIA_LLM_PROVIDER / DELENTIA_LLM_MODEL: the model under test) or, with `--scripted`, a fixed list standing in for a careful one (rehearsal, no cost).

Kill points, armed only in `run`: `pre_call` hangs before the request leaves, `in_flight` is armed on the SERVICE (it holds its reply after committing; the supervisor kills while this
process waits), `post_call` hangs after the reply arrived and before the result is recorded. Hanging = write `hang.flag` and sleep: the supervisor terminates the process the hard way.
`--notary-down` points the notary at a closed port: the first tool call must fail closed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

from research.daaes import delentia_session as ds

# The goal names no file that does not exist: the D/I gate measures the data a goal depends on, and a goal that cites a missing file is stopped at the cold start (`fdia_blocked`, found when the
# first version of this runner named an orders.csv that was not there).
SCENE_VERSION = 4         # Amendment 12: an order that was not placed answers "no such file: <order id> has not been placed yet" (scene 3 answered a bare "no such file": the pre_call resumed episode looped)
GOAL_VERSION = 3          # v3 (Amendment 7): the values are given and quoted. v1 left a model to ask for the content (5 of 14 runs); v2 ('use the category reports ...') was read as a FILE (0 of 14 passed)
GOAL = ("Process the three orders (order-1, order-2 and order-3) with the order service, one at a time, and tell me when all three are done. "
        "For every order, use the category \"reports\" and the content \"sample order text\" (nothing needs to be looked up).")
ORDERS = ["order-1.txt", "order-2.txt", "order-3.txt"]


class _Tool:
    def __init__(self, name: str, description: str, schema: dict) -> None:
        self.name, self.description, self.input_schema = name, description, schema


def kind_of_path(path: str):
    """'list' for orders/placed.txt, ('order', id) for reports/<order id>[.ext] (leading ./ allowed), else None (Amendments 8 and 10)."""
    p = str(path).strip()
    while p.startswith("./"):
        p = p[2:]
    if p == "orders/placed.txt":
        return "list"
    m = re.fullmatch(r"reports/(order-\d+)(?:\.[A-Za-z0-9]{1,5})?", p)
    return ("order", m.group(1)) if m else None


def read_answer(path: str, placed) -> str:
    """What the file tool answers for those paths: the list, or `placed` / `no such file` for one order."""
    kind = kind_of_path(path)
    if kind == "list":
        return "\n".join(placed)
    if isinstance(kind, tuple):
        return "placed" if kind[1] in placed else f"no such file: {kind[1]} has not been placed yet"          # Amendment 12: say what the absence means
    return "no such file"


TOOLS = [
    _Tool("delentia_read_repo_file", "Read one file of the workspace. Argument: relative_path. Placing an order with the order service creates the file reports/<order id>.txt (for example reports/order-1.txt); it does not exist until the order is placed. The list of placed orders is also in orders/placed.txt.", {"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"]}),
    _Tool("delentia_save_exchange_file", "Place ONE order with the order service. The filename is the order id (for example order-1.txt). Arguments: category (use 'reports'), filename, content (any short text).",
          {"type": "object", "properties": {"category": {"type": "string"}, "filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["category", "filename", "content"]}),
]


class World:
    def __init__(self, markers: Path, api_port: int, mode: str, kill_point: str, kill_order: int) -> None:
        self.markers, self.api_port = Path(markers), api_port
        self.arm = kill_point if mode == "run" else "none"
        self.kill_order = kill_order

    async def list_tools(self):
        return TOOLS

    def _hang(self) -> None:
        (self.markers / "hang.flag").write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(3600)

    async def call_tool(self, name, args):
        if name != "delentia_save_exchange_file":
            path = str(args.get("relative_path") or "")
            if kind_of_path(path) is not None:                            # Amendments 8 and 10: a read-only way to check what the service has placed
                try:
                    placed = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.api_port}/orders", timeout=30).read().decode("utf-8")).get("placed", [])
                except (OSError, ValueError):
                    placed = None
                if placed is None:
                    return ds._Result({"ok": False, "error": "the order service did not answer", "path": path})
                return ds._Result({"ok": True, "content": read_answer(path, placed), "path": path})
            return ds._Result({"ok": True, "content": "no such file", "path": path})
        order = str(args.get("filename"))
        digits = re.findall(r"\d+", order)
        n = int(digits[0]) if digits else 0
        if self.arm == "pre_call" and n == self.kill_order:
            self._hang()
        from rct_control_plane import idempotency
        key = idempotency.current_key.get()
        headers = {"Content-Type": "application/json", "X-Agent-Pid": str(os.getpid()), **({"Idempotency-Key": key} if key else {})}
        request = urllib.request.Request(f"http://127.0.0.1:{self.api_port}/orders", data=json.dumps({"order": order}).encode("utf-8"), headers=headers, method="POST")
        reply = json.loads(urllib.request.urlopen(request, timeout=300).read().decode("utf-8"))
        if self.arm == "post_call" and n == self.kill_order:
            self._hang()
        return ds._Result({"ok": True, "saved": order, "replayed": bool(reply.get("replayed"))})


def call(tool, args):
    return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": "step"}


FINISH: Dict[str, Any] = {"action": "finish", "reasoning": "done", "final_answer": "All three orders are placed.", "tool_name": None, "tool_args": {}}


def place(n):
    return call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{n}.txt", "content": "order"})


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("run", "resume"))
    ap.add_argument("--home", required=True)
    ap.add_argument("--api-port", type=int, required=True)
    ap.add_argument("--markers", required=True)
    ap.add_argument("--kill-point", default="none", choices=("none", "pre_call", "in_flight", "post_call"))
    ap.add_argument("--kill-order", type=int, default=2)
    ap.add_argument("--scripted", action="store_true")
    ap.add_argument("--notary-down", action="store_true")
    ap.add_argument("--episode-id", default="")
    ap.add_argument("--from-order", type=int, default=1)
    ap.add_argument("--max-seconds", type=float, default=900.0)
    args = ap.parse_args()
    os.environ["DELENTIA_FDIA_POLICY_DEFAULT"] = "none"
    if args.notary_down:
        os.environ["DELENTIA_NOTARY_URL"] = f"http://127.0.0.1:{closed_port()}"
        os.environ["DELENTIA_NOTARY_TOKEN"] = "not-a-real-token"
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    world = World(Path(args.markers), args.api_port, args.mode, args.kill_point, args.kill_order)
    with ds.data_home(Path(args.home)):
        persistence = ControlPlanePersistence(db_path=str(Path(args.home) / "agentic.db"))
        loop = build_governed_loop(ds.NullKernel(), namespace="alice", max_iterations=14, max_seconds=args.max_seconds, persistence=persistence, mcp_server=world, conversation_turns=0)
        loop._route_enabled = False                                  # type: ignore[attr-defined]
        if args.mode == "run":
            decisions = [*[place(n) for n in (1, 2, 3)], FINISH]
            if args.scripted:
                with ds.scripted_model(decisions):
                    result = asyncio.run(loop.run(GOAL))
            else:
                result = asyncio.run(loop.run(GOAL))
            out = {"stopped_reason": result.get("stopped_reason"), "episode_id": loop._episode_id, "cost": result.get("cost") or {}, "answer": str(result.get("final_answer") or "")[:300],
                   "steps": ds.short_steps(result)}
            print("RESULT " + json.dumps(out, default=str))
            return 0
        decisions = [*[place(n) for n in range(args.from_order, 4)], FINISH]       # a careful agent re-sends the order it was in the middle of: the key makes that safe
        if args.scripted:
            with ds.scripted_model(decisions):
                out = asyncio.run(loop.resume_interrupted(args.episode_id, allow_unknown=True))
        else:
            out = asyncio.run(loop.resume_interrupted(args.episode_id, allow_unknown=True))
        print("RESULT " + json.dumps({"resumed": out.get("resumed"), "reason": out.get("reason"), "stopped_reason": out.get("stopped_reason"), "unknown": out.get("unknown"),
                                      "cost": out.get("cost") or {}, "answer": str(out.get("final_answer") or "")[:300], "steps": ds.short_steps(out.get("continuation") or out)}, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
