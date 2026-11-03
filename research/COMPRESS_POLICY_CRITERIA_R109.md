# Goal-aware COMPRESS: the rules, written before the code and the run (Round 109)

Why. `research/DELTA_TOKEN_SAVINGS_RESULTS_R109.md` found that COMPRESS filters hardest exactly when the goal says least: for a generic goal ("summarise this") it shows 1-50% of the lines and the line the
person needs is usually not among them; for a code file read to be edited it strips the indentation; its focus includes words such as "document" and "points" that match random lines. The owner
asked for the change that fits the kind of work and really reduces tokens, tested before it is recorded.

## The change (decided before measuring)
A pure function `compress_policy.decide(goal, tool_name, tool_args, text)` is asked before COMPRESS filters anything:
1. a **whole-text goal** (summarise, review, compare, explain, translate, rewrite, "list all", Thai equivalents) -> do not filter (the model is shown the text);
2. an **edit goal** (fix, edit, modify, refactor, rename, implement, replace, change, update, Thai equivalents) -> do not filter (exact text is needed);
3. **no content word** left in the goal after removing generic words and path-like tokens -> do not filter (there is nothing to filter by);
4. **none of the content words occurs in the text** -> do not filter (the filter would show only the code-like lines);
5. otherwise filter, with the focus made of the content words only (the generic words no longer match random lines).
Any error in the policy -> do not filter. `DELENTIA_COMPRESS_POLICY=off` restores the old behaviour exactly (needed for the before/after and as a way back).

## Rules (same corpus, same seeds, same script as the Delta measurement; the old numbers come from the old behaviour of the same script)
| # | Rule | Pass when |
|---|---|---|
| R1 | whole-text and no-signal goals (generic, unrelated) lose nothing | needle kept 100% on every item for both goal kinds |
| R2 | lookup goals keep what they had | needle kept for literal 100%, for partial and single at least as high as before; median saving not lower than before minus 5 points; for `single` not lower than before |
| R3 | edit goals are not filtered | a new goal kind "edit" shows needle kept 100% and lines shown 100% |
| R4 | a lookup keeps most of the whole-episode saving | for the large items, the 4-calls-after saving with the full menu stays at least 40% for a lookup goal |
| R5 | what held keeps holding | never worse (0 violations), exact recovery (0 mismatches), time under 1 s |
| R6 | cost of the policy | `decide` on 230 KB of text under 20 ms |
| R7 | fail-safe | a policy that raises leaves the result unfiltered, never crashes the episode |

## What I expect, and what I will say whatever happens
* R1, R3 hold by construction. R2 is the real test: the content-words-only focus should keep the needle (the needle's words are in the goal) and cut more lines for `single`.
* The saving on generic goals falls from 54-98% to 0% by design: that was information removed, not tokens saved. The owner is told the average over a workload depends on how many of the requests are
  lookups, which I do not know; the table will show 0%, 50% and 100% of whole-text requests.
* Nothing here says a model answers as well from the filtered view: that needs a model and a task set.
