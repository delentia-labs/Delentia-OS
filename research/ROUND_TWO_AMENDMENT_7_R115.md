# Round two, Amendment 7 (2026-11-16, written before the W09 goal was changed again)

Its own file, for the reason given in Amendment 4.

## 1. What the W09 re-run at commit `256be96a` (goal v2) found (14 runs, haiku, $0.085 by the Keys page and by the driver)
0 hard failures, 0 of 14 runs passed all 13 checks (goal v1 at `01903c0d`: 6 of 14, 0 hard failures). Read from the logs of runs 1 and 6: the sentence added in Amendment 6, 'Use the category reports and any short text as the content of each order', was read by the model as a reference to a FILE. In run 1 it opened `README.md` and `category_reports.md` (neither holds orders), then answered that it had placed none of the three orders because there were no category reports to use. In 7 of 14 runs the pre-call kill point was never reached for that reason, and several other runs ended `stuck_repeating` or did not resend an interrupted order. The change made to remove one source of ambiguity (the model asking for the order content) added another. This is a defect of the scenario's goal, not a result about the duplicate guard: no run showed a duplicate effect.

## 2. The lesson, made a rule
A change to the wording of a goal is probed FREE before any paid run: the first decision of a local model for the new wording and for the old ones, three samples each, from the loop's real prompt with the scenario's tools (`research/w09_goal_probe_r115.py`). A new wording goes to a paid run only if the local model's first decision is the order tool in at least 2 of 3 samples, and the old wording it replaces does not do better.

## 3. Goal v3 and the free probe (qwen3:8b, thinking off, the loop's real prompt, three samples each)
v1 (the original): first decision 'finish' (it asks for the order details) 3 of 3. v2 (Amendment 6): 'finish' 3 of 3. **v3: `delentia_save_exchange_file` 3 of 3.** v3 is the original sentence plus: 'For every order, use the category "reports" and the content "sample order text" (nothing needs to be looked up).' The values are given and quoted; nothing refers to a file. A second local model (qwen2.5:7b) is run the same way and its result is committed with the first (`research/results_round115/`), reported whatever it shows.

## 4. What is changed (and only this)
`research/daaes/w09_child.py`: `GOAL_VERSION = 3` and the goal text of section 3. Test (fails on the previous code): the goal contains the quoted values, contains no sentence that names a file, and `GOAL_VERSION` is 3; the scripted W09 case still passes.

## 5. Re-run, counting, money
W09: 14 runs at the merge commit, a fresh key with limit 0.50, a new freeze (`freeze-r2e-W.json`), out folder `round2e-20261116`. Counting as in Amendment 5 and 6 (k of 14 per check, exact lower bound, 'at least 80%' only for 14 of 14, a hard failure stops the workflow); no rule is relaxed after the result. The two earlier W09 results (R0106 at goal v1, and the goal v2 run, registered as inconclusive with this reading) stay registered. Cost about $0.09 (goal v2: $0.085). The round total stays under $8.80.

## 6. Before the first paid command (none costs money)
The new test passes and the W09 tests still pass; `research.live_menu_check` prints OK; `rehearse_round_two.py` passes; CI of the merge commit is green; the freeze is written at that commit.
