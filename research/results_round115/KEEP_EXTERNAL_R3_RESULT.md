# Candidate R3: connected external tools always in the ranked menu (2026-11-16; free, offline, tiktoken; compact menu format)

Criteria: `research/THAI_TOOL_MENU_AMENDMENT_4_R115.md` (written before the code). Script `research/tool_menu_keep_external_eval_r115.py`; report `keep_external_r3_report.json`. Switch `DELENTIA_TOOL_MENU_KEEP_EXTERNAL=on` (maximum `..._MAX`, default 40), off by default.

| set | all needed tools in the menu: today | R3 | mean menu tokens today -> R3 |
|---|---|---|---|
| development, Thai (119) | 0.0% | **100.0%** | 370 -> 748 |
| second form, Thai (89) | 0.0% | **100.0%** | 416 -> 795 |
| English external goals (44) | 95.5% | **100.0%** | 333 -> 607 |

Scaling of the cost with the number of connected external tools (development sentences, compact format): 5 tools 463 tokens, 10 tools 565, 19 tools 748, 40 tools 1,241 (the default maximum), against 370 for today's ranked menu and 8,520 for the full menu in the full format. About 20 tokens per external tool; listing them all would cost as much as the full menu at about 400 external tools, so the default maximum of 40 is the binding limit, not the cost.

Guards: built-in dev recall 100% -> 100%, built-in holdout 96.8% -> 96.8%. With the switch off, or with more external tools than the maximum, the menu equals today's (tests: `test_keep_external_round115_real.py`, 7 tests, all fail on the old code).

Rule for proposing (written before the numbers): presence at least 95% on all three sets pass, tokens with 19 external tools at most 2,500 pass (748), built-in recall not lower pass. **R3 is proposed**, with the limits stated in the amendment: presence is 100% by construction (so this is a cost test, not an accuracy test); the cost is paid on every request, including requests that need no external tool; a server set above the maximum falls back to ranking and the Thai problem returns there; nothing was run with a model, so whether a model does a job better or worse with a menu of about 27 tools is not measured (the measured benefit of the ranked menu in P1b compared 8 tools with 40). Turning it on by default changes what every model is shown, so that is the Architect's decision.
