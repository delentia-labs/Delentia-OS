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
