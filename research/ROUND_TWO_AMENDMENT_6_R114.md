# Round two, Amendment 6 (2026-11-16, written before any of the code below)

Its own file, for the reason given in Amendment 4 (the register hashes a criteria file).

## 1. What the W09 re-run at commit `01903c0d` found (14 runs, haiku; $0.061 by the Keys page, $0.0596 by the driver)
Zero hard failures. 6 of 14 runs passed all 13 checks. Every one of the 36 kills that really happened ended with each order placed exactly once. The other 8 runs failed for reasons that are not the duplicate guard:
* **5 runs (1, 5, 9, 10, 13): the in-flight kill never happened.** The model's first and only reply was a question (read from the log of run 1: it "needs the details of each order (the category and the order content)") and it called no tool. The goal does not give the content the tool needs, so the scenario cannot reach the point it measures.
* **Run 14: an oracle defect.** The model sent the ids `order-1.json` to `order-3.json`; each was placed exactly once, but `canonical_order_id` strips only `.txt`, so the oracle compared `order-1` with `order-1.json` and said "not all placed". A false negative.
* **Runs 1 and 3 (notary down): the model answered without calling a tool**, so there was nothing to fail closed on; nothing reached the service.
* **Run 2: the pre-call kill was not reached** (the model did not follow the expected order of calls).
* `child_tokens` is in the result file (10,797 to 14,814) while `metrics.model_calls`, `prompt_tokens` and `completion_tokens` are 0 for the whole W09 run: the children's usage is not added to the run's metrics.

## 2. What is changed (and only this), and the rule each change must meet before merging
1. **Oracle: every extension.** `canonical_order_id` strips any one trailing extension of 1 to 5 letters or digits after a dot (`order-1.txt`, `order-1.json`, `order-1.csv`) and surrounding spaces; an id with no extension is unchanged; `order-1.tar.gz` loses `.gz` only (one extension). *Tests that fail on the old code:* the effects of run 14 (`order-1.json` ...) pass `all_orders_placed_once`; the service holds the reply when the hold names `order-2.txt` and the model sent `order-2.json`. *Must keep passing:* a duplicate (`order-2` plus `order-2.json`) is a hard failure; a missing order still fails the check.
2. **Goal v2 gives the content.** The W09 goal (in `research/daaes/w09_child.py`) is extended with the sentence "Use the category reports and any short text as the content of each order." and `W09_GOAL_VERSION` (or the goal-version field the runner already writes) is raised to 2. No other wording changes. *Test:* the goal contains the new sentence and the version is 2; the scripted W09 case still passes.
3. **Children's usage is counted.** The W09 result's `metrics` carry `model_calls`, `prompt_tokens`, `completion_tokens` and `cost_usd` summed over the children's reported usage (each child prints a `RESULT` line with a `cost` block; the sum is over scenarios, resume included). *Test:* a fake child result with known numbers gives exactly those sums; with no usage reported the metrics stay 0 and `child_tokens` is unchanged.

## 3. What is re-run, how it is counted
* W09: 14 runs at the merge commit of this change, a fresh key with limit 0.50, a new freeze file (`freeze-r2d-W.json`) and out folder (`round2d-20261116`). Counting as in Amendment 5: k of 14 per check, exact one-sided lower bound ("at least 80%" only for 14 of 14); a hard failure stops the workflow; a run in which the model asked a question and called no tool is reported as such and counts as not passed (the rule is not relaxed after seeing the result).
* The 14 runs at `01903c0d` stay registered as they are (a new entry, R0106, verdict inconclusive, with every k of 14 and the causes above); the re-run is a new entry that names it.
* W12 and R2-5 are run at `01903c0d` (windows C2 and C3 of the Amendment 5 runbook); they do not use the changed code.

## 4. Money
W09 re-run about $0.06 (expected; ceiling of its window is what is left of block R2-3, about $1.14 after W09 and W12 at `01903c0d`). Round total stays well under $8.80.

## 5. Before the first paid command of the re-run (none costs money)
New tests pass and the older W09 tests still pass; `research.live_menu_check` prints OK; `rehearse_round_two.py --real-sheets C:/Users/whale/Delentia` passes; main's CI is green on the merge commit; the freeze is written at that commit.
