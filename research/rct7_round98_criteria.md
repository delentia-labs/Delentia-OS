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
