"""
All 41 algorithms as stages of one sequential pipeline (Round 51).

The Architect's definition of the Intent Loop is "self-development by combining
every component of the system in a sequence until a final result that can be
recorded". Until now only 14 of the 41 algorithms ran inside any pipeline
(measured 2026-09-30) and the agent loop used 6. This module gives each of the
41 a real adapter that turns the goal (and the user's own data) into that
algorithm's input, runs it, records what it returned and - where it can - feeds
the result back: advice that is added to the agent's prompt, or a measurement
that is stored with the episode.

Stages, in order:

  understand  ALGO-26 41 04 37 38 02 40 01   what is being asked, and the plan
  recall      ALGO-16 18 13 05 17 10 19      what the user's own data says
  plan        ALGO-21 15 20 12 (32 11 09)    how to order the work
  act         ALGO-35 22 31 (28 29 34 39 23 14 27)   limits and side services
  verify      ALGO-30 33 34 06 24            is the answer supported
  compress    ALGO-03 25                     keep the episode small
  record      ALGO-10 06 25                  keep it provably
  evolve      ALGO-07 08 36                  grow from it

Honesty rules:
  * every adapter returns an AlgoTrace: status ok / not_triggered / skipped /
    error, wall time, what it returned and what *effect* that had;
  * an algorithm that only makes sense for some input (a URL, a video, a build
    request) is reported `not_triggered` with the reason, never given a made-up
    input; the benchmark supplies real fixtures for them instead;
  * algorithms that call the model (ALGO-09, 11, 32), open the network
    (ALGO-28, 29, 34 crawl) or write files (ALGO-39, 23) run only when the
    corresponding option is on;
  * `effect` says "advice added to the prompt" only when it really was.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

PER_ALGORITHM_TIMEOUT_S = 120.0     # first calls load models (spaCy, torch); later calls are milliseconds
STAGES = ("understand", "recall", "plan", "act", "verify", "compress", "record", "evolve")
_URL_RE = re.compile(r"https?://[^\s\"']+")
_VIDEO_RE = re.compile(r"[\w./\\:-]+\.(?:mp4|mov|avi|mkv|webm)", re.IGNORECASE)
_BUILD_RE = re.compile(r"\b(app|api|website|service|backend|frontend|dashboard|scaffold)\b|แอป|เว็บ", re.IGNORECASE)
_IMAGE_RE = re.compile(r"\b(draw|paint|image of|picture of|illustration|generate an image)\b|วาดรูป|สร้างรูป", re.IGNORECASE)


@dataclass
class PipelineOptions:
    enabled: Optional[Set[str]] = None        # None = all 41
    allow_llm: bool = False                   # ALGO-09 / 11 / 32 call the model several times
    allow_network: bool = False               # ALGO-28 / 29 / 34 crawl make real outbound requests
    allow_writes: bool = False                # ALGO-39 / 23 write files under workspace_output/
    fixtures: Dict[str, Any] = field(default_factory=dict)   # benchmark-supplied inputs: url, video_path, image_prompt


@dataclass
class Outcome:
    summary: Dict[str, Any] = field(default_factory=dict)
    effect: str = "recorded"
    advice: List[str] = field(default_factory=list)


@dataclass
class AlgoTrace:
    algo_id: str
    name: str
    stage: str
    status: str                      # ok | not_triggered | skipped | error
    ms: float
    summary: Dict[str, Any] = field(default_factory=dict)
    effect: str = ""
    reason: str = ""
    advice_lines: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algo_id": self.algo_id, "name": self.name, "stage": self.stage, "status": self.status,
            "ms": round(self.ms, 2), "summary": self.summary, "effect": self.effect, "reason": self.reason,
            "advice_lines": self.advice_lines,
        }


class NotTriggered(Exception):
    """Raised by an adapter whose input does not exist for this goal."""


@dataclass
class PipelineContext:
    goal: str
    namespace: str
    kernel: Any
    persistence: Any
    memory: Any = None               # AgentMemory
    skills: Any = None               # SkillLibrary
    options: PipelineOptions = field(default_factory=PipelineOptions)
    clarity: float = 1.0
    D: float = 1.0
    I: float = 1.0
    intent_type: str = "UNKNOWN"
    compile_result: Any = None
    plan_steps: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None       # the governed episode, in the post stages
    scratch: Dict[str, Any] = field(default_factory=dict)

    @property
    def final_answer(self) -> str:
        return str((self.result or {}).get("final_answer") or "")

    @property
    def dimension(self) -> int:
        return int(self.kernel._vector_engine.dimension)

    def embed(self, text: str) -> List[float]:
        """Hashed bag-of-words vector with stopwords removed first: without that,
        "the", "in", "and" alone made unrelated sentences look 0.3-0.5 alike."""
        from rct_control_plane.mcp_server import _hash_embed_query
        from rct_control_plane.skill_library import _tokenize
        return list(_hash_embed_query(" ".join(_tokenize(text)) or text, dim=self.dimension))


def _goal_url(ctx: "PipelineContext") -> Optional[str]:
    if ctx.options.fixtures.get("url"):
        return str(ctx.options.fixtures["url"])
    found = _URL_RE.search(ctx.goal)
    return found.group(0) if found else None


def _goal_video(ctx: "PipelineContext") -> Optional[str]:
    if ctx.options.fixtures.get("video_path"):
        return str(ctx.options.fixtures["video_path"])
    found = _VIDEO_RE.search(ctx.goal)
    return found.group(0) if found else None


AdapterFn = Callable[[PipelineContext], Awaitable[Outcome]]


@dataclass
class Adapter:
    algo_id: str
    name: str
    stage: str
    fn: AdapterFn
    llm: bool = False
    network: bool = False
    writes: bool = False
    post: bool = False               # runs after the episode (needs its result)

    @property
    def phase(self) -> str:
        return "post" if (self.post or self.stage in ("verify", "compress", "record", "evolve")) else "pre"


ADAPTERS: List[Adapter] = []


def adapter(algo_id: str, name: str, stage: str, *, llm: bool = False, network: bool = False, writes: bool = False,
            post: bool = False):
    def register(fn: AdapterFn) -> AdapterFn:
        ADAPTERS.append(Adapter(algo_id, name, stage, fn, llm, network, writes, post))
        return fn
    return register


# =============================================================================
# understand
# =============================================================================
@adapter("ALGO-26", "Intent classification", "understand")
async def _algo26(ctx: PipelineContext) -> Outcome:
    r = ctx.kernel.algo_26_intent_classification(ctx.goal)
    primary = str(r.get("primary_intent", "unknown"))
    ctx.scratch["entities"] = [e.get("entity") for e in r.get("entities", []) if isinstance(e, dict)]
    social = primary in ("greeting", "farewell", "thanks")
    advice = ["This message is conversational (greeting / thanks / goodbye): answer briefly and do not call tools."] if social else []
    return Outcome({"primary_intent": primary, "intents": len(r.get("intents", [])), "entities": len(ctx.scratch["entities"]),
                    "compiler_type": ctx.intent_type, "classified": primary != "unknown", "conversational": social},
                   "conversational messages get a brief-answer instruction; other goals fall outside its chat taxonomy" , advice)


@adapter("ALGO-41", "Crystallizer (golden keywords)", "understand")
async def _algo41(ctx: PipelineContext) -> Outcome:
    golden = ctx.kernel.crystallize_golden_keywords(ctx.goal)
    words = [str(w.get("word") if isinstance(w, dict) else w) for w in golden.get("golden_keywords", [])]
    ctx.scratch["keywords"] = words
    seal = ctx.kernel.algo_41_crystallizer({"goal": ctx.goal, "keywords": words})
    return Outcome({"keywords": words[:8], "seal": seal}, "keywords become extra recall queries; the seal is stored with the episode")


@adapter("ALGO-04", "RCT-7 decomposition", "understand")
async def _algo04(ctx: PipelineContext) -> Outcome:
    ctx.plan_steps = list(ctx.kernel.algo_04_rct7(ctx.goal))
    return Outcome({"steps": len(ctx.plan_steps)}, "steps 1-6 are the plan in the agent's prompt (step 7 verifies the answer)")


@adapter("ALGO-37", "Planning depth expander", "understand")
async def _algo37(ctx: PipelineContext) -> Outcome:
    lines = [str(x) for x in ctx.kernel.algo_37_planning_depth_expander(ctx.goal)]
    ctx.scratch["deep_plan"] = lines
    advice = [f"Expanded plan: {line}" for line in lines[:4]]
    return Outcome({"lines": len(lines)}, "first 4 expanded plan lines added to the prompt", advice)


@adapter("ALGO-38", "Constraint solver", "understand")
async def _algo38(ctx: PipelineContext) -> Outcome:
    intent = getattr(ctx.compile_result, "intent", None)
    constraints = list(getattr(intent, "constraints", None) or [])
    if not constraints:
        raise NotTriggered("the goal states no constraints to check")
    solved = ctx.kernel.algo_38_solve(constraints)
    advice = [f"Constraint conflict in the request: {c}. Ask before acting." for c in solved["conflicts"]]
    return Outcome({"constraints": len(constraints), "satisfiable": solved["satisfiable"], "bounds": solved["bounds"]},
                   "conflicts are added to the prompt as warnings" if advice else "no conflict found", advice)


@adapter("ALGO-02", "MOIP multi-objective planner", "understand")
async def _algo02(ctx: PipelineContext) -> Outcome:
    heads = [s.split(":")[0][:40] for s in (ctx.plan_steps or ctx.kernel.algo_04_rct7(ctx.goal))[:6]]
    r = ctx.kernel.algo_02_moip(heads)
    matrix = r.get("priority_matrix", {})
    ctx.scratch["priorities"] = matrix
    return Outcome({"objectives": len(heads), "pareto_front": len(r.get("pareto_front", [])), "first": (r.get("planned_goals") or [None])[0]},
                   "plan steps ordered by Pareto rank; stored with the episode")


@adapter("ALGO-40", "ITSR tech-stack recommender", "understand")
async def _algo40(ctx: PipelineContext) -> Outcome:
    if ctx.intent_type != "BUILD_APP" and not _BUILD_RE.search(ctx.goal):
        raise NotTriggered("the goal is not a build request")
    domain = (ctx.scratch.get("keywords") or ["general"])[0]
    r = ctx.kernel.algo_40_itsr_recommender(domain)
    return Outcome({"domain": domain, **{k: v for k, v in r.items() if k != "domain_matched"}}, "stack recommendation added to the prompt",
                   [f"Suggested stack for this build: {r.get('backend')} / {r.get('frontend')} / {r.get('db')}"])


@adapter("ALGO-01", "FDIA equation", "understand")
async def _algo01(ctx: PipelineContext) -> Outcome:
    f = ctx.kernel.algo_01_fdia(ctx.D, ctx.I, 1.0)
    return Outcome({"D": ctx.D, "I": ctx.I, "A": 1.0, "F": f}, "the goal's own F, stored with the episode; per-action F is computed by the loop's gate")


# =============================================================================
# recall - the user's own data through the retrieval algorithms
# =============================================================================
def _namespaces(ctx: PipelineContext) -> List[str]:
    """The namespaces whose data belongs to this user: the loop's own, and the
    kernel's default one that `delentia_remember` writes to."""
    names = [ctx.namespace]
    default = getattr(ctx.memory, "namespace", None)
    if default and default not in names:
        names.append(str(default))
    return names


