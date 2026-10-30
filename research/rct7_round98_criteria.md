# RCT-7 round 98: the model-assisted parts, built and measured BEFORE any paid model (criteria written before the code and the first run, 2026-10-24)

Three things a rule cannot do and a language reader can. All three are opt-in, propose-only, fail open, and checked against the text they are about; none can lift a gate, set a
requirement, answer for the person, or skip a signature. The measurement here uses LOCAL models (free) and cases written by the author, so it is a DEV measurement: it decides whether
the code is worth keeping and which guard to turn on, never a claim. The claim needs a holdout labelled by the Architect (R1/R5, sheet already written) and a labelled set of answers for R7.

## J. the judge (R1/R5): "is this request clear enough to act on, and if not, what is unknown?"
* Output is JSON `{"clear": bool, "unknowns": [{"question": "...", "about": "<words copied from the request>"}]}`.
* **Cite guard:** an unknown is kept only if `about` (>= 3 characters) occurs in the request (case-folded, whitespace collapsed). A model that asks about something the request never mentions
  (the commonest way a model invents a reason to stop) is dropped. If every unknown is dropped the verdict is "no opinion", not "unclear".
* DEV measurement on the 40 requests of `research/rct7_model_judge_cases.py` (20 unclear, 20 clear), prompt v2 (asks for `about`), models qwen3:8b, qwen2.5:7b, llama3.2:3b:
  report recall and false pauses WITH and WITHOUT the cite guard. **Keep the guard on by default if** it lowers false pauses (or keeps them at 0) and loses at most 0.05 of recall for the
  best two models; otherwise it stays available and off. Prompt revisions: at most two, each logged.
* Safety rules tested with a scripted provider: never runs for a goal that carries outside text (tainted), never after the person already answered (revised goal), never when the
  episode is not interactive or the stop-and-ask is off, a provider error or unreadable reply = no opinion (the episode goes on), at most 3 questions of at most 240 characters each,
  the question text says a MODEL proposed it.
* **False-pause control:** per person, if of the last 5 or more resolved model questions at least 60% were cancelled or accepted-as-is, the judge is skipped (and the audit says so).

## C. the critic (R7, semantic): "does this answer meet the request?"
* Output `{"meets": bool, "unmet": [{"part": "<words copied from the request>", "why": "..."}]}`; the same cite guard on `part`. Only `meets == false` with at least one grounded unmet part may stop.
* Runs only when the rules found no difference (it adds, it never replaces) and only for an interactive episode with stop-and-ask on.
* DEV measurement on 40 new (request, answer) pairs written before the first run (`research/rct7_round98_cases.py`: 20 that meet, 20 that do not in a way no rule reads). Report found/false
  pauses per model with and without the guard. Same keep rule as above.

## K. cite-and-verify (R4, evidence chain)
* A **deterministic baseline chain** needs no model: for each checkable token of the answer (number, path, address) the chain names the step whose result contains it, or "the request", or
  "unsupported". Pure function, unit tested, always produced, information only.
* A **model-written chain** is asked once (opt-in, `DELENTIA_RCT7_CHAIN=cite`): claims, each with evidence `{"step": n, "quote": "<verbatim from that step's result>"}`. The VERIFIER (code)
  checks that the step exists and the quote occurs verbatim in that step's result. A claim whose citation fails is reported `quote_not_found` / `step_missing` / `no_evidence`; nothing is
  taken from the model's word.
* DEV measurement on 10 scripted episodes (5 faithful, 5 with one invented fact) with the three local models: **keep if** the invented fact is reported unverified in at least 4 of 5
  episodes and at least 80% of the claims of the faithful episodes verify. The verifier itself is a pure function with its own exhaustive unit tests (fabricated quote, wrong step, quote from
  another step, empty evidence, whitespace differences).

## Not claimed
That any of this makes the runtime understand intent. It says how often a model's flag, constrained to cite the request, agreed with one author's labels, and that a citation either appears
verbatim in the evidence or it does not.

