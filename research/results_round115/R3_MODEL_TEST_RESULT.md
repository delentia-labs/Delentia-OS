# R3 against today's menu with a real model (2026-11-16; anthropic/claude-haiku-5.5; 306 decisions; nothing executed)

Criteria: `research/THAI_TOOL_MENU_AMENDMENT_5_R115.md` (written before the script). Script `research/tool_choice_r3_r115.py`, run at commit b96ee761 under freeze `freeze-r3-W.json` (budget and key limit 0.25, `data_collection=deny`, `require_parameters` unset). Provider usage reported by the script: $0.1203 in 1,110 s (the estimate was $0.0842, $0.1262 with margin). Rows: `r3_model_test_haiku_rows.json`.

| set | arm | right | finished without a tool | wrong tool | other | median menu |
|---|---|---|---|---|---|---|
| 89 Thai sentences | today | **0** | 40 | 49 | | 10 tools |
| 89 Thai sentences | R3 | **48** (53.9%) | 5 | 36 | | 29 tools |
| 44 English goals | today | 38 | 3 | 3 | | 11 tools |
| 44 English goals | R3 | 39 | 3 | 2 | | 25 tools |
| 20 Thai requests that need no external tool | today | 20 ok | | | external tool used: 0 | 11 tools |
| 20 Thai requests that need no external tool | R3 | 18 ok | | | **external tool used: 2** | 30 tools |

Paired over all 153 goals: right (or ok) in R3 and not in today 51, the other way round 4. No error and no unparsed reply in either arm.

Rule (written before the run), all five hold: Thai gain at least 15 points: **+53.9** pass; English within 1 goal: R3 is 1 goal better, pass; false use at most 2 more: **2 more, at the limit**, pass; errors plus unparsed at most 10% per arm: 0%, pass; within the ceiling: pass. **The model test supports R3.**

Read after the run (descriptive, not part of the rule):
* By wording, R3 right on the Thai sentences: literal 13 of 21 (62%), synonym 27 of 48 (56%), indirect 8 of 20 (40%).
* Of the 36 wrong first choices with R3, 25 chose another tool of the RIGHT server (mostly `notes__list_notes` before reading, writing or deleting a note by title: looking first), 8 chose a built-in tool (`delentia_ask_user` twice, `delentia_recall` twice and others), 3 chose a tool of another server. So the right server was reached in 73 of 89 sentences (82%); the strict first-tool score counts a look-first as wrong.
* The two false uses: a request to summarise a book it read yesterday went to `notes__list_notes`, and a question about this year's public holidays went to `calendar__list_events`: the model reaches for a connected tool when the request mentions notes or a calendar.
* Today's arm has 0 right because the needed tool is not in its menu; 40 of its replies finished without calling a tool (asked or answered directly).

Limits: one model, one decision per goal at the loop's default temperature (a difference of a few goals is noise; the false-use count is exactly at its limit), synthetic tools, sentences written by the assistant and ticked by the Architect, a strict first-tool score, and no tool was run, so whether the job is then done is not measured. The cost of R3 is paid on every request (about 20 tokens per external tool); the usage above is higher than my estimate because the R3 prompts are larger. Turning it on by default is the Architect's decision.
