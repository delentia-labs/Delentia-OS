# TC-003 headroom tier (2026-11-17): criteria written before any code and before any call

## What the existing data says (read, free)
Round two R2-2 (haiku, b0 and d0, 14 variant seeds 1700-1713, k = 2 to 6 defects, registered R0097 and R0098): the oracle passed 0 of 14 in both arms. Reading `results.jsonl` row by row: every run fixed the defects the VISIBLE tests show (public score 100 in most runs) and left at least one defect that only the hidden suite sees (hidden score 88 to 96 for k = 2 and 3); in most runs the final answer also claimed success, which the oracle counts as a hard failure (`false_success_claim`). Even at k = 2 the pass rate was 0 of 6 (b0) and 0 of 6 (d0).
So two things hold at once: the oracle asks for every defect, while the visible tests only show some, and the agent prompt says "investigate the failures, implement the minimum safe fixes, verify". A comparison between two arms needs tasks both can sometimes pass (headroom); at 0 of 14 it cannot show a difference in either direction.

## Tier V (visible): a graded task family where every defect is shown by the visible tests
`research/daaes/tc003_variants.py` gets a second way to choose defects: seeds `>= 5000` (`VISIBLE_TIER_BASE`) select, by `seed - 5000` modulo the number of combinations, one of the combinations of defects drawn only from the four whose visible tests reveal them (`M01`, `M02`, `M20`, `M09`), never two edits of one slot (M01 and M02 share a slot), with k = 2 or 3. Seeds below 5000 behave exactly as before (a test pins several seeds' defects).
Counted by hand from the slots: slot `lt_calc` holds M01 or M02, `lt_signature` holds M20, `vr` holds M09: k = 2 gives 5 distinct combinations, k = 3 gives 2, so 7 distinct tasks. This is few; it is a headroom screen, not a benchmark, and any report names the number of distinct tasks.

## Rules for the tier (each a free test, written now)
V1 For every combination: the reference package passes the whole hidden suite; the variant fails the hidden suite; the variant fails the VISIBLE suite; and each defect alone, applied to the reference, fails at least one visible test (so nothing in the tier is revealed only by reading).
V2 The same seed always gives the same defects; seeds 5000 to 5006 give the 7 distinct combinations; a seed below 5000 gives what it gave before this change.
V3 `describe(seed)` and the fixture name say the tier (`variant-v<seed>-k<k>`), so a result row can never be mistaken for a mixed-tier row.

## Headroom screen (paid, only after V1 to V3 pass and the code is on main; one fresh key, ceiling $0.40, estimate about $0.10)
`benchmark` with haiku, arm b0 only, the 7 tasks, 2 independent runs each (14 runs; a repeat of a task uses a different run seed, the task is the same). Written now, applied to the result:
H1 Headroom: the oracle pass count is between 3 and 11 of 14 (21% to 79%). Then a paired b0 against d0 comparison on this tier is allowed (a separate amendment states its rule and ceiling before it runs).
H2 Too hard: fewer than 3 passes of 14. Then tier V does not give headroom for this model; the report says so and no comparison is run.
H3 Too easy: more than 11 passes of 14. Same: no comparison on this tier.
H4 A run that ends for a reason other than the model's own work (a refused call, a harness error) is not counted in the 14 and is reported; more than 2 of 14 such runs makes the screen inconclusive.
The result is registered whatever it is; the model is one, the tasks are 7, the oracle is ours.

## Not changed
The oracle, the hidden suite, the visible tests, the agent prompt, the hard-failure rules (including `false_success_claim`) and the arms.