def _user_documents(ctx: PipelineContext) -> Dict[str, str]:
    """{id: text} for this namespace's memories and active skills."""
    docs: Dict[str, str] = {}
    for ns in _namespaces(ctx):
        try:
            for m in ctx.persistence.list_memories(namespace=ns):
                docs[f"{ns}:mem:{m['id']}"] = str(m.get("content", ""))
        except Exception:
            pass
    if ctx.skills is not None and hasattr(ctx.skills, "list_active"):
        try:
            for s in ctx.skills.list_active(limit=200):
                docs[f"{ctx.namespace}:skill:{s.id}"] = s.problem_statement
        except Exception:
            pass
    return docs


def _index_user_data(ctx: PipelineContext) -> int:
    """Put the user's memories and skills into ALGO-16's index once. Ids are
    namespaced, so one user's data is never returned for another."""
    known: Set[str] = ctx.kernel.__dict__.setdefault("_pipeline_indexed", set())
    fresh = {i: t for i, t in _user_documents(ctx).items() if i not in known and t.strip()}
    if fresh:
        ctx.kernel._vector_engine.index([ctx.embed(t) for t in fresh.values()], list(fresh),
                                        [{"text": t, "ns": ctx.namespace} for t in fresh.values()])
        known.update(fresh)
    return len(fresh)


