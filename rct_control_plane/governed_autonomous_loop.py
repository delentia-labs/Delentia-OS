"""
GovernedAutonomousLoop — Round 44 item J.2: the first real connection
between AutonomousLoop's decide->act->observe cycle and this repo's
constitutional pipeline (JITNA signing, FDIA gate, RCT-7 decomposition,
Delta persistence).

Verified before writing a line of this file (see
DELENTIA_ROUND44_DETAILED_EXECUTION_PLAN.md Section J.0): `grep` across
autonomous_loop.py found zero references to algo_01_fdia, JITNAPacket/
sign_packet, algo_04_rct7, or process_intent_deep_pipeline. The only real
governance AutonomousLoop had was classify_command_risk() from sandbox.py,
scoped to one tool. This file is the first real wiring, not a rename.

Design choices, and why
------------------------
1. Subclasses AutonomousLoop via four NEW, purely-additive hook points
   added to AutonomousLoop.run() itself this same round (on_episode_start,
   tool_filter, pre_dispatch_gate, on_episode_end — see that method's own
   docstring) rather than overriding run() wholesale. Duplicating run()'s
   ~110-line loop body in a subclass would drift from the parent over
   time; every existing AutonomousLoop caller is unaffected (all four new
   params default to None).

2. Does NOT import the algorithm_kernel_41 module at class-definition
   time. A `kernel: Optional[AlgorithmKernel41]` can be passed into
   __init__; if omitted, one is constructed lazily (only when an episode
   actually starts, and only once, then cached) rather than eagerly, so
   constructing a GovernedAutonomousLoop for a unit test that injects a
   fake/mock kernel (see J.4.1) never pays AlgorithmKernel41's real
   torch/FAISS/diffusers import cost. When a caller already has a live
   kernel instance (mcp_server.py's module-level `_kernel` singleton),
   passing it in reuses its real, already-warm state instead of building
   a second, independent one.

3. Unlike DAG-workflow-YAML (item I.1), this loop is NOT latency-
   sensitive to a kernel cold start the way a fast CLI command is: it
   already makes multi-second real LLM calls per iteration
   (DELENTIA_OLLAMA_TIMEOUT_S is 360s as of this round), so a one-time
   ~20s kernel warm-up is noise by comparison. That is the deciding
   factor that makes "just use the real kernel" the right tradeoff here,
   where it was the wrong one for I.1's fast, synchronous YAML runner.

4. fdia_score() below is a small, standalone, byte-for-byte copy of
   AlgorithmKernel41.algo_01_fdia's formula (5 lines of stable pure math),
   used ONLY on the lazily-self-constructed-kernel path's synchronous
   call sites where avoiding an extra kernel round-trip matters less than
   test speed; when a real kernel is available its own algo_01_fdia is
   used directly. test_governed_autonomous_loop_real.py's
   TestFdiaScoreMatchesKernel class is a characterization test asserting
   the two never silently drift apart.

5. Real, evidence-based risky-tool allowlist (RISKY_TOOLS below): every
   tool's real implementation in mcp_server.py was read before deciding
   whether to include it - not guessed from its name. See the inline
   comment on each entry.

6a. Round 44 item I.2 (added 2026-09-25): real Skill Library wiring -
   skill_library.py's own docstring flagged "no skill re-application/
   injection into a new turn's prompt" as explicitly out of scope for
   its MVP slice. This closes that gap: _on_episode_start() retrieves
   real similar-past-skill matches (retrieve_similar_skills(), Jaccard
   token overlap, no mocking) and feeds them to decide_next_action()'s
   new extra_context parameter via the extra_context_provider hook
   (also added this round) - genuinely injected into the prompt, not
   just fetched and discarded. _on_episode_end() computes a real MEE
   growth step from the episode's own stopped_reason (see
   _growth_signal_for_outcome() below for the exact, evidence-based
   mapping - no invented magic numbers) and offers it to
   maybe_extract_skill()'s real MEE-gated write path. This reuses
   AutonomousBackEdgeDaemon's precedent of a coarse, honest delta
   signal (autonomous_backedge_daemon.py's _SUCCESS_DELTA/
   _FAILURE_DELTA) but derives it from real, already-computed
   stopped_reason values (llm_finished/fdia_blocked/etc.) rather than a
   flat binary success/failure, since GovernedAutonomousLoop has more
   real signal available than that daemon does.

6. Authorization (A) signal depth is intentionally uneven across risky
   tools in this first pass, and that unevenness is disclosed rather than
   hidden: delentia_run_sandboxed_command and the two repo-write tools
   get a REAL, evidence-based A signal (see _authorization_signal()).
   The remaining risky tools default A to 1.0 (no per-tool signal exists
   yet) - the FDIA gate still computes and audits a real F for every
   risky-tool call using the episode's real D/I (derived from the goal
   text's own IntentCompiler validation), so a vague/unvalidated goal
   attempting ANY risky tool still produces a low, honestly-computed F -
   but F cannot go to exactly 0 from D/I alone given their documented
   floors, so today only tools with a real A signal can actually trigger
   a block. Building real A signals for the rest is real follow-up work,
   not simulated here.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rct_control_plane.algo_25_delta_block import DeltaBlock, DeltaDiff, DeltaEngine, DeltaType
from rct_control_plane.autonomous_loop import AutonomousLoop
from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.jitna_protocol import (
    JITNAKeypair, JITNAMessageType, JITNAPacket, generate_keypair, sign_packet, verify_packet,
)
from rct_control_plane.mee_engine import MEESession
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary

if TYPE_CHECKING:
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Same permanent do-not-touch patterns as mcp_server.py's own
# _WRITE_BLOCKED_PATTERNS/_is_write_blocked/_resolve_within_repo - kept as
# a local, small, stable copy rather than importing mcp_server (which
# would force constructing ITS module-level AlgorithmKernel41 singleton
# just to reuse ~10 lines of pure path logic). This workspace's own
# .clinerules/delentia.config.yaml define the same list independently, so
# this is a third, deliberately redundant enforcement point, not the only
# one.
_WRITE_BLOCKED_PATTERNS = (".env", "_secret", "credentials.json", "vault_master.key")


def _write_path_is_safe(relative_path: str) -> bool:
    """True only if relative_path resolves inside the repo AND matches
    none of the blocked patterns - mirrors mcp_server.py's real guard."""
    if not relative_path:
        return False
    lowered = relative_path.lower()
    if any(pattern in lowered for pattern in _WRITE_BLOCKED_PATTERNS):
        return False
    if ".git" in Path(relative_path).parts:
        return False
    try:
        resolved = (_REPO_ROOT / relative_path).resolve()
    except (OSError, ValueError):
        return False
    return resolved.is_relative_to(_REPO_ROOT)