## A. the agent's own question (R5 mid-episode): the tool `delentia_ask_user` (written before the code, same day)
The proposers above ask before the work starts or after it ends. A model that is already working can find, halfway, that it needs something only the person knows (which of two files, which
date). Today it can only guess or give up. The tool lets it ask once.
* Visible and effective only where the stop-and-ask applies (a person is present and the setting is on); never in a job, a schedule, a webhook, a subagent or the API, where it is not even in the menu.
* At most one question per episode. A second call, or a call where nobody can answer, returns a plain note ("state your assumption and go on") and the episode continues.
* The call ends the episode at once: no tool runs after it. The person gets the question (marked as written by the model, and as untrusted if the episode had read outside text); the answer is
  added to the request exactly like any other answer, so sending the same request again continues with it. A chain of questions keeps every earlier answer.
* The per-person brake covers it: a person who keeps dismissing model questions is not asked by the model any more (the tool then returns the "go on" note).
* The tool is classified for the taint gate (inert: it only ends the episode), for person scope (person-neutral), for the effect inventory and for the tool menu; the repository's own audits must pass.
* Pass: a scripted model that calls it is stopped with a stored question and no later tool ran; the same model in a job gets the note and finishes; the second call gets the note; the answer
  reaches the next episode's goal; a chain of two questions keeps both answers; the menu has it only when it applies.

## P. the simulated person for the research arms (written before the code)
The arms of a controlled run are not interactive, so the judge, the critic and the question tool are never exercised there, and a question would count as a failure. The simulated person is what lets them
be measured: when an episode stops to ask, the harness answers from a fixed policy and runs the same request again, exactly as a person would through the Desk.
* The person only ANSWERS. It never decides for the system, never approves anything, never changes a setting. Deterministic: the same question and task give the same answer.
* Policies: `insist` (the default; for tasks that are fully specified, which every task of the generated domains is): "the request is complete as written, do it as written, do not ask again".
  Because the task is fully specified, **every question is a needless one by construction**, so the number of questions per 100 episodes is the false-pause rate on real tasks, with no labeller.
  `facts` (for a task that deliberately withholds something): answers with the hidden fact when the question mentions its keyword, otherwise insists.
* At most two rounds of question and answer per episode; an episode still waiting after that is recorded as unresolved and graded as it is.
* Every arm of a run gets the same person. Off by default; with it off a row and the run identity are exactly what they were before.
* Cost and tokens of every round are summed (a stop is not free); the row records questions asked, their kinds, rounds, and whether the episode ended unresolved.
* Pass: tests with the real harness, the real governed loop and a scripted judge show: a question is answered and the episode finishes and is graded; costs add up over rounds; the round limit holds;
  person off leaves rows unchanged; the identity changes when the person or the judge setting does.

## T. Thai sets for the judge, the critic and the chain (written before the cases and before any run, 2026-10-24, round 99)
The English dev sets say nothing about the language the Architect actually writes in. Same code, same prompts, same keep rules; only the language of the cases changes.
* Cases (`research/rct7_round99_cases_th.py`, author-written, DEV, not independent evidence): 41 Thai requests (20 unclear, 21 clear), 39 Thai request/answer pairs (19 meet, 20 do not, in a way no
  rule reads) and 10 scripted Thai episodes (5 faithful, 5 with one invented fact). None repeats a request of the English sets.
* Measured with the same models as the English run (qwen3:8b, qwen2.5:7b, llama3.2:3b), thinking off, one run each, cite guard on and off on the very same replies.
* **Reported, not passed or failed:** recall and false pauses per model next to the English numbers. **Rule for the wording of the documents:** if for a model Thai recall is below 0.80 or false
  pauses above 0.15 where the English numbers were not, the documents say that model-assisted parts are not validated for Thai with that model. Nothing is switched on either way (all are opt-in).
