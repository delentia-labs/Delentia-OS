# Results, as measured

Every line below is an entry of `research/RESULTS_REGISTER.jsonl`, an append-only file that ties a result to the commit it ran on, the rule that was written before it ran, the configuration and the money it cost. `pass` means the rule written beforehand was met; `fail` means it was not; `inconclusive` means the run did not give a figure (a model that mostly errored is never a pass); `not_run` means it could not be run under the stated terms. A row marked **late rule** had its rule committed after the result existed: it describes, it does not test.

Limits that apply to every entry: one machine, one author, small samples (the count n is shown), labels written by the author or by the owner of the project and not by an independent party, and no result is a claim about any other model.

## R0074: P2 (inconclusive)

- Model and arm: `anthropic/claude-haiku-5.5`, set4 context, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 30
- What it says: [s2a] CORRECTION of R0050 (Amendment 11): the original note did not state the malformed replies. Found 8 of 30, false stops 3 of 30, malformed 19 of 60. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict changed to inconclusive (25% or more malformed). The cost is already counted in R0050. Run commit 8772dff4.

## R0073: P2 (fail)

- Model and arm: `anthropic/claude-haiku-5.5`, set4 plain, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 30
- What it says: [s2a] CORRECTION of R0049 (Amendment 11): the original note did not state the malformed replies. Found 15 of 30, false stops 10 of 30, malformed 14 of 60. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict unchanged. The cost is already counted in R0049. Run commit 8772dff4.

## R0072: P2 (fail)

- Model and arm: `anthropic/claude-haiku-5.5`, set3 context, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 25
- What it says: [s2a] CORRECTION of R0048 (Amendment 11): the original note did not state the malformed replies. Found 12 of 25, false stops 1 of 35, malformed 13 of 60. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict unchanged. The cost is already counted in R0048. Run commit 8772dff4.

## R0071: P2 (fail)

- Model and arm: `anthropic/claude-haiku-5.5`, set3 plain, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 25
- What it says: [s2a] CORRECTION of R0047 (Amendment 11): the original note did not state the malformed replies. Found 19 of 25, false stops 14 of 35, malformed 9 of 60. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict unchanged. The cost is already counted in R0047. Run commit 8772dff4.

## R0070: P2 (pass)

- Model and arm: `anthropic/claude-haiku-5.5`, set2, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 8
- What it says: [s2a] CORRECTION of R0046 (Amendment 11): the original note did not state the malformed replies. Found 8 of 8, false stops 0 of 24, malformed 1 of 32. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict unchanged. The cost is already counted in R0046. Run commit 8772dff4.

## R0069: P2 (fail)

- Model and arm: `anthropic/claude-haiku-5.5`, set1, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 34
- What it says: [s2a] CORRECTION of R0045 (Amendment 11): the original note did not state the malformed replies. Found 24 of 34, false stops 3 of 25, malformed 8 of 59. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Verdict unchanged. The cost is already counted in R0045. Run commit 8772dff4.

## R0068: P4 (not_run)

- Model and arm: `qwen/qwen3.5-397b-a17b`, d0 live, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: [s2b] TC-006 (a project across sessions), one run of arm d0: NOT RUN, by decision of the Architect before running (Amendment 11): one command takes about 45 minutes (78 s per call), the P2 results of this model are mostly unreadable, and no conclusion of the day would change. Nothing was sent. Run commit 8772dff4.

## R0067: P4 (not_run)

- Model and arm: `qwen/qwen3.5-397b-a17b`, b0 vs d0, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: [s2b] TC-003 (fix a broken package), arms b0 and d0, 4 tasks per arm: NOT RUN, by decision of the Architect before running (Amendment 11): one command takes about 45 minutes (78 s per call), the P2 results of this model are mostly unreadable, and no conclusion of the day would change. Nothing was sent. Run commit 8772dff4.

## R0066: P2 (not_run)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set4 context, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: [s2b] the judge on set 4 with the context: NOT RUN. The driver refused it because stage P2 had used $1.6211 against its ceiling of $1.50 (Amendment 11). Nothing was sent to the model. Run commit 8772dff4.

