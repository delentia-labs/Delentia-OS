# Goal-aware COMPRESS: results (Round 109)

Rules and expectations: `COMPRESS_POLICY_CRITERIA_R109.md` (committed before the code). Same script, corpus and seeds as `DELTA_TOKEN_SAVINGS_RESULTS_R109.md`, run twice: with the policy off (the old behaviour,
`research/compress_policy_off_r109.json`) and on (`research/compress_policy_on_r109.json`); the table is printed by `scripts/compare_compress_policy_r109.py`. No model was called; tokens are tiktoken
(approximate). What the policy does: a whole-text goal, an edit goal, a goal with no content word and a goal whose words are not in the text are shown WHOLE; a lookup is filtered by its content words
only (the generic words and file paths no longer act as focus); above 120,000 characters the old filter is kept so a context window is not filled; `DELENTIA_COMPRESS_POLICY=off` restores the old behaviour.

## Before and after (median over the 12 items; "when filtered" counts only the requests the filter was applied to)
| goal kind | share filtered, off to on | saved % when filtered | saved % overall | needle line still shown % (mean) |
|---|---|---|---|---|
| literal (the line's own words) | 67 to 62 | 48.3 to 52.8 | 34.6 to 33.1 | 100 to 100 |
| partial (two words) | 74 to 65 | 75.6 to 74.9 | 73.8 to 56.5 | 98.6 to 100 |
| single (one word) | 83 to 72 | 82.2 to 84.2 | 79.6 to 80.7 | 99.3 to 100 |
| edit ("fix the typo in this line") | 65 to 0 | 42.1 to none | 32.8 to 0 | 100 to 100 |
| generic ("summarise this") | 100 to 0 | 79.9 to none | 79.9 to 0 | **20.8 to 100** |
| unrelated | 100 to 8 | 86.6 to 88.1 | 86.6 to 0 | **16.0 to 92.4** |

## The rules, scored as written
| # | Result | Verdict |
|---|---|---|
| R1 whole-text and no-signal goals lose nothing | 100% of lines shown for every item except one: the test file with the unrelated goal (8.3% of the needles kept). The goal's words ("capital", "city", "france") do occur in that Python file, so the filter was applied as for a lookup, and the random needle has nothing to do with that question | **FAIL (1 of 12 items)**; not an information loss for the question asked, but the rule said 100% |
| R2 lookups keep what they had: needle kept never lower | never lower; higher for partial (98.6 to 100) and single (99.3 to 100) | PASS |
| R2 median saving not lower by more than 5 points, single not lower | literal -1.5, partial **-17.3**, single +1.1. When the filter is applied the saving is the same (75.6 to 74.9); the drop is requests whose content words are all generic or stop words ("the audit" has one content word, "each item" none), which are no longer filtered | **FAIL as written** (explained by the requests that are now shown whole) |
| R3 edit goals are shown whole | 0% filtered, 100% lines shown, 100% kept | PASS |
| R4 lookup keeps most of the whole-episode saving (full menu, 4 calls after the read, large items at least 40%) | Python 58.4 to **61.1**, English prose 50.7 to **50.9** (the generated table and log: 0 before and after, because the goal's word occurs in every line) | PASS |
| R5 never worse, exact recovery, time | 0 violations, 0 mismatches, 1-19 ms | PASS |
| R6 decision under 20 ms for 230 KB | pinned by a unit test | PASS |
| R7 a broken policy never filters | pinned by unit tests, also through the real loop | PASS |

## What it means for the number of tokens
Whole episode, full menu, 4 calls after the read:
| content | whole-text task, off to on | lookup task, off to on |
|---|---|---|
| Python 30 KB | 42.1% to 0% | 58.4% to **61.1%** |
| English prose 30 KB | 46.0% to 0% | 50.7% to **50.9%** |
| generated table | 77.4% to 0% | 0% to 0% |
| generated log | 87.7% to 0% | 0% to 0% |

Average saving over a workload, by the share of whole-text requests (the four large items): 0% whole-text requests 27.3% off, **28.0% on**; 25% whole: 36.3% off, 21.0% on; 50%: 45.3% off, 14.0% on; 100%:
63.3% off, 0% on. The "off" figures for whole-text requests are tokens removed from what the model was allowed to read, not tokens saved; I do not know the owner's mix of requests, so no average is claimed.

## What this establishes and does not
Established (this corpus, no model): whole-text and edit goals are no longer cut (20.8% to 100% of needles shown for generic goals); lookups keep their line (100%) at the same or a slightly better saving
where the filter applies; the decision is pure, fast and fails safe; the old behaviour is one switch away. Not established: that a model answers better or as well (needs a model and a task set); the saving
on real users' requests (their mix of lookups and whole-text tasks decides it); anything for requests where the filter's words occur in every line (tables, logs), where nothing is saved either way.
The honest summary: this change removes a saving that was information loss and keeps the one that is not; for whole-text tasks the way to spend fewer tokens is elsewhere (the compact tool menu, 7,900 to
about 1,000 tokens a call; prompt caching), not in hiding the text.

## After the first run (labelled)
* The first policy run showed every "What does the document say about X?" lookup being skipped (my whole-text pattern matched "what does the document say"); fixed with a rule that "say about/on/for X" is a lookup,
  and the numbers above are from the run after the fix.
* The 120,000-character guard was added after the run; no item of this corpus exceeds 30,000 characters, so it changes none of the numbers (it is pinned by a unit test).
* `test_rct_plan_context_real.py` (Codex's area) had a goal with no word to filter by ("Read source.md and answer in Thai") and expected it to be compressed; with the policy the text is shown whole, so its goal
  now names a line ("find line 350") and the omitted-passage path is still exercised. Flagged in the pull request for Codex.
