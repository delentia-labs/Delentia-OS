# Law Pack, third fresh Thai set (Round 91). Criteria written BEFORE any retrieval or answer was run on it.

**Question.** Rounds 89-90 left the pass rule unmet with a local 8B reader (retrieval 8-10 of 10, keyword-graded facts 5-8 of 10 on the Thai text). Is that a property of the system, of the earlier question sets, or of the reader? This third set (10 facts/lists, 3 traps; `research/law_pack_questions_th_r91.py`) uses sections none of the earlier sets used.

**Text.** The same pack as Round 90 (th.wikisource revision 195183, imported with `delentia law import ... --allow-flagged` after the nine flagged places were read: ordinary statutory phrases such as "ปิด ... คำสั่ง" and "ทำลายข้อมูล"). Not compared with the Royal Gazette.

**Run.** Retrieval arm A0 only (the shipping arm), bge-m3, top 5 passages; reader qwen3:8b through Ollama with thinking off (`DELENTIA_OLLAMA_THINK=off`); one run per question; the answer grader is the keyword grader of Round 90 (`research/law_pack_measure_r89.py`), and I ALSO read every answer myself and report both.

## Pass rule (fixed now; the same as Round 90)
1. Retrieval: hit@5 = 10 of 10 on the 10 fact/list questions.
2. Answers: facts >= 9 of 10 by the keyword grader AND traps 3 of 3.
If retrieval is >= 9 of 10 and facts are below 9, the finding is that the reader is the limit.

## What the result may be used for
A reading of THIS pack and THIS reader on THIS kind of question. It is not "the system knows the law" and not a comparison with another reader: that needs the capable-model run (a key and a prepaid cap, the Architect's).

## Limits stated in advance
Thirteen questions; one run each; a volunteer transcription; one statute; keyword grading; the author's own ground truth. The three earlier sets were development data for the retrieval arms; this one is not tuned on.
