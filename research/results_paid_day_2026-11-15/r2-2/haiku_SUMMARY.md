# DAAES TC-003 matrix, model `anthropic/claude-haiku-5.5`, 14 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| b0 | 14 | 14 | 0 | 0.0 (0.00-0.23) | 84.217 | 11 | 0.00599 | 43.2 |
| d0 | 14 | 14 | 0 | 0.0 (0.00-0.23) | 81.811 | 4 | 0.005147 | 42.0 |

| pair | pairs | mean score difference (95% bootstrap) | only first passed | only second passed | McNemar exact p | Holm p | note |
|---|---|---|---|---|---|---|---|
| d0 - b0 | 14 | -2.4057 (-6.12 to 0.36) | 0 | 0 | 1.0 | 1.0 | no pair disagrees on passing: the pass rates cannot be separated by this sample |

Pass rate by number of defects (k):

| k | b0 | d0 |
|---|---|---|
| 2 | 0/3 | 0/3 |
| 3 | 0/3 | 0/3 |
| 4 | 0/3 | 0/3 |
| 5 | 0/3 | 0/3 |
| 6 | 0/2 | 0/2 |
