# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 42 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| d0 | 42 | 42 | 2 | 0.0476 (0.01-0.16) | 69.865 | 2 | 0.006483 | 52.4 |

Pass rate by number of defects (k):

| k | d0 |
|---|---|
| 2 | 2/30 |
| 3 | 0/12 |
