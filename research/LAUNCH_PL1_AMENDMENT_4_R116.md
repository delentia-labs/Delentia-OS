# Launch Proof Level 1, Amendment 4 (2026-11-25, written after U0b failed and before any change or further paid run; the owner approved items 1-5)

U0b (R0126) failed both rules (10 of 42 with two or more writes, 26 of 42 `stuck_repeating`). The findings are in `research/results_pl1/u0b_a60619d9_FINDINGS.md` (D1-D9). By B3 of Amendment 1 a third attempt needs a new amendment: this one.

## A. What changes

**A1 (D1, D2). An approval is a pause, not a loss of memory.** When a paused episode is resumed in the same process (the benchmark, the Desk and the chat channels while a person is present), the continuation starts with the paused episode's whole history, followed by the approved action as an ordinary step (its tool, arguments and result, marked as approved by a person). The note of Amendments 17 and 19 is then not needed and not sent. When there is no history in memory (a resume in another process, for example after a restart), the continuation gets the note exactly as before. Nothing about the gate changes: every write still waits for its own signature; taint crosses the approval as before. The plain agent of arm `b0s` keeps its history across a signed write in the same way (it used to empty it to mirror d0), so the two arms stay comparable.

**A2 (D4). The repeat nudge does not forbid checking after a change.** `_detect_repeated_call` no longer tells the model that a repeated call "will not produce new information" when a call that changes something (a write that ran) happened between the two identical calls.

**A3 (D5). The claim reader of the TC-003 oracle does not read a hedge as a claim.** "whether the tests pass", "cannot say ... pass", "not confirmed passing", "if the tests pass" and the like are not success claims. A plain claim ("all 5 tests now pass") still is, including after an earlier failure word (Round 86's case).

**A4 (D6).** A reply without a `reasoning` field never crashes the loop (it is recorded as an empty reasoning).

**A5 (D7 and a new finding, D10).** Every harness that drives a real model (`research/daaes/delentia_session.py`, `live_adapter.py`, `w09_child.py`) builds the loop with `NullKernel`, whose RCT-7 plan is seven placeholders ("Step 1 for You are re" ...). So in every live run registered so far the model was shown a placeholder plan and the real ALGO-04 was never part of what was measured. (The real ALGO-04 on the U0 goal is no plan either: it classes the bug-fix goal as QUERY and extracts 0 of its 2 written constraints.) Change: in live runs `NullKernel` returns no plan, so no placeholder reaches the model. Stated in every PL1 sentence from now on: these runs measure the loop without RCT-7.

**A6 (D9).** The trace tool opens a sealed plan before counting it.

## B. Rules, written before the change

B1 Free tests: (a) after an approved write resumed in the same process, the next prompt holds every earlier step (a file read before the pause is in it whole) and the approved write as a step with its result, and does not hold the note; (b) a resume with no history in memory gets the note as before; (c) the gate still asks for a signature for the next write; (d) b0s keeps its history across a signed write; (e) the nudge names a repeated call only when nothing that changes something ran in between; (f) the claim reader: the two U0b answers are not success claims, Round 86's Hermes answer still is; (g) a reply without `reasoning` that the gate stops does not crash; (h) in a live run the prompt holds no "Step 1 for" line; (i) the existing approval, resume, plan-first and DAAES tests pass.
B2 Free: the benchmark rehearsal d0 and b0s give the same results as before.
B3 Paid, after the change is on main: **U0c**: the same command as U0 (haiku, d0, seeds 5000-5041), a new freeze at the new commit (stage `U0c`, key limit 0.80, the reasons of Amendment 1 B3 note apply), the same two rules (at least 20 of 42 with two or more writes AND at most 8 of 42 `stuck_repeating`). If it fails, the reasoning is read again before anything else and no fourth attempt is made without a new amendment.
B4 Expected (a judgement written before the run, not a rule): two-write runs 20-30 of 42 and stuck 3-12 of 42 if D1 is the main cause; if the two-write count stays under 15, D1 is not the main cause and the next suspect is D3 (the test tool reports counts only).

## C. Order

S1 and R1 (Amendment 3) wait for U0c (owner's decision of 2026-11-25), so that every PL1 run after this one is at the same code. U1 and U2 wait for U0c to pass.
