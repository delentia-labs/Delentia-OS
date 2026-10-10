# VERIFY batch D: rules written BEFORE the rule changes and BEFORE the batch is collected

Date written: 2026-10-10, before any change to `verify_grounding.py` or `answer_declines_goal` in Round 66 and before one question of batch D exists.

## Why
On the second holdout (batch C, 25 real answers of qwen2.5:7b) the grounding check let 4 of 14 bad answers through but rejected 7 of 11 good ones (the old rule rejected 8 of 11). A check
that rejects most good answers teaches the agent almost nothing. Reading batch C to see why is allowed and done; **batches A, B and C are therefore all development data from now on.**

## What the development data show (A+B+C; this is what the change is allowed to be built from)
1. Good short answers that carry a SPECIFIC VALUE from a tool result ("仓库主管是 Wanida", "08:00-17:00 ICT", "120 ... 30") share only one word with the result, so they were not "supported".
2. Good answers to arithmetic or counting questions with no tool ("102", "60") have nothing to be supported by and share no words with the goal.
3. Bad answers that decline or defer in Chinese ("未提供…", "并未列出…", "建议查阅相关文档") passed, because the decline patterns know English and Thai.

## The change that may be made (and nothing else)
- (a) `evidence_support`: one distinct value that a successful tool result contains and the GOAL does not (a name, a number, a time, a path) is enough to count as supported.
- (b) A bare short answer (at most 12 characters, digits and units only) to a goal that is an arithmetic or counting question, with no decline, counts as answering. It says nothing about correctness.
- (c) `answer_declines_goal` also knows the common Chinese ways of saying a thing is not provided / cannot be found / should be looked up elsewhere.

## Adoption rule for the change (evaluated ONLY on batch D, once)
Batch D = at least 30 new questions about files the model has not seen in A, B or C, collected AFTER the code is frozen, answers not read before the measurement.
Compared with the rules as they stood at the end of Round 65 ("current"):
1. the share of GOOD answers rejected must fall by at least 25 percentage points; and
2. the number of BAD answers let through must not rise by more than 1.
If either fails, the change is not adopted by default (it stays behind `DELENTIA_VERIFY_V2=on`) and the numbers are reported as they are. No rule is edited after batch D is seen.

## What this cannot show
One small model on a CPU, labels from ground truth by a script written by the same person, 30-ish questions: a point estimate with a wide interval, not a general statement about VERIFY.