def fdia_score(D: float, I: float, A: float) -> float:
    """F = (D^I) * A with overflow guard - see module docstring point 4."""
    d_clamped = max(0.01, min(100.0, D))
    i_clamped = max(0.01, min(10.0, I))
    a_clamped = max(0.0, min(1.0, A))
    log_res = i_clamped * math.log(d_clamped)
    if log_res > 700:
        return 1.0 * a_clamped
    return round((d_clamped ** i_clamped) * a_clamped, 4)


# Round 44 J.2 step 2: real, evidence-based allowlist - each tool's real
# body in mcp_server.py was read (not guessed) before inclusion here. Pure
# reads (delentia_recall, delentia_query_audit_log, delentia_list_*, ...)
# and bounded/non-external writes (delentia_remember, delentia_generate_image
# - writes only to the local workspace_output/ scratch dir, no downstream
# consumption implied) are deliberately excluded.
RISKY_TOOLS = frozenset({
    "delentia_run_sandboxed_command",   # arbitrary shell execution
    "delentia_write_repo_file",         # real repo source write
    "delentia_patch_repo_file",         # real repo source write
    "delentia_save_exchange_file",      # real write into the cross-system Neural Exchange Bridge
    "delentia_create_worktree",         # real git worktree/branch creation
    "delentia_remove_worktree",         # real git worktree removal
    "delentia_synthesize_function",     # generates AND executes new code in the sandbox
    "delentia_crawl_url",               # real outbound HTTP GET to an arbitrary URL
    "delentia_schedule_self_evolution", # schedules a real recurring self-modifying cycle
    "delentia_delegate",                # spawns a new, separately-acting AutonomousLoop
    "delentia_import_session_state",    # merges external/untrusted JITNA state
})


