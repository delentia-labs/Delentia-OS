# RCT-7 round 98: DEV results with local models (2026-10-24)

Criteria: `research/rct7_round98_criteria.md` (written before the code). Cases: `research/rct7_model_judge_cases.py`, `research/rct7_round98_cases.py`: written by the author, **DEV, not a claim**.
Models via Ollama on CPU, thinking off, temperature 0, prompt version 2, one call per case. Raw files: `research/results_round98/`. Reproduce:
`DELENTIA_OLLAMA_THINK=off python -m research.rct7_round98_measure --model qwen3:8b [--only judge|critic|chain]`.

## J. the judge (R1/R5): 20 requests with something missing, 20 clear

| model | found (guard on) | false pauses (guard on) | with the guard off | median |
|---|---|---|---|---|
| qwen3:8b | 20/20 | 0/20 | 20/20, 0 | 2.4 s |
| qwen2.5:7b | 18/20 (missed "สรุปประชุมเมื่อวาน", "Rewrite the intro to sound better") | 0/20 | 18/20, 0 | 1.8 s |
| llama3.2:3b | **10/20** | 2/20 | 10/20, 2 | 0.7 s |

* The cite guard changed nothing for the two models that cite correctly (nothing was dropped), so it costs them nothing: **kept on** (criteria rule: loses at most 0.05 of recall for the best two).
* **A finding against a small model:** with the earlier prompt (no `about` field) llama3.2:3b found 17/20 with 1 false pause; with the v2 prompt that asks it to copy the words of the request it is
  about, it finds 10/20. Asking a model to cite costs the 3B model most of its recall. The judge is not used with a model that small.

## C. the critic (R7, semantic): 20 answers that meet the request, 20 that do not (in ways no rule reads)

| model | found (guard on) | false stops (guard on) | guard off |
|---|---|---|---|
| qwen3:8b | 17/20 | 0/20 | 17/20, 0 |
| qwen2.5:7b | 19/20 | 1/20 | 19/20, 1 |
| llama3.2:3b | 17/20 | 4/20 | 19/20, 6 |

The guard lowered the 3B model's false stops from 6 to 4 and cost it 2 found; it changed nothing for the two larger models.

## K. cite-and-verify (R4): 5 faithful and 5 episodes with one invented fact

First run (before the coverage check): qwen2.5:7b flagged the invented fact in **3 of 5** (below the rule's 4): it left the invented claim out of its own list in 2 episodes. A check was added afterwards (**a
change made after seeing this result; the figures below are with it**): the code reports every clause of the answer that no listed claim speaks about (`gaps`).

| model | faithful claims verified | invented fact detected (flagged by status, or reported as a gap) | gaps reported in the faithful episodes |
|---|---|---|---|
| qwen3:8b | 8/8 | **5/5** (4 + 1 gap) | 0 |
| qwen2.5:7b | 10/10 | **4/5** (3 + 1 gap) | 0 |
| llama3.2:3b | 5/5 | 4/5 (3 + 1 gap) | 2 (false) |

Rule (>= 4 of 5 invented, >= 80% of the faithful claims verified): met by qwen3:8b and qwen2.5:7b; llama3.2:3b meets it but with false gaps.

## What this says and does not say
* Local 7-8B models, asked for JSON, behave as proposers within the safety shape (nothing malformed, no question about things the request does not mention). That is all it says.
* It does **not** say they understand intent: the cases are short, written by the author, and mostly obvious. The holdout labelled by the Architect (60 requests, 40 request/answer pairs) is the test.
* A model that cites a quote can still cite an irrelevant one: the verifier checks that the quote exists, that its numbers and names are in the quotes, and that the claim's words are covered; it does not
  prove the quote means what the claim says.
* Not measured: any paid model, any Thai-heavy set for the critic and the chain, any real user's requests.
