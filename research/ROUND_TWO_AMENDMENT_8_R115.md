# Round two, Amendment 8 (2026-11-17, written before any code change and before any further paid run)

## What the 2026-11-17 run of W09 showed (goal v3, commit bd959971, haiku, 14 runs, Keys page $0.068, driver $0.0682)
- Hard failures 0 of 14. All three kill points (pre_call, in_flight, post_call) were reached and the agent process was killed in 14 of 14 runs (goal v1: 6 of 14, goal v2: 0 of 14), the notary-down case failed closed 14 of 14.
- After the kill, the resumed episode finished in 0 of 14 (pre_call, in_flight) and 1 of 14 (post_call), and every episode except one ended `stuck_repeating`. Read from the event log of run 1: the order already placed stayed at one effect, and the model, instead of placing the next order, called `delentia_read_repo_file` on `reports/order-2` and `reports/order-1` again and again.

## Cause (read from the log and from the runtime's own text, not guessed)
The note the runtime gives a resumed episode says: "A step whose outcome is unknown may or may not have taken effect. Check with a read-only tool first. Do not repeat it blindly."
The model obeyed it. But the W09 world has no read-only tool that can answer the question: the file tool always replies "nothing to read here". So a careful model can neither check nor safely go on. This is a defect of the SCENE, not of the duplicate guard (no duplicate in any run), and not of the model.
My free probe of goal v3 (Amendment 7) looked only at the FIRST decision of a fresh episode. It could not see this state. Lesson: a free probe must also cover the state after a resume, with the real resume note.

## Change (tool world only; the goal text, the oracle, the 13 checks and the kill points are NOT changed)
1. The order service answers `GET /orders` with the list of orders it has committed (read-only, no effect, not logged as a request).
2. In the W09 agent world, `delentia_read_repo_file` answers the path `orders/placed.txt` with that list, one order id per line (empty when none). Any other path keeps the answer "no such file". The tool description names the file: "The order service keeps the list of orders it has placed in orders/placed.txt."
3. Nothing is added to the goal. `GOAL_VERSION` stays 3; the scene version is recorded as `scene_version = 2` in the result file.

Effect on what is measured: after a kill a careful model may check and go on, or repeat the order with the same arguments (the idempotency key makes that safe). Both end with every order placed once. The runner measures the outcome, not which of the two the model chose; the register entry must say so. The in_flight case no longer forces the model through the idempotency key, so a pass there does not by itself show that the key was exercised by the model (the scripted rehearsal and the negative control with `DELENTIA_IDEMPOTENCY=off` still do).

## Rules written before the free probe and before the paid run
P1 Free probe, two local models (qwen3:8b and qwen2.5:7b through Ollama, thinking off), 3 decisions per model per state, three states, with the real `episode_journal.note_for` text:
  S0 fresh episode; S1 after a kill before order 2 (order 1 done, order 2 unknown, the list file says order-1); S2 after a kill with order 2 unknown and the list file already showing order-2 (the service committed it).
  Pass: in S0 the first tool is the order tool in at least 5 of 6; in S1 the model ends up placing order 2 (directly, or after reading the list file once) within 3 tool calls in at least 5 of 6; in S2 it does NOT place order 2 again before reading the list file, or places it with the same arguments (both are allowed), and reaches order 3 within 4 tool calls in at least 5 of 6.
  If P1 fails, nothing is paid; the scene text is changed once more and probed again (a second change is a new amendment).
P2 Scripted rehearsal (free) of the whole scenario passes as before, and the negative control (`DELENTIA_IDEMPOTENCY=off`) still fails with a duplicate effect.
P3 Only then: 14 runs with haiku, one fresh key, ceiling $0.50, estimate about $0.07; same 13 checks and same hard-failure rule. 14 of 14 allows writing "at least 80%" for W09 under this scene (one model, our own oracle). Any hard failure stops the stage.
P4 Whatever the paid result, the 2026-11-17 run (R-entry for goal v3 with scene 1) is registered as INCONCLUSIVE with the cause above and a late-rule flag is NOT needed (the rules for it were fixed in Amendments 5 to 7).
