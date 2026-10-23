// Run with: npm run test:unit  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { deriveRun } from "./run-state.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };
const user = { kind: "user", text: "Read pyproject.toml and tell me the name" };
const tool = (name) => ({ kind: "step", step: { iteration: 1, kind: "tool", tool: name, thinking: "read it", result: "ok" } });
const summary = (extra = {}) => ({ kind: "summary", seconds: 4.2, summary: { stopped_reason: "llm_finished", iterations: 1, route: { path: "FAST", reason: "narrow read" }, verification: { applicable: true, aligned_with_intent: true, similarity_score: 0.4 }, guard: { cord_verdict: "allowed" }, notary: { enabled: true, receipts: 3 }, ...extra }, fdia: { D: 1, I: 1, A: 1, F: 1, signed: true, signature_hash: "abc123" } });

test("nothing happened yet: idle, nothing claimed", () => {
  const r = deriveRun([], false);
  assert.equal(r.mood, "idle");
  assert.equal(r.intent, null);
  assert.ok(r.cycle.every((c) => c.status === "unknown"));
});
test("a running episode with a tool step is acting; the intent is the user's own words", () => {
  const r = deriveRun([user, tool("delentia_read_repo_file")], true);
  assert.equal(r.mood, "acting");
  assert.equal(r.intent, user.text);
  assert.deepEqual(r.gates, [{ tool: "delentia_read_repo_file", verdict: "ran" }]);
  assert.equal(r.cycle.find((c) => c.name === "ACT").status, "active");
});
test("a finished, verified episode is done and shows the evidence the stream carried", () => {
  const r = deriveRun([user, tool("delentia_read_repo_file"), { kind: "answer", text: "sample-service" }, summary()], false);
  assert.equal(r.mood, "done");
  assert.equal(r.verification.state, "aligned");
  assert.deepEqual(r.evidence, { signed: true, signatureHash: "abc123", notaryReceipts: 3, stoppedReason: "llm_finished", seconds: 4.2 });
  assert.equal(r.cycle.find((c) => c.name === "ROUTE").note, "FAST: narrow read");
  assert.equal(r.cycle.find((c) => c.name === "VERIFY").status, "done");
});
test("what the stream does not report stays unknown (COMPRESS, LEARN), never 'done'", () => {
  const r = deriveRun([user, tool("x"), summary()], false);
  assert.equal(r.cycle.find((c) => c.name === "COMPRESS").status, "unknown");
  assert.equal(r.cycle.find((c) => c.name === "LEARN").status, "unknown");
});
test("a blocked gate is a blocked mood and a blocked ACT, with the reason and F", () => {
  const blocked = { kind: "step", step: { iteration: 1, kind: "blocked", tool: "delentia_write_repo_file", thinking: "", result: null, F: 0.39, reason: "F below the threshold" } };
  const r = deriveRun([user, blocked, summary({ stopped_reason: "fdia_blocked" })], false);
  assert.equal(r.mood, "blocked");
  assert.deepEqual(r.gates[0], { tool: "delentia_write_repo_file", verdict: "blocked", F: 0.39, reason: "F below the threshold" });
  assert.equal(r.cycle.find((c) => c.name === "ACT").status, "blocked");
});
test("a step that waits for a signature is a waiting mood, running or finished", () => {
  const pending = { kind: "step", step: { iteration: 1, kind: "pending", tool: "delentia_write_repo_file", thinking: "", result: null } };
  assert.equal(deriveRun([user, pending], true).mood, "waiting");
  const r = deriveRun([user, pending, summary({ stopped_reason: "pending_approval", approval_id: "c689e67b86bb" })], false);
  assert.equal(r.mood, "waiting");
  assert.equal(r.approvalId, "c689e67b86bb");
});
test("CORD stopping the request blocks GUARD and the mood", () => {
  const r = deriveRun([user, summary({ stopped_reason: "goal_blocked", guard: { cord_verdict: "rejected", cord_findings: [{ pattern_id: "CORD-I001" }] } })], false);
  assert.equal(r.mood, "blocked");
  const guard = r.cycle.find((c) => c.name === "GUARD");
  assert.equal(guard.status, "blocked");
  assert.match(guard.note, /CORD-I001/);
});
test("an error entry is a blocked mood, not a success", () => {
  assert.equal(deriveRun([user, { kind: "error", text: "API not reachable" }], false).mood, "blocked");
});
test("a verification that does not apply is not reported as aligned", () => {
  const r = deriveRun([user, summary({ verification: { applicable: false } })], false);
  assert.equal(r.verification.state, "not_applicable");
});
test("with several goals in one chat the Inspector shows the current run only", () => {
  const second = { kind: "user", text: "Write a note to README.md" };
  const pending = { kind: "step", step: { iteration: 1, kind: "pending", tool: "delentia_write_repo_file", thinking: "", result: null } };
  const r = deriveRun([user, tool("delentia_read_repo_file"), summary(), second, pending], true);
  assert.equal(r.intent, "Write a note to README.md");
  assert.deepEqual(r.gates, [{ tool: "delentia_write_repo_file", verdict: "waiting" }]);
  assert.equal(r.mood, "waiting");
  assert.equal(r.verification.state, "unknown");           // the first run's verification is not carried over
});
test("a plan that arrived before the first tool is shown as such, and the THINK step says where it was shown", () => {
  const planEntry = { kind: "plan", plan: { steps: ["Observe", "Analyze", "Reverse"], route: { path: "fast" } } };
  const running = deriveRun([user, planEntry], true);
  assert.deepEqual(running.plan, ["Observe", "Analyze", "Reverse"]);
  assert.equal(running.cycle.find((c) => c.name === "THINK").status, "done");
  assert.match(running.cycle.find((c) => c.name === "THINK").note, /shown before the first tool/);
  const none = deriveRun([user, tool("x"), summary()], false);
  assert.equal(none.plan, null);                                   // no plan event: nothing is claimed
});
console.log(`${n} tests passed`);
