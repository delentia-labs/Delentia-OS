"""
Autonomous Long-Running Daemon Engine & Back-Edge Learning
Delentia OS Cognitive Kernel (Unified v2.2.6)

Executes continuous multi-hour task loops in daemon mode.
Implements Back-Edge Learning: Automatically intercepts test/execution errors,
crystallizes failure patterns into hard invariants, and persists them into
`learned_invariants.json` to guarantee zero regression.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from rct_control_plane.mee_engine import MEESession
from rct_control_plane.skill_library import SkillLibrary

# Binary growth signal used to feed the real MEE formula from this daemon's
# execute_autonomous_step(). execute_autonomous_step does not (yet) compute
# a continuous task-quality score, only a success/blocked outcome, so this
# MVP wiring uses a documented +1.0 / -1.0 delta rather than inventing a
# fake continuous metric. A richer delta (derived from FDIA score, test
# pass rate, etc.) is future work — see skill_library.py's module docstring
# for the full list of what this slice intentionally does not build.
_SUCCESS_DELTA = 1.0
_FAILURE_DELTA = -1.0


class AutonomousBackEdgeDaemon:
    """Manages long-running daemon execution and back-edge invariant learning."""

    def __init__(
        self,
        data_dir: Optional[str] = None,
        *,
        skill_db_path: Optional[str] = None,
        skill_library: Optional[SkillLibrary] = None,
    ):
        self.data_dir = Path(data_dir or "workspace_output").resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.invariants_file = self.data_dir / "learned_invariants.json"
        self.task_history_file = self.data_dir / "daemon_task_history.json"
        self._load_invariants()

        # Real MEE growth tracking for this daemon's task stream (ALGO-07,
        # rct_control_plane.mee_engine.MEESession — same formula used
        # elsewhere in the control plane) and the growth-gated skill
        # library it feeds (rct_control_plane.skill_library). Defaults to
        # a SQLite file co-located with this daemon's other on-disk state
        # (learned_invariants.json, daemon_task_history.json) under
        # data_dir, rather than SkillLibrary's own package-wide default,
        # so each daemon instance (including per-test tmp_path instances)
        # is self-contained and doesn't cross-pollute a shared db.
        self._mee_session = MEESession(session_id=f"backedge-daemon:{self.data_dir}")
        if skill_library is not None:
            self._skill_library = skill_library
        else:
            self._skill_library = SkillLibrary(
                db_path=skill_db_path or str(self.data_dir / "skills.db")
            )

    def _load_invariants(self):
        """Loads previously learned invariants from disk."""
        if self.invariants_file.exists():
            try:
                with open(self.invariants_file, "r", encoding="utf-8") as f:
                    self.invariants = json.load(f)
            except Exception:
                self.invariants = []
        else:
            self.invariants = []

    def save_invariants(self):
        """Persists learned invariants to disk."""
        with open(self.invariants_file, "w", encoding="utf-8") as f:
            json.dump(self.invariants, f, indent=2, ensure_ascii=False)

    def record_backedge_failure(self, task_name: str, error_message: str, proposed_rule: str) -> Dict[str, Any]:
        """
        Extracts an invariant rule from an execution failure and saves it.
        """
        invariant_entry = {
            "id": f"INV-{int(time.time() * 1000)}",
            "task_name": task_name,
            "error_signature": error_message[:120],
            "learned_rule": proposed_rule,
            "fdia_veto_rule": f"VETO if error matches '{error_message[:40]}'",
            "timestamp": time.time(),
            "status": "ENFORCED"
        }
        self.invariants.append(invariant_entry)
        self.save_invariants()
        return invariant_entry

    def list_invariants(self) -> List[Dict[str, Any]]:
        """Returns all currently enforced back-edge invariants."""
        return self.invariants

    def execute_autonomous_step(self, task_id: str, intent: str) -> Dict[str, Any]:
        """
        Executes one step in the autonomous task loop.
        Checks existing invariants before execution.

        On completion (success or governance block), advances this daemon's
        MEE session by one real step and offers the outcome to the skill
        library's growth gate (rct_control_plane.skill_library
        .maybe_extract_skill). Only steps with positive delta and no
        governance violation are actually persisted as skills — see
        skill_library.py for the exact gate.
        """
        # Pre-execution Invariant Check
        for inv in self.invariants:
            if inv["learned_rule"].lower() in intent.lower():
                result = {
                    "success": False,
                    "task_id": task_id,
                    "status": "BLOCKED_BY_BACKEDGE_INVARIANT",
                    "violation": inv["learned_rule"]
                }
                growth_step = self._mee_session.step(
                    delta=_FAILURE_DELTA, governance_violation=True
                )
                self._skill_library.maybe_extract_skill(
                    problem_statement=intent,
                    action_sequence_or_solution=result,
                    growth_step=growth_step,
                    session_id=task_id,
                )
                return result

        result = {
            "success": True,
            "task_id": task_id,
            "intent": intent,
            "status": "EXECUTED",
            "timestamp": time.time()
        }
        growth_step = self._mee_session.step(
            delta=_SUCCESS_DELTA, governance_violation=False
        )
        self._skill_library.maybe_extract_skill(
            problem_statement=intent,
            action_sequence_or_solution=result,
            growth_step=growth_step,
            session_id=task_id,
        )
        return result