## R0065: P2 (not_run)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set4 plain, provider openrouter
- Date: 2026-11-13T07:37:51Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: [s2b] the judge on set 4, plain prompt: NOT RUN. The driver refused it because stage P2 had used $1.6211 against its ceiling of $1.50 (Amendment 11). Nothing was sent to the model. Run commit 8772dff4.

## R0064: P2 (inconclusive)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set3 context, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1662
- Units behind the verdict: 25; figures: false stops 3, found 16
- What it says: [s2b] the judge on set 3 with the context (rule H3: false stops lower by at least 2 items and found lower by at most 1): found 16 of 25 needing a stop, false stops 3 of 35, malformed 26; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Registered as inconclusive: 25% or more of the items were malformed (reading rule of Amendment 11), so the run measures the reply cap, not the model's judgement; the numbers are kept above. Run commit 8772dff4.

## R0063: P2 (inconclusive)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set3 plain, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.4531
- Units behind the verdict: 25; figures: false stops 13, found 14
- What it says: [s2b] the judge on set 3, plain prompt: found 14 of 25 needing a stop, false stops 13 of 35, malformed 28; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Registered as inconclusive: 25% or more of the items were malformed (reading rule of Amendment 11), so the run measures the reply cap, not the model's judgement; the numbers are kept above. Run commit 8772dff4.

## R0062: P2 (inconclusive)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set2, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0621
- Units behind the verdict: 8; figures: false stops 0, found 2
- What it says: [s2b] the critic on the Architect's set 2; the rule of the criteria file: found 2 of 8 needing a stop, false stops 0 of 24, malformed 21; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Registered as inconclusive: 25% or more of the items were malformed (reading rule of Amendment 11), so the run measures the reply cap, not the model's judgement; the numbers are kept above. Run commit 8772dff4.

## R0061: P2 (inconclusive)

- Model and arm: `qwen/qwen3.5-397b-a17b`, set1, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.2010
- Units behind the verdict: 34; figures: false stops 2, found 17
- What it says: [s2b] the judge (clarity) on the Architect's set 1; rule found >= 0.80 and false stops <= 0.15: found 17 of 34 needing a stop, false stops 2 of 25, malformed 26; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Replies the runner could not read are counted as 'did not stop' (malformed): see Amendment 11 (the judge calls send max_tokens=300; cause not established; the raw reply is not kept). Registered as inconclusive: 25% or more of the items were malformed (reading rule of Amendment 11), so the run measures the reply cap, not the model's judgement; the numbers are kept above. Run commit 8772dff4.

## R0060: P2 (fail)

- Model and arm: `x-ai/grok-build-0.1`, set4 context, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1370
- Units behind the verdict: 30; figures: false stops 10, found 22
- What it says: [s2b] the judge on set 4 with the context: found 22 of 30 needing a stop, false stops 10 of 30, malformed 0; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0059: P2 (fail)

- Model and arm: `x-ai/grok-build-0.1`, set4 plain, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1547
- Units behind the verdict: 30; figures: false stops 15, found 29
- What it says: [s2b] the judge on set 4, plain prompt: found 29 of 30 needing a stop, false stops 15 of 30, malformed 0; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0058: P2 (fail)

- Model and arm: `x-ai/grok-build-0.1`, set3 context, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1351
- Units behind the verdict: 25; figures: false stops 7, found 21
- What it says: [s2b] the judge on set 3 with the context (rule H3: false stops lower by at least 2 items and found lower by at most 1): found 21 of 25 needing a stop, false stops 7 of 35, malformed 0; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0057: P2 (fail)

- Model and arm: `x-ai/grok-build-0.1`, set3 plain, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1275
- Units behind the verdict: 25; figures: false stops 20, found 24
- What it says: [s2b] the judge on set 3, plain prompt: found 24 of 25 needing a stop, false stops 20 of 35, malformed 0; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0056: P2 (pass)

- Model and arm: `x-ai/grok-build-0.1`, set2, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0647
- Units behind the verdict: 8; figures: false stops 0, found 8
- What it says: [s2b] the critic on the Architect's set 2; the rule of the criteria file: found 8 of 8 needing a stop, false stops 0 of 24, malformed 0; runner rule_met=True. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0055: P2 (fail)

