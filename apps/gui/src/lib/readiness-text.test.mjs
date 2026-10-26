// Run with: npm run test:readiness  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { describeCheck, knownStates } from "./readiness-text.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

// Every (check, state) rct_control_plane/readiness.py can produce.
const SERVER = ["model:ready", "model:configured", "model:server_down", "model:model_missing", "model:no_key", "approver:ready", "approver:nobody", "first_request:done", "first_request:not_yet"];
const sample = (key) => { const [id, state] = key.split(":"); return { id, state, essential: true, ok: state === "ready", model: "qwen2.5:7b", provider: "ollama", installed: ["llama3.2:3b"], keys: 1, devices: 0, episodes: 2 }; };

test("every state the server can produce has a text in both languages", () => {
  for (const key of SERVER) for (const lang of ["th", "en"]) {
    const t = describeCheck(sample(key), lang);
    assert.ok(t.label && t.what && t.next, `${key}/${lang}`);
    assert.ok(!t.label.startsWith(key.split(":")[0] + ":"), `${key}/${lang}: not the fallback text`);
  }
});
test("no text is written for a state the server does not produce", () => {
  assert.deepEqual(knownStates().filter((k) => !SERVER.includes(k)), []);
});
test("Thai texts contain Thai and English texts do not", () => {
  const thai = /[฀-๿]/;
  for (const key of SERVER) {
    assert.ok(thai.test(describeCheck(sample(key), "th").label), `${key} th label`);
    assert.ok(!thai.test(describeCheck(sample(key), "en").label), `${key} en label`);
  }
});
test("a problem points at a page the person can open; a state that is fine points nowhere", () => {
  for (const key of ["model:server_down", "model:model_missing", "model:no_key", "approver:nobody"]) assert.ok(describeCheck(sample(key), "en").href?.startsWith("/"), key);
  for (const key of ["model:ready", "approver:ready", "first_request:done"]) assert.equal(describeCheck(sample(key), "en").href, null, key);
});
test("a missing model names what is installed instead", () => {
  assert.match(describeCheck(sample("model:model_missing"), "en").what, /llama3\.2:3b/);
});
test("an unknown state is shown as reported, never hidden", () => {
  const t = describeCheck({ id: "model", state: "something_new", essential: true, ok: false }, "en");
  assert.match(t.label, /something_new/);
});
console.log(`${n} tests passed`);
