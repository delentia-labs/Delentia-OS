# Thai tool menu, Amendment 6 (2026-11-16): R3 becomes the default (the Architect's decision), written before the default was changed

## 1. The decision
The model test (`research/results_round115/R3_MODEL_TEST_RESULT.md`, register entry R0110) met all five rules of Amendment 5 with haiku: Thai first-tool right 0 -> 48 of 89, English 38 -> 39 of 44, false use of an external tool on 20 Thai requests that need none 0 -> 2 (the limit), no unreadable reply. The Architect read the result, the cost (about 20 tokens per connected external tool, about 20 more tokens per decision and a small rise in reaching for a connected tool when a request mentions the same subject) and decided on 2026-11-16: **agreed that R3 is the default.**

## 2. What changes
* `DELENTIA_TOOL_MENU_KEEP_EXTERNAL` unset now means **on** (every connected external tool stays in the ranked menu while there are at most `DELENTIA_TOOL_MENU_KEEP_EXTERNAL_MAX`, default 40; above that, ranking as before). `off` restores the old menu exactly. Any other value of the variable is read as on only when it is `on`; `off`, `0`, `false`, `no` turn it off, an unreadable value falls back to the default (on).
* The setting joins `results_register.CONFIG_ENV`, so every registered result records whether it was on (an entry made before this change records nothing for it, which means it was off).
* A new test fails on the previous code (the default menu of a Thai request contains the external tools); the previous tests that pinned 'off by default' are rewritten to name `off` explicitly.
* The two other candidates (T1 table, A1 hints) stay off and are not part of this change.

## 3. What is checked before it is merged
The tests of the menu, of the external-tool paths and of the research harness; the offline numbers of Amendment 4 (presence 100%, tokens 748 with 19 external tools) are re-run with the default and must be equal to the explicit `on` run; `off` equals the menu of the previous release for every request in all sets.

## 4. Known costs, stated so they are not found later
The menu is larger on every request when external tools are connected, including requests that need none; the model sometimes reaches for a connected tool when a request mentions notes or a calendar without needing it; a set of more than 40 external tools falls back to ranking, and then Thai requests are again not matched to English-described tools. A person with many external tools can lower `..._MAX` or set `off`.
