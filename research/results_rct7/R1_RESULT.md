# RCT-7 stage R-1: result (2026-11-25)

Criteria: `research/RCT7_R1_CRITERIA_R116.md` (committed before the set and any measurement). Set: `research/rct7/r1_goals.py` (80 requests written by the assistant; 60 development, 20 held out by a hash of the id, pinned by digest `66b4dd03...`). Rules frozen at commit `4d25db40`; the held-out 20 were measured once against it. No model.

| | development 60, before | development 60, after (tuned there) | **held out 20, once** | rule (held out) |
|---|---|---|---|---|
| kind of work right | 35 | 60 | **19** | at least 18: met |
| requests with every stated constraint found | 8 of 39 | 38 of 39 | **13 of 15** | at least 12: met |
| constraint kinds reported that were not stated | 0 | 0 | **1** | at most 2: met |
| question read as a change / change read as a question | 0 / 2 | 0 / 0 | **0 / 0** | 0 / 0: met |

**R-1: PASS** (all four rules).

The held-out misses, as they are:
* g58 "Something is wrong with the totals again, can you sort it out? Don't touch the tests." read as TEST instead of DEBUG: the request names no fix verb, only "sort it out"; the word "tests" decides. This is the indirect phrasing the plan expected to miss.
* g62 "... as a markdown file named RELEASE_TH.md": the artifact phrased "a file named X" is not read (only "save it as X" and "write the result to X" are).
* g71 "do not change the DNS settings": a protected setting that is neither a file nor one of the categories (tests, configuration, code) is not read.
* g14 "converts CSV invoices to JSON and save it as tools/csv2json.py": "to JSON" describes what the tool does, and was read as a format the answer must have (1 invented kind). A JSON-format requirement is checked against the answer, so in a live run this could stop an episode whose answer is plain prose; to be fixed before R-2 relies on it (format read only when it is about the answer: "answer in JSON", "return ... as JSON", not "a tool that converts ... to JSON").

Stated limits: the labels are the assistant's, not independent; 20 held-out requests give coarse intervals (19 of 20: 95% interval about 75-99%); English and Thai only; nothing here shows that a model plans better or that a task succeeds more often (that is R-3).
