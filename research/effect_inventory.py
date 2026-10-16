"""
Round 82, plan item T05: the trust boundaries and the inventory of every effect, generated from the code that enforces them.

    python research/effect_inventory.py          # writes research/EFFECT_INVENTORY.md

What is generated: for every tool the runtime exposes, what kind of effect it can have (the one column written by hand: EFFECTS below), who has to approve it (derived from the sets
the loop actually uses), what it may touch, and how it is scoped to the asking person (also derived). A test fails when a tool has no entry, when an entry names a tool that does not
exist, when a hand-written effect label contradicts the loop's own sets (a tool labelled "read" that the loop gates as dangerous, a tool that writes a file but is not always signed), or when
the generated page is out of date. So the page cannot drift from the code, and a new tool cannot be added without deciding what it does.

The page also lists the surfaces that are NOT mediated by the governed loop (the raw /mcp gateway) and what is not covered at all, because an inventory that lists only what is controlled
would flatter the system.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# effect classes (the vocabulary the test enforces)
READ, COMPUTE, OUTSIDE, EGRESS, LOCAL_WRITE, ARTIFACT, CODE, SCHEDULE, DELEGATE, MEMORY, STATE, EXCHANGE = (
    "read", "compute", "outside-text", "egress", "local-write", "artifact-write", "code-exec", "schedule", "delegate", "memory-write", "state-change", "exchange-write")
SIDE_EFFECT = {EGRESS, LOCAL_WRITE, CODE, SCHEDULE, DELEGATE, MEMORY, STATE, EXCHANGE}          # must be gated once an episode has read outside text
INERT_OK = {READ, COMPUTE, ARTIFACT}

# (effect class, what it can touch). Written by hand, checked against the loop's own sets by the test.
EFFECTS: Dict[str, tuple] = {
    "delentia_assemble_nodes": (COMPUTE, "the kernel's built-in analysis algorithms, by name; no files"),
    "delentia_autonomous_loop": (DELEGATE, "starts another governed loop as the asking person (nesting limited to 2)"),
    "delentia_browse_page": (EGRESS, "one public page in a headless browser, name resolved once and pinned, every other host cut off; read-only"),
    "delentia_browser_act": (EGRESS, "click/type/press/scroll on one page; payment, purchase, account-deletion controls and password/card fields refused even when signed"),
    "delentia_check_ground_truth_claim": (COMPUTE, "checks a claim against given text; may use the local model"),
    "delentia_check_reminders": (SCHEDULE, "fires every stored reminder's goal as a new episode (owner-only on chat and API)"),
    "delentia_compress_intent_delta": (COMPUTE, "compresses text it is given"),
    "delentia_convert_content": (OUTSIDE, "converts a document it is given; its output is text from outside"),
    "delentia_crawl_url": (EGRESS, "one HTTP GET; private, loopback and metadata addresses refused at every hop; only an address the person wrote or the agent saw"),
    "delentia_create_worktree": (STATE, "creates a git worktree and branch under the workspace"),
    "delentia_cron_create": (SCHEDULE, "a recurring job that runs unattended as the asking person; always waits for a signature"),
    "delentia_cron_delete": (SCHEDULE, "switches off one of the caller's own jobs (soft delete, history kept)"),
    "delentia_cron_list": (READ, "the caller's own jobs"),
    "delentia_crystallize_keywords": (COMPUTE, "keyword extraction over given text"),
    "delentia_daemon_status": (READ, "scheduler status"),
    "delentia_delegate": (DELEGATE, "a sub-goal to an isolated agent profile with its own memory"),
    "delentia_describe_image": (OUTSIDE, "one image file under the workspace, sent to the owner's vision model after the sovereignty policy"),
    "delentia_expand_tool_output": (READ, "the full text behind a shortened tool result of this episode"),
    "delentia_export_session_state": (STATE, "writes a signed state container"),
    "delentia_generate_image": (ARTIFACT, "one bounded image file under the scratch/exchange folders"),
    "delentia_import_session_state": (OUTSIDE, "merges a state container produced elsewhere: untrusted input"),
    "delentia_list_capabilities": (READ, "the registered capabilities"),
    "delentia_list_exchange_files": (READ, "the exchange folder's file names"),
    "delentia_list_forged_tools": (READ, "the tools a human signed"),
    "delentia_list_worktrees": (READ, "the active worktrees"),
    "delentia_patch_repo_file": (LOCAL_WRITE, "one workspace file; secret-looking files refused; the previous content is stored for rollback"),
    "delentia_process_intent": (CODE, "the deep pipeline, which can execute generated code in the sandbox"),
    "delentia_query_audit_log": (READ, "raw audit rows, which contain every person's goals (owner-only on chat and API)"),
    "delentia_query_intents": (READ, "every person's compiled goals (owner-only on chat and API)"),
    "delentia_read_exchange_file": (OUTSIDE, "one file from the exchange folder, which other systems write"),
    "delentia_read_repo_file": (READ, "one workspace file; secret-looking files refused; text under an untrusted folder taints the episode"),
    "delentia_recall": (READ, "the asking person's memories"),
    "delentia_remember": (MEMORY, "stores a memory in the asking person's namespace with its origin; a persisted instruction survives restarts"),
    "delentia_remove_worktree": (STATE, "removes a git worktree under the workspace"),
    "delentia_run_forged_tool": (COMPUTE, "one pure function a human signed by hash, in its own process with a time limit"),
    "delentia_run_sandboxed_command": (CODE, "a shell command in a local-process sandbox (resource ceilings, environment stripped, risky commands held): NOT a jail"),
    "delentia_save_exchange_file": (EXCHANGE, "one file in the exchange folder, which OTHER systems read: a cross-system write"),
    "delentia_schedule_reminder": (SCHEDULE, "a session-scoped reminder that later runs a goal"),
    "delentia_schedule_self_evolution": (SCHEDULE, "a periodic self-evolution cycle; new capability only enters through the Tool Forge and a human signature"),
    "delentia_search_repo_files": (READ, "a regex search across the workspace; secret-looking files skipped"),
    "delentia_search_sessions": (READ, "the asking person's own past episodes"),
    "delentia_spawn_subagents": (DELEGATE, "up to 3 goals in separate OS processes and git worktrees; the child's taint comes back signed"),
    "delentia_speak": (ARTIFACT, "one bounded audio file under the scratch/exchange folders"),
    "delentia_synthesize_function": (CODE, "generates and executes a function in the sandbox"),
    "delentia_transcribe_audio": (OUTSIDE, "one audio file under the workspace, transcribed locally; the transcript is text from outside"),
    "delentia_verify_intent_conservation": (COMPUTE, "a fidelity check over given text"),
    "delentia_web_search": (OUTSIDE, "the owner's configured search provider; the query leaves under the sovereignty policy; results are screened as third-party content"),
    "delentia_write_repo_file": (LOCAL_WRITE, "one workspace file; secret-looking files refused; the previous content is stored for rollback"),
}

# the raw JSON-RPC gateway (rct_control_plane/mcp_gateway.py): not mediated by the governed loop
GATEWAY_TOOLS = [
    ("delentia_compile_intent", "compiles an intent"), ("delentia_fdia_gate_eval", "evaluates F = D^I x A for given numbers"), ("delentia_cord_entropy_scan", "scans a text"),
    ("delentia_execute_safe_shell", "runs an allow-listed executable (git, python, pytest, ruff, mypy, node, npm, npx, pip) in the gateway workspace; python and npm can run any code"),
    ("delentia_system_health", "status"), ("delentia_workspace_fs", "reads and writes files inside the gateway workspace; secret-looking names refused"),
    ("delentia_git_ops", "git operations inside the gateway workspace"), ("delentia_web_fetch", "an HTTP fetch; private and loopback addresses refused unless the operator allows them"),
    ("delentia_cron_scheduler", "schedules a job"), ("delentia_neural_exchange", "the exchange folder"),
]


def derived(name: str) -> Dict[str, str]:
    from rct_control_plane import governed_autonomous_loop as g
    if name in g._ALWAYS_NEEDS_APPROVAL_TOOLS:
        rule = "a signature on every call"
    elif name in g.TAINT_GATED_TOOLS:
        rule = "FDIA gate; a signature once the episode has read outside text"
    elif name in g.TAINT_EGRESS_TOOLS:
        rule = "FDIA gate; only an address the person wrote or the agent saw; taints the episode"
    elif name in g.TAINT_SOURCE_TOOLS:
        rule = "FDIA gate; its result is outside text and taints the episode"
    else:
        rule = "FDIA gate; reviewed inert"
    if name in g.OWNER_ONLY_TOOLS:
        scope = "owner only on chat channels and the HTTP agent API"
    elif name in g.GovernedAutonomousLoop.MEMORY_TOOLS:
        scope = "pinned to the asker (the loop overwrites its namespace argument)"
    else:
        scope = "person-neutral (reviewed)"
    return {"rule": rule, "scope": scope}


def tool_names() -> List[str]:
    from rct_control_plane.mcp_server import mcp
    return sorted(t.name for t in asyncio.run(mcp.list_tools()))


def render() -> str:
    names = tool_names()
    lines = [
        "# Effect inventory and trust boundaries (generated)", "",
        "Generated by `research/effect_inventory.py` from the sets the governed loop enforces; a test fails when this page is out of date or when a tool has no entry. Round 82, plan item T05.", "",
        "## 1. Data flow and who is trusted with what", "",
        "```", "person (token) -> goal -> GUARD (CORD screen + FDIA gate) -> plan -> tool call -> [taint gate] -> [approval: Ed25519 signature] -> effect", "                                                                            |",
        "                                          audit chain (hash-chained, signed) <- notary (another process) <- witnesses (another operator)", "```", "",
        "| Boundary | What crosses it | What decides |", "|---|---|---|",
        "| person -> runtime | a goal, under a token that names the person (namespace, memory, role come from the token, never from the request) | `api_auth.py`, `api_tokens.py`; a person's token reaches only the agent API and their own data |",
        "| text from outside -> model | pages, files in untrusted folders, search results, images, audio, external MCP output | the taint rule: once shown to the model, every side-effect tool needs a signature, whatever the model asks for |",
        "| model -> tool | a tool name and arguments | the FDIA gate and the owner's policy (can only tighten the built-in floor), then the approval store |",
        "| tool -> world | a file write, a request out, a shell command, a scheduled job, a subagent | the loop (not the model) executes; every call is recorded before it runs when a notary is configured |",
        "| runtime -> record | audit rows, episode signatures | a key the agent's file tools cannot read; a notary in another OS process; independent witnesses |", "",
        "### The trusted computing base", "",
        "authority resolver (token -> person, role), canonicalisation of arguments, the FDIA gate and the owner's policy evaluator, the taint rule, the approval verifier (Ed25519, payload-bound), the executor and its OS limits, the persistent stores, the audit signing key and the notary. "
        "Cryptography proves who wrote a record and that it was not altered; it does not prove the record is true, and it does not help against root on the host.", "",
        "## 2. Every tool, what it can do, who must approve it", "",
        "| Tool | Effect class | What it can touch | Who decides | Person scope |", "|---|---|---|---|---|",
    ]
    for name in names:
        effect, touches = EFFECTS[name]
        d = derived(name)
        lines.append(f"| `{name}` | {effect} | {touches} | {d['rule']} | {d['scope']} |")
    lines += [
        "", "### Tools from outside the runtime", "",
        "External MCP servers (`mcp__<server>__<tool>`) and services reached through the OpenAPI bridge are judged by the same FDIA gate; their results are screened as third-party content and taint the episode; a tool the owner did not declare read-only waits for a signature on every call; descriptions are screened for tool poisoning and the tool list can be pinned by hash.", "",
        "## 3. Surfaces that are NOT mediated by the governed loop", "",
        "The raw JSON-RPC gateway (`rct_control_plane/mcp_gateway.py`, route `/mcp`) runs its own tools. It answers 403 to a per-person token (owner only) and has its own workspace boundary, but it applies **no signed approval, no taint rule and no owner policy**. Treat it as a maintenance surface for the host's owner, and leave it off a host that people other than the owner can reach.", "",
        "| Gateway tool | What it can do |", "|---|---|",
    ]
    for name, what in GATEWAY_TOOLS:
        lines.append(f"| `{name}` | {what} |")
    lines += [
        "", "## 4. Not covered", "",
        "- Root on the host, or the OS user that runs the agent: the shell sandbox is a speed bump with resource ceilings, not a jail, and a key kept where the agent runs can be read by the agent.",
        "- What a model writes in an answer: a signed record shows that the answer was recorded, not that it is true.",
        "- A compromised witness operator together with a compromised host.",
        "- The effects of an external service after a request has left (an e-mail cannot be recalled). Only a workspace file write has a rollback (the previous content is stored); nothing else in this table is reversible by the runtime.",
        "- Tools added later by hand without an entry in `research/effect_inventory.py`: the test refuses them.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    out = ROOT / "research" / "EFFECT_INVENTORY.md"
    out.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(tool_names())} tools, {len(GATEWAY_TOOLS)} gateway tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
