// Run with: npm run test:sessionfilter
import assert from "node:assert/strict";
import { isNoModelAttempt, splitSessions, hiddenLabel, NO_MODEL_REASONS } from "./session-filter.ts";
import { knownReasons } from "./reason-text.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };
const list = [{ id: 1, stopped_reason: "llm_finished" }, { id: 2, stopped_reason: "model_not_running" }, { id: 3, stopped_reason: "llm_error" }, { id: 4, stopped_reason: "pending_approval" }];

test("attempts that never reached a model are recognised", () => {
  assert.ok(isNoModelAttempt("model_not_running") && isNoModelAttempt("llm_error"));
  assert.ok(!isNoModelAttempt("llm_finished") && !isNoModelAttempt(null) && !isNoModelAttempt(undefined) && !isNoModelAttempt("fdia_blocked"));
});
test("by default they are hidden and counted", () => {
  const r = splitSessions(list, false);
  assert.deepEqual(r.visible.map((s) => s.id), [1, 4]);
  assert.equal(r.hiddenCount, 2);
});
test("with the switch on nothing is hidden", () => {
  const r = splitSessions(list, true);
  assert.equal(r.visible.length, 4);
  assert.equal(r.hiddenCount, 0);
});
test("a selected session stays visible even when it would be hidden", () => {
  const r = splitSessions(list, false, 2);
  assert.deepEqual(r.visible.map((s) => s.id), [1, 2, 4]);
  assert.equal(r.hiddenCount, 1);
});
test("the input is not changed (nothing is deleted)", () => {
  const copy = JSON.stringify(list);
  splitSessions(list, false);
  assert.equal(JSON.stringify(list), copy);
});
test("every hidden reason is a reason the Desk knows", () => {
  for (const r of NO_MODEL_REASONS) assert.ok(knownReasons().includes(r), r);
});
test("the labels exist in both languages and say the count", () => {
  assert.match(hiddenLabel(3, false, "en"), /3 more attempts/);
  assert.match(hiddenLabel(1, false, "en"), /1 more attempt where/);
  assert.match(hiddenLabel(3, false, "th"), /3/);
  assert.match(hiddenLabel(3, false, "th"), /[\u0E00-\u0E7F]/);
  assert.ok(hiddenLabel(0, true, "en") && hiddenLabel(0, true, "th"));
});
console.log(n + " tests passed");
