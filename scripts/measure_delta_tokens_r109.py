"""
Delta and tokens, in the form the loop really applies it (Round 109). The questions and the rules were written first: research/DELTA_TOKEN_SAVINGS_CRITERIA_R109.md.

No model is called. Tokens are counted with tiktoken cl100k_base (approximate for any provider: ratios are meaningful, invoices are not).

    python scripts/measure_delta_tokens_r109.py --out research/delta_token_savings_r109.json [--quick]

Q1 saving on the tool-output message itself, by kind of content      Q2 fidelity (needle lines kept), by kind of goal
Q3 net saving once misses are priced                                  Q4 compounding over later calls (real prompt builder)
Q5 the share of a whole episode Delta can reach                       Q6 never worse        Q7 exact recovery
Q8 time cost                                                          Q9 history patches (render_history)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

NL = chr(10)
WORDS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
GENERIC_GOAL = "Summarise this document in three bullet points."
UNRELATED_GOAL = "What is the capital city of France?"
EXPAND_SLICE_TOKENS = 300          # what one expand call returns when it is needed (the loop caps it; a needle region is a few lines)
LATER_CALLS_FOR_NET = 3            # calls after the read in the net-saving table


def tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:              # noqa: BLE001 - characters/4 when tiktoken cannot load; the output says so
        return max(1, len(text) // 4)


def tokenizer_name() -> str:
    try:
        import tiktoken
        tiktoken.get_encoding("cl100k_base")
        return "tiktoken cl100k_base (approximate)"
    except Exception:              # noqa: BLE001
        return "characters / 4 (tiktoken unavailable)"


def build_corpus(quick: bool) -> List[Tuple[str, str, str]]:
    """(kind, name, text). Real files of this repository, plus tables and logs from fixed seeds. At most ~30 KB each unless the name says otherwise."""
    cut = 30000

    def real(rel: str, limit: int = cut) -> str:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")[:limit]

    rng = random.Random(1109)
    owners = [f"team-{i}" for i in range(9)]
    table = "\n".join(f"| row {j} | item {rng.randrange(40)} | status {'ok' if rng.random() > 0.2 else 'late'} | owner {rng.choice(owners)} | note {rng.randrange(10**5)} |" for j in range(520))
    log_lines: List[str] = []
    for j in range(700):
        level = rng.choice(["INFO", "INFO", "INFO", "WARN", "DEBUG"])
        log_lines.append(f"2026-11-02 10:{j // 60 % 60:02d}:{j % 60:02d} {level} worker-{rng.randrange(4)} request {rng.randrange(10**6)} handled in {rng.randrange(900)} ms path=/v1/agent/run status=200")
    pytest_out = "\n".join(["============================= test session starts =============================", "platform win32 -- Python 3.13, pytest-8"]
                           + [f"rct_control_plane/tests/test_module_{j // 8}_real.py::test_case_{j} PASSED                      [{j * 100 // 600:3d}%]" for j in range(600)]
                           + ["========================= 600 passed in 311.40s ========================="])
    th_demo = "\n\n".join(real(f"docs/demo/{n}", 12000) for n in ("FIRST_APPROVER_TH.md", "INSTALL_WINDOWS_TH.md", "APPROVE_WITH_DEVICE_TH.md"))
    corpus = [
        ("python", "governed_autonomous_loop.py[:30k]", real("rct_control_plane/governed_autonomous_loop.py")),
        ("python", "cli.py[:30k]", real("rct_control_plane/cli.py")),
        ("python", "a test file", real("rct_control_plane/tests/test_sovereignty_round52_real.py")),
        ("markdown_en", "whitepaper EN[:30k]", real("docs/whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md")),
        ("markdown_en", "README[:30k]", real("README.md")),
        ("markdown_th", "Thai guides (3 files joined)", th_demo),
        ("markdown_th", "whitepaper TH[:30k]", real("docs/whitepaper/DELENTIA_WHITEPAPER_3.0_TH.md")),
        ("json", "prompt_cost.json", real("research/prompt_cost.json")),
        ("yaml", "windows-installer.yml", real(".github/workflows/windows-installer.yml")),
        ("table", "generated table (520 rows)", table),
        ("log", "generated service log (700 lines)", "\n".join(log_lines)),
        ("log", "generated pytest output (600 lines)", pytest_out),
    ]
    if quick:
        keep = {"governed_autonomous_loop.py[:30k]", "whitepaper EN[:30k]", "Thai guides (3 files joined)", "generated table (520 rows)", "generated service log (700 lines)"}
        corpus = [c for c in corpus if c[1] in keep]
    return [c for c in corpus if len(c[2]) >= 6000]


def needles(text: str, n: int, seed: int = 7) -> List[str]:
    rng = random.Random(seed)
    pool = sorted({ln.strip() for ln in text.split("\n") if 30 <= len(ln.strip()) <= 200 and len(ln.split()) >= 4})
    return rng.sample(pool, min(n, len(pool)))


def goal_variants(needle: str) -> Dict[str, str]:
    words = [w for w in needle.split() if len(w) >= 3] or needle.split()
    rarest = max(words, key=len) if words else needle
    return {"literal": "Find this in the document: " + needle, "partial": "What does the document say about " + " ".join(words[:2]) + "?",
            "single": "What does the document say about " + rarest + "?"}


async def setup(repo: Path, corpus: List[Tuple[str, str, str]]):
    for i, (_, _, text) in enumerate(corpus):
        (repo / "corpus").mkdir(parents=True, exist_ok=True)
        (repo / "corpus" / f"item{i}.txt").write_text(text, encoding="utf-8")
    logging.disable(logging.CRITICAL)
    try:
        from loguru import logger as _loguru
        _loguru.remove()
    except Exception:              # noqa: BLE001
        pass
    from rct_control_plane import autonomous_loop as al
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.mcp_server import _kernel, mcp
    tools = await mcp.list_tools()
    specs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
    loop = build_governed_loop(_kernel, "deltatokens", persistence=_kernel._persistence, mcp_server=mcp)
    loop._episode_evidence = []
    return al, loop, mcp, specs


async def measure(quick: bool = False) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="delentia-deltatokens-"))
    repo = work / "repo"
    repo.mkdir()
    os.environ.update({"DELENTIA_HOME": str(work / "data"), "DELENTIA_REPO_ROOT": str(repo)})
    for name in ("DELENTIA_TOOL_MENU", "DELENTIA_TOOL_MENU_FORMAT", "DELENTIA_WARM_RECALL", "DELENTIA_ALGORITHM_PIPELINE", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_PROMPT_LAYOUT"):
        os.environ.pop(name, None)
    corpus = build_corpus(quick)
    al, loop, mcp, specs = await setup(repo, corpus)
    from rct_control_plane.delta_v2 import compress_context
    from rct_control_plane.tool_output_store import MAX_EXPAND_CHARS
    from rct_control_plane import tool_menu

    async def read_result(i: int) -> Dict[str, Any]:
        raw = await mcp.call_tool("delentia_read_repo_file", {"relative_path": f"corpus/item{i}.txt", "max_bytes": 400000})
        return json.loads(raw.content[0].text)

    def shown_of(goal: str, result: Dict[str, Any]) -> Tuple[Any, bool]:
        before = len(loop._episode_compressions)
        shown = loop._compress_tool_output(goal, "delentia_read_repo_file", {}, result)
        return shown, len(loop._episode_compressions) > before

    report: Dict[str, Any] = {"tokenizer": tokenizer_name(), "corpus": [], "quick": quick}
    never_worse_violations: List[str] = []
    recovery_mismatches: List[str] = []
    rows: List[Dict[str, Any]] = []
    n_needles = 6 if quick else 12

    for i, (kind, name, text) in enumerate(corpus):
        result = await read_result(i)
        raw_tokens = tokens(json.dumps(result, ensure_ascii=False, default=str))
        item = {"kind": kind, "name": name, "chars": len(text), "raw_message_tokens": raw_tokens, "goals": {}}
        pool = needles(text, n_needles)
        goal_sets: Dict[str, List[Tuple[str, Optional[str]]]] = {
            "literal": [(goal_variants(nd)["literal"], nd) for nd in pool],
            "partial": [(goal_variants(nd)["partial"], nd) for nd in pool],
            "single": [(goal_variants(nd)["single"], nd) for nd in pool],      # ADDED AFTER the first run (see the criteria file): one content word of the needle, the way a short question reads
            "generic": [(GENERIC_GOAL, nd) for nd in pool],
            "unrelated": [(UNRELATED_GOAL, nd) for nd in pool],
        }
        for gkind, entries in goal_sets.items():
            saved: List[float] = []
            coverage: List[float] = []
            kept = 0
            applied = 0
            cache: Dict[str, Tuple[Any, bool]] = {}
            for goal, nd in entries:
                if goal not in cache:
                    cache[goal] = shown_of(goal, result)
                shown, did = cache[goal]
                shown_tokens = tokens(json.dumps(shown, ensure_ascii=False, default=str))
                if did:
                    applied += 1
                    if shown_tokens > raw_tokens:
                        never_worse_violations.append(f"{name} / {gkind}: {shown_tokens} > {raw_tokens}")
                    present = nd in (shown.get("content") or "")
                else:
                    present = True                  # left raw: every line is there
                kept += 1 if present else 0
                saved.append(100.0 * (raw_tokens - shown_tokens) / raw_tokens)
                if did:
                    original_lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
                    shown_lines = {ln.strip() for ln in (shown.get("content") or "").splitlines() if ln.strip()}
                    coverage.append(100.0 * len(original_lines & shown_lines) / len(original_lines))
                else:
                    coverage.append(100.0)
            item["goals"][gkind] = {"applied_pct": round(100.0 * applied / len(entries), 1), "saved_pct_median": round(statistics.median(saved), 1),
                                    "saved_pct_min": round(min(saved), 1), "saved_pct_max": round(max(saved), 1), "needle_kept_pct": round(100.0 * kept / len(entries), 1), "lines_shown_pct_median": round(statistics.median(coverage), 1),
                                    "shown_tokens_median": int(statistics.median([tokens(json.dumps(cache[g][0], ensure_ascii=False, default=str)) for g, _ in entries]))}
        # Q7: exact recovery of the original behind a compressed message
        shown, did = shown_of(goal_sets["generic"][0][0], result)
        if did:
            stored = loop._tool_output_store.get(shown["original_id"])
            rendered = loop._render_tool_result(result)
            if hashlib.sha256((stored or "").encode()).hexdigest() != hashlib.sha256(rendered.encode()).hexdigest():
                recovery_mismatches.append(name)
            n_lines = len(rendered.split(NL))
            whole = loop._tool_output_store.expand(shown["original_id"], start_line=1, end_line=n_lines, max_chars=10 ** 9)
            back = [re.sub(r"^L\d+: ", "", ln, count=1) for ln in whole["content"].split(NL)]
            if back != rendered.split(NL):
                recovery_mismatches.append(name + " (expand)")
        item["compressed_in_the_generic_goal"] = bool(did)
        rows.append(item)
    report["corpus"] = rows
    report["q6_never_worse_violations"] = never_worse_violations
    report["q7_recovery_mismatches"] = recovery_mismatches

    # Q1 / Q2 summary by kind and goal kind (median of the item medians)
    by_kind: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = by_kind.setdefault(r["kind"], {g: {"saved": [], "kept": []} for g in ("literal", "partial", "single", "generic", "unrelated")})
        for g, v in r["goals"].items():
            k[g]["saved"].append(v["saved_pct_median"])
            k[g]["kept"].append(v["needle_kept_pct"])
            k[g].setdefault("lines", []).append(v["lines_shown_pct_median"])
    report["by_kind"] = {kind: {g: {"saved_pct_median": round(statistics.median(v["saved"]), 1), "needle_kept_pct_mean": round(statistics.mean(v["kept"]), 1), "lines_shown_pct_median": round(statistics.median(v["lines"]), 1)} for g, v in gs.items()} for kind, gs in by_kind.items()}

    # Q4 / Q5: whole episodes through the real prompt builder, raw against compressed, with later calls
    class Spy:
        def __init__(self) -> None:
            self.prompt = ""

        async def complete(self, prompt: str, *a: Any, **kw: Any) -> str:
            system = kw.get("system_prompt") or (a[0] if a else None)
            self.prompt = (system + "\n" if system else "") + prompt
            return json.dumps({"action": "finish", "reasoning": "x", "final_answer": "x"})

    spy = Spy()

    async def prompt_for(goal: str, history: List[Any], menu: str) -> str:
        os.environ.pop("DELENTIA_TOOL_MENU", None)
        os.environ.pop("DELENTIA_TOOL_MENU_FORMAT", None)
        available = specs
        if menu == "ranked":
            os.environ["DELENTIA_TOOL_MENU"] = "ranked"
            os.environ["DELENTIA_TOOL_MENU_FORMAT"] = "compact"
            available = tool_menu.maybe_ranked(goal, specs) or specs
        await al.decide_next_action(goal, history, available, spy, "")
        return spy.prompt

    episodes: Dict[str, Any] = {}
    pick = [r for r in rows if r["name"] in ("generated table (520 rows)", "generated service log (700 lines)", "governed_autonomous_loop.py[:30k]", "whitepaper EN[:30k]")]
    index_of = {c[1]: i for i, c in enumerate(corpus)}
    small = await mcp.call_tool("delentia_list_repo_files", {"relative_path": "corpus"}) if False else None   # noqa: F841 - a small second step is made below without a tool call
    for r in pick:
        i = index_of[r["name"]]
        result = await read_result(i)
        goal = "Read corpus/item%d.txt and tell me what it contains." % i
        shown, _ = shown_of(goal, result)
        for menu in ("full", "ranked"):
            for later in (2, 4, 8):
                totals = {}
                for label, out in (("raw", result), ("compressed", shown)):
                    steps = [al.LoopStep(iteration=0, tool_name="delentia_read_repo_file", tool_args={"relative_path": f"corpus/item{i}.txt"}, tool_result=out, llm_reasoning="")]
                    prompts = [await prompt_for(goal, [], menu)]
                    for k in range(1, later + 1):
                        if k > 1:       # a small follow-up step (a short listing) so later calls differ from the first, as a real episode does
                            steps.append(al.LoopStep(iteration=k - 1, tool_name="delentia_search_repo_files", tool_args={"pattern": f"x{k}"}, tool_result={"matches": [f"corpus/item{i}.txt:{k}"]}, llm_reasoning=""))
                        prompts.append(await prompt_for(goal, list(steps), menu))
                    totals[label] = sum(tokens(p) for p in prompts)
                    if label == "raw":
                        totals["first_prompt_tokens"] = tokens(prompts[0])
                episodes[f"{r['name']} | menu={menu} | {later} calls after the read"] = {
                    "episode_prompt_tokens_raw": totals["raw"], "episode_prompt_tokens_compressed": totals["compressed"],
                    "saved_pct": round(100.0 * (totals["raw"] - totals["compressed"]) / totals["raw"], 1),
                    "message_tokens_raw": tokens(json.dumps(result, ensure_ascii=False, default=str)), "message_tokens_compressed": tokens(json.dumps(shown, ensure_ascii=False, default=str)),
                    "tool_output_share_of_raw_episode_pct": round(100.0 * tokens(json.dumps(result, ensure_ascii=False, default=str)) * later / totals["raw"], 1)}
    report["episodes"] = episodes

    # Q3: net saving once misses are priced (generic and partial goals; the miss price is one more call whose prompt re-sends the history)
    # Two kinds of task. ADDED AFTER the first run (see the criteria file): the first version priced a miss as ONE extra call, which is right for a lookup and wrong for a task that needs the whole text.
    #   lookup   - the answer is one line (the needle): a miss costs one more call that re-sends the history, plus the slice it brings back.
    #   whole    - the answer needs every line (summarise, review, compare): what was not shown is either not used (information was removed, not tokens saved) or fetched back with expand calls, so the
    #              best case is that the original comes back in full: the net is then the negative of the extra calls' overhead (the original tokens are paid again).
    net: Dict[str, Any] = {}
    for r in rows:
        for g in ("literal", "partial", "single", "generic"):
            v = r["goals"][g]
            raw_t, shown_t = r["raw_message_tokens"], v["shown_tokens_median"]
            p_miss = 1.0 - v["needle_kept_pct"] / 100.0
            base_call = 1100 + shown_t                                    # a compact-menu call (about 1.1k tokens of everything else) carrying the compressed message
            gross = (raw_t - shown_t) * LATER_CALLS_FOR_NET
            cost_of_miss = base_call + EXPAND_SLICE_TOKENS
            expand_calls = max(1, -(-int(len(corpus[index_of[r["name"]]][2]) * (1 - v["lines_shown_pct_median"] / 100.0)) // MAX_EXPAND_CHARS))
            net[f"{r['name']} | {g}"] = {
                "gross_saving_tokens": gross,
                "lookup": {"p_miss": round(p_miss, 3), "expected_miss_cost_tokens": round(p_miss * cost_of_miss), "net_saving_tokens": round(gross - p_miss * cost_of_miss),
                           "breakeven_p_miss": round(gross / cost_of_miss, 2) if cost_of_miss else None},
                "whole": {"lines_shown_pct": v["lines_shown_pct_median"], "expand_calls_to_get_everything_back": expand_calls,
                          "net_if_everything_is_fetched_back_tokens": -round(expand_calls * base_call), "meaning": "saving exists only if answering from the lines shown is acceptable (information removed)"}}
    report["q3_net"] = net

    # Q8: time
    timing = {}
    for r in rows:
        if r["name"] in ("governed_autonomous_loop.py[:30k]", "generated table (520 rows)"):
            text = corpus[index_of[r["name"]]][2]
            samples = []
            for _ in range(5):
                t0 = time.perf_counter()
                compress_context(text, intent_focus=GENERIC_GOAL, aggressive_mode=True, outline=True)
                samples.append((time.perf_counter() - t0) * 1000)
            timing[f"{r['name']} ({len(text)} chars)"] = {"median_ms": round(statistics.median(samples), 1), "max_ms": round(max(samples), 1)}
    big = (ROOT / "rct_control_plane" / "cli.py").read_text(encoding="utf-8", errors="replace")[:230000]
    samples = []
    for _ in range(3):
        t0 = time.perf_counter()
        compress_context(big, intent_focus=GENERIC_GOAL, aggressive_mode=True, outline=True)
        samples.append((time.perf_counter() - t0) * 1000)
    timing[f"cli.py ({len(big)} chars)"] = {"median_ms": round(statistics.median(samples), 1), "max_ms": round(max(samples), 1)}
    report["q8_time_ms"] = timing

    # Q9: history patches over a 6-step episode of similar steps
    def plain_render(history, delta_engine=None):
        return "\n".join(al._render_turn_full(st) for st in history) if history else "(no actions taken yet)"

    steps9 = []
    for k in range(6):
        steps9.append(al.LoopStep(iteration=k, tool_name="delentia_read_repo_file", tool_args={"relative_path": f"corpus/part{k}.txt", "max_bytes": 4000},
                                  tool_result={"path": f"corpus/part{k}.txt", "content": "\n".join(f"line {j} of part {k}: value {j * (k + 1)}" for j in range(25)), "truncated": False}, llm_reasoning="read the next part"))
    with_delta = al.render_history(steps9)
    without = plain_render(steps9)
    q9 = {"six different parts": {"tokens_with_render_history": tokens(with_delta), "tokens_written_out": tokens(without), "patch_lines": with_delta.count("[delta vs iteration"),
                                  "saved_pct": round(100.0 * (tokens(without) - tokens(with_delta)) / tokens(without), 1)}}
    polling = [al.LoopStep(iteration=k, tool_name="delentia_read_repo_file", tool_args={"relative_path": "corpus/status.txt", "max_bytes": 4000},
                           tool_result={"path": "corpus/status.txt", "content": NL.join(f"service-{j}: ok" for j in range(40)) + NL + f"counter: {k}", "truncated": False}, llm_reasoning="check again") for k in range(6)]
    with_delta, without = al.render_history(polling), plain_render(polling)
    q9["the same file read six times, one number changing"] = {"tokens_with_render_history": tokens(with_delta), "tokens_written_out": tokens(without), "patch_lines": with_delta.count("[delta vs iteration"),
                                                              "saved_pct": round(100.0 * (tokens(without) - tokens(with_delta)) / tokens(without), 1)}
    keyed = []
    for k in range(6):
        res = {f"service_{j}": "ok" for j in range(40)}
        res["counter"] = k
        keyed.append(al.LoopStep(iteration=k, tool_name="delentia_status", tool_args={"a": 1}, tool_result=res, llm_reasoning="check again"))
    with_delta, without = al.render_history(keyed), plain_render(keyed)
    q9["a status dictionary of 40 separate fields, one changing (the shape a patch can use)"] = {
        "tokens_with_render_history": tokens(with_delta), "tokens_written_out": tokens(without), "patch_lines": with_delta.count("[delta vs iteration"),
        "saved_pct": round(100.0 * (tokens(without) - tokens(with_delta)) / tokens(without), 1)}
    report["q9_history"] = q9
    return report


def render(rep: Dict[str, Any]) -> str:
    out = [f"tokenizer: {rep['tokenizer']}", ""]
    out.append("Q1/Q2  saving on the tool-output message (median %) / needle still shown (%), by kind and goal; 'raw' = left uncompressed (under 6,000 chars or under 20% reduction)")
    goal_kinds = ("literal", "partial", "single", "generic", "unrelated")
    out.append(f"{'kind':<13}" + "".join(f"{g:>15}" for g in goal_kinds) + "     (saved% / needle kept% / lines shown%)")
    for kind, gs in rep["by_kind"].items():
        out.append(f"{kind:<13}" + "".join(f"{gs[g]['saved_pct_median']:>5.0f}/{gs[g]['needle_kept_pct_mean']:<4.0f}/{gs[g]['lines_shown_pct_median']:<4.0f}" for g in goal_kinds))
    out.append("")
    out.append("per item (saved % / needle kept % / lines shown %):")
    for r in rep["corpus"]:
        parts = "   ".join(f"{g} {r['goals'][g]['saved_pct_median']:.0f}/{r['goals'][g]['needle_kept_pct']:.0f}/{r['goals'][g]['lines_shown_pct_median']:.0f}" for g in ("literal", "single", "generic"))
        out.append(f"  {r['kind']:<12}{r['name']:<38}{r['raw_message_tokens']:>7} tok  {parts}")
    out.append("")
    out.append(f"Q6 never worse: {len(rep['q6_never_worse_violations'])} violation(s) {rep['q6_never_worse_violations'][:3]}")
    out.append(f"Q7 exact recovery: {len(rep['q7_recovery_mismatches'])} mismatch(es) {rep['q7_recovery_mismatches'][:3]}")
    out.append("")
    out.append("Q4/Q5 whole episodes (prompt tokens summed over every call):")
    for k, v in rep["episodes"].items():
        out.append(f"  {k:<95} {v['episode_prompt_tokens_raw']:>8} -> {v['episode_prompt_tokens_compressed']:>8}  ({v['saved_pct']:>5.1f}%)  tool output = {v['tool_output_share_of_raw_episode_pct']}% of the raw episode")
    out.append("")
    out.append("Q3 net saving in tokens over 3 later calls. LOOKUP task: gross saving minus the expected price of a miss (one more call). WHOLE task: lines shown, and the net if everything is fetched back:")
    for k, v in rep["q3_net"].items():
        if k.endswith("| generic") or k.endswith("| single"):
            lk, wh = v["lookup"], v["whole"]
            out.append(f"  {k:<58} gross {v['gross_saving_tokens']:>7} | lookup: p(miss) {lk['p_miss']:<5} net {lk['net_saving_tokens']:>7} | whole: {wh['lines_shown_pct']:>5.1f}% shown, "
                       f"{wh['expand_calls_to_get_everything_back']} expand call(s), net if all fetched back {wh['net_if_everything_is_fetched_back_tokens']:>7}")
    out.append("")
    out.append(f"Q8 time (ms): {rep['q8_time_ms']}")
    out.append(f"Q9 history patches: {rep['q9_history']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    rep = asyncio.run(measure(args.quick))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
