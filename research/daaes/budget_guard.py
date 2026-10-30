"""
The experiment budget guard of DAAES (specification: "a Model Gateway with a hard budget guard"; zero-budget roadmap sections 7.4 and 9).

Delentia already meters ONE episode (`MeteredProvider`: it refuses a call whose worst case would exceed that episode's cap). An experiment is many runs; its money has to be guarded ACROSS them, at the
gateway, before the call is made, and survive a crash. This module is that layer:

  BudgetPolicy      the numbers (total, warning, stop-new-runs, reserve, per-run cost / calls / tokens, retries, steps) and two switches that must stay off: automatic paid fallback and
                    "continue when exceeded". Unknown prices FAIL CLOSED: a budget that cannot be checked is not a budget.
  ExperimentLedger  a JSON file written atomically and fsynced after every change: what was spent, what is reserved for calls in flight, which runs started, which warnings fired.
  RunBudget         one run's allowance. `before_call(prompt_tokens, max_output_tokens)` reserves the WORST case of the call and raises BudgetExceeded when it would break any limit, so the call
                    is never made; `after_call(usage)` replaces the reservation with what the provider reported.
  GuardedProvider   wraps any LLMProvider (the thing Delentia's loop and the Hermes adapter would both call) so every model call of every arm passes the same guard.

A reservation that was never settled (the process died between the call and its record) stays counted until the experiment is reviewed: the guard errs towards having spent too much.
Provider-side spending limits still matter (this guard cannot see a request that was already on its way when it stopped); `reserve_usd` is the margin for those.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane.llm_provider import LLMProvider, LLMUsage


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def good_price(x: Any) -> bool:
    """A price in USD per million tokens: a real, finite, non-negative number. NaN, a negative, infinity, a string or a bool is malformed (every comparison with NaN is False, so a NaN
    worst case would pass every limit; a negative price would make the reservation shrink)."""
    return _is_number(x) and math.isfinite(x) and x >= 0


def good_cost(x: Any) -> bool:
    return good_price(x)


def _good_int(x: Any, minimum: int) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= minimum


class BudgetExceeded(RuntimeError):
    """A call (or a new run) was refused before anything was sent."""


@dataclass
class BudgetPolicy:
    total_usd: float = 5.0
    warning_usd: float = 3.0
    stop_new_runs_usd: float = 4.0
    reserve_usd: float = 1.0
    max_cost_per_run_usd: float = 0.25
    max_llm_calls_per_run: int = 15
    max_input_tokens_per_run: int = 200_000
    max_output_tokens_per_run: int = 20_000
    max_retries_per_tool: int = 1
    max_agent_steps: int = 20
    automatic_fallback: bool = False                       # must stay False: a silent switch to another paid model changes the experiment and the bill
    on_budget_exceeded: str = "stop"

    def validate(self) -> "BudgetPolicy":
        for name in ("total_usd", "warning_usd", "stop_new_runs_usd", "reserve_usd", "max_cost_per_run_usd"):      # type and sign first: a string or NaN must not reach a comparison
            if not good_price(getattr(self, name)):
                raise ValueError(f"{name} must be a finite, non-negative number (got {getattr(self, name)!r})")
        if not self.total_usd > 0 or not self.max_cost_per_run_usd > 0:
            raise ValueError("total_usd and max_cost_per_run_usd must be greater than zero")
        for name in ("max_llm_calls_per_run", "max_input_tokens_per_run", "max_output_tokens_per_run", "max_agent_steps"):
            if not _good_int(getattr(self, name), 1):
                raise ValueError(f"{name} must be a whole number of at least 1 (got {getattr(self, name)!r})")
        if not _good_int(self.max_retries_per_tool, 0):
            raise ValueError(f"max_retries_per_tool must be a whole number, zero or more (got {self.max_retries_per_tool!r})")
        if self.automatic_fallback:
            raise ValueError("automatic paid fallback is not allowed in an experiment: a model change mid-run invalidates the comparison")
        if self.on_budget_exceeded != "stop":
            raise ValueError("on_budget_exceeded must be 'stop'")
        if not (0 <= self.reserve_usd < self.total_usd and self.warning_usd <= self.stop_new_runs_usd <= self.total_usd - self.reserve_usd):
            raise ValueError("limits must satisfy: warning <= stop_new_runs <= total - reserve")
        return self

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BudgetPolicy":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known).validate()

    def delentia_env(self) -> Dict[str, str]:
        """The per-episode caps of Delentia's own meter, so the same numbers bind inside the runtime too (defence in depth, not a substitute for this guard)."""
        return {"DELENTIA_EPISODE_BUDGET_USD": f"{self.max_cost_per_run_usd}", "DELENTIA_EPISODE_MAX_TOKENS": str(self.max_input_tokens_per_run + self.max_output_tokens_per_run)}


