# Thai tool menu, Amendment 4 (2026-11-16): candidate R3, 'an external tool the owner connected is always in the menu' (written before R3 was built or measured)

## 1. Why a fourth candidate, and what kind of test it is
T1 (66.3%), E1 (44.9%) and A1 (43.8%) all tried to GUESS, from a Thai request, which English-described external tool is meant, and none met the pre-registered rule (70% of sentences with every needed tool, and few false additions). The failure is the same each time: a request with no domain noun or word in common with the tool cannot be matched by words, and a model-written bridge adds noise. R3 does not guess: an external tool is one the owner chose to connect, usually a handful, and the tokens of listing them are small next to the full menu. It is language independent, so it also fixes Thai written with English tool names and any other language.

R3 is not an accuracy test: by construction every needed external tool is present, so the question is COST. This amendment fixes the cost rule before the numbers are seen.

## 2. The rule
After the ranked menu is chosen (today's rule, unchanged), when `DELENTIA_TOOL_MENU_KEEP_EXTERNAL=on` and the number of external tools (names that start with `mcp__`) is at most `DELENTIA_TOOL_MENU_KEEP_EXTERNAL_MAX` (default 40), every external tool is added to the menu. With more than the maximum, or with the switch off (default), the menu is exactly today's. Built-in tools are ranked exactly as today.

## 3. What is measured (free, offline, the real ranking and format code, tiktoken)
On the 119 development sentences and the 89 second-form sentences, and on the English external goals: (a) the share with every needed tool in the menu; (b) mean tokens of the menu in the compact format the loop sends by default, for today's ranked menu, for R3, and for the full menu; (c) the same token figure when the number of external tools is 5, 10, 19 and 40 (the first n synthetic tools, in file order) so the scaling is visible; (d) the guards: built-in recall on the built-in dev and holdout sets must not fall.

## 4. Rule for proposing R3 (all)
1. (a) is at least 95% on both Thai sets and on the English goals (the two misses of the English set were read tools that today's ranking dropped).
2. With the 19 synthetic external tools, mean menu tokens at most 2,500 (about a third of the 7,900-token full menu measured in Round 94).
3. Built-in recall on the built-in dev and holdout sets does not fall.
4. A test shows that with the switch off, and with more external tools than the maximum, the menu equals today's menu.

## 5. Reported whatever the result
The token table of section 3c and the break-even: the number of external tools above which listing them all costs more than the whole full menu does. The cost of this rule is paid on every request, including requests that need no external tool; a server with many tools (more than the maximum) falls back to ranking, where the Thai problem remains. Nothing is run with a model; whether a model does a job better with the bigger menu is not measured here. If R3 meets the rule it is not turned on by default by me: it changes what every model is shown, so the default is the Architect's decision.
