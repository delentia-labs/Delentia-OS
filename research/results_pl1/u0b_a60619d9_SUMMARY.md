# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 42 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| d0 | 42 | 41 | 6 | 0.1463 (0.06-0.29) | 69.209 | 2 | 0.007484 | 58.0 |

Invalid runs (harness failures, listed and excluded):
- d0@5017: KeyError: 'reasoning'

Pass rate by number of defects (k):

| k | d0 |
|---|---|
| 2 | 5/29 |
| 3 | 1/12 |