class ExperimentLedger:
    def __init__(self, path: Path, policy: BudgetPolicy) -> None:
        self.path, self.policy = Path(path), policy
        self.state: Dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"spent_usd": 0.0, "reserved_usd": 0.0, "runs": {}, "warnings": [], "refusals": []}

    _thread_lock = threading.RLock()

    @contextlib.contextmanager
    def locked(self):
        """One writer at a time across threads AND processes (a lock file next to the ledger), and the state is re-read from the file inside the lock: two gateways of two arms that share a
        ledger must each see what the other has already spent, or the experiment total is not enforced. Re-entrant in one thread. A lock file older than 60 s is taken to be a dead holder's."""
        with self._thread_lock:
            if getattr(self, "_depth", 0) > 0:
                self._depth += 1
                try:
                    yield self
                finally:
                    self._depth -= 1
                return
            lock = self.path.with_suffix(".lock")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.time() + 30
            while True:
                try:
                    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    break
                except FileExistsError:
                    try:
                        if time.time() - lock.stat().st_mtime > 60:
                            lock.unlink()
                            continue
                    except OSError:
                        pass
                    if time.time() > deadline:
                        raise TimeoutError(f"the ledger lock {lock} could not be taken in 30 s") from None
                    time.sleep(0.01)
            self._depth = 1
            try:
                if self.path.exists():
                    self.state = json.loads(self.path.read_text(encoding="utf-8"))
                yield self
            finally:
                self._depth = 0
                try:
                    lock.unlink()
                except OSError:
                    pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(json.dumps(self.state, indent=1, sort_keys=True).encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(40):                                  # on Windows a reader that has the file open for a moment makes the rename fail; try again
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.01)

    @property
    def committed(self) -> float:
        return float(self.state["spent_usd"]) + float(self.state["reserved_usd"])

    def refuse(self, why: str) -> None:
        self.state["refusals"].append({"at": time.time(), "why": why})
        self.save()
        raise BudgetExceeded(why)

    def start_run(self, run_id: str) -> "RunBudget":
        with self.locked():
            return self._start_run(run_id)

    def _start_run(self, run_id: str) -> "RunBudget":
        if run_id in self.state["runs"]:
            self.refuse(f"run {run_id} was already started (a run is never restarted under the same id)")
        if self.committed >= self.policy.stop_new_runs_usd:
            self.refuse(f"no new runs: ${self.committed:.4f} spent or reserved reached the stop-new-runs line (${self.policy.stop_new_runs_usd})")
        if self.committed + self.policy.max_cost_per_run_usd > self.policy.total_usd - self.policy.reserve_usd:
            self.refuse(f"no new runs: another run could cost ${self.policy.max_cost_per_run_usd} and would cut into the ${self.policy.reserve_usd} reserve")
        self.state["runs"][run_id] = {"cost_usd": 0.0, "reserved_usd": 0.0, "calls": 0, "inflight": 0, "uncertain_calls": 0, "input_tokens": 0, "output_tokens": 0, "status": "running"}
        self.save()
        return RunBudget(self, run_id)


