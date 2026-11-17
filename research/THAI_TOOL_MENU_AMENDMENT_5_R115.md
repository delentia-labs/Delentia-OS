# Thai tool menu, Amendment 5 (2026-11-16): a real model chooses a tool from today's menu and from the R3 menu (criteria written before the script or any call)

## 1. Question
R3 keeps every connected external tool in the ranked menu. The offline test showed that it costs about 20 tokens per external tool and that every needed tool is present. It did not show whether a real model, given a menu of about 27 tools instead of about 8 to 10, still picks the right first tool, and whether it starts reaching for external tools when the request does not need them. That is what this test measures. Nothing is executed: one decision per goal and arm, using the loop's real prompt (`autonomous_loop.decide_next_action`), as `scripts/measure_tool_choice.py` does.

## 2. Design (fixed now)
* **Model:** `anthropic/claude-haiku-5.5`, through OpenRouter with `data_collection=deny`, `require_parameters` unset, one fresh key with a credit limit, the freeze file for the run (every real call asks the freeze first). One model: the result says nothing about other models.
* **Tools:** the runtime's built-in tools plus the 19 synthetic external tools (notes, tickets, calendar, mailbox) with their English descriptions, the same list as the offline measurements. Nothing is executed.
* **Arms (same menu format, compact, top 10):** `today` = ranked menu as shipped (`DELENTIA_TOOL_MENU_KEEP_EXTERNAL` off); `r3` = the same with it on.
* **Goal sets, one decision per goal and arm, goals in a fixed order, the two arms for a goal one after the other:**
  1. the 89 Thai sentences the Architect ticked in the second form (`tool_menu_owner_holdout_r115.json`), each with the tools the situation needs: scored 'right' when the first tool called is one of the needed tools;
  2. the 44 English external goals (`tool_menu_external_goals_r114.json`), the guard: scored the same way;
  3. the 20 Thai requests of the third negative set (`tool_menu_thai_negatives3_r115.json`) that need NO external tool: scored 'false use' when the first tool called is an external one.
* **Scoring of a reply:** 'right' (first tool, or any tool of a batch, is in the needed set), 'wrong tool', 'finished without a tool', 'unparsed', 'error'. A multi-tool situation counts as right when the first call is one of the needed tools (reading before writing is right).
* **Cost ceiling:** the key's credit limit and `--budget-usd` are 0.25; the script stops at 90% of the budget by the provider's own usage figure. Expected cost about $0.08 (306 calls of about 2,000 tokens at $0.10 and $0.50 per million).

## 3. Rule (all must hold for 'the model test supports R3'; otherwise R3 is not recommended, whatever the offline result)
1. On the 89 Thai sentences, `r3` right is at least **15 percentage points** above `today`.
2. On the 44 English goals, `r3` right is within **1 goal** of `today` (no harm where `today` already works).
3. On the 20 negatives, `r3` false use is at most **2 goals** more than `today`.
4. In each arm, errors plus unparsed replies are at most **10%** of the goals; otherwise the comparison is inconclusive, not a pass.
5. The run stays within the ceiling.

## 4. Reported whatever the result
Counts per arm and set with the kinds of miss; the sentences each arm got wrong; the paired changes (goals right in one arm and wrong in the other, both directions); the tokens and cost per arm from the provider's usage. Limits: one model, one decision per goal at the loop's default temperature (a difference of a few goals is noise), synthetic tools, sentences written by the assistant and ticked by the Architect, and no tool is run, so whether the job is then done is not measured. If the model test supports R3, enabling it by default is still the Architect's decision.