* The cite guard for Thai: an unknown's `about` (>= 3 characters) must occur in the request. Thai is written without spaces, so a model that quotes a different word boundary than the request
  uses is dropped by the guard; the measurement reports how many Thai unknowns the guard dropped that the same reply would have kept without it (the guard's price in Thai).
* The chain's verifier compares quotes after whitespace folding; Thai has few spaces, so a model that adds or removes a space inside a Thai quote still fails verification. Reported as
  `quote_not_found` counts on the faithful Thai episodes.

### T.1 First Thai result and the defect it showed (added after the run, 2026-10-24)
qwen3:8b, thinking off, Thai sets: judge 20/20 found, 0/21 false pauses (cite guard on and off identical); critic 19/20 found, 0/19 false stops; chain: 11/11 claims of the faithful episodes
verified, but only **3/5 invented facts detected** (the English run: 5/5; the keep rule is >= 4/5). Cause found by reading the code, not by tuning: `verify_claims`' coverage test and
`coverage_gaps` both read words with `[A-Za-z]{4,}`, so a Thai phrase has no words at all and an invented Thai phrase can never be reported as a gap or as weak support.
**Change made AFTER seeing this (ADDED_AFTER):** Thai runs (4 or more Thai characters in a row, i.e. one phrase between spaces) are checked by character trigrams, in the claim-versus-quote
coverage and in the answer-versus-claims gap check. The 10 episodes above are now DEV for this change. Six more were written BEFORE the change (`EPISODES_FRESH`, 3 faithful, 3 invented)
and are run once with it. **Keep rule for the change:** on the 6 fresh episodes at least 2 of 3 invented facts reported (as an unverified claim or as a gap) and 0 gaps on the 3 faithful ones;
the English results (cases, 128 chain tests) must not change.

### T.2 What the check did to faithful claims, and what was kept (added after the second run, 2026-10-24)
The Thai trigram test was first applied twice: the answer's phrases against the listed claims (the gap check) and each claim's phrases against its quote (a new claim status). Second run
(qwen3:8b), 10 development episodes and the 6 fresh ones:
* invented facts reported (a model-listed claim without evidence, or a gap): development 5/5 (was 3/5), fresh 3/3 (rule: at least 2 of 3); faithful episodes with a gap: 0 of 8 (rule: 0).
* **but** the claim-versus-quote test rejected faithful claims: 4 of 10 on the development set and 3 of 6 on the fresh set (the first run verified 11/11), against the keep rule of 80%. The
  rejected phrases are Thai glue words the model adds when it explains English evidence in Thai (เท่ากับ, ได้แก่, ชั่วโมง, เก็บไว้, สองที่อยู่ใน); no evidence can contain them.
* **Decision:** the claim-versus-quote test is removed (every invented fact it flagged was already flagged another way); the gap check, which compares Thai with Thai, stays. The fresh set
  is now seen and counts as development data for any further change.

### T.3 Final Thai numbers (after the change in T.2; thinking off, one run each, DEV, not a claim; files in `research/results_round99/`)
| | qwen3:8b | qwen2.5:7b | llama3.2:3b |
|---|---|---|---|
| judge: found / false pauses (Thai) | 20/20 / 0 of 21 | 16/20 / 0 of 21 | 14/20 / **6 of 21** |
| judge: English (round 98) | 20/20 / 0 | 18/20 / 0 | 10/20 / 2 |
| critic: found / false stops (Thai) | 19/20 / 0 of 19 | 20/20 / 1 of 19 | 17/20 / **9 of 19** |
| critic: English (round 98) | 17/20 / 0 | 19/20 / 1 | 17/20 / 4 |
| chain, 10 dev episodes: faithful claims verified; invented facts reported | 10/10; 5/5 | 8/10; 4/5 | 3/6; 5/5 |
| chain, 6 fresh episodes: faithful claims verified; invented facts reported | 6/6; 3/3 | 6/7; 3/3 | 4/5; 3/3 |
| faithful episodes with a gap (dev / fresh) | 0 / 0 | 0 / 0 | 1 / 3 |
Reading, by the rule of T: for the two 7-8B models Thai is not worse than English except qwen2.5:7b's judge (16/20 = 0.80, exactly at the rule and 2 below its English run). For llama3.2:3b Thai
false pauses are 0.29 and false stops 0.47, far over 0.15: **the documents say that the model-assisted parts are not validated for Thai with a 3B model** (they were already advised against
for 3B in English). The cite guard changes at most one case per model (no price in Thai measured). Nothing is switched on by any of this (all opt-in), and the cases are the author's.

## H1. The Architect's holdout, set 1 (60 requests; sealed 2026-10-24 17:59, labels hash 6ee37ed0c338...; added BEFORE the first model run)
* **Primary, as registered:** the judge's `found` over all 34 requests labelled A and `false stops` over the 25 labelled B; rule found >= 0.80 and false stops <= 0.15; one run per model.
  Request 4 is `?` and is not scored. Models: qwen3:8b and qwen2.5:7b (thinking off). llama3.2:3b is not run (the 3B model failed the English and Thai DEV rules).
* **Why the primary rule is expected not to be met, written before the run:** the sheet said A = "ask first because information that is needed is missing". The Architect's notes show that
  22 of his 34 A are that, but 12 are requests that are understandable as they stand and that he wants a PLAN AND A CONFIRMATION for because of their consequence (delete, send, pay, open
  permissions, publish, overwrite) or an outline before creative work. A clarity judge has no reason to stop those. The classes are in `research/rct7_holdout1_reason_classes_r99.json`
  (Claude's reading of his notes, fixed before the run).
* **Secondary (post-hoc, stratified, reported next to the primary and never instead of it):** found per class (INFO 7, BOTH 15, APPROVAL 11, PLAN_ONLY 1) and false stops on B. No prompt change
  follows from this run; a second run on the same labels is refused by the runner.

### H1.1 Result of the registered runs (2026-10-24, same day; files `research/results_round99/holdout1_sealed.json` and `holdout1_runs.json`)
Registered (first run of each model, prompt version 8292fc3416cc, cite guard on, thinking off):
* qwen3:8b: found **29/34 = 0.853** (95% 0.70-0.94), false stops **4/25 = 0.16** (95% 0.06-0.35): the rule (found >= 0.80 and false stops <= 0.15) is **NOT met, by one case**.
* qwen2.5:7b: found 18/34 = 0.529 (0.37-0.69), false stops 3/25 = 0.12: **NOT met** (recall).
A repeat (same prompt and labels, run only to keep per-item verdicts, which the first run did not store) gave exactly the same totals for both models: the verdicts are stable at temperature 0.
**The expectation written before the run was partly wrong:** it said a clarity judge would not stop the APPROVAL requests. qwen3:8b stopped 9 of 11 of them and 13 of 15 BOTH, because most of those requests are in fact
under-specified ("Delete the duplicate entries": which entries?). The recall problem is only for qwen2.5:7b (APPROVAL 7/11, BOTH 8/15); qwen3:8b's miss list is 25 (Remove John), 36 (Notify the team), 44 (thank-you note),
47 (Update the README), 15 (poem). **The failure of the rule for qwen3:8b is on the other side:** its four false stops (19 Approve the pending request, 24 Find the cheapest option, 39 Look up the latest version,
60 Make the logo bigger) are all requests for which the Architect's note says the missing piece comes from context or can be looked up (a pending request exists, research it, the latest version is known, a logo exists).
The judge sees only the sentence (as the sheet told the labeller to assume); the Architect's notes show that in real use the agent has context. No prompt is changed because of this run (a second look is refused);
the hypothesis "tell the judge what the agent can look up and what the chat already holds" needs a NEW sealed set with the context written next to each request.

## H2. The Architect's holdout, set 2 (R7: 40 request/answer pairs; sealed 2026-10-24 18:44, labels hash 471ac6879a23...; added BEFORE the first model run)
* **Primary, as registered:** the critic's `found` over the 8 pairs labelled N (the answer does not meet the request: 3, 6, 10, 21, 23, 27, 32, 35) and `false stops` over the 24 labelled M; rule found >= 0.80
  (at least 7 of 8) and false stops <= 0.15 (at most 3 of 24). The 8 pairs labelled `?` (4, 9, 13, 17, 20, 28, 30, 34) are not scored. One run per model (qwen3:8b, qwen2.5:7b; thinking off); the runner now keeps
  per-item verdicts, so no repeat is needed.
* **Expectation written before the run:** the eight N are plain factual or completeness failures (90 minutes for 2 hours, 4/5 bigger, 28 for 20-8, Sydney, "Childs", coal as renewable, one language
  and no use each, an advantage without the disadvantage), so a critic that reads the request should find most of them; the risk is on the M side: the Architect's notes show a standard of answer that goes
  beyond "meets the request" (names and roles in a greeting, more options for a broad question, reasons, a follow-up question to the user) and a critic that applies it will stop M answers.
  Two planted wrong answers were left unscored by him (13 gold is "Go", 17 hexagon not answered); a critic that stops them is not penalised and not credited.
* The notes on the `?` and M items are kept verbatim in `RCT7_HOLDOUT_2_ARCHITECT_LABELS_AND_NOTES_2026-10-24.md`; they are read afterwards as a description of what the Architect wants an answer to contain, not scored.

### H2.1 Result of the registered runs on set 2 (2026-10-24; `research/results_round99/holdout2_sealed.json`, `holdout2_runs.json`; prompt version 8292fc3416cc, cite guard on, thinking off)
* qwen3:8b (critic): found **6/8 = 0.75** (95% 0.41-0.93), false stops **0/24 = 0.00** (0.00-0.14): the rule (found >= 0.80, false stops <= 0.15) is **NOT met, by one pair** (missed: 3 "2 hours is 90 minutes", 27 "Sydney").
* qwen2.5:7b (critic): found 6/8 = 0.75 (missed 3 and 10 "4/5 is bigger"), false stops **8/24 = 0.33** (0.18-0.53): **NOT met**. Its false stops include "Jupiter." for the largest planet, "24/10/2026" for the date format, and "9" for the square root of 81.
* Of the 8 pairs the Architect left as `?`, qwen3:8b stopped 3 (17 hexagon not answered, 30, 34) and let 5 pass; qwen2.5:7b stopped 4 (13 "Go" for gold, 17, 30, 34). Not scored.
* The expectation written before the run held for the N side (the eight failures are plain) and for the risk on the M side only for qwen2.5:7b; qwen3:8b applied no stricter standard than the Architect's labels.
* The Architect's notes on M and `?` items describe a standard above "meets the request" (names and roles in a greeting, more options for a broad question, reasons, a follow-up question to the user, answering in both
  numeral and words). The critic does not look for that and none of it is scored; it is read as a description of what he wants an answer to contain.
* Together with set 1 (judge): for qwen3:8b both rules are missed by one case on small samples (n = 8 and 25), with wide intervals; neither run supports "validated" and neither supports "useless".

## H3. Set 3 (two axes plus the context the agent has) and the context-aware judge — FROZEN 2026-10-24, before the Architect has labelled a single item
* Sheet: `RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md` (60 requests; 16 sentences twice, without and with context; `research/holdout3_sheet_r99.py` builds it, the pairs are in `RCT7_HOLDOUT_3_PAIRS_SIDECAR.json`).
  Q = ask for missing information first? C = show a plan and wait for a human confirmation first? Y / N / ? on each.
* **The context-aware judge prompt is fixed now:** `rct_control_plane/rct7_judge.SYSTEM_REQUEST_CTX`, version hash **5dbf3fa34125**; the original judge prompt version stays **8292fc3416cc**. A test pins both hashes.
  A change to the context prompt after this point is a new version and a new registered run, never a retry. The cite guard is unchanged (the question's `about` must occur in the REQUEST).
* **Registered runs after sealing (qwen3:8b and qwen2.5:7b, thinking off, one run each per variant):** `plain` (sentence only) and `context` (sentence + context line), both scored on axis Q with the rule
  found >= 0.80 and false stops <= 0.15 (Y plays "should ask", N plays "may go ahead", ? is not scored). `python -m research.rct7_holdout_twoaxis seal|run|report`.
* **The context hypothesis, registered:** the context judge is better than the plain one for a model if its false stops are lower by at least 2 items and its found count is lower by at most 1.
  If that does not hold, the hypothesis that giving the judge the context helps is not supported on this set, and nothing is wired into the loop.
* **A second, descriptive reading of the pairs (about the Architect, not about a model):** for each of the 16 sentences, whether his Q on the with-context row differs from his Q on the no-context row. Expected: where the
  context supplies the missing piece, Y becomes N. Reported as counts; no threshold.
* The C axis is counted and kept for the owner-calibration plan (`DELENTIA_ROUND99_PLAN_...md`); no judge answers it yet.

### H3.1 Set 3 labelled and sealed (2026-10-25 09:57, labels hash 1812d60fb529...; written BEFORE the first model run)
* The Architect labelled all 60 items on both axes (no `?`): Q (ask for missing information first) Y 25 / N 35; C (show a plan and wait for a confirmation) Y 43 / N 17. Notes verbatim in `RCT7_HOLDOUT_3_ARCHITECT_LABELS_AND_NOTES_2026-10-25.md`.
* **The pairs, read from his labels alone before any model ran** (descriptive): of the 16 sentences that appear without and with context, his Q goes Y -> N in 13, stays Y in 3, and never goes N -> Y;
  his C stays Y in 12 of 16 (Y -> N in 3, N -> Y in 1). So for him context removes the need to ask in most cases and does NOT remove the need for a plan and a confirmation: the two axes are separate.
* **Registered runs (qwen3:8b, qwen2.5:7b; thinking off; one run per variant):** `plain` and `context` judges scored on axis Q with found >= 0.80 (Y rows stopped) and false stops <= 0.15 (N rows stopped).
  The context judge counts as better than the plain one for a model if its false stops are lower by at least 2 items and its found count is lower by at most 1 (H3).
* **Expectation written before the run:** half of the 35 Q=N rows are the with-context copies of a sentence, so a judge that sees only the sentence (`plain`) should stop many of them (high false stops) while the
  `context` judge should stop fewer; whether it also keeps finding the 25 Q=Y rows is the open question. A small model may not use the context at all.

### H3.2 Set 3 result (2026-10-25, the four registered runs, one per model and variant; rule H3 written before any run)
* qwen3:8b: plain found 21/25 (0.84), false stops 17/35 (0.486); with context found 20/25 (0.80, 95% 0.61-0.91), false stops 5/35 (0.143, 95% 0.06-0.29).
  H3 (context better iff false stops lower by >= 2 items and found lower by <= 1): false stops -12, found -1 -> **context judge is better for qwen3:8b**; it also meets the original rule on the Architect's own set (found >= 0.80, false stops <= 0.15), at the edge of both bounds.
* qwen2.5:7b: plain found 19/25 (0.76), false stops 13/35 (0.371); with context found 4/25 (0.16), false stops 2/35 (0.057). H3: false stops -11 but found -15 -> **context judge is NOT better**: the 7B model answers "no question needed" almost everywhere once a context line is present, including the rows that have no context.
* The pairs (16 sentences that appear with and without a context line): the Architect changed his own Q answer in 13 of 16 pairs when the context supplied the missing piece; the plain judge never changed (it ignores what the agent can see); the qwen3:8b context judge followed him in several pairs and not in others (kept asking about 'Delete the duplicate files' and 'Send the report to the client' where the previous step / chat made the target clear).
* Scope: 60 rows, one run each at temperature 0, one labeller; the judge prompt version `5dbf3fa34125` was frozen before any label existed. Not a claim about a capable model. The Architect's C axis (confirm a plan) was Y for 43 of 60 and is not a target of the judge at all; it is the data for the plan-approval design (Q2).

## H4. Set 4 (fresh requests, each with the context the BUILDER produces) — FROZEN 2026-10-30, before any label or model run exists

Why: set 3's context lines were written by hand. Set 4 shows the judge the text `rct_control_plane/judge_context.build` produces for a described state, and shows the Architect the SAME text. The design and the
reasons are in `DELENTIA_DESIGN_NOTE_JUDGE_CONTEXT_AND_SET4_2026-10-25.md` (section 4); this section fixes what is measured.

1. **60 fresh requests** (`research/holdout4_sheet_r105.py`; none equal to, or closer than 0.85 string similarity to, a request of sets 1-3; checked by a test). Written by the author, 30 meant to need a
   question (the missing piece is in neither the shown context nor reachable by a lookup the context lists) and 30 meant not to (the piece is in the context or can be looked up). The author's intent is
   stored beside the sheet and is NOT the label: the Architect labels, and the agreement between his labels and the author's intent is reported afterwards as a description of the author, not as a score.
2. **The context is the builder's own**: every state is data (earlier chat, tools waiting for approval, standing rules, memories, file names, tool names) and the sheet and the runs use
   `judge_context.build(...)` of that data. In the markdown sheet a line break of that text is written as the single character U+23CE; the runner turns it back before the judge sees it.
3. **Labels**: Q axis only (ask for missing information? Y / N / ?). The C axis is not asked; every C is recorded as `?`. Labels are sealed by hash before any model runs (`rct7_holdout_twoaxis seal`).
4. **Runs**: the plain judge and the context judge, once each per model, same rule as H3 (a repeat needs `--again` and is marked). Models: the ones that ran set 3 (qwen3:8b, qwen2.5:7b) and later a capable model.
5. **Rules, registered now**:
   * H3 rule again: the context judge counts as better only if its false stops are lower by at least 2 items AND its found count is lower by at most 1.
   * The original rule (found >= 0.80 and false stops <= 0.15 on Q) is reported beside it.
   * Nothing is wired as a default on any outcome of local models alone (the switch stays an environment variable of the host).
6. **Not claimed**: that the product's judge stops less in use; that a model other than the ones run does the same; anything about axis C.
