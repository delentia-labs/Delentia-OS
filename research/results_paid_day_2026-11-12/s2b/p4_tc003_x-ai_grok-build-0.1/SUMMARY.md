# DAAES TC-003 matrix, model `x-ai/grok-build-0.1`, 4 tasks

One model on one task family (thousands of variants of a broken `ledgercalc`, one oracle). Evidence about these systems with THIS model on THESE tasks only; per model, never pooled.

| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |
|---|---|---|---|---|---|---|---|---|
| b0 | 4 | 4 | 0 | 0.0 (0.00-0.60) | 69.108 | 0 | 0.051961 | 159.1 |
| d0 | 4 | 4 | 0 | 0.0 (0.00-0.60) | 69.108 | 0 | 0.052039 | 160.2 |

| pair | pairs | mean score difference (95% bootstrap) | only first passed | only second passed | McNemar exact p | Holm p | note |
|---|---|---|---|---|---|---|---|
| d0 - b0 | 4 | 0.0 (0.00 to 0.00) | 0 | 0 | 1.0 | 1.0 | too few pairs to say anything |

Pass rate by number of defects (k):

| k | b0 | d0 |
|---|---|---|
| 2 | 0/1 | 0/1 |
| 3 | 0/1 | 0/1 |
| 4 | 0/1 | 0/1 |
| 5 | 0/1 | 0/1 |