class RunBudget:
    def __init__(self, ledger: ExperimentLedger, run_id: str) -> None:
        self.ledger, self.run_id = ledger, run_id

    @property
    def run(self) -> Dict[str, Any]:
        return self.ledger.state["runs"][self.run_id]

    def before_call(self, prompt_tokens: int, max_output_tokens: int, price_in_per_mtok: Optional[float], price_out_per_mtok: Optional[float]) -> float:
        with self.ledger.locked():
            return self._before_call(prompt_tokens, max_output_tokens, price_in_per_mtok, price_out_per_mtok)

    def _before_call(self, prompt_tokens: int, max_output_tokens: int, price_in_per_mtok: Optional[float], price_out_per_mtok: Optional[float]) -> float:
        p, run, led = self.ledger.policy, self.run, self.ledger
        if price_in_per_mtok is None or price_out_per_mtok is None:
            led.refuse("the price of this model is unknown, so the call cannot be checked against the budget (fail closed)")
        if not good_price(price_in_per_mtok) or not good_price(price_out_per_mtok):
            led.refuse(f"the price of this model is malformed (in {price_in_per_mtok!r}, out {price_out_per_mtok!r}): it must be a finite, non-negative number, so the call cannot be checked (fail closed)")
        if not _good_int(prompt_tokens, 0) or not _good_int(max_output_tokens, 1):
            led.refuse(f"the size of this call is malformed (prompt {prompt_tokens!r}, output limit {max_output_tokens!r}): the worst case cannot be computed (fail closed)")
        price_in, price_out = float(price_in_per_mtok or 0.0), float(price_out_per_mtok or 0.0)      # checked above (refuse raised otherwise): finite and not negative
        worst = (prompt_tokens * price_in + max_output_tokens * price_out) / 1_000_000
        run.setdefault("inflight", 0)
        run.setdefault("uncertain_calls", 0)
        started = run["calls"] + run["inflight"]                       # calls STARTED, not only finished: four callers at once must not all pass a limit of two
        if started + 1 > p.max_llm_calls_per_run:
            led.refuse(f"run {self.run_id}: call {started + 1} exceeds the limit of {p.max_llm_calls_per_run} model calls")
        if run["input_tokens"] + prompt_tokens > p.max_input_tokens_per_run or run["output_tokens"] + max_output_tokens > p.max_output_tokens_per_run:
            led.refuse(f"run {self.run_id}: this call could exceed the run's token limits")
        if run["cost_usd"] + run["reserved_usd"] + worst > p.max_cost_per_run_usd:
            led.refuse(f"run {self.run_id}: ${run['cost_usd']:.4f} spent + up to ${worst:.4f} for this call exceeds ${p.max_cost_per_run_usd} per run")
        if led.committed + worst > p.total_usd - p.reserve_usd:
            led.refuse(f"experiment: ${led.committed:.4f} committed + up to ${worst:.4f} would cut into the ${p.reserve_usd} reserve")
        run["reserved_usd"] += worst
        run["inflight"] += 1
        led.state["reserved_usd"] += worst
        led.save()
        return worst

    def after_call(self, reserved: float, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
        with self.ledger.locked():
            self._after_call(reserved, prompt_tokens, completion_tokens, cost_usd)

    def _after_call(self, reserved: float, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
        run, led = self.run, self.ledger
        if not good_cost(cost_usd):                                    # NaN, negative or infinite: it would poison or shrink the total, so the worst case that was reserved is what was spent
            cost_usd = reserved
            run["cost_replaced_by_worst_case"] = int(run.get("cost_replaced_by_worst_case", 0)) + 1
        prompt_tokens = prompt_tokens if _good_int(prompt_tokens, 0) else 0
        completion_tokens = completion_tokens if _good_int(completion_tokens, 0) else 0
        run["reserved_usd"] = max(0.0, run["reserved_usd"] - reserved)
        led.state["reserved_usd"] = max(0.0, led.state["reserved_usd"] - reserved)
        run["inflight"] = max(0, int(run.get("inflight", 0)) - 1)
        run["cost_usd"] += cost_usd
        run["calls"] += 1
        run["input_tokens"] += prompt_tokens
        run["output_tokens"] += completion_tokens
        led.state["spent_usd"] += cost_usd
        if led.committed >= led.policy.warning_usd and not any(w["line"] == "warning" for w in led.state["warnings"]):
            led.state["warnings"].append({"line": "warning", "at": time.time(), "committed_usd": round(led.committed, 6)})
        led.save()

    def uncertain(self, reserved: float, prompt_tokens: int) -> None:
        """The call raised after the request may have reached the provider (a dropped connection, a timeout, a cancelled task). It is counted as a call and its input tokens as used, and its
        reservation STAYS: the guard errs towards having spent it. A failing paid endpoint therefore reaches the call limit instead of being retried for free."""
        with self.ledger.locked():
            run = self.run
            run["inflight"] = max(0, int(run.get("inflight", 0)) - 1)
            run["calls"] += 1
            run["uncertain_calls"] = int(run.get("uncertain_calls", 0)) + 1
            run["input_tokens"] += prompt_tokens if _good_int(prompt_tokens, 0) else 0
            self.ledger.save()

    def finish(self, status: str = "finished") -> None:
        with self.ledger.locked():
            self.run["status"] = status
            self.ledger.save()


class GuardedProvider(LLMProvider):
    """Wraps a provider so every call passes the budget guard BEFORE it is made. Prices are USD per million tokens."""

    def __init__(self, inner: LLMProvider, budget: RunBudget, price_in_per_mtok: Optional[float], price_out_per_mtok: Optional[float]) -> None:
        self._inner, self._budget, self._pin, self._pout = inner, budget, price_in_per_mtok, price_out_per_mtok
        self.refused: Optional[str] = None

    @property
    def model(self) -> str:
        return str(getattr(self._inner, "model", "?"))

    async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
        from rct_control_plane.llm_provider import _count_tokens
        full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        tokens_in = _count_tokens(full)
        try:
            reserved = self._budget.before_call(tokens_in, max_tokens, self._pin, self._pout)
        except BudgetExceeded as exc:
            self.refused = str(exc)
            raise
        try:
            out = await self._inner.complete(prompt, system_prompt, temperature, max_tokens, json_mode)
        except BaseException:
            # the request may have reached the provider: the reservation STAYS counted and the call counts (the guard errs towards having spent it)
            self._budget.uncertain(reserved, tokens_in)
            raise
        usage: Optional[LLMUsage] = self._inner.last_usage
        used_in = usage.prompt_tokens if usage and usage.prompt_tokens else tokens_in
        used_out = usage.completion_tokens if usage and usage.completion_tokens else _count_tokens(out)
        cost = usage.cost_usd if usage and usage.cost_usd is not None else (used_in * (self._pin or 0.0) + used_out * (self._pout or 0.0)) / 1_000_000      # a malformed value is replaced in after_call
        self._budget.after_call(reserved, used_in, used_out, cost)
        self.last_usage = LLMUsage(used_in, used_out, cost)
        return out


def summary(ledger: ExperimentLedger) -> List[Dict[str, Any]]:
    return [{"run": rid, **asdict_safe(r)} for rid, r in sorted(ledger.state["runs"].items())]


def asdict_safe(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}

