"""
Delentia MCP Server — exposes the 41-algorithm kernel as real MCP tools.

Round 21 Phase 2: the first concrete piece of a real agentic loop. This
lets ANY MCP client (Claude Code, a future Hermes-style runtime, this
kernel's own future multi-agent dispatch) call into the kernel's real
capabilities using the same protocol delentia-mcp-ecosystem already
speaks — reusing an existing standard instead of inventing a new
tool-call wire format.

Uses `mcp.server.mcpserver.MCPServer` (the real, current mcp>=2.0 API —
`FastMCP` was renamed to `MCPServer` in mcp 2.x; confirmed by direct
inspection of the installed package, not assumed from older docs).
"""
import re
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.sandbox import run_sandboxed
from rct_control_plane.nodal_assembly import assemble
from rct_control_plane.algo_32_mctr import ChainMerger, AnswerSynthesizer
from rct_control_plane.autonomous_loop import AutonomousLoop
from rct_control_plane.agent_profile import delegate_to_profile
from rct_control_plane.agent_memory import MemoryType
from rct_control_plane.scheduler import schedule_reminder, check_and_fire_due_reminders, schedule_self_evolution
from rct_control_plane.exchange_bridge import NeuralExchangeBridge, PathTraversalError
from rct_control_plane.algo_34_swcar import WebCrawler
from rct_control_plane.ground_truth_store import GroundTruthStore
from rct_control_plane.git_worktree_isolator import GitWorktreeIsolator

# Round 32: real repo root for the read-only file-access tools (Task 73) -
# mcp_server.py lives at <repo_root>/rct_control_plane/mcp_server.py.
REPO_ROOT = Path(__file__).resolve().parent.parent
_SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".delentia_worktrees", ".venv", "venv"}

mcp = MCPServer("delentia-kernel")
_kernel = AlgorithmKernel41()
_exchange_bridge = NeuralExchangeBridge()
_web_crawler = WebCrawler()
_worktree_isolator = GitWorktreeIsolator()


def _hash_embed_query(text: str, dim: int = 384):
    """Real, deterministic, content-derived text->vector (feature-hashed
    signed bag-of-words, L2-normalized) - the exact same real "hashing
    trick" technique already established in algo_36_rflh.py's
    _embed_text, reused here (not duplicated logic reinvented) so
    delentia_assemble_nodes can feed real vector_search a real query
    vector instead of a fabricated/random one."""
    import hashlib
    import re
    import numpy as np
    vector = np.zeros(dim, dtype=np.float64)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % dim
        sign = 1.0 if (digest[8] & 1) == 0 else -1.0
        vector[bucket] += sign
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()


# Real allowlist mapping a JSON-safe node name to the kernel method it
# invokes. This is a security boundary (MCP tool args are untrusted
# JSON, never arbitrary Python callables) - extend deliberately per
# reviewed node, not open-ended.
_ALLOWED_ASSEMBLY_NODES = {
    "algo_05_graphrag": lambda k, q: (k.algo_05_graphrag, (q,), {}),
    "algo_17_graph_traversal": lambda k, q: (k.algo_17_graph_traversal, ([], []), {"operation": "stats"}),
    "algo_16_vector_search": lambda k, q: (k.algo_16_vector_search, (_hash_embed_query(q),), {"k": 5}),
    "algo_30_abv": lambda k, q: (k.algo_30_abv, (q, []), {}),
    "algo_41_crystallize_golden_keywords": lambda k, q: (k.crystallize_golden_keywords, (q,), {}),
}


@mcp.tool()
async def delentia_process_intent(intent: str) -> dict:
    """Run a real intent through Delentia's full deep pipeline: RCT-7
    decomposition, FDIA safety gate, JITNA-signed audit trail, Fast/Slow
    routing, and real downstream execution (Reflexion+/BBA-PCF/MCTR or a
    fast no-LLM path, depending on real risk/scope)."""
    return await _kernel.process_intent_deep_pipeline(intent)


@mcp.tool()
async def delentia_run_sandboxed_command(command: str, timeout_seconds: float = 10.0) -> dict:
    """Run a real shell command in a local-process sandbox (real timeout
    with real process-tree termination, real output cap, real denylist
    checked before execution — NOT container-isolated; see sandbox.py's
    module docstring for the honest scope of this protection)."""
    result = run_sandboxed(command, timeout_seconds=timeout_seconds)
    return {
        "stdout": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code,
        "timed_out": result.timed_out, "blocked_reason": result.blocked_reason,
    }


