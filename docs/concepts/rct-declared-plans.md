# Declared RCT planning context (experimental)

This opt-in CLI/API contract path accepts an inspectable plan from the user. It validates structure and references, retains provenance and asks for missing critical input **before any model/tool execution**. It is not an automatic semantic decomposition engine, a truth oracle or complete RCT-7.

A `planning_context` needs explicit `acceptance_criteria`. It has schema version1, reported `facts` (`id`, `text`, `source`), `unknowns` (`id`, `question`, `critical`, optional `answer`), `assumptions` and `components`. Each component has `id`, `action` (`read`, `transform_answer`, `compare`), `description`, `input_facts`, `requires` (unknown ids), `outputs`, `depends_on` and `criteria` (C1… assigned by the contract). Every criterion must have a component. Duplicate ids, dangling references, cycles, undeclared authority fields and unsupported schemas fail closed. Stored contract payload schema remains1; the enriched plan is `plan_schema_version: 2`.

```json
{
  "schema_version": 1,
  "facts": [{"id": "quote", "text": "ราคา 12,500 บาท", "source": "user-provided synthetic quote"}],
  "unknowns": [{"id": "budget", "question": "งบสูงสุดกี่บาท?", "critical": true}],
  "assumptions": ["ราคาใช้สกุลเงินบาท"],
  "components": [{
    "id": "compare", "action": "compare", "description": "เทียบราคากับงบที่ยืนยัน",
    "input_facts": ["quote"], "requires": ["budget"], "outputs": ["คำตอบภาษาไทย"],
    "criteria": ["C1"]
  }]
}
```

Use that context with a C1 criterion `{"kind":"language","value":"th"}`. Context source text is user-reported data, not independently verified fact or new tool authority. This schema cannot add tools, bypass policy or grant signatures. Existing default/legacy RCT prompt planning remains unchanged.

## CLI

```bash
delentia agent 'เทียบราคากับงบและตอบภาษาไทย' --namespace owner \
  --criteria-file criteria.json --planning-context-file context.json
# waiting_for_input: no model or tools called, exit1 is an expected wait
# answers.json: {"budget":"15,000 บาท"}
delentia intent-contract continue ACTUAL_ID --namespace owner \
  --version ACTUAL_VERSION --answers-file answers.json
```

A CLI callback prints the revised plan before execution. `show`/`export` expose the original goal, declared graph, answers and revision provenance under the namespace. Exports contain personal text and must stay private.

## HTTP

`POST /v1/agent/run` accepts `goal`, `acceptance_criteria` and `planning_context`. Critical unanswered unknowns persist `waiting_for_input`; ordinary preparation still returns `plan_ready`. GET the existing contract endpoint after restart to inspect the wait.

POST `/v1/agent/intent-contracts/{id}/continue` with the current integer `version` and `answers: {"budget":"15,000 บาท"}`. Every critical unknown id needs a nonempty bounded answer; freeform `response: "looks good"`, missing/extra ids and stale versions cannot resolve the input gate. Answers are recorded as confirmed user input, not a model's success claim. This HTTP call returns the revised `plan_ready` without a model call. A separate continue request starts it. Noncritical unknowns remain visible without blocking. Existing post-result mismatch clarification still uses `response` and preserves the original intent.

Revisions cannot silently invent components for new criteria. A declared graph that no longer covers the selected criteria must be revised through a future planning-context revision facility; it currently fails structural validation. Crashed `running` contracts still require reconciliation and never auto-reset by timeout.

## Recover compressed evidence

`delentia_expand_tool_output` is now permitted in the read-only contract menu. The governed pre-dispatch gate requires both namespace ownership in the store and an original id actually issued by compression in the **current episode**. Another person's id or a same-person previous episode id is refused before dispatch. Read the source again in the new episode rather than treating an old id as authority. Expanded output is not compressed again.

This guarantee belongs to the governed dispatch boundary; the raw owner MCP tool remains a separate trust boundary, as described in the gate-properties document. No effect/approval tools were added to contracts. The real-MCP regression recovers an omitted Thai passage and exact price while source bytes remain unchanged.

## What this advances and what remains

R1 evidence categories, R3 component/dependency structure, R4 criterion→component→inputs/prerequisites and R5 initial critical-input wait are now observable for declared plans. Tests change declared output/components while keeping reported facts constant. They do **not** prove the runtime autonomously derives a correct semantic plan from every natural-language goal. R6 visibility is scoped to these CLI/API flows; R7 predicates remain limited. Signed effects, crash reconciliation, broader entry points, capable-model development and formal value evaluation remain separate gates.
