// Run with: npm run test:servertext  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { KNOWN_EXACT, KNOWN_PATTERN_COUNT, serverText } from "./server-text-th.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };
const THAI = /[฀-๿]/;

test("English is returned as the server wrote it", () => {
  for (const s of KNOWN_EXACT) assert.equal(serverText(s, false), s);
  assert.equal(serverText("advanced 3 task(s)", false), "advanced 3 task(s)");
});
test("every known exact sentence has a Thai text with Thai letters", () => {
  for (const s of KNOWN_EXACT) assert.ok(THAI.test(serverText(s, true)), s);
});
test("the numbers of a daemon result survive into the Thai text", () => {
  assert.match(serverText("audit chain OK: 139 chained rows (139 signed), head seq 139", true), /139 แถว \(เซ็นแล้ว 139\), head seq 139/);
  assert.match(serverText("advanced 4 task(s)", true), /4 งาน/);
  assert.match(serverText("2 reminder(s) fired", true), /2 รายการ/);
  assert.match(serverText("reviewed 12 learned skill(s): 3 proposal(s) {'weak': 3}; nothing archived", true), /12 รายการ.*3 รายการ/);
  assert.match(serverText("signatures verified with this host's key (fingerprint ab12cd34ef56)", true), /ab12cd34ef56/);
});
test("the witness summary keeps both counts and says the second witness is wanted", () => {
  const th = serverText("1 independent witness(es) hold a recent signed head; the 7 row(s) newer than the newest anchor are the window an attacker with the host's root could still rewrite unnoticed; with only one witness, a compromise of that one party defeats it: add a second", true);
  assert.match(th, /1 ราย/); assert.match(th, /7 แถว/); assert.match(th, /พยานคนที่สอง/);
});
test("a sentence nobody listed is shown as it is, never dropped", () => {
  assert.equal(serverText("something new the server says", true), "something new the server says");
  assert.equal(serverText(null, true), "");
});
test("the table is not empty", () => { assert.ok(KNOWN_EXACT.length >= 10 && KNOWN_PATTERN_COUNT >= 7); });
console.log(`${n} tests passed`);
