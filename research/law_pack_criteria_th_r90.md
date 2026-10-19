# Law Pack with the OFFICIAL-LANGUAGE text — Thai questions against Thai statute text (Round 90, 2026-10-19). Criteria written BEFORE any retrieval or answer was run on it.

**Why.** Round 89 asked Thai questions against an English translation, and the 8B reader failed on questions whose passage was in front of it ("not found in the supplied text" when it was). Two things were mixed: the language gap and the reader's strength. This run removes the language gap.

**The text.** The Thai text of the Personal Data Protection Act B.E. 2562 as transcribed on th.wikisource.org (revision 195183, fetched 2026-10-19 by `scripts/fetch_thai_pdpa_r90.py`; the Royal Gazette site refuses scripted downloads, so the Gazette PDF was NOT used and the transcription has not been compared with it). 96 sections, all present, Thai numerals normalised to ASCII digits on import. It is the Act AS ENACTED on 27 May 2019. It does NOT contain: the royal decrees that postponed enforcement (so the 1 June 2022 date is not in it), the PDPC notifications (e.g. the 16 July 2026 notification on access requests, effective 14 September 2026), the BCR regulation of February 2026, or the draft amendment that was in public consultation from 16 July to 15 August 2026 (found by web search on 2026-10-19; not read from the primary source). A pack is a snapshot; its edition is shown with every answer.

## Data
* **thai-fresh** — 10 fact questions and 2 false-premise traps written on 2026-10-19 from the Thai text before anything was run (`research/law_pack_questions_th_r90.py`), plus **2 currency traps**: questions about instruments newer than the statute (the 2026 notification; the 2026 draft amendment) whose correct answer from this pack is "not in the supplied text".
* **dev-th** and **validation-th** — the 12 + 12 questions of Rounds 88/89, asked now against the Thai text (their gold sections are the same Act). They were seen before, so they are comparison data, not held out.

## Retrieval: A0 only
The embedding of the question (bge-m3), top-5 passages of 900 characters (overlap 150). Round 89 found the other arms (section-number cue, translation, BM25, store-time questions) not helpful.

## Pass rule (fixed now) — on **thai-fresh** only
1. **Retrieval:** hit@5 = 10 of 10 fact questions.
2. **Answers (keyword grader, as before):** facts >= 9 of 10 AND traps (false premise + currency) 4 of 4, with qwen3:8b (thinking off).
3. **Number check:** no fixture with an invented number passes (tests exist); `grounded` is reported separately and is NOT part of the pass rule.
If retrieval is 10/10 and facts are below 9/10, the finding is "the 8B reader is the limit even in one language".

## Comparison (reported, no pass rule)
Thai text vs English translation on the same 24 Round 88/89 questions: hit@5, keyword-graded facts, traps.

## Limits stated in advance
Small sets; keyword grading (false negatives for synonyms; false positives for lucky words); one run per question; a volunteer transcription; one statute; a local 8B model on CPU; the author's own ground truth read from the text. Nothing here is legal advice and none of it shows that the system "knows the law".

## Result of the first Thai run, and the second set (section added before the second set or arm A5 was run)
**First set (thai-fresh, A0), pass rule NOT met:** retrieval hit@5 8 of 10 (H02 "how much may be collected" and H03 "how the data must be kept" are one-sentence sections s.22 and s.35 that the embedding ranked below long multi-topic sections), keyword-graded facts 8 of 10, traps 4 of 4 (both currency traps answered "not in the supplied text").

**Hypothesis:** a character-trigram BM25 ranking of the question, fused with the embedding ranking (arm **A5**), lifts one-sentence sections whose wording the question repeats, without losing the long ones.
**Second set (thai-fresh2):** 10 fact/list questions + 2 false-premise traps + 1 currency trap, `research/law_pack_questions_th_r90b.py`, written now. The first Thai set, dev and validation are development data for A5 (A5 must not do worse than A0 on their retrieval hit@5 before the second set is run); the second set is run ONCE with A0 and A5.
**Success for the hypothesis:** A5 hit@5 >= A0 hit@5 on thai-fresh2 and A5 facts >= A0 facts, with traps equal. **Success for the claim** stays the Round 89 threshold: hit@5 >= 9 of 10 and facts >= 9 of 10 and all traps, on a set the arm was not tuned on.
