# Bounded bilingual semantic task planner

Experimental opt-in rules infer task components for **summary** and **budget comparison**, using Thai/English cues in the user goal. This advances beyond predicate-only compilation but is not general semantic RCT-7. Unsupported, negated and mixed supported task requests are rejected before model/tool execution. Pattern matching is not an intent-understanding benchmark.

Use the existing CLI `--criteria-file` and `--planning-context-file` or HTTP `/v1/agent/run` with:

```json
{
  "goal": "เทียบใบเสนอราคากับงบ",
  "acceptance_criteria": [{"kind": "language", "value": "th"}],
  "planning_context": {
    "semantic_plan": {
      "facts": [{"id": "quote", "text": "ราคา 12,500 บาท", "source": "user-provided quote"}]
    }
  }
}
```

No component graph or critical unknown list is supplied by this request. The planner infers inspect_sources → compare_budget → compose_answer → predicate preparations/checks. Summary uses inspect_sources → compose_answer without budget comparison. Missing sources infer a critical source_text question; budget comparison without budget infers a critical budget question. It does not discover every missing amount, currency, tax, conflicting claim or material scope detail.

Initial missing inputs persist waiting_for_input before model/tools. Budget input requires a positive decimal amount (up to 1e15, two decimal places) and an explicit THB/USD/EUR/บาท currency, e.g. `15,000 บาท`, `THB 15000`, `99.50 USD`. Currency conversion, locale-general number parsing, Thai numeral parsing and dollar-symbol disambiguation are not supported. `yes`, `15000`, `0 THB` and `THB 100 USD` do not resolve a budget question. A budget can also be supplied in semantic_plan.budget using the same validation.

Answer through the existing versioned continuation using `answers: {"budget": "15,000 บาท"}`. API returns a revised plan_ready before a later execution request; CLI displays the revised plan before proceeding. Replanning a summary into budget comparison can introduce a new initial-input wait; continuation now handles this state instead of attempting execution. CLI uses exit1 for this expected wait. Original intent and confirmed revisions remain durable. Replanning from the original semantic request conservatively asks again for inputs not present in that request; context/answer reuse across revised goals remains future work.

Plans record planning_origin=bounded_semantic_rules and semantic_planning with:

- ruleset bilingual-summary-budget-1 and selected task;
- classification status rule_inferred, matched cue and original goal SHA-256;
- per-source user_reported status, original id/locator and text SHA-256;
- explicit semantic_completeness=false and limitations.

Source text is not fetched or verified by declaring a locator/hash. It cannot grant tools or approve effects. Confirmation answers retain confirmed_user_input revision provenance, without promoting reported sources to observed evidence. The existing structural validator checks criterion coverage, cycles, references and bounds. Maximum20 source facts/20 criteria produce41 facts and43 components for budget comparison.

The default agent path and read-only fence are unchanged. Final acceptance remains declared predicates plus existing heuristic grounding, **not** an independent oracle proving the budget conclusion. Development regression cases cover bilingual cues, same facts/different goals, critical waits, currency/amount validation, restart, revision, source status and CLI/API ordering. They are not held-out evaluation and establish no semantic accuracy percentage or causal benefit.

The graph is supplied to model context, not executed by a scheduler enforcing per-component completion receipts. Existing tool policy/journaling remains active; binding individual components to actual observations/results is still required before claiming complete plan execution.

See [implementation](../../rct_control_plane/semantic_plan.py), [tests](../../rct_control_plane/tests/test_semantic_plan_real.py), [report and remaining gaps](../development/BOUNDED_SEMANTIC_PLANNER_RESULTS_TH.md) and [integration failure remedies](../development/INTEGRATION_FAILURE_CATALOG_TH.md).
