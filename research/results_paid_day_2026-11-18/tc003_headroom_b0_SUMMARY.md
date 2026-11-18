# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 14 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| b0 | 14 | 14 | 9 | 0.6429 (0.35-0.87) | 87.868 | 0 | 0.008846 | 66.4 |

Pass rate by number of defects (k):

| k | b0 |
|---|---|
| 2 | 8/10 |
| 3 | 1/4 |
