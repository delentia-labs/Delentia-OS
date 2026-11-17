"""Generates the Thai hints of the 17 synthetic external tools with the local model (Amendment 3), once. Output: research/tool_hints_th_synthetic_r115.json (committed, not edited by hand).

    python -m research.make_thai_hints_r115 [--model qwen3:8b]
"""
import argparse
import json
import time
from pathlib import Path

from rct_control_plane import tool_hints_th as th
from research import tool_menu_siblings_r114 as sib

OUT = Path(__file__).resolve().parent / "tool_hints_th_synthetic_r115.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=th.DEFAULT_MODEL)
    args = ap.parse_args()
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    tools = sib.synthetic_tools(spec["servers"])
    entries, times = {}, []
    for tool in tools:
        t0 = time.perf_counter()
        got = th.generate([tool], model=args.model)
        times.append(time.perf_counter() - t0)
        entries.update(got)
        print(f"{time.perf_counter() - t0:5.1f}s {tool['name'].replace('mcp__', '')}: {got.get(tool['name'], {}).get('hint', '(none)')}", flush=True)
        th.write(entries, OUT)                          # written after every tool: an interrupted run keeps what it has
    print(f"{len(entries)} of {len(tools)} tools have a hint; slowest {max(times):.1f}s, median {sorted(times)[len(times) // 2]:.1f}s")


if __name__ == "__main__":
    main()
