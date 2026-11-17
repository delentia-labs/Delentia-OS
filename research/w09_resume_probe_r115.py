"""Free probe of the W09 scene (Amendment 8, rule P1): two local models, three states, the real resume note from episode_journal. Nothing is paid.
python -m research.w09_resume_probe_r115 qwen3:8b"""
import asyncio
import collections
import logging
import os
import sys
import time

logging.disable(logging.WARNING)
sys.path.insert(0, ".")
os.environ.update({"DELENTIA_LLM_PROVIDER": "ollama", "DELENTIA_LLM_MODEL": sys.argv[1], "DELENTIA_OLLAMA_THINK": "off", "DELENTIA_TOOL_MENU_FORMAT": "compact"})
from rct_control_plane import autonomous_loop, episode_journal  # noqa: E402
from rct_control_plane.autonomous_loop import LoopStep  # noqa: E402
from rct_control_plane.llm_provider import get_default_provider  # noqa: E402
from research.daaes import w09_child  # noqa: E402

TOOLS = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in w09_child.TOOLS]
SIDE = frozenset({"delentia_save_exchange_file"})
ARGS = {"category": "reports", "filename": "order-2.txt", "content": "sample order text"}


class _S:                                   # the fields note_for reads
    def __init__(self, n, tool, args, state, preview="", idem=None):
        self.n, self.tool, self.args, self.state, self.preview, self.idem = n, tool, args, state, preview, idem


class _Ep:
    def __init__(self, steps):
        self.steps = steps


def place(n):
    return {"category": "reports", "filename": f"order-{n}.txt", "content": "sample order text"}


def step(i, tool, args, result):
    return LoopStep(iteration=i, tool_name=tool, tool_args=args, tool_result=result, llm_reasoning="")


# S1: order 1 done, order 2 was about to run when the process stopped.   S2: same, and the list file now shows order-2 (the service committed it).
NOTE = episode_journal.note_for(_Ep([_S(1, "delentia_save_exchange_file", place(1), "done", "saved order-1.txt"), _S(2, "delentia_save_exchange_file", place(2), "dangling", idem="k2")]), SIDE, True)


def classify(state, decision, called):
    tool = decision.get("tool_name") or ("finish" if decision.get("action") == "finish" else "other")
    return tool, (decision.get("tool_args") or {})


async def episode(state, provider, max_calls):
    """Drive up to max_calls decisions; the world answers like the W09 agent world. Returns the list of (tool, filename-or-path)."""
    history, placed, trace = [], (["order-1"] if state in ("S1", "S2") else []), []
    if state == "S2":
        placed.append("order-2")
    for i in range(max_calls):
        d = await autonomous_loop.decide_next_action(w09_child.GOAL, history, TOOLS, llm_provider=provider, extra_context=NOTE if state != "S0" else "")
        tool, args = classify(state, d, None)
        trace.append((tool, args.get("filename") or args.get("relative_path")))
        if tool == "finish" or tool == "other":
            break
        if tool == "delentia_read_repo_file":
            p = str(args.get("relative_path") or "").strip().lstrip("./")
            res = {"ok": True, "content": "\n".join(placed)} if p == "orders/placed.txt" else {"ok": True, "content": "no such file"}
        elif tool == "delentia_save_exchange_file":
            o = str(args.get("filename") or "").rsplit(".", 1)[0]
            if o and o not in placed:
                placed.append(o)
            res = {"ok": True, "saved": args.get("filename")}
        else:
            res = {"ok": False, "error": "unknown tool"}
        history.append(step(i + 1, tool, args, res))
    return trace


async def main():
    p = get_default_provider()
    out = {}
    for state, max_calls in (("S0", 1), ("S1", 3), ("S2", 4)):
        ok = 0
        for r in range(3):
            t0 = time.time()
            tr = await episode(state, p, max_calls)
            names = [(a or "").rsplit(".", 1)[0] for tool, a in tr if tool == "delentia_save_exchange_file"]
            reads = [i for i, (tool, a) in enumerate(tr) if tool == "delentia_read_repo_file"]
            if state == "S0":
                good = bool(tr) and tr[0][0] == "delentia_save_exchange_file"
            elif state == "S1":
                good = "order-2" in names
            else:                                       # S2: never re-place order 2 before reading the list file, or places it again (allowed); must reach order 3
                good = "order-3" in names                    # S2: checking first or placing order 2 again with the same arguments are both allowed; the model must reach order 3
            ok += bool(good)
            print("  ", state, r + 1, "ok" if good else "FAIL", tr, "%.0fs" % (time.time() - t0), flush=True)
        out[state] = ok
    print("PROBE", sys.argv[1], collections.OrderedDict(out), "(rule: each state >= 5 of 6 over the two models, i.e. >= 2.5 of 3 per model; the sum is read by the caller)", flush=True)


asyncio.run(main())
