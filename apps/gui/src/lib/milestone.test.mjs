// Run with: npm run test:milestone  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { milestoneLine } from "./milestone.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

const DECLARED = { id: "preview-0.1", number: "0.1", release_level: "L1", name_en: "Public Technical Preview", name_th: "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ" };

test("nothing is shown until the server reports a milestone", () => {
  assert.equal(milestoneLine(null, "th"), null);
  assert.equal(milestoneLine(undefined, "en"), null);
  assert.equal(milestoneLine({}, "en"), null);
});

test("a half-filled label is not shown", () => {
  assert.equal(milestoneLine({ ...DECLARED, name_th: "" }, "th"), null);
  assert.equal(milestoneLine({ ...DECLARED, name_en: "   " }, "en"), null);
  assert.equal(milestoneLine({ ...DECLARED, number: "" }, "en"), null);
});

test("the interface language decides the primary text and the other language is kept", () => {
  const th = milestoneLine(DECLARED, "th");
  const en = milestoneLine(DECLARED, "en");
  assert.equal(en.primary, "Public Technical Preview 0.1");
  assert.equal(th.primary, "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1");
  assert.equal(th.secondary, en.primary);
  assert.equal(en.secondary, th.primary);
});

test("both languages appear in one line, English first, and the level is kept", () => {
  const l = milestoneLine(DECLARED, "th");
  assert.equal(l.both, "Public Technical Preview 0.1 / รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1");
  assert.equal(l.level, "L1");
});

test("the label never contains a package version", () => {
  const l = milestoneLine(DECLARED, "en");
  assert.doesNotMatch(l.both, /\b\d+\.\d+\.\d+\b/);                  // 2.4.1 is the version; 0.1 is the stage number
});

console.log(`${n} tests passed`);
