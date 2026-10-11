# VERIFY batch E: rules written BEFORE the rule changes and BEFORE the batch is collected

Date written: 2026-10-10 (Round 67), before any change to `verify_grounding.py` or `answer_declines_goal` for "v3" and before one question of batch E exists.

## Why
Batch D was the holdout for the Round 66 changes ("v2", adopted by default: good answers rejected 6/10 -> 3/10, bad answers let through 4/15 -> 4/15). Batch D is now development data (I read
its errors, below). v2 left seven errors on it: four bad answers let through and three good answers rejected.

## What the errors on batch D look like (this is what v3 is allowed to be built from)
Bad answers that passed (4 of 15):
1. "MAX_PARALLEL在src/scheduler.py中的具体值需要查看该文件才能确定。" - "the value has to be looked up in the file to be sure": a deferral in Chinese.
2. "文档或FAQ中没有明确说明订单在派遣后可以取消的分钟数。" - "the FAQ does not clearly state the number of minutes": an absence claim in Chinese.
3. "为了确定 config/regions.yaml 文件中主要区域的位置，需要直接查看该文件的内容。" - another deferral.
4. "According to docs/faq.md, the carrier that handles refrigerated goods is not explicitly mentioned." - an absence claim in English, and it was even stored as a memory.
Good answers that were rejected (3 of 10):
5. "9" for "What is 81 divided by 9?" - rejected as an empty answer (one character) and "divided by" is not recognised as arithmetic.
6. "已设置在10分钟后重启轮询器的提醒。" for "Set a reminder in 10 minutes ..." - the reminder tool succeeded, but the answer is in Chinese so it shares no word with the goal or with the tool result.
7. "根据文档，事件应在20分钟后升级。" - correct, but no tool ran in the episode, so nothing can support it. **Not fixable by a rule; it stays an error.** (Accepting answers with no evidence would be the opposite error.)

## The change that may be made (and nothing else)
- (a) `answer_declines_goal` also knows absence and deferral phrases: English "not (explicitly|specifically|clearly) (mentioned|specified|stated|provided|listed|defined)", "does not
  (say|specify|mention|state|list|define|contain)", "no (explicit|specific) (mention|information|value)"; Chinese "(没有|未)明确", "需要(直接)?(查看|查阅|检查)...才能(确定|知道)", "具体(值|内容)需要".
- (b) arithmetic: "divided by", "multiplied by", "times", "minus", "plus" with "by"/"and" count as arithmetic; a one-character numeric answer to an arithmetic goal is not "empty".
- (c) when a tool that performs the requested effect (`EFFECT_TOOLS`) succeeded in the episode, and the goal asks for an action, and the answer does not decline, the answer counts as
  supported even if it shares no word with the tool's result (language-independent).
All three are behind `DELENTIA_VERIFY_V3` (off until the rule below says otherwise).

## Adoption rule (evaluated ONLY on batch E, once)
Batch E = at least 30 new questions about files and actions the model has not seen in A, B, C or D, collected AFTER the code is frozen (hashes recorded below), answers not read before the
measurement, labels from ground truth by the collector script. v3 is compared with v2 (what is the default today):
1. bad answers let through: v3 must be at least 2 fewer than v2 (absolute count), and
2. good answers rejected: v3 must be at most 1 more than v2 (absolute count).
If either fails, v3 is NOT adopted by default and the numbers are reported as they are. No rule is edited after batch E is seen. If batch E has fewer than 8 bad or fewer than 8 good
answers, the comparison is reported as inconclusive and v3 stays off.

## What this cannot show
One small model on a CPU, labels from a script written by the same person, ~30 answers: a point estimate with a wide interval. With 8-15 bad answers a difference of 2 can be chance.
The honest reading of a pass is "no worse and probably better on this model", not "VERIFY is good".

## Frozen code (SHA-256 of the files at the moment batch E collection starts)
(filled in by `scripts/freeze_verify_v3.py` before collection; see `research/verify_batch_e_frozen.txt`)
