# Round two, Amendment 13 (2026-11-17, written before the script change and before any further call to nova-pro)

## What the first nova-pro window showed (B1, `research/tool_choice_r3_r115.py`, `amazon/nova-pro-v1`, commit 8c803b16, key limit 1.10)
The run stopped by its own ceiling after 90 of the 306 decisions (only the first 90 Thai decisions: 45 goals x 2 arms): provider usage $1.0621 (the Keys page figure is still to be read), 1,616 s.
- Cost per decision $0.0118; the script's estimate was $0.0021 per decision (2,000 prompt tokens x $0.80 + 150 completion tokens x $3.20 per million). The real cost was 5.6 times the estimate. The haiku run of 2026-11-16 had been 1.4 times its estimate.
- Replies the loop could not read: 41 of 90 (46%): today 22 of 45, r3 19 of 45. The pass rule of Thai Amendment 5 allows at most 10% per arm; the result is therefore inconclusive, not a pass or a fail.
- Of the 26 replies of the r3 arm that were readable, 16 chose a needed tool; of the 23 readable replies of the `today` arm, none did (paired: right with r3 only 16, with today only 0). This is a direction, not a result: the run did not reach the English set or the negatives.
- The script kept neither the raw replies nor the usage of a call, so the cause of the unreadable replies and of the cost cannot be read from the rows. This is a defect of the MEASURING TOOL, the same kind as the one fixed in the agent loop on 2026-11-15 (raw replies of a parse error kept).
- The budget check ran only every 10 decisions on the key's usage; 10 decisions cost about $0.12 here, so the run passed its ceiling ($0.99) by $0.07. The key's own credit limit (1.10) held.

## Change (the tool only; the goals, the scoring, the five rules and the arms are NOT changed)
1. Each row keeps, per model call of the decision: prompt tokens, completion tokens, the provider-reported cost (`usage.cost`), which upstream provider answered, and the raw reply text (at most 600 characters; kept for every unreadable or errored reply, and for every reply when `--keep-raw` is given).
2. The ceiling is also checked after EVERY decision against the sum of the provider-reported costs of the calls already made (a local meter), in addition to the key's usage every 10 decisions. A decision that would pass the ceiling is not started.
3. `--limit-per-set N` runs only the first N goals of each set (both arms), for a probe. With it the rule of Amendment 5 is NOT applied (the output says "probe"), the estimate is made for that many decisions, and the freeze/ceiling checks are unchanged.
4. A test fails if a row lacks the usage fields, if the local meter does not stop a run at the ceiling, or if the probe applies the pass rule.

## Rules for the probe (written now, before it runs)
P1 Free: the tests of change 4 pass, the scoring tests of the script still pass.
P2 Probe: `--model amazon/nova-pro-v1 --limit-per-set 1 --keep-raw --budget-usd 0.30` (6 decisions: the first Thai goal, the first English goal and the first negative, each in both arms), a fresh key with credit limit 0.30, estimate about $0.07, expected real cost about $0.07 to $0.10. Registered as a probe (n = 6), whatever the result.
P3 What is read from it, and what follows (decided now):
  a. Unreadable replies 0 or 1 of 6 AND real cost per decision at most $0.0030: the first window's 46% is not typical; a full R3 run with nova-pro is allowed (ceiling $1.10, as in Amendment 11).
  b. Unreadable replies 2 or more of 6: nova-pro does not follow the loop's reply format with this menu. That is a result about nova-pro (recorded with the raw replies), not about R3, and B1 to B3 move to another second model by a later amendment (candidate: `moonshotai/kimi-k2`, T1 90.0% on day one, cheaper), not by a change of the rules.
  c. Real cost per decision above $0.0030 (whatever the replies): the full R3 run (306 decisions) and W12 (14 runs with three children) with nova-pro are not run; the same follows as in (b).
P4 The first window (90 decisions) is registered as INCONCLUSIVE, n = 90, with the causes above, once main's CI is green and the Keys page figure is known; it is not repeated, not extended and not mixed into any later run.

## Not changed
The goals, the sets, the scoring function, the five rules, the freeze, the model setting (`require_parameters` unset, `data_collection=deny`).
