"""
The live D0 adapter (DAAES_ADAPTER_PLAN.md, step 1-2): Delentia's governed loop with a REAL model call path and the experiment budget guard standing in front of it.

    guard (experiment ledger: total, reserve, per run: cost, calls, tokens, unknown price = refuse)
      -> the provider Delentia resolved itself (OpenRouter / Ollama / openai-compat, key pool, fallback chain, sovereignty policy, per-episode meter)

What it is for. The pre-API checklist says the first paid call must go through a guard that has been seen to stop spending, and that the stop must survive a crash. This module makes that true
without spending: it is run against a fake OpenRouter on loopback (scripts/fake_openrouter.py) whose answers cost "money" in a ledger, and the tests prove that

  * every model call of an episode passes the guard BEFORE it is made (a refused call never reaches the endpoint: the endpoint's own counter shows it);
  * an episode that would pass its per-run limit stops with `stopped_reason == "model_error"`-class output, not by luck of the script, and the ledger shows what was spent;
  * the experiment total survives a new process (the ledger is a file) and a run that died with a call in flight keeps its reservation;
  * an unknown price is refused (fail closed) and a paid fallback is never taken on its own.

What it is not: a measurement of any real model. With a real key the same function is the live pilot's entry point; nothing in it knows whether the endpoint is real.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from research.daaes.budget_guard import BudgetPolicy, ExperimentLedger, GuardedProvider
from research.daaes.delentia_session import NullKernel, data_home


def guarded(inner: Any, ledger_path: Path, policy: BudgetPolicy, run_id: str, price_in_per_mtok: Optional[float], price_out_per_mtok: Optional[float]) -> GuardedProvider:
    ledger = ExperimentLedger(Path(ledger_path), policy)
    return GuardedProvider(inner, ledger.start_run(run_id), price_in_per_mtok, price_out_per_mtok)


def run_live_episode(goal: str, home: Path, provider: Any, *, namespace: str = "daaes-live", max_iterations: int = 6, mcp_server: Any = None, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """One governed episode whose model calls go through `provider` (normally a GuardedProvider). Returns the loop's result plus what the guard saw."""
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    with data_home(Path(home), extra_env=extra_env):
        persistence = ControlPlanePersistence(db_path=str(Path(home) / "agentic.db"))
        loop = build_governed_loop(NullKernel(), namespace=namespace, max_iterations=max_iterations, persistence=persistence, mcp_server=mcp_server, conversation_turns=0, llm_provider=provider)
        result = asyncio.run(loop.run(goal))
    result["guard_refused"] = getattr(provider, "refused", None)
    return result


def openrouter_provider(model: str, base_url: Optional[str] = None, api_key: Optional[str] = None) -> Any:
    """Delentia's own OpenRouter provider. A base_url is accepted only on loopback or openrouter.ai (llm_provider.openrouter_base_url); the key is read from the environment or given by the caller and never written anywhere."""
    from rct_control_plane.llm_provider import OpenRouterProvider
    if base_url:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = base_url
    return OpenRouterProvider(api_key=api_key, model=model)
