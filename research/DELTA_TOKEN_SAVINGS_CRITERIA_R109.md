# Delta and tokens: what is measured, and the rules, written before the run (Round 109)

Question from the owner: where in a Delentia episode does the Delta engine touch what is sent to a language model, and how many tokens does it really save? Earlier work measured pieces
(Round 52 retention with plain compression, Round 64 whole-episode prompt cost); this round measures the form the loop actually applies, with the fidelity cost and the compounding made explicit.
No model is called: tokens are counted with tiktoken `cl100k_base` (approximate for any provider: ratios are meaningful, invoices are not).

## What touches the prompt (read from the code, not measured)
1. COMPRESS (`governed_autonomous_loop._compress_tool_output`): a tool result of at least 6,000 characters is compressed by Delta v2 with `aggressive_mode=True, outline=True`, the focus being the
   GOAL, and the shorter text is used only when the character reduction is at least 20%. The original is stored (`tool_output_store`) and the model can read any part back with
   `delentia_expand_tool_output`.
2. History rendering (`autonomous_loop.render_history`): each earlier step is sent as a JSON patch against the step before when that is smaller; otherwise written out in full.
3. NOT a token feature: the `DeltaBlock` record of each episode and the verified state log (`agent_state_log`) store state for audit and growth; they add nothing to a prompt and remove nothing.
4. NOT touched by any Delta code: the tool menu (Round 64: 94% of a small prompt), the instruction block, the goal.

## Questions, the rule for each, and what I expect (written now)
| # | Question | Rule | Expectation before running |
|---|---|---|---|
| Q1 | Tokens saved on the tool-output message itself, in the loop's own form (wrapper text included), by kind of content | report median and range per kind; a kind "benefits" only if the median saving is at least 20% | tables and logs 60-90%; Python source 15-30% (many fall under the 20% rule and are left raw); English and Thai prose under 10% (left raw) |
| Q2 | Fidelity: is the line a question needs still in what the model sees? Needles = content lines; goals = literal (the needle's words), partial (two words), generic ("summarise this"), unrelated | report kept% per goal kind; compare with the recoverability path | literal and partial at least 90%; generic and unrelated clearly lower |
| Q3 | Expected NET saving once misses are priced: a miss costs one extra model call whose prompt re-sends the whole history | net = saving - P(miss) x (tokens of one more call); report per kind and per number of later calls | positive for tables and logs; near zero or negative for source code with generic goals |
| Q4 | Compounding: the compressed result is re-sent in every later call | measure whole-episode prompt tokens through the real prompt builder, raw against compressed, with 2, 4 and 8 calls after the read | the saving grows with the number of later calls, up to the saving of the message itself |
| Q5 | Share of a whole episode that Delta can reach, with the full menu and with the ranked compact menu (the local-model default) | report tool-output tokens / total prompt tokens | small with the full menu (about 6%); large with the compact menu |
| Q6 | Never worse: a result shown after compression has fewer tokens than the raw result | 0 violations over the whole corpus | holds |
| Q7 | Exact recovery: `expand` returns the stored original byte for byte | 0 mismatches (sha-256) | holds |
| Q8 | Cost in time of compressing, 30 KB and 230 KB | report milliseconds; flag anything over 1 second | tens of milliseconds |
| Q9 | History patches: does `render_history` ever send fewer tokens than writing every step out, and never more? | never more by more than 1% on any episode; report whether it ever fires | rarely fires; never harms |

## Wording rules
* "Saves X% of the tokens" is said only for the corpus and settings measured, with its limit. No claim about any model's quality, price or answer correctness: those need a model.
* A saving that depends on the answer being in the part that was kept is reported together with the kept% and the extra-call cost, never alone.
* Needles and corpus are fixed here by rule (seeded draws from files of this repository, generated tables and logs from fixed seeds); if a rule below fails the result is reported, the rule is not changed afterwards.
