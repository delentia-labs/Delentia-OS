"""
Where do the prompt tokens go, and do the compressors in the system save any of them? (Round 64)

Every model call re-sends the whole prompt: the goal, the menu of tools, a fixed instruction block, the extra context and the history of the episode so far. What an
episode costs is therefore the SUM of the prompts of its calls, not one prompt. This script builds the real prompts with the real tools on a real workspace (no model is
called), counts tokens, and varies one thing at a time:

  menu         full / compact+ranked
  history      each earlier step written out / as a JSON-Patch delta against the step before (render_history, Round 41; used only when it is smaller)
  tool output  as returned / compressed by Delta v2 when it is over 6,000 characters and the saving is at least 20% (Round 48)
  cache        the share of every prompt that is byte-identical to the previous call's prompt (what a provider that caches a prefix could serve at the cheap rate)

Tokens are counted with tiktoken cl100k_base: an approximation of any provider's own tokenizer (it can differ by roughly +-15%), good for ratios, not for invoices.

    python scripts/measure_prompt_cost.py --out research/prompt_cost.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEMO_FILES = {
    "quotes/vendor_a.md": "# ใบเสนอราคา บริษัท สยามแอร์\nรายการ: ซ่อมระบบปรับอากาศ ชั้น 3\nราคารวม: 12,500 บาท\nระยะเวลาทำงาน: 5 วัน\nเงื่อนไข: ยืนราคา 30 วัน\n",
    "quotes/vendor_b.md": "# ใบเสนอราคา บริษัท ไทยคูลลิ่ง\nรายการ: ซ่อมระบบปรับอากาศ ชั้น 3\nราคารวม: 16,800 บาท\nระยะเวลาทำงาน: 3 วัน\nเงื่อนไข: ยืนราคา 30 วัน\n",
    "quotes/vendor_c.md": "# ใบเสนอราคา บริษัท บางกอกเทคนิค\nรายการ: ซ่อมระบบปรับอากาศ ชั้น 3\nราคารวม: 9,900 บาท\nระยะเวลาทำงาน: 9 วัน\nเงื่อนไข: ยืนราคา 30 วัน\n",
}
DEMO_GOAL = ("อ่านใบเสนอราคาในไฟล์ quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md ทำตารางเปรียบเทียบราคา แล้วสรุปว่าบริษัทไหนราคาไม่เกินงบ 15,000 บาท "
             "ห้ามแก้ไฟล์ต้นฉบับและห้ามส่งข้อมูลออกไป")


def tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:                                   # noqa: BLE001 - without tiktoken fall back to the usual characters/4 estimate and say so in the output
        return max(1, len(text) // 4)


def common_prefix_tokens(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return tokens(a[:n])


async def run(out_path: str | None) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="delentia-promptcost-"))
    repo = work / "repo"
    for rel, text in DEMO_FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    (repo / "big").mkdir()
    for i, name in enumerate(("report_a.md", "report_b.md", "report_c.md")):       # realistic larger documents: repeated structure, as real reports have
        (repo / "big" / name).write_text("\n".join(f"| row {j} | item {j % 17} | status {'ok' if j % 5 else 'late'} | owner team-{j % 9} | note {i}-{j} |" for j in range(520)), encoding="utf-8")
    (repo / "docs").mkdir()
    for name in ("README.md", "docs/whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md", "docs/whitepaper/DELENTIA_WHITEPAPER_3.0_TH.md"):     # real prose written by people, not generated rows
        (repo / "docs" / Path(name).name).write_text((ROOT / name).read_text(encoding="utf-8")[:30000], encoding="utf-8")
    os.environ.update({"DELENTIA_HOME": str(work / "data"), "DELENTIA_REPO_ROOT": str(repo)})
    for name in ("DELENTIA_TOOL_MENU", "DELENTIA_TOOL_MENU_FORMAT", "DELENTIA_WARM_RECALL", "DELENTIA_ALGORITHM_PIPELINE", "DELENTIA_UNTRUSTED_PATHS"):
        os.environ.pop(name, None)
    logging.disable(logging.CRITICAL)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:                                   # noqa: BLE001
        pass
    from rct_control_plane import autonomous_loop as al
    from rct_control_plane import tool_menu
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.mcp_server import _kernel, mcp

    tools = await mcp.list_tools()
    specs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]

    class Spy:
        def __init__(self) -> None:
            self.prompt = ""

        async def complete(self, prompt: str, *args: Any, **kwargs: Any) -> str:
            system = kwargs.get("system_prompt") or (args[0] if args else None)
            self.prompt = (system + "\n" if system else "") + prompt          # what is sent, in the order it is sent: the system message first
            return json.dumps({"action": "finish", "reasoning": "x", "final_answer": "x"})

    spy = Spy()

    async def prompt_for(goal: str, history: List[Any], menu: str, extra: str = "") -> str:
        os.environ.pop("DELENTIA_TOOL_MENU", None)
        os.environ.pop("DELENTIA_TOOL_MENU_FORMAT", None)
        available = specs
        if menu == "ranked":
            os.environ["DELENTIA_TOOL_MENU"] = "ranked"
            os.environ["DELENTIA_TOOL_MENU_FORMAT"] = "compact"
            available = tool_menu.maybe_ranked(goal, specs) or specs
        await al.decide_next_action(goal, history, available, spy, extra)
        return spy.prompt

    loop = build_governed_loop(_kernel, "promptcost", persistence=_kernel._persistence, mcp_server=mcp)
    loop._episode_evidence = []

    async def real_step(i: int, name: str, args: Dict[str, Any], goal: str, compress: bool) -> Any:
        raw = await mcp.call_tool(name, args)
        result = json.loads(raw.content[0].text)
        shown = loop._compress_tool_output(goal, name, args, result) if compress else result
        return al.LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result=shown, llm_reasoning="")

    report: Dict[str, Any] = {"tokenizer": "tiktoken cl100k_base (approximate)", "tools_in_registry": len(specs)}

    # 0. what a provider that caches a prompt prefix could reuse from one EPISODE to the next (two different goals, no history)
    other_goal = "Summarise the release checklist in docs/release/checklist.md in three bullet points."
    layouts = {}
    for layout in ("current", "cache_friendly"):
        if layout == "cache_friendly":
            os.environ["DELENTIA_PROMPT_LAYOUT"] = "cache_friendly"
        else:
            os.environ.pop("DELENTIA_PROMPT_LAYOUT", None)
        first = await prompt_for(DEMO_GOAL, [], "full")
        second = await prompt_for(other_goal, [], "full")
        layouts[layout] = {"prompt_tokens": tokens(first), "identical_prefix_tokens_across_two_goals": common_prefix_tokens(first, second),
                           "share_reusable_across_episodes": round(common_prefix_tokens(first, second) / tokens(first), 3)}
    os.environ.pop("DELENTIA_PROMPT_LAYOUT", None)
    report["layouts"] = layouts

    # 1. what one prompt is made of (no history)
    empty = await prompt_for(DEMO_GOAL, [], "full")
    compact = await prompt_for(DEMO_GOAL, [], "ranked")
    menu_full = tool_menu.format_menu(specs, compact=False)
    menu_compact = tool_menu.format_menu(tool_menu.rank_tools(DEMO_GOAL, specs, tool_menu.top_k()), compact=True)
    report["one_prompt"] = {
        "full_menu_prompt": tokens(empty), "compact_ranked_prompt": tokens(compact),
        "menu_only_full": tokens(menu_full), "menu_only_compact": tokens(menu_compact),
        "everything_but_the_menu": tokens(empty) - tokens(menu_full),
        "menu_share_of_full_prompt": round(tokens(menu_full) / tokens(empty), 3),
        "tools_in_compact_menu": len(tool_menu.rank_tools(DEMO_GOAL, specs, tool_menu.top_k())),
    }

    # 2. whole episodes: the sum of the prompts of every call
    scenarios = {
        "demo (3 small files, answer)": [("delentia_read_repo_file", {"relative_path": r}) for r in DEMO_FILES],
        "larger documents (3 files of ~30 KB each)": [("delentia_read_repo_file", {"relative_path": f"big/{n}", "max_bytes": 200000}) for n in ("report_a.md", "report_b.md", "report_c.md")],
        "natural prose (3 real documents of 30 KB: README, whitepaper EN, whitepaper TH)": [("delentia_read_repo_file", {"relative_path": f"docs/{n}", "max_bytes": 200000})
                                                                                          for n in ("README.md", "DELENTIA_WHITEPAPER_3.0_EN.md", "DELENTIA_WHITEPAPER_3.0_TH.md")],
        "search then read (30 matches, then one file)": [("delentia_search_repo_files", {"pattern": "row 1", "glob": "big/*.md", "max_results": 30}),
                                                          ("delentia_read_repo_file", {"relative_path": "big/report_a.md", "max_bytes": 200000})],
    }
    report["episodes"] = {}
    original_render = al.render_history

    def plain_render(history, delta_engine=None):                                 # every earlier step written out, as before Round 41
        return "\n".join(al._render_turn_full(st) for st in history) if history else "(no actions taken yet)"

    for name, calls in scenarios.items():
        goal = DEMO_GOAL
        variants: Dict[str, Dict[str, Any]] = {}
        for compress in (False, True):
            steps: List[Any] = []
            for i, (tool, args) in enumerate(calls):
                steps.append(await real_step(i, tool, args, goal, compress))
            for menu in ("full", "ranked"):
                for delta in (False, True):
                    al.render_history = original_render if delta else plain_render
                    try:
                        prompts = [await prompt_for(goal, steps[:k], menu) for k in range(len(steps) + 1)]       # the call before any step, ..., the call that answers
                    finally:
                        al.render_history = original_render
                    per_call = [tokens(pr) for pr in prompts]
                    shared = [common_prefix_tokens(prompts[k - 1], prompts[k]) for k in range(1, len(prompts))]
                    variants[f"menu={menu} history={'delta' if delta else 'plain'} output={'compressed' if compress else 'raw'}"] = {
                        "calls": len(prompts), "prompt_tokens_per_call": per_call, "episode_prompt_tokens": sum(per_call),
                        "prefix_identical_to_previous_call": shared, "share_cacheable_after_first_call": round(sum(shared) / max(1, sum(per_call[1:])), 3),
                        "tool_output_tokens_as_shown": sum(tokens(json.dumps(st.tool_result, ensure_ascii=False, default=str)) for st in steps),
                    }
        report["episodes"][name] = variants
    if out_path:
        Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def render(report: Dict[str, Any]) -> str:
    one = report["one_prompt"]
    lines = [f"tokenizer: {report['tokenizer']}; tools in the registry: {report['tools_in_registry']}", "",
             f"one prompt with no history: full menu {one['full_menu_prompt']} tokens, compact ranked {one['compact_ranked_prompt']} ({one['tools_in_compact_menu']} tools); "
             f"the menu alone is {one['menu_only_full']} of the full prompt ({one['menu_share_of_full_prompt'] * 100:.0f}%), everything else {one['everything_but_the_menu']}", ""]
    for layout, v in report["layouts"].items():
        lines.append(f"layout {layout}: prompt {v['prompt_tokens']} tokens, identical prefix across two different goals {v['identical_prefix_tokens_across_two_goals']} tokens "
                     f"({v['share_reusable_across_episodes'] * 100:.0f}% reusable from one episode to the next)")
    lines.append("")
    for name, variants in report["episodes"].items():
        lines += [f"## {name}", "", "| variant | calls | tokens per call | episode total | prefix cacheable after call 1 |", "|---|---|---|---|---|"]
        for label, v in variants.items():
            lines.append(f"| {label} | {v['calls']} | {v['prompt_tokens_per_call']} | {v['episode_prompt_tokens']} | {v['share_cacheable_after_first_call'] * 100:.0f}% |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    report = asyncio.run(run(args.out))
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