def _own(ctx: PipelineContext, item_id: str) -> bool:
    return any(str(item_id).startswith(f"{ns}:") for ns in _namespaces(ctx))


@adapter("ALGO-16", "Vector search", "recall")
async def _algo16(ctx: PipelineContext) -> Outcome:
    newly = _index_user_data(ctx)
    query = " ".join([ctx.goal] + list(ctx.scratch.get("keywords") or [])[:5])
    r = ctx.kernel.algo_16_vector_search(ctx.embed(query), k=20)
    hits = [h for h in r.get("results", []) if _own(ctx, h.get("id")) and h.get("score", 0) >= 0.2][:3]
    ctx.scratch["vector_hits"] = hits
    advice = [f"From your stored data (vector match {h['score']:.2f}): {str((h.get('metadata') or {}).get('text', ''))[:200]}" for h in hits]
    return Outcome({"newly_indexed": newly, "hits": len(hits), "best": hits[0]["score"] if hits else None},
                   "matching memories/skills added to the prompt" if hits else "no stored data matched", advice)


@adapter("ALGO-18", "Adaptive prompting / RAG retrieval", "recall")
async def _algo18(ctx: PipelineContext) -> Outcome:
    _index_user_data(ctx)
    r = ctx.kernel.algo_18_rag_retrieve(ctx.embed(ctx.goal), top_k=20)
    own = [x for x in r if _own(ctx, x.get("id")) and x.get("score", 0) > 0.0][:3]
    vec_ids = {h["id"] for h in ctx.scratch.get("vector_hits", [])}
    return Outcome({"contexts": len(own), "agree_with_vector_search": sum(1 for x in own if x["id"] in vec_ids)},
                   "second retrieval path; agreement with ALGO-16 is recorded")


