# Delta and tokens: results (Round 109)

Measured with `scripts/measure_delta_tokens_r109.py` (raw output: `research/delta_token_savings_r109.json`; questions and rules written first in `DELTA_TOKEN_SAVINGS_CRITERIA_R109.md`).
No model was called; tokens are tiktoken `cl100k_base` (approximate). Corpus: 12 items of 6,000 to 30,000 characters (real files of this repository: Python, English and Thai Markdown, JSON, YAML; a generated
520-row table, a generated 700-line service log, a generated 600-line pytest output), 12 needle lines per item drawn with a fixed seed, goals of five kinds. The numbers describe THIS corpus and
THESE settings (aggressive focus, outline on, 6,000-character threshold, 20% rule); they are not a promise for any other workload and say nothing about the quality of any model's answer.

## What the Delta engine does for tokens inside Delentia (read from the code)
| Where | What it does to the prompt | Measured effect |
|---|---|---|
| COMPRESS (`_compress_tool_output`, Delta v2) | a tool result of 6,000 characters or more is replaced by the lines that share words with the GOAL (plus code-like lines, one line of context each side, an outline); the original is stored and comes back through `delentia_expand_tool_output` | large, see below, but it is a **filter by the goal's words**, not a lossless compression |
| History rendering (`render_history`) | an earlier step is sent as a patch against the step before when that is smaller | 0 tokens on file reads; 75% on a status dictionary with one changing field |
| `DeltaBlock` per episode, the verified state log | record state for audit and growth | adds and removes no prompt tokens |
| The tool menu (about 94% of a small prompt) and the instruction block | not touched by any Delta code | 0 |

## Q1 and Q2: saving on the tool-output message / needle line still shown / share of the document's lines shown (median per kind)
| kind | goal shares the line's words (literal) | two words (partial) | one word (single) | generic ("summarise this") | unrelated |
|---|---|---|---|---|---|
| Python source | 61 / 100 / 31 | 76 / 100 / 10 | 81 / 100 / 9 | 80 / 19 / 11 | 87 / 14 / 4 |
| English Markdown | 16 / 100 / 79 | 61 / 96 / 36 | 64 / 100 / 32 | 54 / 46 / 40 | 77 / 33 / 20 |
| Thai Markdown | 43 / 100 / 47 | 81 / 100 / 15 | 85 / 96 / 11 | 81 / 29 / 11 | 86 / 29 / 9 |
| JSON | 86 / 100 / 26 | 90 / 100 / 16 | 92 / 100 / 10 | 96 / 17 / 3 | 97 / 0 / 4 |
| YAML | 25 / 100 / 73 | 40 / 92 / 51 | 49 / 100 / 43 | 53 / 25 / 38 | 53 / 25 / 38 |
| generated table | 0 / 100 / 100 | 0 / 100 / 100 | 0 / 100 / 100 | 97 / 0 / 2 | 97 / 0 / 2 |
| generated log | 0 / 100 / 100 | 0 / 100 / 100 | 49 / 100 / 51 | 98 / 0 / 1 | 98 / 0 / 1 |

How to read it. When the goal names words that are in the line the person needs, the line is kept (needle kept 100% for literal, 96-100% for a one-word goal, 92-100% for two words) and 16-92% of the tokens of that
message are removed. When the goal is generic or about something else, 54-98% of the tokens are removed and the line asked about is usually NOT shown (kept 0-50%). For a table or a log, a goal that
repeats the columns' words matches every line, so nothing is removed (0%).

## Q4 and Q5: a whole episode (prompt tokens summed over every call), compressed against raw
With a goal of the form "read this file and tell me what it contains" (a generic goal: the upper bound of the saving):

| content read | full menu, 4 calls after the read | ranked compact menu (the local-model default), 4 calls | the file's tokens as a share of the raw episode |
|---|---|---|---|
| Python 30 KB | 48,796 to 28,260 (42%) | 39,406 to 18,870 (52%) | 71-88% |
| English Markdown 30 KB | 37,520 to 20,244 (46%) | 28,130 to 10,854 (61%) | 63-84% |
| generated table | 63,864 to 14,464 (77%) | 54,474 to 5,074 (91%) | 78-92% |
| generated log | 117,576 to 14,468 (88%) | 108,186 to 5,078 (95%) | 88-96% |

