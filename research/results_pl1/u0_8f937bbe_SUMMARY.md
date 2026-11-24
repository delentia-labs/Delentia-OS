# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 42 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| d0 | 42 | 42 | 6 | 0.1429 (0.05-0.29) | 71.433 | 0 | 0.00781 | 64.8 |

Pass rate by number of defects (k):

| k | d0 |
|---|---|
| 2 | 3/30 |
| 3 | 3/12 |
