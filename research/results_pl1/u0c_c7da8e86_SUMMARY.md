# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 42 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| d0 | 42 | 42 | 21 | 0.5 (0.34-0.66) | 84.897 | 2 | 0.011191 | 82.2 |

Pass rate by number of defects (k):

| k | d0 |
|---|---|
| 2 | 17/30 |
| 3 | 4/12 |