@adapter("ALGO-13", "GraphRAG (TF-IDF + vector + graph)", "recall")
async def _algo13(ctx: PipelineContext) -> Outcome:
    engine = ctx.kernel._graphrag_engine
    for doc_id, text in _user_documents(ctx).items():
        if doc_id not in engine.documents and text.strip():
            engine.add_document(text, doc_id=doc_id)
    r = await ctx.kernel.algo_13_graphrag(ctx.goal, "graphrag", 5)
    own = [x for x in r.get("results", []) if _own(ctx, x.get("doc_id")) and x.get("fusion_score", 0) > 0][:3]
    advice = [f"Related from your data (GraphRAG): {x['content'][:200]}" for x in own[:2]]
    return Outcome({"results": len(own), "best_fusion": own[0]["fusion_score"] if own else None},
                   "top related items added to the prompt" if own else "no stored data matched", advice)


@adapter("ALGO-05", "GraphRAG knowledge graph", "recall")
async def _algo05(ctx: PipelineContext) -> Outcome:
    r = ctx.kernel.algo_05_graphrag(ctx.goal)
    ctx.scratch["graph_nodes"] = r.get("nodes", [])
    return Outcome({"nodes": len(r.get("nodes", [])), "edges": len(r.get("edges", [])), "graph": r.get("graph_stats")},
                   "the goal's terms are added to the long-lived knowledge graph")


@adapter("ALGO-17", "Graph traversal (PageRank)", "recall")
async def _algo17(ctx: PipelineContext) -> Outcome:
    terms = list(dict.fromkeys((ctx.scratch.get("graph_nodes") or []) + (ctx.scratch.get("keywords") or [])))[:8]
    if len(terms) < 2:
        raise NotTriggered("fewer than two terms to connect")
    rels = [{"from": a, "to": b} for a, b in zip(terms, terms[1:], strict=False)]
    pr = ctx.kernel.algo_17_graph_traversal([{"id": t} for t in terms], rels, "pagerank")
    top = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)[:3] if isinstance(pr, dict) else []
    return Outcome({"terms": len(terms), "most_central": [t for t, _ in top]}, "term salience recorded")


@adapter("ALGO-10", "Delta memory (vault)", "recall")
async def _algo10(ctx: PipelineContext) -> Outcome:
    stats = ctx.kernel.algo_10_delta_memory()
    found = ctx.kernel._rctdb_client.search_documents(text=ctx.goal, limit=3)
    return Outcome({"vault_documents": stats.get("total_documents", stats.get("documents")), "matches": len(found)}, "vault lookup recorded (mock-mode vault)")


@adapter("ALGO-19", "Data fusion", "recall")
async def _algo19(ctx: PipelineContext) -> Outcome:
    hits = ctx.scratch.get("vector_hits") or []
    if not hits:
        raise NotTriggered("no retrieved data to fuse with the goal")
    context_text = " ".join(str((h.get("metadata") or {}).get("text", "")) for h in hits)
    r = ctx.kernel.algo_19_data_fusion({"goal": ctx.embed(ctx.goal), "context": ctx.embed(context_text)}, "hybrid")
    return Outcome({"confidence": r.get("confidence"), "strategy": r.get("strategy_used")}, "goal/context fusion confidence recorded")


# =============================================================================
# plan
# =============================================================================
@adapter("ALGO-21", "Fast/Slow router", "plan")
async def _algo21(ctx: PipelineContext) -> Outcome:
    decision = ctx.kernel._fast_slow_router.decide(ctx.goal)        # the decision only: the loop itself does the work
    ctx.scratch["route"] = decision.path.value
    summary: Dict[str, Any] = {"path": decision.path.value, "reason": decision.reason}
    effect = "decides the step budget in the loop (FAST = 3 steps)"
    if ctx.options.allow_llm and decision.path.value == "slow":
        full = await ctx.kernel.algo_21_fast_slow_route(ctx.goal)   # dispatches ALGO-09/11/32: model calls
        summary["dispatched_to"] = full.get("slow_strategy")
        effect += "; the slow strategy was also dispatched"
    return Outcome(summary, effect)


@adapter("ALGO-15", "HRM scheduler", "plan")
async def _algo15(ctx: PipelineContext) -> Outcome:
    sched = ctx.kernel._hrm_scheduler
    for w in ("pipeline-w1", "pipeline-w2"):
        if w not in sched.workers:
            sched.register_worker(w)
    run = f"{ctx.namespace}-{int(time.time() * 1000)}"
    steps = (ctx.plan_steps or ctx.kernel.algo_04_rct7(ctx.goal))[:6]
    tasks = [{"id": f"{run}-{i}", "task_type": "plan_step", "payload": {"step": s[:60]}, "priority": 5,
              "dependencies": ([f"{run}-{i - 1}"] if i >= 3 else [])} for i, s in enumerate(steps)]
    r = await ctx.kernel.algo_15_hrm_scheduler(tasks)
    assigned = r.get("assignments", [])
    for task_id, _worker in assigned:                       # free the workers for the next run
        await sched.complete_task(task_id, {"ok": True})
    return Outcome({"steps": len(tasks), "first_wave": len(assigned), "workers": len(sched.workers)},
                   "independent plan steps identified (first wave size)")


