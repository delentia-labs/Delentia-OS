# RCT-7 R1/R5 with a model as the judge: criteria written BEFORE the first run (2026-10-24)

Question: the rules of round 97 see only what the request's words show (a named file that does not exist, a bare "fix it"). The creator's R1 asks for what is NOT known and R5 for
asking when the intent is unclear. A rule cannot judge "which report?". Can a language model, used ONLY as a proposer of questions, do it, and how small can it be?

## What is measured
Two roles are separate and must not be confused:
* **judge role**: given one request (no tools, no workspace), say whether it is clear enough to act on, and if not, what is unknown. This probe measures only this role.
* **driver role**: choose tools and finish tasks. Not measured here (K.1.5, the DAAES live tasks and the 12 master workflows measure it).

## Cases
`research/rct7_model_judge_cases.py`: 20 requests with a planted unknown or ambiguity, 20 clear requests. Written by the author of the probe, so this is the DEV set: it may be used to fix the
prompt at most twice (each change is logged in the result file), and its numbers are never a claim. Only a HOLDOUT of at least 40 requests labelled by someone other than the author counts.

## Rules (fixed before running)
* The model may only PROPOSE: the output is a list of questions. It never skips a gate, never sets a requirement, never answers on the person's behalf, and its text is shown as the system's
  question, not as fact. A model-proposed stop is a guess, so it needs the false-pause bound below.
* Output format: JSON `{"clear": true|false, "unknowns": ["..."]}`. Anything else counts as a miss for an unclear request and as clear for a clear one (no stop on a malformed reply).
* Pass for adoption as an opt-in: on the holdout, recall of planted unknowns >= 0.80 AND false pauses <= 0.15 of the clear requests, for the same model, two runs agreeing within 2 cases.
* Below that, the model is not used as a judge, and the report says "not met" with the numbers.
* The result is per model and per prompt; vendors are never pooled.

## Not claimed
That any score here says a model understands intent. It says how often a model's flag agreed with one author's labels on short requests.
