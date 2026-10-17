"""
A governed episode in its own process, for the tests that kill it for real (episode-level resume, DAAES TC-010 beyond the approval).

    python -m research.daaes.episode_child run    --home H --world W --hang-at N [--after-effect] [--hang-before-decision N]
    python -m research.daaes.episode_child resume --home H --world W --episode-id ID [--allow-unknown]

`run` executes a scripted episode (read the orders, save three receipts, finish) and, at the chosen point, writes `hang.flag` and sleeps forever; the parent then terminates the process the hard way
(TerminateProcess / SIGKILL), so nothing after that line runs and nothing is cleaned up. `resume` is the NEXT process: it asks the governed loop to continue the interrupted episode and prints one JSON line.
The tool that "changes something" appends a receipt to a file on disk, so what really happened is visible to the parent without trusting the agent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from research.daaes import delentia_session as ds


class World:
    def __init__(self, root: Path, hang_at: int = 0, after_effect: bool = False) -> None:
        self.root, self.hang_at, self.after_effect = Path(root), hang_at, after_effect
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipts = self.root / "receipts.jsonl"
        self.calls = 0

    async def list_tools(self):
        return [ds._Tool("delentia_read_repo_file"), ds._Tool("delentia_save_exchange_file")]

    def _hang(self) -> None:
        (self.root / "hang.flag").write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(3600)

    async def call_tool(self, name, args):
        self.calls += 1
        if name == "delentia_save_exchange_file":
            if self.hang_at == self.calls and not self.after_effect:
                self._hang()
            with open(self.receipts, "a", encoding="utf-8") as f:
                f.write(json.dumps({"op": args.get("filename"), "pid": os.getpid()}) + "\n")
                f.flush()
                os.fsync(f.fileno())
            if self.hang_at == self.calls and self.after_effect:
                self._hang()
            return ds._Result({"ok": True, "saved": args.get("filename")})
        if self.hang_at == self.calls:
            self._hang()
        return ds._Result({"ok": True, "content": "orders: 1, 2, 3" if "receipts" not in str(args.get("relative_path")) else self.receipts.read_text(encoding="utf-8") if self.receipts.exists() else ""})

    def effects(self):
        return [json.loads(line)["op"] for line in self.receipts.read_text(encoding="utf-8").splitlines()] if self.receipts.exists() else []


def call(tool, args):
    return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": "step"}


FINISH = {"action": "finish", "reasoning": "done", "final_answer": "all done", "tool_name": None, "tool_args": {}}
GOAL = "Process the three orders and save a receipt file for each"


def save(n):
    return call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{n}.txt", "content": "x"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("run", "resume"))
    ap.add_argument("--home", required=True)
    ap.add_argument("--world", required=True)
    ap.add_argument("--hang-at", type=int, default=0)
    ap.add_argument("--after-effect", action="store_true")
    ap.add_argument("--hang-before-decision", type=int, default=0)
    ap.add_argument("--episode-id", default="")
    ap.add_argument("--allow-unknown", action="store_true")
    args = ap.parse_args()
    os.environ["DELENTIA_FDIA_POLICY_DEFAULT"] = "none"
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    world = World(Path(args.world), hang_at=args.hang_at if args.mode == "run" else 0, after_effect=args.after_effect)
    with ds.data_home(Path(args.home)):
        persistence = ControlPlanePersistence(db_path=str(Path(args.home) / "agentic.db"))
        loop = build_governed_loop(ds.NullKernel(), namespace="alice", max_iterations=12, persistence=persistence, mcp_server=world, conversation_turns=0)
        loop._route_enabled = False                                  # type: ignore[attr-defined]
        if args.mode == "run":
            decisions = [call("delentia_read_repo_file", {"relative_path": "orders.csv"}), save(1), save(2), save(3), FINISH]
            if args.hang_before_decision:
                original = decisions[args.hang_before_decision - 1]
                decisions[args.hang_before_decision - 1] = lambda g, h, ctx, d=original: (world._hang(), d)[1]
            with ds.scripted_model(decisions):
                result = asyncio.run(loop.run(GOAL))
            print("RESULT " + json.dumps({"stopped_reason": result["stopped_reason"], "effects": world.effects(), "episode_id": loop._episode_id}))
            return 0
        done = set(world.effects())
        todo = [n for n in (1, 2, 3) if f"order-{n}.txt" not in done]
        decisions = [call("delentia_read_repo_file", {"relative_path": "receipts.jsonl"}), *[save(n) for n in todo], FINISH]   # looks at what really happened FIRST
        with ds.scripted_model(decisions):
            out = asyncio.run(loop.resume_interrupted(args.episode_id, allow_unknown=args.allow_unknown))
        print("RESULT " + json.dumps({"resumed": out.get("resumed"), "reason": out.get("reason"), "unknown": out.get("unknown"), "stopped_reason": out.get("stopped_reason"),
                                      "effects": world.effects(), "model_calls": None}, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