@adapter("ALGO-20", "Workflow orchestrator", "plan")
async def _algo20(ctx: PipelineContext) -> Outcome:
    steps = (ctx.plan_steps or ctx.kernel.algo_04_rct7(ctx.goal))[:4]
    run = f"{int(time.time() * 1000)}"
    tasks = [{"id": f"s{run}-{i}", "name": s[:30], "type": "data_fusion", "dependencies": ([f"s{run}-{i - 1}"] if i else [])} for i, s in enumerate(steps)]
    r = await ctx.kernel.algo_20_workflow_orchestrator(f"plan-{ctx.namespace}", tasks, "sequential")
    return Outcome({"tasks": len(tasks), "status": r.get("status"), "workflow_id": r.get("workflow_id")}, "plan registered as a DAG workflow (scheduled, not executed)")


@adapter("ALGO-12", "Meta-algorithm generator", "plan", llm=True)
async def _algo12(ctx: PipelineContext) -> Outcome:
    if not ctx.options.allow_llm:
        raise NotTriggered("names and validates compositions with a model (allow_llm is off)")
    r = await ctx.kernel.algo_12_meta_algorithm_generator(["analyze", "optimize", "generate"], "sequential", ctx.goal)
    return Outcome({"status": r.get("status"), "error": r.get("error")}, "composed analyze->optimize->generate chain recorded")


@adapter("ALGO-32", "MCTR multi-chain reasoning", "plan", llm=True)
async def _algo32(ctx: PipelineContext) -> Outcome:
    if not ctx.options.allow_llm:
        raise NotTriggered("calls the model several times (allow_llm is off)")
    r = await ctx.kernel.algo_32_mctr(ctx.goal, 2)
    answer = str(r.get("final_answer") or r.get("answer") or "")[:300]
    return Outcome({"chains": len(r.get("chains", [])), "answer": answer}, "reasoning summary added to the prompt",
                   [f"Independent reasoning chains concluded: {answer}"] if answer else [])


@adapter("ALGO-11", "BBA->P->CF analysis", "plan", llm=True)
async def _algo11(ctx: PipelineContext) -> Outcome:
    if not ctx.options.allow_llm:
        raise NotTriggered("calls the model several times (allow_llm is off)")
    evidence = [t for t in (str((h.get("metadata") or {}).get("text", "")) for h in ctx.scratch.get("vector_hits", [])) if t] or [ctx.goal]
    r = await ctx.kernel.algo_11_bba_pcf(ctx.goal, evidence, [ctx.goal])
    return Outcome({"keys": sorted(r)[:6]}, "belief/plan/forecast recorded")


# =============================================================================
# act
# =============================================================================
@adapter("ALGO-35", "Adaptive timeout control", "act", post=True)
async def _algo35(ctx: PipelineContext) -> Outcome:
    if ctx.result is not None:
        duration = float((ctx.result.get("metrics") or {}).get("duration_s") or ctx.scratch.get("episode_seconds") or 0.0)
        if duration > 0:
            await ctx.kernel._timeout_controller.record_response(duration, True)
    r = await ctx.kernel.algo_35_adaptive_timeout({"workload_type": "api_call"})
    return Outcome({"timeout_s": r.get("current_timeout_s"), "predicted_s": r.get("predicted_timeout_s")},
                   "the episode's duration is fed back so the next timeout prediction adapts")


@adapter("ALGO-22", "Halting detection", "act", post=True)
async def _algo22(ctx: PipelineContext) -> Outcome:
    snippets = []
    for step in (ctx.result or {}).get("steps", []):
        command = str((step.get("tool_args") or {}).get("command", ""))
        code = str((step.get("tool_args") or {}).get("content_text", ""))
        for text in (command, code):
            if "while" in text or "for " in text or "def " in text or "python -c" in text:
                snippets.append(text)
    if not snippets:
        raise NotTriggered("no executable code among the episode's tool calls")
    verdicts = [ctx.kernel.algo_22_halting_detection(s[:2000], "python") for s in snippets[:3]]
    return Outcome({"snippets": len(verdicts), "may_not_halt": sum(1 for v in verdicts if v.get("halts") is False)},
                   "termination verdicts recorded for code the agent ran")


