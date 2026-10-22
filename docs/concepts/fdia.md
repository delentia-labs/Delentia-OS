# FDIA Equation and its runtime interpretations

**FDIA Equation has no approved expanded name.** Its variables are Future, Data, Intent and Architect. The creator's framework and a numeric implementation must be described separately.

$$F = (D^I) \times A$$

## Concept, computation and enforcement

| Layer | Meaning | Evidence required |
|---|---|---|
| Creator's concept | Future as actual outcome; Data as reality, experience and constraints; Intent as clarity, depth and persistence; Architect as the responsible human designer | Creator-confirmed definition and attributed history |
| Computational model | An assessment score using explicit proxies, ranges, transforms and thresholds | Function/version, vectors and calibration; the score is not automatically a probability |
| Execution controls | Policy, delegated authority, signatures and hard restrictions applied before an effect | Actual execution paths and negative/approval/effect tests |

A zero score when A = 0 demonstrates a function property. Preventing an unauthorized effect additionally requires the gate to be applied by the relevant execution path. A passing score cannot lift a forbidden path or replace a required signature.

## Inspect the path before interpreting its numbers

| Path | Inputs and domain | Interpretation and limits |
|---|---|---|
| `governed_autonomous_loop.fdia_score` and `AlgorithmKernel41.algo_01_fdia` | Positive D/I domain guards; clamping, rounding and overflow handling; helpers accept values beyond D = 1 | Numeric gate helpers are not uniformly normalised to 0–1. I ≤ 0 returns zero by an added domain rule. |
| `AlgorithmKernel41.synthesize_fdia_inputs` | Compiler clarity/type/scope and risk/scope bonuses | Goal-derived proxies; a risk bonus is not a measurement of lifelong persistence of intent. |
| `data_evidence.assess` and the governed loop's episode data | Clarity, workspace grounding, relevant memories, skills and verified record | D measures evidence available in this namespace/workspace. Missing evidence is reported. Retrieval may miss relevant data. |
| `_pre_dispatch_gate`, `judge_tool_fdia` and `fdia_policy` | Tool arguments, authority, path/risk rules, taint, owner policy and approval state | A is grounded in declared authority. Trust depends on caller identity, policy/key custody and the paths actually enforcing the gate. |
| `core.fdia.fdia.FDIAScorer` | NPC action ranking with desire, intent compatibility and governance weights | A separate weighted scorer; its enum labels and ranges are not a universal specification of the governed loop. Legacy expanded names in source comments are not the approved name. |

See [numeric/estimator source](../../rct_control_plane/algorithm_kernel_41.py), [episode evidence](../../rct_control_plane/data_evidence.py), [loop gate](../../rct_control_plane/governed_autonomous_loop.py), [owner policy](../../rct_control_plane/fdia_policy.py) and [NPC scorer](../../core/fdia/fdia.py).

## What the exponent means

| Domain/example | Raw equation behaviour, A = 1 |
|---|---|
| 0 < D < 1 | Larger I lowers the score: 0.5^1 = 0.5; 0.5^2 = 0.25. I can represent strictness in this domain. |
| D = 1 | D^I = 1 for defined I; changing I does not affect the score. |
| D > 1 | Larger I increases the score: 2^1 = 2; 2^2 = 4. |
| D > 0, I = 0 | D^0 = 1. Returning zero is an explicit additional rule. |
| A = 0 | The product is zero in the defined domain; enforcement still needs an execution control. |

Do not explain all domains as “more intent always raises the score”. Do not silently change the equation or normalisation to match a narrative. The conceptual framework is not a universal empirical law that predicts future events.

## NPC action-ranking example

```python
from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType

scorer = FDIAScorer(weights=FDIAWeights())
score = scorer.score_action(
    agent_intent=NPCIntentType.DISCOVER,
    action=NPCAction(action_id="a1", action_type="explore"),
    world_resources={"knowledge": 50.0, "energy": 80.0},
    agent_reputation=0.85,
    other_intents=[NPCIntentType.PROTECT],
    governance_penalty=0.0,
)
print(score)
```

This demonstrates the separate NPC API, not authorization for a tool effect. Default weights are configurable; no production-calibration claim is made here.

## Evidence and open questions

The 11/12 hand-written rank cases are a small smoke test, not a benchmark or a calibrated safety accuracy. No accuracy against an “industry 0.65” baseline is claimed. See [core tests](../../core/tests/test_core.py), [FDIA properties](../../tests/hypothesis/test_fdia_properties.py), [gate properties](../../research/GATE_PROPERTIES.md) and [research protocol](../../research/PROTOCOL.md).

Calibration, false rejection, unauthorized effects and comparative value are separate measurements. Keep their domain/model/configuration and failure counts attached to any result. The owner-policy gate does not establish control over a compromised operating system or uninspected maintenance paths.

Related: [RCT-7 requirements](rct-7-thinking.md) · [Current public information](../public/CURRENT_PUBLIC_INFORMATION_EN.md).
