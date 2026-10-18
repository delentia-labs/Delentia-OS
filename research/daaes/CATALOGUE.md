# DAAES: the thirty cases and where each stands

Generated from `research/daaes/catalogue.py`; a test checks that every evidence file exists. Hermes (H0, pinned v0.22.2, in a container): only TC-003 is run for it; every other row is `not_evaluated` for Hermes.

| id | case | L | P | status | evidence | what is still needed |
|---|---|---|---|---|---|---|
| TC-001 | Basic Tool Selection | L1 | P0 | existing_battery | `scripts/k1_5_formal_acceptance.py` | a capable model (local 7B: 3 of 5 simple goals) |
| TC-002 | Multi-Step File Processing | L2 | P0 | partly | `research/generate_ops.py`, `rct_control_plane/tests/test_research_ops_domain_round82_real.py` | 12 shapes of office work are graded with a scripted model; a real model has not run them |
| TC-003 | Bug Fix + Regression | L3 | P0 | scripted_proven | `research/daaes/tc003.py`, `rct_control_plane/tests/test_daaes_tc003_round83_real.py` | a capable model to find the fixes (live pilot C4) |
| TC-004 | Tool Timeout Recovery | L3 | P0 | scripted_proven | `research/daaes/tc003.py` | faults F1-F3 on the runner tool, recovery scored; a model's decision quality is the live part |
| TC-005 | Failed API Fallback | L3 | P0 | scripted_proven | `rct_control_plane/tests/test_provider_fallback_round57_real.py`, `research/daaes/tc005.py`, `rct_control_plane/tests/test_daaes_tc005_round84_real.py` | scripted (Round 84): the runtime's fallback provider and an idempotent order API in one scenario; a live model that checks before it retries is the live part |
| TC-006 | Goal Continuity Across Sessions | L5 | P0 | scripted_proven | `research/daaes/tc006.py`, `rct_control_plane/tests/test_daaes_tc006_round83_real.py` | whether a live model keeps the goal on its own (live pilot C3) |
| TC-007 | Conflicting User Instructions | L5 | P0 | partly | `research/daaes/tc006.py`, `research/daaes/tc007_tc020.py`, `rct_control_plane/tests/test_constraints_outside_retrieval_round82_real.py`, `rct_control_plane/tests/test_daaes_tc007_tc020_round84_real.py` | scripted (Round 84): a rule in the owner policy binds a second person, a rule pinned in one person's memory does not; a live model's handling of two people disagreeing is not measured |
| TC-008 | Memory Retrieval Accuracy | L5 | P0 | existing_battery | `research/recall_dataset_r70.py`, `rct_control_plane/tests/test_memory_recall_round69_real.py` | held-out recall sets exist (English, Thai); not in the DAAES evidence format |
| TC-009 | Memory Delta Reconstruction | L5 | P0 | scripted_proven | `research/daaes/tc009.py`, `rct_control_plane/tests/test_daaes_tc009_round83_real.py` | the Delta Engine's versioned log passes the whole matrix since Round 83; the way the engine was used until Round 82 fails it (pinned as an arm) |
| TC-010 | Interrupted Task Recovery | L5 | P0 | scripted_proven | `research/daaes/tc010.py`, `rct_control_plane/tests/test_daaes_tc010_round83_real.py` | an agent loop that resumes a whole episode (today only the approval of an action is recoverable) |
| TC-011 | Scheduled Research | L4 | P1 | partly | `rct_control_plane/tests/test_cron_jobs_round57_real.py` | the scheduler is tested; a research task on a schedule needs a model and time |
| TC-012 | Daily Monitoring | L4 | P1 | needs_host | `scripts/autonomy_drill.py` | a host that runs for days (the drill ran two minutes) |
| TC-013 | Inventory Agent | L4-5 | P1 | scripted_proven | `research/daaes/tc013.py`, `rct_control_plane/tests/test_daaes_tc013_round84_real.py` | scripted (Round 84): 100 SKUs, six review days, an oracle that recomputes who was at risk; whether a model reads 100 rows and judges reorder quantities is the live part |
| TC-014 | Business Data Reconciliation | L3 | P1 | partly | `research/generate_ops.py` | csv_totals / report_number / inventory_join families, scripted only |
| TC-015 | Long-Horizon Project Planning | L5 | P0 | needs_model | `rct_control_plane/tests/test_task_board_round60_real.py` | the task board exists; planning quality is a model's |
| TC-016 | Plan Revision Under Constraint | L5 | P0 | needs_model | `rct_control_plane/tests/test_task_board_round60_real.py` | replan exists; whether a model revises well is the live part |
| TC-017 | Learning From Repeated Mistakes | L5 | P0 | needs_model | `research/PROTOCOL.md` | arms M on/off are built in the research harness; they need a capable model |
| TC-018 | Skill Reuse Across Sessions | L5 | P1 | partly | `rct_control_plane/tests/test_warm_recall_round51_real.py` | reuse is tested with a scripted model; learning a skill from a live episode is not |
| TC-019 | Multi-Agent Delegation | L6 | P1 | scripted_proven | `scripts/full_pipeline_cases.py`, `rct_control_plane/tests/test_jitna_subagent_real.py` | decomposition quality is a model's |
| TC-020 | Multi-Agent Goal Conflict | L6 | P0 | partly | `rct_control_plane/tests/test_jitna_subagent_real.py`, `research/daaes/tc007_tc020.py`, `rct_control_plane/tests/test_daaes_tc007_tc020_round84_real.py` | scripted (Round 84): a planner's plan is data, the legitimate step runs and the destructive and outbound steps are stopped when the folder is declared untrusted; with a live planner agent and a live developer agent it is not measured |
| TC-021 | Permission Boundary | L3 | P0 | scripted_proven | `research/daaes/tc003.py`, `research/daaes/tc006.py` | - |
| TC-022 | Prompt Injection Resistance | L3 | P0 | scripted_proven | `scripts/measure_injection_defence.py`, `research/daaes/tc006.py` | an obedient scripted model only; a real model may behave differently |
| TC-023 | Duplicate Action Prevention | L4 | P0 | scripted_proven | `research/daaes/tc010.py`, `rct_control_plane/tests/test_crash_windows_round82_real.py` | - |
| TC-024 | Audit Trail Reconstruction | L5 | P0 | scripted_proven | `research/daaes/tc025.py`, `rct_control_plane/tests/test_daaes_tc025_round83_real.py` | truncation of the newest rows is caught only by an external anchor |
| TC-025 | Replay Determinism | L5 | P0 | scripted_proven | `research/daaes/tc025.py`, `rct_control_plane/tests/test_daaes_tc025_round83_real.py` | R4 (live re-execution) is variance, never byte identity |
| TC-026 | Context Compression Retention | L5 | P0 | partly | `research/daaes/tc006.py`, `scripts/measure_prompt_cost.py` | pins survive 300 irrelevant memories; Delta v2 on tool output is measured for size, not for what a model can still answer |
| TC-027 | Dynamic Web Workflow | L3 | P1 | scripted_proven | `rct_control_plane/tests/test_browser_act_round62_real.py`, `research/daaes/tc027.py`, `rct_control_plane/tests/test_daaes_tc027_round85_real.py` | scripted (Round 85): the real headless browser against a page whose price changes and which talks to the assistant; whether a model re-reads before answering is the live part |
| TC-028 | Autonomous Incident Recovery | L4-5 | P1 | scripted_proven | `research/daaes/tc028.py`, `rct_control_plane/tests/test_daaes_tc028_round85_real.py` | scripted (Round 85): three real service processes, two killed, a runbook with a restricted service; a live model following a runbook over days is the live part |
| TC-029 | Long-Running Cost Control | L5 | P1 | scripted_proven | `research/daaes/budget_guard.py`, `rct_control_plane/tests/test_daaes_budget_guard_round83_real.py`, `rct_control_plane/tests/test_budget_reservation_round82_real.py` | the guard has not stood in front of a real model |
| TC-030 | End-to-End Autonomous Project | L6 | P2 | needs_model | - | everything above, a capable model and a host |

Totals: scripted_proven 16, partly 7, existing_battery 2, needs_model 4, needs_host 1 (30 cases).

`scripted_proven` is about the RUNTIME around a scripted model: it says nothing about what a language model would do with the same task.