@mcp.tool()
async def delentia_assemble_nodes(query: str, node_names: list[str]) -> dict:
    """Real Nodal Assembly: dispatch the named real kernel algorithms
    concurrently, merge their real results into one synthesized answer.
    node_names must be from the real allowlist (not arbitrary method
    names) - this is a security boundary, not a convenience shortcut."""
    nodes = []
    for name in node_names:
        if name not in _ALLOWED_ASSEMBLY_NODES:
            return {"error": f"'{name}' is not an allowed assembly node"}
        fn, args, kwargs = _ALLOWED_ASSEMBLY_NODES[name](_kernel, query)
        nodes.append((name, fn, args, kwargs))
    answer = await assemble(query, nodes, ChainMerger(), AnswerSynthesizer())
    return {"answer": answer.answer, "confidence": answer.confidence, "chains_used": answer.chains_used}


@mcp.tool()
async def delentia_autonomous_loop(goal: str, max_iterations: int = 5) -> dict:
    """Real autonomous decide/act/observe loop over this kernel's MCP
    tools. Bounded by max_iterations and a 120s wall-clock cap. Only has
    access to this server's own already safety-reviewed tools."""
    loop = AutonomousLoop(mcp_server=mcp, persistence=_kernel._persistence,
                           max_iterations=max_iterations, namespace="mcp_loop")
    return await loop.run(goal)


@mcp.tool()
async def delentia_delegate(profile_name: str, sub_goal: str, max_iterations: int = 3) -> dict:
    """Delegate a sub-goal to a real, isolated agent profile (own MEE
    growth state + own persistence namespace), running its own
    AutonomousLoop. Multiple profiles can be delegated to concurrently
    with genuinely independent state."""
    return await delegate_to_profile(_kernel, profile_name, sub_goal, max_iterations)


@mcp.tool()
async def delentia_remember(content: str, memory_type: str = "fact") -> dict:
    """Store a real memory in the kernel's default namespace, recallable
    later via delentia_recall (semantic ranking, not exact match)."""
    memory_id = await _kernel._agent_memory.store(content, MemoryType(memory_type))
    return {"memory_id": memory_id}


@mcp.tool()
async def delentia_recall(query: str, limit: int = 5) -> dict:
    """Recall real memories from the kernel's default namespace,
    ranked by real semantic similarity to the query."""
    memories = await _kernel._agent_memory.recall(query, limit=limit)
    return {"memories": memories}


@mcp.tool()
async def delentia_schedule_reminder(goal: str, fire_in_seconds: float) -> dict:
    """Schedule a real, session-scoped reminder that runs a real
    AutonomousLoop for `goal` once it becomes due. Session-local, not a
    cron/calendar system - call delentia_check_reminders to actually
    fire due ones."""
    reminder_id = schedule_reminder(_kernel, goal, fire_in_seconds)
    return {"reminder_id": reminder_id}


@mcp.tool()
async def delentia_check_reminders() -> dict:
    """Poll for due reminders and really run each one's goal through a
    real AutonomousLoop, marking each fired only after a real result."""
    results = await check_and_fire_due_reminders(_kernel)
    return {"fired": results}


@mcp.tool()
async def delentia_crystallize_keywords(text: str) -> dict:
    """Real Golden Keyword Extraction (Round 24): scores real Shannon
    entropy per candidate word, keeps those >= 0.8, adds them as real
    nodes to the kernel's persistent Concept Map, and feeds the top
    keyword into the real ALGO-40 ITSR recommender."""
    return _kernel.crystallize_golden_keywords(text)


@mcp.tool()
async def delentia_verify_intent_conservation(original_intent: str, stage_representations: dict) -> dict:
    """Real per-stage semantic fidelity check (Round 24): does each
    named pipeline stage's text still carry the original intent's real
    meaning, using the ported SemanticMatcher."""
    return _kernel.verify_intent_conservation(original_intent, stage_representations)


@mcp.tool()
async def delentia_schedule_self_evolution(interval_seconds: float = 3600.0) -> dict:
    """Schedules a real periodic ALGO-08 self-evolution cycle (Round 25).
    Fires via delentia_check_reminders like any other reminder, but is
    dispatched directly as a real algorithm call, not routed through an
    LLM-driven loop."""
    reminder_id = schedule_self_evolution(_kernel, interval_seconds)
    return {"reminder_id": reminder_id}


