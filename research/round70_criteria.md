# Round 70: pass criteria, written BEFORE the code or any measurement of the items below (2026-10-11, after Round 69 was pushed)

The product story is "it remembers what you told it to respect and applies it in a new session". Recall of FACTS was measured in Round 69; this round measures recall of CONSTRAINTS: standing rules and preferences
that matter at the moment the agent is about to ACT, where the query is not a question about the rule but the goal that the rule governs ("fix the typo in contracts_signed/nda.pdf" must bring back
"never edit the originals in contracts_signed"). A similarity search is weak at this: the goal and the rule share a topic, not an answer.

## 1. Constraint recall (set H6)
H6 = 40 constraints (24 Thai, 16 English), each with a goal that the constraint governs; 40 near-topic neutral statements (same topic, not a rule) and 120 generic preferences/facts as distractors. Written once, frozen by SHA-256.
Hit = the EXACT constraint text is among the memories returned (top-k of the ranking; and "shown" = what `_recall_for_goal` gives an episode after the relevance floor and the limit of 5).
Measured once per model/mode: lexical matcher alone, nomic-embed-text, bge-m3 (the setting the Architect now runs: DELENTIA_MEMORY_EMBED=auto, bge-m3). Reported with the exact counts and the Wilson interval, per language, and every miss.
Decision rule: if bge-m3 SHOWS at least 36 of 40 (90%) constraints to the episode, recall is enough and nothing is built; otherwise the pinned-constraint mechanism below is built.

## 2. Pinned constraints (built only if section 1 says so)
A person (never the model, never an episode that read outside text) can PIN a memory: `delentia memory add --pin` / `delentia memory pin <id>`. A pinned memory is shown to every episode of that person (at most 5, newest
first, a pinned memory never counts as evidence for D), is revocable, erasable and listed in the Governance view. Pass: (a) on H6 with the constraints pinned, 40 of 40 are shown when there are at most 5 pinned
per person and the first 5 are shown when there are more (nothing else changes for the person who pinned nothing: every older test passes unchanged); (b) D is not raised by a pinned memory for an unrelated goal
(same unrelated-question measurement as Round 69: mean D gain unchanged within 0.002); (c) a pin made by the model or inside a tainted episode is refused; (d) erasing the person destroys the pins.

## 3. Near-duplicate memories (the scale defect of Round 69: top-3 falls by 4-7 of 30 at 1,120 memories)
Consolidation: memories whose cosine is at least 0.97 AND whose normalised texts differ only in digits/names are NOT merged (they are different facts: "vendor A" and "vendor B"); only exact normalised duplicates and
cosine >= 0.985 pairs where one text contains the other are folded: the older is revoked with reason "superseded by <id>" and stays in the log. Pass: on the SCALE set (DEV + 1,000 near-duplicate distractors) top-3 falls by at most 3
from the 120-memory figure; if the distractors are NOT duplicates in this sense nothing is merged and the number is reported as it is (the honest outcome: the defect is ranking among look-alikes, not duplication).

## 4. Regex audit (CodeQL found two ReDoS in our own code in Round 69)
A test imports every module of `rct_control_plane` and runs every module-level compiled pattern against hostile strings (long runs of spaces, digits, dots, '-c ', 'a!' repeated; 20,000 characters) with a time limit of 0.5 s each.
Pass: no pattern exceeds the limit; each that does is bounded and listed.

## 5. Not decided here
Anything that needs the Architect (OpenRouter key, notary OS user, witness, merges, relabelling).
