// Run with: npm run test:nav  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { GROUPS, SIMPLE, allItems, groupOf, parseMode } from "./nav-model.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

// The 27 pages of the flat menu before the regrouping (Status is always shown on its own and is not part of a group).
const BEFORE = ["/chat", "/sessions", "/subagents", "/growth", "/memory", "/algorithms", "/governance", "/fdia", "/forge", "/hooks", "/learning", "/law", "/safety",
  "/approvals", "/signatures", "/checkpoints", "/identity", "/sovereignty", "/jitna", "/audit", "/llm", "/skills", "/tools", "/cron", "/channels", "/experiments"];

test("every page of the old menu is still reachable, exactly once", () => {
  const now = allItems().map((i) => i.href).sort();
  assert.deepEqual(now, [...BEFORE].sort());
  assert.equal(new Set(now).size, now.length);
});
test("five groups, none empty", () => {
  assert.equal(GROUPS.length, 5);
  assert.ok(GROUPS.every((g) => g.items.length > 0));
});
test("Simple mode only lists pages that exist in the full menu, and keeps approvals", () => {
  const all = new Set(allItems().map((i) => i.href));
  assert.ok(SIMPLE.every((i) => all.has(i.href)));
  assert.ok(SIMPLE.some((i) => i.href === "/approvals"));      // nothing about control is hidden in Simple mode
  assert.ok(SIMPLE.length < 8);
});
test("a path finds its group, including pages below it", () => {
  assert.equal(groupOf("/approvals"), "gates");
  assert.equal(groupOf("/sessions/abc"), "work");
  assert.equal(groupOf("/llm"), "connect");
  assert.equal(groupOf("/"), null);
  assert.equal(groupOf("/settings"), null);
});
test("Simple is the default for anything that is not exactly 'advanced'", () => {
  assert.equal(parseMode(null), "simple");
  assert.equal(parseMode(undefined), "simple");
  assert.equal(parseMode("garbage"), "simple");
  assert.equal(parseMode("advanced"), "advanced");
});
console.log(`${n} tests passed`);