@mcp.tool()
async def delentia_list_exchange_files(category: str = "all") -> dict:
    """Real listing of the Neural Exchange Bridge's shared file-transfer
    directory (Round 31): categories are projects/audio/video/logs/
    datasets/podcasts, each entry includes a real SHA-256 checksum.
    `category` is validated against path traversal (Round 31 security fix)."""
    try:
        return {"files": _exchange_bridge.list_files(category)}
    except PathTraversalError as e:
        return {"error": str(e)}


@mcp.tool()
async def delentia_read_exchange_file(category: str, filename: str) -> dict:
    """Real read of a file from the Neural Exchange Bridge, with its
    real SHA-256 integrity hash. Content is returned as UTF-8 text when
    decodable, otherwise as a note that it's binary (never silently
    corrupts binary content by force-decoding it)."""
    try:
        result = _exchange_bridge.read_file(category, filename)
    except PathTraversalError as e:
        return {"error": str(e)}
    if result is None:
        return {"error": f"not found: {category}/{filename}"}
    try:
        text = result["content"].decode("utf-8")
        return {**{k: v for k, v in result.items() if k != "content"}, "content_text": text}
    except UnicodeDecodeError:
        return {**{k: v for k, v in result.items() if k != "content"}, "content_binary": True}


@mcp.tool()
async def delentia_save_exchange_file(category: str, filename: str, content_text: str) -> dict:
    """Real save of UTF-8 text content into the Neural Exchange Bridge.
    `category`/`filename` are validated against path traversal (Round 31
    security fix) before anything touches the filesystem."""
    try:
        return _exchange_bridge.save_file(category, filename, content_text.encode("utf-8"))
    except PathTraversalError as e:
        return {"error": str(e)}


@mcp.tool()
async def delentia_crawl_url(url: str) -> dict:
    """Real web crawl of a single URL (Round 31), subject to SWCAR's real
    robots.txt honoring, per-domain rate limiting, and circuit breaker -
    not a fabricated fetch, a genuine HTTP GET through algo_34_swcar."""
    page = await _web_crawler.crawl(url)
    return page.model_dump(mode="json")


@mcp.tool()
async def delentia_query_audit_log(limit: int = 50) -> dict:
    """Real query of the kernel's persisted audit trail (Round 31) -
    every append_audit call this session (ARCHITECT_VETO events, etc.)
    is queryable here, most recent first."""
    return {"entries": _kernel._persistence.recent_audit(limit=limit)}


@mcp.tool()
async def delentia_query_intents(user_id: Optional[str] = None, limit: int = 20) -> dict:
    """Real query of persisted intents processed by the kernel (Round 31),
    optionally filtered by user_id, most recent first."""
    return {"intents": _kernel._persistence.list_intents(user_id=user_id, limit=limit)}


@mcp.tool()
async def delentia_check_ground_truth_claim(subject: str, predicate: str, claimed_value: str) -> dict:
    """Real ALGO-33 ground-truth check (Round 31): verifies a claimed
    fact against the kernel's persisted, seeded ground-truth database.
    Returns matches=None (honest unknown) when the subject/predicate
    pair isn't seeded - never guesses."""
    return _kernel._ground_truth_store.check_claim(subject, predicate, claimed_value)


def _resolve_within_repo(relative_path: str) -> Path:
    """Real traversal guard for repo-wide (not just exchange-bridge-scoped)
    file access - Round 32 Task 73. Generalizes Round 31's
    _safe_path_component to a relative path that may contain
    subdirectories."""
    resolved = (REPO_ROOT / relative_path).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise PathTraversalError(f"path escapes repo root: {relative_path!r}")
    return resolved


@mcp.tool()
async def delentia_read_repo_file(relative_path: str, max_bytes: int = 200_000) -> dict:
    """Real, read-only access to any file inside this kernel's own repo
    (Round 32) - closes the gap where Round 31's file tools were scoped
    only to the exchange/ bridge directory. Bounded to max_bytes to avoid
    dumping huge binaries/model weights into an MCP response. Write/patch
    access is deliberately NOT included this round (higher blast radius,
    needs its own explicit sign-off - see Round 32 synthesis)."""
    try:
        resolved = _resolve_within_repo(relative_path)
    except PathTraversalError as e:
        return {"error": str(e)}
    if not resolved.is_file():
        return {"error": f"not found: {relative_path}"}
    raw = resolved.read_bytes()[:max_bytes]
    try:
        text = raw.decode("utf-8")
        return {"path": relative_path, "content_text": text, "truncated": resolved.stat().st_size > max_bytes}
    except UnicodeDecodeError:
        return {"path": relative_path, "error": "file is not valid UTF-8 text (binary content not returned)"}