The saving grows with the number of calls after the read (2, 4, 8 calls: 40, 42, 43% for the Python file with the full menu), because the compressed message is re-sent in every later call. An episode that reads
nothing large gets nothing: below 6,000 characters Delta does nothing, and there the menu is the cost (full menu about 7,900 tokens a call, ranked compact about 1,000).

## Q3: what the saving is worth once the lost lines are priced
* **A lookup task** (the answer is one line): the gross saving over 3 later calls is 11,000-76,000 tokens on the large items, and the expected price of a miss (one more call, about 3,000 tokens) is small
  next to it: the net stays positive everywhere (for example 17,846 for the Python file with a generic goal, where 92% of lookups miss and need the extra call).
* **A task that needs the whole text** (summarise, review, compare): the generic goal shows 1-49% of the lines. The tokens that were not sent are either not used (information was removed, not
  tokens saved) or fetched back with expand calls: 1-9 calls of at most 8,000 characters each, whose overhead alone is 2,000-14,000 tokens, and then the original is paid for again. **There is no
  net saving to claim for that kind of task**; the 97% of the table above is a 97% cut of what the model was allowed to read.

## The other questions
| Q | Result | Rule | Met |
|---|---|---|---|
| Q6 never worse | 0 violations over every item and goal | 0 | yes |
| Q7 exact recovery | 0 mismatches: the stored original equals the rendered result byte for byte, and expand of the whole range returns every line unchanged | 0 | yes |
| Q8 time | 1-2 ms for 30 KB, 9-17 ms for 230 KB | under 1 s | yes |
| Q9 history patches | 0 patch lines for six different parts and for the same file read six times with one number changing (a change inside one long string cannot be patched); 5 patch lines and 75.5% fewer tokens for a status dictionary of 40 fields with one changing | never more than writing every step out | yes |

## My expectations, written before the run, against what happened
* Q1: "tables and logs 60-90%; Python 15-30%; prose under 10%": **wrong for Python and prose** (45-87% and 16-77%). I had thought of plain compression; the loop uses the aggressive focus filter, which drops
  every line that does not share a word with the goal.
* Q2: "literal and partial at least 90%; generic and unrelated clearly lower": met (100 and 96-100; 0-50).
* Q3: "positive for tables and logs; near zero or negative for source code with generic goals": half right. For lookups it is positive everywhere; for whole-text tasks it is negative everywhere.
  The first version of the net table priced a miss as one call, which understates the cost for whole-text tasks; the second model (added after the first run, labelled in the script) fixes that.
* Q5: "small with the full menu (about 6%)": only for small reads; for a large read the file is 59-89% of the episode.
* Q9: "rarely fires": it never fired on file reads, and does fire for a dictionary of separate fields.

## Findings that are not token numbers
* The compressed text is made of stripped lines: **indentation is removed** (`line.strip()` in the port of the TypeScript original), so Python read through COMPRESS has no indentation. A model that copies a block from
  that view into an edit would not match the file. The expand path returns the original lines unchanged (checked), so the recovery exists; it costs a call.
* The saving depends on the words of the goal. A person who writes "summarise" gets a very small view of a large document; one who writes the name they are looking for gets a large saving and the line.

## What this does and does not establish
Established (this corpus, these settings, no model): the saving on a large tool result, its fidelity cost by kind of goal, the compounding over later calls, the exactness of recovery, the time cost, and the
fact that the history patch rarely applies. Not established: that a model answers as well from the compressed view (needs a model and a task set), the saving on real users' reads (their files, their goals),
or any claim about price. The honest one-line statement: **on a large read with a specific goal the Delta compression removes about half to nine tenths of the tokens of an episode and keeps the line asked
about; with a generic goal it removes the same amount by showing a fraction of the text.**

## Open questions for the owner (nothing here is changed)
1. Should COMPRESS be skipped, or limited to the head, the tail and the outline, when the goal is generic (no content word that matches a meaningful share of the lines)? Today it filters hardest exactly when
   the goal says least.
2. Should a code file read for an edit be exempt from COMPRESS (indentation, exact text)? The agent can expand a range, at the price of a call.
3. Is the history patch worth keeping for its one case (a status dictionary), or is it dead weight? It never cost tokens in these measurements.