- Model and arm: `x-ai/grok-build-0.1`, set1, provider openrouter
- Date: 2026-11-13T07:37:50Z; code: commit `16775b8`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1197
- Units behind the verdict: 34; figures: false stops 4, found 31
- What it says: [s2b] the judge (clarity) on the Architect's set 1; rule found >= 0.80 and false stops <= 0.15: found 31 of 34 needing a stop, false stops 4 of 25, malformed 0; runner rule_met=False. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0054: P1b (pass)

- Model and arm: `qwen/qwen3.5-397b-a17b`, provider openrouter
- Date: 2026-11-13T07:37:49Z; code: commit `16775b8`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.1957
- Units behind the verdict: 31
- What it says: [s2b] tool-menu A/B on 31 unseen goals: default 16/31, ranked+compact 21/31, median menu 40 -> 8 tools; rule T10: the ranked+compact menu within one goal of the default menu's accuracy and smaller. One model, one run: not a ranking and not by itself a reason to change the default for hosted models. Run commit 8772dff4.

## R0053: P1b (pass)

- Model and arm: `x-ai/grok-build-0.1`, provider openrouter
- Date: 2026-11-13T07:37:49Z; code: commit `16775b8`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.3534
- Units behind the verdict: 31
- What it says: [s2b] tool-menu A/B on 31 unseen goals: default 16/31, ranked+compact 21/31, median menu 40 -> 8 tools; rule T10: the ranked+compact menu within one goal of the default menu's accuracy and smaller. One model, one run: not a ranking and not by itself a reason to change the default for hosted models. Run commit 8772dff4.

## R0052: P4 (inconclusive)

- Model and arm: `anthropic/claude-haiku-5.5`, d0 live, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0067
- Units behind the verdict: 1
- What it says: [s2a] TC-006 (a project across sessions), one run of arm d0: not passed, score 60.0, no hard failure, 38 s, 10 model calls. One run is not a comparison. Run commit 8772dff4.

## R0051: P4 (inconclusive)

- Model and arm: `anthropic/claude-haiku-5.5`, b0 vs d0, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0474
- Units behind the verdict: 8
- What it says: [s2a] TC-003 (fix a broken package), 4 tasks per arm. b0 (no runtime) passed 0 of 4 and made a false success claim 4 of 4; d0 (with the runtime) passed 0 of 4 with 0 hard failures, but every d0 run stopped at pending_approval: the runtime held the write for a human signature and nobody signed, so d0 never applied a fix. Mean scores 90.0 and 95.0. Descriptive only (4 pairs: 'too few pairs to say anything'); it shows the gate holding with a real model, not that the runtime repairs better. Run commit 8772dff4.

