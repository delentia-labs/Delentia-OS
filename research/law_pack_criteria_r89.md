# Law Pack v0 — criteria written BEFORE the code or the fresh questions were run (Round 89, 2026-10-18)

**Question.** Can "the system knows country X's law" be made true in a way a person can check, by letting the owner supply the statute text and having the system retrieve, cite and check the numbers it quotes?

**What it is not.** Not legal advice. Not knowledge inside any model. The statute text is supplied by the owner (here: an unofficial English translation of the Thai Personal Data Protection Act B.E. 2562, a PDF the repository does not ship). Nothing is learned into a model's weights; nothing becomes a skill or a warm answer.

## Data
* **dev** = the 12 questions of `research/national_law_probe_r88.py` (seen: Round 88's results were read, and the retrieval was changed after looking at them, so they are development data).
* **validation** = 12 NEW Thai questions in `research/law_pack_questions_r89.py` (10 facts, 2 traps), with required keywords and the gold section written down in the same file before any retrieval or answer was run on them. Ground truth is my reading of the same translation, not a lawyer's.

## Arms (retrieval only; the answering model and prompt are the same in every arm)
* **A0** the Round 88 pipeline: embed the Thai question with bge-m3, top-5 chunks of 900 characters (overlap 150).
* **A1** A0 + a section-number cue: a question that names a section ("มาตรา 37") gets the chunks of that section first.
* **A2** A1 + the question translated to English by the local model, embedded as well, each chunk scored by the larger cosine.
* **A3** A2 + a lexical score (BM25 over word tokens) between the translated question and the chunk, fused by rank.
The configuration that ships is chosen **on dev only**. Validation is then run once with the chosen configuration and once with A0 for reference. Nothing is tuned after the validation numbers are seen; anything changed afterwards is reported as development data.

## Measures
1. **Retrieval hit@5**: the gold section is among the top-5 chunks' sections (validation, dev).
2. **Answer correct**: the keyword rule of the question (facts: every required group has one alternative; lists: at least `min_of` items; traps: the answer says the premise is false or that the section is not in the supplied text).
3. **Number check** (a property of the checker, tested with fixtures): an answer that contains a number (digits, or a spelled-out Thai/English number word) that is not in the cited chunks, the question or a small fixed list (section numbers) is marked `unsupported`; an answer with no citation is marked `uncited`. The label "not from the supplied text" is shown whenever either fires.

## Pass rule (fixed now)
* **Retrieval:** validation hit@5 ≥ 10 of 10 facts for the chosen configuration, or the failure is explained row by row.
* **Answers:** validation facts ≥ 9 of 10 AND traps 2 of 2, with the local model qwen3:8b. If hit@5 is 10/10 and the answers still fall short, the finding is "the 8B reader is the limit", not "the method failed"; a stronger model is then needed to decide, and that needs the Architect's OpenRouter key. No claim of "the system knows the law" is made unless this rule is met on validation.
* **Honesty:** the checker must never mark a fixture with an invented number as supported (fixtures in the test file), and every answer path that returns text must carry the pack name, edition and the sentence "not legal advice".
* **Cost/time:** one answer ≤ 90 s on this CPU machine for A2 (one extra model call for the translation), reported.

## Known limits stated in advance
Twelve questions per set; keyword grading; one run per question; one statute, one language pair (Thai question, English text); a local 8B model; my own ground truth. This can show that the mechanism works on this statute or that it does not; it cannot show a general accuracy.

## Note added before any arm was run
The chunker is the same in every arm and is NOT Round 88's: a heading must start a line and section numbers must count up (Round 88's version split at every inline "Section N", which mislabelled fragments). So A0 here is "Round 88's retrieval over the corrected chunks", not a re-run of Round 88's numbers.
