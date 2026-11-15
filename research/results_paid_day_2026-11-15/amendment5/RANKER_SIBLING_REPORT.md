# Should the ranked tool menu keep the write tools of an external server? (Amendment 5, section 3; free, offline, no model)

Measured 2026-11-15 with `python -m research.tool_menu_siblings_r114` (the real ranking code, menu size 10, 69 tools in the list: 52 built-in plus 17 synthetic tools of four external servers). Goals and the rule were written before the run (`research/tool_menu_external_goals_r114.json`, Amendment 5 section 3). Raw report: `tool_menu_siblings_report.json`.

| set | n | ranked menu: all needed tools present | mean menu | with rule R1 (add the write tools of a server whose read tool is shown) | mean menu |
|---|---|---|---|---|---|
| external goals (written for this) | 44 | 95.5% (42 of 44) | 10.57 | 95.5% | 11.89 |
| built-in dev (existing set) | 36 | 100% | 9.42 | 100% | 9.69 |
| built-in holdout (existing set) | 31 | 96.8% | 8.16 | 96.8% | 8.65 |

**Pre-registered rule: not met.** Recall gain on the external goals 0.0 points (needed at least 10), menu growth 1.32 tools (allowed 2), built-in holdout loss 0.0 points (allowed 1). R1 is therefore **not proposed for adoption**.

What it means, and what it does not:
* On these 44 goals the ranker already kept every needed tool in 42. The two misses (calendar `list_events`, mailbox `search_messages`) are READ tools that fell out of the menu; a rule that adds write siblings cannot help them.
* The W12 defect is real: for the real W12 goal ("... then save the combined result as a note ...") the ranked menu holds `read_note` and not `write_note`, and rule R1 does add it (menu 11 to 15 tools). The reason is wording: "save" does not match the tool description "Write a note". My 44 goals mostly use words that match their tool descriptions, so this set is probably too easy to show the effect; one real counterexample and 44 easy cases are not enough to adopt or reject the rule on the evidence, only to say the pre-registered test did not support it.
* A better test needs goals written by someone other than the author of the rule, with everyday verbs (save, put, record, store, remember) for write tools. That is a task for the Architect's own wording or for outside testers, not something to tune here.
* Nothing about the default menu changed. The W12 runner now forces the full menu, so W12 measures the model and not the menu.