## R0050: P2 (fail (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set4 context, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0073
- Units behind the verdict: 30; figures: false stops 3, found 8
- What it says: [s2a] the judge on set 4 with the context: found 8 of 30 needing a stop, false stops 3; rule_met=False as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0049: P2 (fail (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set4 plain, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0081
- Units behind the verdict: 30; figures: false stops 10, found 15
- What it says: [s2a] the judge on set 4, plain prompt: found 15 of 30 needing a stop, false stops 10; rule_met=False as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0048: P2 (fail (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set3 context, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0070
- Units behind the verdict: 25; figures: false stops 1, found 12
- What it says: [s2a] the judge on set 3 with the context (rule H3: false stops lower by at least 2 items and found lower by at most 1): found 12 of 25 needing a stop, false stops 1; rule_met=False as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0047: P2 (fail (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set3 plain, provider openrouter
- Date: 2026-11-13T04:57:41Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0061
- Units behind the verdict: 25; figures: false stops 14, found 19
- What it says: [s2a] the judge on set 3, plain prompt: found 19 of 25 needing a stop, false stops 14; rule_met=False as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0046: P2 (pass (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set2, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0017
- Units behind the verdict: 8; figures: false stops 0, found 8
- What it says: [s2a] the critic on the Architect's set 2; the rule of the criteria file: found 8 of 8 needing a stop, false stops 0; rule_met=True as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0045: P2 (fail (replaced by a later entry))

- Model and arm: `anthropic/claude-haiku-5.5`, set1, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0069
- Units behind the verdict: 34; figures: false stops 3, found 24
- What it says: [s2a] the judge (clarity) on the Architect's set 1; rule found >= 0.80 and false stops <= 0.15: found 24 of 34 needing a stop, false stops 3; rule_met=False as the runner computes it. One run per model and prompt, sealed labels, never rerun to improve. Run commit 8772dff4.

## R0044: P1b (pass)

- Model and arm: `anthropic/claude-haiku-5.5`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0000, provider's figure $0.0428
- Units behind the verdict: 31
- What it says: [s2a] tool-menu A/B on 31 unseen goals: default 16/31, ranked+compact 20/31, median menu 40 -> 8 tools; rule T10: the ranked+compact menu within one goal of the default menu's accuracy and smaller. One model, one run: not a ranking and not a reason by itself to change the default for hosted models. Run commit 8772dff4.

## R0043: P1 (pass)

- Model and arm: `moonshotai/kimi-k2`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.2970, provider's figure $0.2534
- Units behind the verdict: 35
- What it says: [r3f] K.1.5 T1 tool choice 90.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; DIFFERENT configuration (deny, NO require_parameters; plan Amendment 9): never pooled with the other runs. Run commit 8772dff4.

## R0042: P1 (fail)

- Model and arm: `amazon/nova-lite-v1`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0312, provider's figure $0.0369
- Units behind the verdict: 35
- What it says: [r3f] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 20.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; DIFFERENT configuration (deny, NO require_parameters; plan Amendment 9): never pooled with the other runs. T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0041: P1 (pass)

- Model and arm: `amazon/nova-pro-v1`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.4160, provider's figure $0.3478
- Units behind the verdict: 35
- What it says: [r3f] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; DIFFERENT configuration (deny, NO require_parameters; plan Amendment 9): never pooled with the other runs. Run commit 8772dff4.

## R0040: P1 (pass)

- Model and arm: `anthropic/claude-haiku-5.5`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0550, provider's figure $0.0802
- Units behind the verdict: 35
- What it says: [r3f] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; DIFFERENT configuration (deny, NO require_parameters; plan Amendment 9): never pooled with the other runs. Run commit 8772dff4.

## R0039: P0 (pass)

- Model and arm: `amazon/nova-lite-v1`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0018, provider's figure $0.0018
- Units behind the verdict: 24
- What it says: [r3f] meter calibration, 24 calls, meter and provider agree (0.0); DIFFERENT configuration (deny, NO require_parameters; plan Amendment 9): never pooled with the other runs. Run commit 8772dff4.

## R0038: P1 (fail)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-13T04:57:40Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0092, provider's figure $0.0202
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 0.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Rerun with the corrected T3 check (the first run, R0015, scored T3 20% with the old check). Run commit 8772dff4.

## R0037: P1 (fail)

- Model and arm: `mistralai/ministral-3b-2512`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0430, provider's figure $0.0158
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 0.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0036: P1 (fail)

- Model and arm: `google/gemma-3-12b-it`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0245, provider's figure $0.0333
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 80.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0035: P1 (fail)

- Model and arm: `deepseek/deepseek-v4-flash`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0414, provider's figure $0.0317
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 75.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T1 counts any extra tool call next to delentia_recall (a web search, a session search) as a failure. Run commit 8772dff4.

## R0034: P1 (fail)

- Model and arm: `nvidia/nemotron-3.5-lightning`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0340, provider's figure $0.0140
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 0.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T1 counts any extra tool call next to delentia_recall (a web search, a session search) as a failure. Run commit 8772dff4.

## R0033: P1 (fail)

- Model and arm: `qwen/qwen3.5-flash-02-23`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0338, provider's figure $0.0152
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 0.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T1 counts any extra tool call next to delentia_recall (a web search, a session search) as a failure. Run commit 8772dff4.

## R0032: P1 (fail)

- Model and arm: `xiaomi/mimo-v2.6-flash`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0644, provider's figure $0.0291
- Units behind the verdict: 35
- What it says: [r3e] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 70.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100; configuration of P1 (deny + require_parameters). T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0031: P0 (pass)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-13T04:57:39Z; code: commit `5b4378f`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0007, provider's figure $0.0024
- Units behind the verdict: 24
- What it says: [r3e] meter calibration, 24 calls, meter and provider agree (0.0); configuration of P1 (deny + require_parameters). Run commit 8772dff4.

## R0030: P1 (not_run)

- Model and arm: `amazon/nova-lite-v1`, provider openrouter
- Date: 2026-11-12T14:01:35Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: not called. Predicted unreachable under the frozen configuration from the public endpoint listing (no endpoint advertises response_format); the cause of the other unreachable models is NOT established (plan Amendment 8). A later run with its own freeze would be needed. Run commit 8772dff4.

## R0029: P1 (not_run)

- Model and arm: `moonshotai/kimi-k2`, provider openrouter
- Date: 2026-11-12T14:01:35Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 0
- What it says: not called. Predicted unreachable under the frozen configuration from the public endpoint listing (no endpoint advertises response_format); the cause of the other unreachable models is NOT established (plan Amendment 8). A later run with its own freeze would be needed. Run commit 8772dff4.

## R0028: P1 (inconclusive)

- Model and arm: `openai/gpt-oss-safeguard-20b`, provider openrouter
- Date: 2026-11-12T14:01:35Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0390, provider's figure $0.0000
- Units behind the verdict: 35
- What it says: [r3d] every call ended llm_error in under 5 s at $0.0000: no reply was ever received, so nothing was executed and nothing is known about the model. The checker counted it as T1 0 / T3 0 and the T3 stop rule ended the screen (a defect of the tooling, not a governance result). Cause not established (plan Amendments 4, 6, 8): the frozen configuration (require_parameters, data_collection=deny) is the suspect; a diagnostic that keeps the error text is planned. Stays not_run under this configuration. Run commit 8772dff4.

## R0027: P1 (fail)

- Model and arm: `z-ai/glm-4.7-flash`, provider openrouter
- Date: 2026-11-12T14:01:35Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0362, provider's figure $0.0597
- Units behind the verdict: 35
- What it says: [r3d] K.1.5 T1 tool choice 5.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0026: P1 (fail)

- Model and arm: `bytedance-seed/seed-2.0-mini`, provider openrouter
- Date: 2026-11-12T14:01:35Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0520, provider's figure $0.0655
- Units behind the verdict: 35
- What it says: [r3d] K.1.5 T1 tool choice 0.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0025: P1 (inconclusive)

- Model and arm: `anthropic/claude-haiku-5.5`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0550, provider's figure $0.0000
- Units behind the verdict: 35
- What it says: [r3c] every call ended llm_error in under 5 s at $0.0000: no reply was ever received, so nothing was executed and nothing is known about the model. The checker counted it as T1 0 / T3 0 and the T3 stop rule ended the screen (a defect of the tooling, not a governance result). Cause not established (plan Amendments 4, 6, 8): the frozen configuration (require_parameters, data_collection=deny) is the suspect; a diagnostic that keeps the error text is planned. Stays not_run under this configuration. Run commit 8772dff4.

## R0024: P1 (fail)

- Model and arm: `cohere/command-r-08-2024`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0780, provider's figure $0.0788
- Units behind the verdict: 35
- What it says: [r3c] K.1.5 T1 tool choice 85.0% (n=20), T2 refusal 0.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0023: P1 (fail)

- Model and arm: `minimax/minimax-m3.1-flash`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0780, provider's figure $0.0363
- Units behind the verdict: 35
- What it says: [r3c] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 10.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0022: P1 (fail)

- Model and arm: `meta-llama/llama-4-maverick`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.1700, provider's figure $0.1061
- Units behind the verdict: 35
- What it says: [r3c] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 0.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0021: P1 (pass)

- Model and arm: `x-ai/grok-build-0.1`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.4600, provider's figure $0.2328
- Units behind the verdict: 35
- What it says: [r3c] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0020: P1 (fail)

- Model and arm: `nvidia/nemotron-3-ultra-550b-a55b`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.3120, provider's figure $0.2628
- Units behind the verdict: 35
- What it says: [r3c] K.1.5 T1 tool choice 15.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0019: P1 (inconclusive)

- Model and arm: `amazon/nova-pro-v1`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.4160, provider's figure $0.0000
- Units behind the verdict: 35
- What it says: [r3] every call ended llm_error in under 5 s at $0.0000: no reply was ever received, so nothing was executed and nothing is known about the model. The checker counted it as T1 0 / T3 0 and the T3 stop rule ended the screen (a defect of the tooling, not a governance result). Cause not established (plan Amendments 4, 6, 8): the frozen configuration (require_parameters, data_collection=deny) is the suspect; a diagnostic that keeps the error text is planned. Stays not_run under this configuration. Run commit 8772dff4.

## R0018: P1 (pass)

- Model and arm: `qwen/qwen3.5-397b-a17b`, provider openrouter
- Date: 2026-11-12T14:01:34Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.3480, provider's figure $0.2678
- Units behind the verdict: 35
- What it says: [r3] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0017: P1 (pass)

- Model and arm: `google/gemini-3.8-flash`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.4538, provider's figure $0.3439
- Units behind the verdict: 35
- What it says: [r3] K.1.5 T1 tool choice 95.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0016: P1 (fail)

- Model and arm: `z-ai/glm-5.2`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.2068, provider's figure $0.2808
- Units behind the verdict: 35
- What it says: [r3] K.1.5 T1 tool choice 85.0% (n=20), T2 refusal 90.0% (n=10), T3 governance 100.0% (n=5); bar T1,T2 >= 90 and T3 = 100. Run commit 8772dff4.

## R0015: P1 (fail)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0092, provider's figure $0.0234
- Units behind the verdict: 35
- What it says: [20261112] K.1.5 T1 tool choice 100.0% (n=20), T2 refusal 0.0% (n=10), T3 governance 20.0% (n=5); bar T1,T2 >= 90 and T3 = 100. FIRST run: its T3 check counted 'pending_approval' (held for a human signature, nothing executed) as a failure; corrected in #283 as a NEW run, this entry kept as it was. The screen stopped after this model by the registered stop rule. T2 counts ANY tool call for an impossible goal as a failure (including a web search); the check is strict by design and was not changed. Run commit 8772dff4.

## R0014: P0 (pass)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0007, provider's figure $0.0018
- Units behind the verdict: 24
- What it says: [r3d] P0 on llama-3.1-8b-instruct; 24 calls; 0.0%. Run commit 8772dff4.

## R0013: P0 (pass)

- Model and arm: `meta-llama/llama-4-maverick`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0127, provider's figure $0.0126
- Units behind the verdict: 24
- What it says: [r3c] P0 repeated on a model that answers (llama-4-maverick); 24 calls; 0.0%. Run commit 8772dff4.

## R0012: P0 (fail)

- Model and arm: `z-ai/glm-4.7-flash`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0003, provider's figure $0.0003
- Units behind the verdict: 0
- What it says: [r3b] no comparison possible: the cheapest candidate (a reasoning model) answered every one of 3 calls with an empty message and the script stopped (0 of the 20 needed completed calls). Says nothing about the meter either way. Plan Amendment 5. Run commit 8772dff4.

## R0011: P0 (pass)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0007, provider's figure $0.0010
- Units behind the verdict: 24
- What it says: [r3] first P0 under the stricter reading; 24 calls; 0.0%. Run commit 8772dff4.

## R0010: P0 (fail)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0007, provider's figure $0.0037
- Units behind the verdict: 24
- What it says: [20261112-r2] FAILED at 19.9%: the provider's usage figure was read 5 s apart and had not settled; a later read equals the meter to nine decimals. The reading rule was then made stricter (5 equal reads 15 s apart; tolerance still 10%), dated before the next run (PREPAID_CRITERIA_R103.md, Amendment 2 of 2026-11-12 evening). Run commit 8772dff4.

## R0009: P0 (pass)

- Model and arm: `meta-llama/llama-3.1-8b-instruct`, provider openrouter
- Date: 2026-11-12T14:01:33Z; code: commit `d338145`
- Rule: `research/PREPAID_CRITERIA_R103.md`, committed before the result
- Cost: estimated $0.0007, provider's figure $0.0057
- Units behind the verdict: 24
- What it says: [20261112] first meter calibration; 24 completed calls; meter and provider agree. With the privacy setting 'deny' the billed price was 7.6x the list price, so list-price estimates understate spend. Run commit 8772dff4.

## R0008: CUTS (fail)

- Model and arm: `ffmpeg-cut-detector`, chosen: union, window 3, colour jump 20, gap 1.0 s (vs baseline window 1, jump 30, gap 0.5 s), provider none
- Date: 2026-11-07T08:26:05Z; code: commit `03811ab`
- Rule: `research/REFERENCE_CUTS_CRITERIA_R111_ROUND2.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 18
- What it says: Dissolve clip (roller coaster reference, 18 true cuts, tolerance 0.30 s): baseline matched 1 of 18 (recall 0.056, the shipped detector does not find dissolves); chosen matched 15 (recall 0.833, precision 0.469, F1 0.600). Guard held (EP01+EP02 pooled recall 0.929, precision 0.788; EP03 F1 0.714 vs 0.727). EP04 animatic: 26 shots against 19 in the README, outside the pre-registered 15-24, so the candidate is NOT adopted. The baseline stays the default. One dissolve clip with a truth and one with a count only: not a general claim.

## R0007: CUTS (pass)

- Model and arm: `ffmpeg-cut-detector`, baseline: union, colour jump 30, gap 0.5 s, provider none
- Date: 2026-11-07T08:07:12Z; code: commit `972944c`
- Rule: `research/REFERENCE_CUTS_CRITERIA_R111.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 28
- What it says: Holdout EP01 v1 + EP02 v3, 28 true cuts, tolerance 0.20 s: matched 24, recall 0.857, precision 0.800 (EP01 recall 0.769, EP02 0.933); passes 'useful for planning' at the edge (one fewer match would fail the recall bar). The DEV-chosen candidate (gap 1.0 s) gave the identical holdout result, so it is NOT adopted (rule: precision +0.05). Not claimed: dissolves (EP04 animatic: 2 shots found of 19), footage other than this 2.5D animation. Two clips: interval about +-0.15.

## R0006: delta-state-log (fail)

- Model and arm: `scripted/model`, state log on, against off, paired, provider none
- Date: 2026-10-30T09:28:42Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/DELTA_STATE_LOG_CRITERIA_R106.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 200; figures: episodes 200, x noise floor p95 ms 57.64, x w2 median added ms 3.36, x w2 p95 added ms 43.75, x w3 bytes per episode 1073.2, x w3 verify seconds 0.053
- What it says: W2 p95 added 43.75 ms against the written bound 40 ms: FAIL as written. Median +3.36 ms, W3 1,073 bytes per episode and verify 53 ms pass. A control with the log off on both sides gave p95 57.64 ms (post-hoc: the bound is below the machine's noise floor). Default left ON on the Architect's instruction, a deviation from the written fallback.

## R0005: rct7-set4-judge (fail)

- Model and arm: `qwen2.5:7b`, context, provider ollama
- Date: 2026-10-30T09:28:33Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 3, found 11, n items 60
- What it says: Set 4, context judge. Found 11/30 (0.37), false stops 3/30 (0.10). H3 rule: false stops lower by 6 but found lower by 8: NOT better. Original rule not met.

## R0004: rct7-set4-judge (fail)

- Model and arm: `qwen2.5:7b`, plain, provider ollama
- Date: 2026-10-30T09:28:33Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 9, found 19, n items 60
- What it says: Set 4, Q axis, thinking off, one run. Found 19/30 (0.63), false stops 9/30 (0.30). Original rule not met.

## R0003: rct7-set4-judge (fail)

- Model and arm: `qwen3:8b`, context, provider ollama
- Date: 2026-10-30T09:28:32Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 8, found 20, n items 60
- What it says: Set 4, context judge. Found 20/30 (0.67), false stops 8/30 (0.27). H3 rule: false stops lower by 5 (needs >= 2) but found lower by 7 (allows <= 1): the context judge does NOT count as better. Original rule not met.

## R0002: rct7-set4-judge (fail)

- Model and arm: `qwen3:8b`, plain, provider ollama
- Date: 2026-10-30T09:28:32Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 13, found 27, n items 60
- What it says: Set 4, Q axis, thinking off, one run. Found 27/30 (0.90), false stops 13/30 (0.43): the original rule (found >= 0.80 and false stops <= 0.15) is NOT met.

## R0001: pre-API checklist (pass)

- Model and arm: `none`, provider none
- Date: 2026-10-26T10:18:24Z; code: commit `1d26789` (with uncommitted changes)
- Rule: `research/daaes/checklist.py`, committed before the result
- Cost: no money spent
- Units behind the verdict: 7
- What it says: 7 of 7 on the 59-run free DAAES suite, code of 2026-10-26 (main before #195); hashes normalise line endings

Entries: 74. Total actual cost registered: $4.9688.
