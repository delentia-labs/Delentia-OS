# Thai requests and the ranked tool menu: criteria (2026-11-16, written before any rule or holdout run)

## 1. The defect (measured, `research/results_round115/OWNER_CHOICES_REPORT.md`)
The ranked tool menu scores a tool by words shared between the request and the tool's name and description. A Thai request shares none with an English description, so none of the external tools reached the menu for any of the 119 Thai sentences the Architect ticked (0 of 119 had every needed tool; R1 'keep sibling write tools' changed nothing). The same request in English brings the whole server in. The ranked menu is the default for every provider since 2026-11-13.

## 2. Data roles (fixed now)
* **Development set:** the 119 ticked sentences (`research/tool_menu_owner_choices_r115.json`). They have been seen; the lexicon below is built looking at them. Their result is reported but decides nothing.
* **Holdout set:** a second form with 30 NEW situations and NEW sentences, none equal to or sharing the wording of a development sentence beyond a place name or number, filled in by the Architect before any rule is run on it (`research/tool_menu_owner_holdout_r115.json`, written when he sends it back). Every sentence he ticks is one case; the needed tools are the ones he confirms. Nothing about the rule is changed after the holdout is run.
* **Guards (no judgement needed, run on every candidate):** (a) the 44 English external goals (`tool_menu_external_goals_r114.json`), (b) the built-in dev and holdout sets (`tool_menu_goals_round56.json`), (c) a negative set of 20 Thai requests that need NO external tool (`research/tool_menu_thai_negatives_r115.json`, written now, before the rule).

## 3. Candidate rule T1 (the only candidate that will be built first)
A small fixed lexicon from Thai words to the English tool words they mean (verbs of reading, writing, creating, deleting, updating, moving, drafting, searching, listing; nouns for note, ticket, calendar/event, mail/message, folder, file, and a few more), applied to the request before scoring. It is a table in the code, reviewed by reading it, no model, no network. Switch `DELENTIA_TOOL_MENU_THAI` (default OFF until the Architect decides after the holdout); `on` applies the table, `off` is today's behaviour. English requests and requests with no Thai character are scored exactly as today (a test pins this).
Not built now, because each has a cost the Architect should weigh first: an embedding model that reads Thai (bge-m3: more accurate, but needs Ollama and adds latency per request) and 'show all external tools when nothing matches' (simple, but the menu grows with the number of servers).

## 4. Adoption rule (all must hold on the holdout and the guards; otherwise T1 is not proposed)
1. On the holdout, the share of sentences whose needed tools are ALL in the menu is at least **70%**, and at least **40 percentage points** higher than today's rule on the same sentences.
2. The mean menu grows by at most **3 tools** on the holdout.
3. On the negative set, the mean number of external tools in the menu is at most **1** (a Thai request about something else must not pull a server in).
4. Guards (a) and (b): recall does not fall by more than **1 point** against today's rule.
5. A test shows the table is applied only when the request contains a Thai character.

## 5. What is reported whatever the result
Both sets, the per-kind split (L literal, S synonym, I indirect wording; recorded in the file, never shown to the Architect), every sentence that still misses a needed tool, and the limits: the sentences were written by the assistant (general knowledge, not user data); tools are synthetic with English descriptions; nothing is run with a model, so whether a model then does the job better is not measured; a fixed table covers the words someone thought of, so the holdout is the test of whether it generalises.

## 6. If T1 passes
The result goes to the Architect with its costs (the table needs maintenance; other languages need their own). Turning the switch on by default is his decision, and it changes the default tool menu for Thai requests, so it is registered with the results.