@adapter("ALGO-31", "ALBAS adaptive load balancing", "act")
async def _algo31(ctx: PipelineContext) -> Outcome:
    import psutil
    cpu = psutil.cpu_percent(interval=None) / 100.0
    mem = psutil.virtual_memory().percent / 100.0
    r = ctx.kernel.algo_31_albas(cpu, mem)
    ctx.scratch["load"] = {"cpu": cpu, "memory": mem}
    return Outcome({"cpu": round(cpu, 2), "memory": round(mem, 2), "keys": sorted(r)[:5]}, "host load and scaling recommendation recorded (used when fanning out subagents)")


@adapter("ALGO-34", "SWCAR web crawler", "act", network=True)
async def _algo34_crawl(ctx: PipelineContext) -> Outcome:
    url = _goal_url(ctx)
    if not url:
        raise NotTriggered("the goal contains no URL")
    if not ctx.options.allow_network:
        raise NotTriggered("would make a real outbound request (allow_network is off)")
    r = await ctx.kernel.algo_34_web_crawl(url)
    html = str(getattr(r, "html", "") or "")
    ctx.scratch["crawled_text"] = html[:2000]
    return Outcome({"url": url, "status": getattr(r, "status_code", None), "chars": len(html)}, "page content recorded and kept for the answer's evidence")


@adapter("ALGO-28", "CIO request batching", "act", network=True)
async def _algo28(ctx: PipelineContext) -> Outcome:
    url = _goal_url(ctx)
    if not url:
        raise NotTriggered("the goal contains no URL")
    if not ctx.options.allow_network:
        raise NotTriggered("would make a real outbound request (allow_network is off)")
    r = await ctx.kernel.algo_28_cio_batch(url)
    return Outcome({"url": url, "status": (r or {}).get("status_code") if isinstance(r, dict) else None}, "request went through the shared priority batcher")


@adapter("ALGO-29", "UIA universal integration adapter", "act", network=True)
async def _algo29(ctx: PipelineContext) -> Outcome:
    url = _goal_url(ctx)
    if not url:
        raise NotTriggered("the goal contains no URL")
    if not ctx.options.allow_network:
        raise NotTriggered("would make a real outbound request (allow_network is off)")
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    r = await ctx.kernel.algo_29_uia("REST", {"base_url": f"{parts.scheme}://{parts.netloc}"}, f"GET {parts.path or '/'}", {})
    return Outcome({"url": url, "type": type(r).__name__, "ok": bool(r)}, "REST adapter call recorded")


@adapter("ALGO-39", "Genesis project generator", "act", writes=True)
async def _algo39(ctx: PipelineContext) -> Outcome:
    if ctx.intent_type != "BUILD_APP" and not _BUILD_RE.search(ctx.goal) and "build_name" not in ctx.options.fixtures:
        raise NotTriggered("the goal is not a build request")
    if not ctx.options.allow_writes:
        raise NotTriggered("would scaffold files under workspace_output/ (allow_writes is off)")
    name = str(ctx.options.fixtures.get("build_name") or "pipeline_project")
    r = ctx.kernel.algo_39_genesis_engine(name)
    return Outcome({"files": r.get("files_scaffolded"), "dir": r.get("project_dir")}, "project skeleton scaffolded")


@adapter("ALGO-23", "Content-Box storage", "act", writes=True, post=True)
async def _algo23(ctx: PipelineContext) -> Outcome:
    if not ctx.final_answer:
        raise NotTriggered("no final answer to store")
    if not ctx.options.allow_writes:
        raise NotTriggered("would write under workspace_output/ (allow_writes is off)")
    content_id = f"answer-{ctx.namespace}-{int(time.time())}"
    saved = await ctx.kernel.algo_23_content_box(content_id, 1, ctx.final_answer.encode("utf-8"))
    return Outcome({"content_id": content_id, "size": saved.get("size"), "checksum": saved.get("checksum")}, "the answer is stored with a SHA-256 checksum")


@adapter("ALGO-14", "RCT-Diffusion image generation", "act")
async def _algo14(ctx: PipelineContext) -> Outcome:
    prompt = ctx.options.fixtures.get("image_prompt") or (ctx.goal if _IMAGE_RE.search(ctx.goal) else None)
    if not prompt:
        raise NotTriggered("the goal does not ask for an image")
    r = await ctx.kernel.algo_14_rct_diffusion(prompt, num_steps=2, width=64, height=64)
    return Outcome({k: r[k] for k in list(r)[:4]}, "image generated")


@adapter("ALGO-27", "TVRA video analysis", "act")
async def _algo27(ctx: PipelineContext) -> Outcome:
    path = _goal_video(ctx)
    if not path:
        raise NotTriggered("the goal names no video file")
    if not os.path.exists(path):
        raise NotTriggered(f"video file not found: {path}")
    r = await ctx.kernel.algo_27_tvra_analyze("pipeline-video", path, {"fps": 1, "transcribe_audio": False})
    return Outcome({k: r[k] for k in ("scenes", "frames_analyzed") if k in r}, "video analysed")


