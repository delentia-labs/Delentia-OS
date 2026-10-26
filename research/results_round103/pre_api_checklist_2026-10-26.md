# Pre-API Spending Checklist

1. **PASS** - TC-009: state reconstruction equals the reference at every check point, and every fault is detected or refused
   the Delta Engine's versioned log: 25/25 versions exact, 7/7 faults detected or refused, 0 hard failure(s). The way the engine was used until Round 82 (no verification) is kept as an arm for comparison: 2 hard failure(s). The memory event log: 4/7 faults; it carries memory records only
2. **PASS** - TC-025: replay calls no external API and log tampering is detected
   R2 external attempts 0; every listed tamper is caught by the chains except truncation of the newest rows, which only an external anchor catches (3 logs)
3. **PASS** - TC-010: a killed process resumes without a duplicate side effect
   4/4 kill points passed with a real process termination and a separate mock API; the naive control duplicated in 2 windows, so the check can fail
4. **PASS** - TC-006 (scripted): the user's intent survives a session reset and memory pressure
   the default shows 8 pinned rules since Round 87 (the Architect's decision): restored in every session. The control with the old cap of 5 (DELENTIA_MAX_PINNED_SHOWN=5) still drops the goal rule when a sixth is added (restoration 50), so the check can fail. Protected constraints held in every Delentia arm because the owner policy enforces them; the pins only inform
5. **PASS** - the harness has external oracles and a separate workspace per run
   hidden tests and the answer key are outside the agent's workspace (tested); the oracle runs the agent's package in a clean folder in another process; every run has its own work folder; all 59 bundles verify
6. **PASS** - the model gateway has token and cost logging and a hard budget guard
   research/daaes/budget_guard.py enforces per-run and experiment limits before each call, fails closed on an unknown price and refuses automatic paid fallback; research/daaes/live_adapter.py puts it in front of Delentia's own provider code (build_governed_loop(llm_provider=...)). Tested against a fake OpenRouter that charges in its own counter: a refused call never reaches the endpoint, the ledger agrees with what the endpoint charged, the total survives a new reader of the file, a call that died in flight keeps its reservation. It has never stood in front of a REAL model, and it cannot see a request already on its way: a prepaid provider-side limit is still required
7. **PASS** - fixtures and run manifests are reproducible
   the same seed gives the same fixture hash; every bundle carries its fixture hash, the commit, the command line and a seal that re-verifies

7 PASS, 0 PARTIAL, 0 FAIL of 7. Ready for a paid call: **True**.
