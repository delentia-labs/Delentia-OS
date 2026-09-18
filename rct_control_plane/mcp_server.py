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
from mcp.server.mcpserver import MCPServer

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.sandbox import run_sandboxed
from rct_control_plane.nodal_assembly import assemble
from rct_control_plane.algo_32_mctr import ChainMerger, AnswerSynthesizer
from rct_control_plane.autonomous_loop import AutonomousLoop
from rct_control_plane.agent_profile import delegate_to_profile
from rct_control_plane.agent_memory import MemoryType
from rct_control_plane.scheduler import schedule_reminder, check_and_fire_due_reminders

mcp = MCPServer("delentia-kernel")
_kernel = AlgorithmKernel41()


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


if __name__ == "__main__":
    mcp.run()