# =============================================================================
# verify
# =============================================================================
def _evidence_texts(ctx: PipelineContext) -> List[str]:
    evidence = [ctx.goal]
    for step in (ctx.result or {}).get("steps", []):
        result = step.get("tool_result")
        if result:
            evidence.append(str(result)[:500])
    evidence += [str((h.get("metadata") or {}).get("text", "")) for h in ctx.scratch.get("vector_hits", [])]
    return [e for e in evidence if e]


@adapter("ALGO-30", "Adaptive belief validation", "verify")
async def _algo30(ctx: PipelineContext) -> Outcome:
    if not ctx.final_answer:
        raise NotTriggered("no final answer")
    r = ctx.kernel.algo_30_abv(ctx.final_answer[:500], _evidence_texts(ctx))
    return Outcome({"confidence": round(float(r.get("confidence_score", 0.0)), 3), "level": r.get("confidence_level")},
                   "belief confidence in the answer, given the tool results, recorded with the episode")


@adapter("ALGO-33", "FGHF hallucination filter", "verify", llm=True)
async def _algo33(ctx: PipelineContext) -> Outcome:
    """Pattern checks always run; when none match FGHF asks a model (local
    Ollama) for a second opinion - that part only with allow_llm."""
    if not ctx.final_answer:
        raise NotTriggered("no final answer")
    r = await ctx.kernel.algo_33_fghf(ctx.final_answer[:1000], llm_fallback=ctx.options.allow_llm)
    return Outcome({"hallucination_probability": r.get("hallucination_probability"), "flagged": bool(r.get("has_hallucination")),
                    "model_second_opinion": ctx.options.allow_llm},
                   "hallucination probability recorded with the episode" + ("" if ctx.options.allow_llm else " (patterns only, no model call)"))


@adapter("ALGO-34", "SWCAR semantic analysis", "verify")
async def _algo34(ctx: PipelineContext) -> Outcome:
    if not ctx.final_answer:
        raise NotTriggered("no final answer")
    r = ctx.kernel.algo_34_semantic_analysis(ctx.final_answer[:1000])
    return Outcome({"entities": len(r.get("entities", [])), "sentiment": r.get("sentiment")}, "entities and sentiment of the answer recorded")


@adapter("ALGO-06", "Reflexion self-correction", "verify")
async def _algo06(ctx: PipelineContext) -> Outcome:
    errors = [str(s.get("tool_result"))[:200] for s in (ctx.result or {}).get("steps", [])
              if isinstance(s.get("tool_result"), dict) and (s["tool_result"].get("error") or s["tool_result"].get("fdia_blocked"))]
    r = ctx.kernel.algo_06_reflexion(ctx.final_answer or "", errors[0] if errors else None)
    return Outcome({"has_error": r.get("has_error"), "action": r.get("correction_action"), "errors": len(errors)},
                   "correction action recorded")


@adapter("ALGO-09", "Reflexion+", "verify", llm=True)
async def _algo09(ctx: PipelineContext) -> Outcome:
    if not ctx.options.allow_llm:
        raise NotTriggered("calls the model several times (allow_llm is off)")
    r = await ctx.kernel.algo_09_reflexion_plus(ctx.goal, {"draft": ctx.final_answer})
    return Outcome({"keys": sorted(r)[:5]}, "critique of the draft answer recorded")


@adapter("ALGO-24", "Benchmark suite", "verify")
async def _algo24(ctx: PipelineContext) -> Outcome:
    r = await ctx.kernel.algo_24_benchmark("pipeline_router_stats", "algo_21_router_stats", 3)
    summary = ctx.kernel.algo_24_benchmark_summary()
    return Outcome({"mean_ms": r.get("mean_ms"), "benchmarks_run": summary.get("total_benchmarks", summary.get("benchmarks"))},
                   "timing of the kernel's own summary call recorded")


# =============================================================================
# compress / record / evolve
# =============================================================================
@adapter("ALGO-03", "Delta engine tick compressor", "compress")
async def _algo03(ctx: PipelineContext) -> Outcome:
    state = {"goal": ctx.goal, "steps": [{"tool": s.get("tool_name"), "args": s.get("tool_args")} for s in (ctx.result or {}).get("steps", [])],
             "answer": ctx.final_answer}
    r = ctx.kernel.algo_03_delta_engine(state)
    return Outcome({"delta_bytes": r.get("delta_bytes"), "compressed_bytes": r.get("compressed_bytes"), "ratio": r.get("compressed_ratio")},
                   "compressed episode state; ratio recorded")