@mcp.tool()
async def delentia_search_repo_files(pattern: str, glob: str = "**/*.py", max_results: int = 30) -> dict:
    """Real, read-only grep-style search across this kernel's own repo
    (Round 32) - a real work grep, not a fabricated result. Skips
    .git/__pycache__/node_modules/.delentia_worktrees/venv directories."""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"invalid regex: {e}"}
    matches = []
    for path in REPO_ROOT.glob(glob):
        if len(matches) >= max_results:
            break
        if not path.is_file() or any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                if regex.search(line):
                    matches.append({
                        "path": path.relative_to(REPO_ROOT).as_posix(),
                        "line_number": i,
                        "line_text": line.strip(),
                    })
                    if len(matches) >= max_results:
                        break
        except OSError:
            continue
    return {"matches": matches}


@mcp.tool()
async def delentia_list_capabilities() -> dict:
    """Real list of every capability registered in the kernel's
    CapabilityRegistry (Round 32) - closes the Hermes skills_list gap
    with zero new logic (the registry has existed since Round 26)."""
    return {"capabilities": _kernel._capability_registry.list_capabilities()}


@mcp.tool()
async def delentia_convert_content(content_id: str, version: int, target_format: str) -> dict:
    """Real ALGO-23 format conversion (Round 26 capability, exposed as an
    MCP tool in Round 32): converts previously-saved content to html/pdf/
    json. Honestly reports converted=False for unsupported formats."""
    return await _kernel._content_box.convert_content(content_id, version, target_format)


@mcp.tool()
async def delentia_synthesize_function(capability_spec: str, function_name: str, smoke_test_code: str) -> dict:
    """Real ALGO-39 on-the-fly single-function synthesis (Round 27
    capability, exposed as an MCP tool in Round 32): generates a real
    Python function via the LLM, writes it + a real smoke test, and
    actually executes it in the sandbox. Honestly reports verified=False
    (not a crash) when the generated code fails its own smoke test."""
    return await _kernel.algo_39_genesis_synthesize_module(capability_spec, function_name, smoke_test_code)


@mcp.tool()
async def delentia_export_session_state(session_id: str) -> dict:
    """Real ALGO-06 JITNA state container export (Round 27 capability,
    exposed as an MCP tool in Round 32): real, signed, portable export
    of a session's reconstructed context."""
    return _kernel.algo_06_jitna_export_state_container(session_id)


@mcp.tool()
async def delentia_import_session_state(packet: dict) -> dict:
    """Real ALGO-06 JITNA state container import (Round 27 capability,
    exposed as an MCP tool in Round 32): real signature verification
    before ever handing back "restored" context - a tampered or
    unverifiable packet honestly returns no context."""
    return _kernel.algo_06_jitna_import_state_container(packet)


@mcp.tool()
async def delentia_generate_image(prompt: str, num_steps: int = 6, width: int = 256, height: int = 256) -> dict:
    """Real ALGO-14 RCT-Diffusion image generation (exposed as an MCP
    tool in Round 32) - real diffusers-backed generation (segmind/tiny-sd,
    CPU). Runs on CPU and is slow, not claiming GPU speed it doesn't have."""
    return await _kernel.algo_14_rct_diffusion(prompt, num_steps=num_steps, width=width, height=height)


@mcp.tool()
async def delentia_create_worktree(agent_id: str, base_branch: str = "main") -> dict:
    """Real git worktree creation for isolated parallel subagents (Round
    32, Architect-approved). Always creates a branch named
    swarm/agent_{agent_id} under .delentia_worktrees/ - never touches
    main or any branch outside that naming convention."""
    return _worktree_isolator.create_worktree(agent_id, base_branch)


@mcp.tool()
async def delentia_remove_worktree(agent_id: str) -> dict:
    """Real removal of an isolated agent worktree created via
    delentia_create_worktree - only ever operates on the isolated
    .delentia_worktrees/{agent_id} path, never the main working tree."""
    return {"removed": _worktree_isolator.remove_worktree(agent_id)}


@mcp.tool()
async def delentia_list_worktrees() -> dict:
    """Real list of currently active isolated agent worktrees."""
    return {"active": _worktree_isolator.list_active()}


if __name__ == "__main__":
    mcp.run()
