// Run with: npm run test:reason  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { describeReason, knownReasons } from "./reason-text.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

// Every stopped_reason the runtime can produce (collected from rct_control_plane by grep, Round 101).
const RUNTIME = ["llm_finished", "warm_recall", "pending_approval", "plan_ready", "needs_clarification", "waiting_for_clarification", "waiting_for_input", "fdia_blocked", "guard_blocked",
  "jury_rejected", "intent_constraint_blocked", "notary_unavailable", "residency_blocked", "budget_exceeded", "daily_budget_exhausted", "rate_limited", "paused", "stuck_repeating",
  "max_iterations_reached", "max_seconds_exceeded", "parse_error", "llm_error", "exception", "nesting_limit", "delegation_depth_exceeded", "running", "interrupted"];

test("every code the runtime can produce has a text in both languages", () => {
  for (const code of RUNTIME) {
    for (const lang of ["th", "en"]) {
      const t = describeReason(code, lang);
      assert.ok(t.label && t.what && t.next, `${code}/${lang}`);
      assert.notEqual(t.label, code, `${code}/${lang}: the label must not be the raw code`);
    }
  }
});
test("no text in the table is for a code the runtime does not produce", () => {
  assert.deepEqual(knownReasons().filter((c) => !RUNTIME.includes(c)), []);
});
test("a Thai text contains Thai and an English text does not", () => {
  for (const code of RUNTIME) {
    assert.match(describeReason(code, "th").what, /[฀-๿]/, code);
    assert.doesNotMatch(describeReason(code, "en").what, /[฀-๿]/, code);
  }
});
test("a state that needs the person is amber, a refusal is rust, finishing is leaf", () => {
  assert.equal(describeReason("pending_approval").tone, "amber");
  assert.equal(describeReason("fdia_blocked").tone, "rust");
  assert.equal(describeReason("llm_finished").tone, "leaf");
});
test("an unknown code is shown as reported with a neutral sentence, never hidden", () => {
  const t = describeReason("some_future_reason", "en");
  assert.equal(t.label, "some_future_reason");
  assert.equal(t.tone, "muted");
  assert.equal(describeReason(null, "th").label, "ไม่ทราบ");
});
test("what the text says to do never asks the person to type a command", () => {
  for (const code of RUNTIME) for (const lang of ["th", "en"]) assert.doesNotMatch(describeReason(code, lang).next, /delentia |python |--/);
});
console.log(`${n} tests passed`);