@adapter("ALGO-25", "Delta block", "compress")
async def _algo25(ctx: PipelineContext) -> Outcome:
    r = ctx.kernel.algo_25_delta_block(ctx.namespace, f"pipeline episode: {ctx.goal[:80]}", source="algorithm_pipeline")
    return Outcome({"delta_id": r.get("delta_id")}, "episode stored as a delta block")


@adapter("ALGO-10", "Delta memory (incremental store)", "record")
async def _algo10_store(ctx: PipelineContext) -> Outcome:
    r = ctx.kernel.algo_10_delta_memory_incremental_store(ctx.namespace, f"episode: {ctx.goal[:80]} -> {(ctx.result or {}).get('stopped_reason')}")
    return Outcome({"delta_id": r.get("delta_id"), "total_deltas": (r.get("stats") or {}).get("total_deltas")}, "incremental state delta stored")


@adapter("ALGO-06", "JITNA state container", "record")
async def _algo06_export(ctx: PipelineContext) -> Outcome:
    r = ctx.kernel.algo_06_jitna_export_state_container(ctx.namespace)
    return Outcome({"packet_id": r.get("packet_id"), "signed": bool(r.get("signature")), "type": r.get("message_type")}, "signed JITNA state container exported")


@adapter("ALGO-07", "MEE v2 (kernel-wide growth)", "evolve")
async def _algo07(ctx: PipelineContext) -> Outcome:
    growth = float(((ctx.result or {}).get("growth") or {}).get("delta", 0.0))
    violation = bool(((ctx.result or {}).get("growth") or {}).get("governance_violation", False))
    r = ctx.kernel.algo_07_mee(growth, violation)
    return Outcome({"G": r.get("g_after"), "step": r.get("step")}, "the episode's growth signal also advances the kernel-wide session")


@adapter("ALGO-08", "Self-evolving orchestrator", "evolve")
async def _algo08(ctx: PipelineContext) -> Outcome:
    r = await ctx.kernel.algo_08_self_evolving()
    return Outcome({"status": r.get("status"), "reason": r.get("reason"), "g_level": r.get("g_level")}, "evolution conditions evaluated against MEE growth")


@adapter("ALGO-36", "RFLH few-shot meta-learning", "evolve")
async def _algo36(ctx: PipelineContext) -> Outcome:
    runs = []
    try:
        runs = ctx.persistence.recent_governed_runs(ctx.namespace, 12)
    except Exception:
        pass
    examples = [{"input": str(r.get("experiment_id")), "output": int((r.get("metrics") or {}).get("finished") == 1)} for r in runs if r.get("metrics")]
    if len(examples) < 2:
        raise NotTriggered("fewer than two recorded episodes to learn from")
    r = await ctx.kernel.algo_36_rflh(f"{ctx.namespace}-outcomes", examples)
    return Outcome({"examples": len(examples), "accuracy": r.get("accuracy"), "loss": r.get("loss")}, "a few-shot model of this namespace's episode outcomes was adapted")


# =============================================================================
# the runner
# =============================================================================
class AlgorithmPipeline:
    def __init__(self, kernel: Any, persistence: Any, namespace: str, *, memory: Any = None, skills: Any = None,
                 options: Optional[PipelineOptions] = None) -> None:
        self.kernel = kernel
        self.persistence = persistence
        self.namespace = namespace
        self.memory = memory
        self.skills = skills
        self.options = options or PipelineOptions()

    def adapters_for(self, stage: str, phase: Optional[str] = None) -> List[Adapter]:
        wanted = self.options.enabled
        return [a for a in ADAPTERS if a.stage == stage and (phase is None or a.phase == phase)
                and (wanted is None or a.algo_id in wanted)]

    @staticmethod
    def algorithm_ids() -> List[str]:
        return sorted({a.algo_id for a in ADAPTERS})

    async def run_stage(self, stage: str, ctx: PipelineContext, phase: Optional[str] = None) -> tuple[List[AlgoTrace], List[str]]:
        traces: List[AlgoTrace] = []
        advice: List[str] = []
        for a in self.adapters_for(stage, phase):
            started = time.perf_counter()
            try:
                outcome = await asyncio.wait_for(a.fn(ctx), PER_ALGORITHM_TIMEOUT_S)
                status, reason = "ok", ""
            except NotTriggered as why:
                outcome, status, reason = Outcome(effect="not triggered"), "not_triggered", str(why)
            except Exception as exc:
                outcome, status, reason = Outcome(effect="failed"), "error", f"{type(exc).__name__}: {str(exc)[:200]}"
            ms = (time.perf_counter() - started) * 1000
            traces.append(AlgoTrace(a.algo_id, a.name, a.stage, status, ms, outcome.summary, outcome.effect, reason, len(outcome.advice)))
            advice.extend(outcome.advice)
        return traces, advice


def adapter_source_sanity() -> bool:     # used by tests: every adapter is an async function
    return all(inspect.iscoroutinefunction(a.fn) for a in ADAPTERS)