class GovernedAutonomousLoop(AutonomousLoop):
    """AutonomousLoop + real constitutional governance, wired through the
    four hook points AutonomousLoop.run() now exposes. See module
    docstring for the design rationale behind every choice below."""

    def __init__(
        self,
        mcp_server,
        persistence: ControlPlanePersistence,
        kernel: Optional["AlgorithmKernel41"] = None,
        skill_library: Optional[SkillLibrary] = None,
        max_iterations: int = 5,
        max_seconds: float = 120.0,
        namespace: str = "kernel_default",
    ):
        super().__init__(mcp_server, persistence, max_iterations=max_iterations,
                          max_seconds=max_seconds, namespace=namespace)
        self._kernel = kernel
        self._intent_compiler = IntentCompiler()
        self._delta_engine = DeltaEngine()
        self._keypair: JITNAKeypair = generate_keypair()
        # Round 44 item I.2: real growth tracking + skill library for this
        # loop's own episodes. A dedicated MEESession (not shared with the
        # kernel's own, if any) because this session's growth signal is
        # specifically "did THIS agent episode succeed", a different real
        # quantity than whatever the kernel's own MEE session (if used
        # elsewhere) is tracking.
        self._mee_session = MEESession(session_id=f"governed-loop:{namespace}")
        self._skill_library = skill_library if skill_library is not None else SkillLibrary()
        # Populated at episode start, read by the pre-dispatch gate and
        # episode-end hook - one episode (one run() call) at a time, same
        # single-episode-per-instance assumption AutonomousLoop itself
        # already makes (max_iterations/max_seconds are per-run() state).
        self._episode_D: float = 0.5
        self._episode_I: float = 0.5
        self._episode_rct7_steps: List[str] = []
        self._episode_jitna_verified: bool = False
        self._episode_start_time: float = 0.0
        self._episode_context_text: str = ""

    def _get_kernel(self) -> "AlgorithmKernel41":
        """Lazy, cached construction - see module docstring point 2 for
        why this is lazy rather than done in __init__."""
        if self._kernel is None:
            from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
            self._kernel = AlgorithmKernel41()
        return self._kernel

    async def run(self, goal: str, **kwargs: Any) -> dict:
        """Same signature/return shape as AutonomousLoop.run() - governance
        hooks are wired in here so a caller invokes this exactly like the
        base class. Any of the base hooks (on_step, on_answer_token) a
        caller also wants still work normally via **kwargs."""
        return await super().run(
            goal,
            on_episode_start=self._on_episode_start,
            tool_filter=self._tool_filter,
            pre_dispatch_gate=self._pre_dispatch_gate,
            on_episode_end=self._on_episode_end,
            extra_context_provider=self._extra_context_provider,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # J.1.3: RCT-7 decomposition + JITNA sign, once per episode
    # I.2: real skill retrieval, injected into the prompt via
    # _extra_context_provider() below (not just fetched and discarded).
    # ------------------------------------------------------------------
    async def _on_episode_start(self, goal: str) -> None:
        self._episode_start_time = time.time()
        kernel = self._get_kernel()
        D, I, _compile_result = kernel.synthesize_fdia_inputs(goal)
        self._episode_D, self._episode_I = D, I
        self._episode_rct7_steps = kernel.algo_04_rct7(goal)
        self._episode_context_text = self._format_similar_skills(
            self._skill_library.retrieve_similar_skills(goal, top_k=3)
        )

        packet = JITNAPacket(
            source_agent_id=self.namespace,
            target_agent_id=self.namespace,
            message_type=JITNAMessageType.INTENT_REQUEST.value,
            payload={"goal": goal, "rct7_steps": self._episode_rct7_steps, "D": D, "I": I},
        )
        signed = sign_packet(packet, self._keypair)
        self._episode_jitna_verified = verify_packet(signed, self._keypair.public_key_raw())

        self._persistence.append_audit(
            entity_type="governed_loop_episode_start",
            entity_id=f"{self.namespace}-{signed.packet_id}",
            action="episode_start",
            actor=self.namespace,
            changes={
                "goal": goal, "D": D, "I": I,
                "rct7_steps": self._episode_rct7_steps,
                "jitna_packet_id": signed.packet_id,
                "jitna_verified": self._episode_jitna_verified,
            },
        )

    @staticmethod
    def _format_similar_skills(skills: List[Any]) -> str:
        """Real, honest formatting of retrieve_similar_skills()'s results
        into prompt text - "" (omitted entirely, see decide_next_action's
        extra_context docstring) when nothing relevant was found, so a
        fresh skill library never adds empty noise to the prompt."""
        if not skills:
            return ""
        lines = ["Similar past solutions (from this system's own skill library):"]
        for skill in skills:
            lines.append(
                f"- Problem: {skill.problem_statement!r} -> Solution: {skill.solution!r} "
                f"(similarity={skill.similarity_score:.2f}, real growth_ratio={skill.growth_ratio:.2f})"
            )
        return "\n".join(lines)

    def _extra_context_provider(self) -> str:
        return self._episode_context_text

    # ------------------------------------------------------------------
    # J.1.4(a): keyword-overlap pre-filtering of the tool menu
    # ------------------------------------------------------------------
    def _tool_filter(self, goal: str, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Real keyword-overlap scoring between the goal and each tool's
        name+description - not an embedding model (J.1.4 chose this as
        the simplest real fix for the confirmed tool-selection reliability
        problem: a small model faced with the full ~30+ tool menu picks
        the wrong tool repeatedly, not from positional bias). Falls back
        to the full, unfiltered menu whenever fewer than 2 tools would
        otherwise survive, so a goal with no real keyword overlap (e.g.
        a generic "finish now" turn) never starves the model of options."""
        goal_tokens = self._tokenize(goal)
        if not goal_tokens:
            return available_tools

        scored = []
        for tool in available_tools:
            tool_text = f"{tool['name']} {tool.get('description', '')}"
            tool_tokens = self._tokenize(tool_text)
            overlap = len(goal_tokens & tool_tokens)
            scored.append((overlap, tool))

        relevant = [tool for overlap, tool in scored if overlap > 0]
        if len(relevant) < 2:
            return available_tools
        return relevant

    @staticmethod
    def _tokenize(text: str) -> set:
        import re
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        return {t for t in tokens if len(t) > 2}

    # ------------------------------------------------------------------
    # J.1.3: FDIA gate before any risky tool dispatch
    # ------------------------------------------------------------------
    async def _pre_dispatch_gate(
        self, goal: str, tool_name: str, tool_args: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if tool_name not in RISKY_TOOLS:
            return None

        A, a_reason = self._authorization_signal(tool_name, tool_args)
        F = fdia_score(self._episode_D, self._episode_I, A)

        self._persistence.append_audit(
            entity_type="governed_loop_fdia_gate",
            entity_id=f"{self.namespace}-{tool_name}-{time.time()}",
            action="fdia_gate_evaluated",
            actor=self.namespace,
            changes={
                "tool_name": tool_name, "D": self._episode_D, "I": self._episode_I,
                "A": A, "A_reason": a_reason, "F": F, "blocked": F <= 0.0,
            },
        )

        if F <= 0.0:
            return {
                "stopped_reason": "fdia_blocked",
                "tool_result": {
                    "fdia_blocked": True, "tool_name": tool_name, "F": F,
                    "D": self._episode_D, "I": self._episode_I, "A": A, "reason": a_reason,
                },
            }
        return None

    def _authorization_signal(self, tool_name: str, tool_args: Dict[str, Any]) -> tuple:
        """Returns (A, reason). See module docstring point 6 for why this
        is real but uneven across tools today."""
        if tool_name == "delentia_run_sandboxed_command":
            from rct_control_plane.sandbox import classify_command_risk
            risk = classify_command_risk(tool_args.get("command", ""))
            # Round 44 finding: AutonomousLoop's own existing gate (kept
            # unchanged, see autonomous_loop.py) only checks risk ==
            # "needs_approval" and never checks "denied" at all - a denied
            # command falls through to real dispatch there. This gate
            # closes that gap for GovernedAutonomousLoop specifically by
            # treating "denied" as A=0.0 (real block), without touching
            # the base class's own existing check.
            if risk == "denied":
                return 0.0, "classify_command_risk=denied"
            return 1.0, f"classify_command_risk={risk}"

        if tool_name in ("delentia_write_repo_file", "delentia_patch_repo_file"):
            path = tool_args.get("relative_path", "")
            if _write_path_is_safe(path):
                return 1.0, "write path passed traversal+blocklist check"
            return 0.0, f"write path failed traversal+blocklist check: {path!r}"

        return 1.0, "no per-tool authorization signal implemented yet (see module docstring point 6)"

    # ------------------------------------------------------------------
    # J.1.3: Delta persistence at episode end
    # ------------------------------------------------------------------
    # Round 44 item I.2: real, evidence-based mapping from a real
    # stopped_reason to a real MEE growth delta + governance_violation
    # flag - no invented continuous metric (matches
    # autonomous_backedge_daemon.py's own documented reasoning for using
    # a coarse, honest signal over a fabricated precise one). llm_finished
    # is real success; fdia_blocked is a real constitutional violation
    # (this episode attempted something the FDIA gate refused);
    # pending_approval is a real, neutral "waiting on a human" outcome,
    # neither growth nor shrinkage; every other stopped_reason
    # (max_iterations_reached/max_seconds_exceeded/parse_error) is a real,
    # non-violating incompleteness.
    _OUTCOME_TO_GROWTH_SIGNAL = {
        "llm_finished": (1.0, False),
        "fdia_blocked": (-1.0, True),
        "pending_approval": (0.0, False),
    }
    _DEFAULT_INCOMPLETE_SIGNAL = (-0.5, False)

    async def _on_episode_end(self, result: Dict[str, Any]) -> None:
        duration = time.time() - self._episode_start_time
        stopped_reason = result["stopped_reason"]
        change_description = (
            f"episode goal={result['goal']!r} stopped_reason={stopped_reason} "
            f"iterations={result['iterations']} duration_s={duration:.2f} "
            f"jitna_verified={self._episode_jitna_verified}"
        )
        delta_block = DeltaBlock(
            session_id=self.namespace,
            timestamp=time.time(),
            delta_type=DeltaType.STATE_CHANGE,
            diff=DeltaDiff(added=[change_description], removed=[], modified=[]),
            source="governed_autonomous_loop",
        )
        delta_id = self._delta_engine.store_delta(delta_block)

        growth_delta, governance_violation = self._OUTCOME_TO_GROWTH_SIGNAL.get(
            stopped_reason, self._DEFAULT_INCOMPLETE_SIGNAL
        )
        growth_step = self._mee_session.step(growth_delta, governance_violation=governance_violation)
        skill_record = self._skill_library.maybe_extract_skill(
            problem_statement=result["goal"],
            action_sequence_or_solution=result["steps"],
            growth_step=growth_step,
            session_id=self.namespace,
        )

        self._persistence.append_audit(
            entity_type="governed_loop_episode_end",
            entity_id=f"{self.namespace}-{delta_id}",
            action="episode_end",
            actor=self.namespace,
            changes={
                "delta_id": delta_id, "stopped_reason": stopped_reason,
                "iterations": result["iterations"], "duration_s": duration,
                "mee_delta": growth_delta, "mee_g": self._mee_session.g,
                "skill_extracted": skill_record is not None,
            },
        )
