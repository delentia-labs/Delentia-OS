// Run with: node --experimental-strip-types apps/gui/src/lib/signed-decision.test.mjs  (Node 22.6+; no test framework needed)
import assert from "node:assert/strict";
import { parseSignedDecision } from "./signed-decision.ts";

const key = "a".repeat(64);
const sig = "b".repeat(128);
const good = JSON.stringify({ decision: "APPROVED", public_key_hex: key, signature_hex: sig });

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

test("a good signature is accepted and normalised", () => {
  const r = parseSignedDecision(`  ${good}\n`);
  assert.equal(r.ok, true);
  assert.deepEqual(r.body, { decision: "APPROVED", public_key_hex: key, signature_hex: sig });
});
test("the signature pasted twice is named as such", () => {
  const r = parseSignedDecision(good + "\n" + good);
  assert.equal(r.ok, false);
  assert.match(r.message, /Two JSON objects/);
  assert.match(parseSignedDecision(good + good, "th").message, /ซ้อนกันสองก้อน/);
});
test("a cut-off paste is named as cut off", () => {
  const r = parseSignedDecision(good.slice(0, 60));
  assert.equal(r.ok, false);
  assert.match(r.message, /cut off/);
});
test("text that is not JSON at all", () => {
  assert.match(parseSignedDecision("hello").message, /No \{ found/);
});
test("text after the closing brace", () => {
  assert.match(parseSignedDecision(good + " thanks").message, /text after the closing/);
});
test("curly quotes from a word processor", () => {
  assert.match(parseSignedDecision(good.replaceAll('"', "“")).message, /straight quotes|Not valid JSON/);
});
test("missing fields are listed", () => {
  const r = parseSignedDecision(JSON.stringify({ decision: "APPROVED" }));
  assert.equal(r.ok, false);
  assert.match(r.message, /public_key_hex, signature_hex/);
});
test("a wrong decision word", () => {
  const r = parseSignedDecision(JSON.stringify({ decision: "yes", public_key_hex: key, signature_hex: sig }));
  assert.match(r.message, /APPROVED or REJECTED/);
});
test("a key of the wrong length says how long it is", () => {
  const r = parseSignedDecision(JSON.stringify({ decision: "APPROVED", public_key_hex: key.slice(0, 40), signature_hex: sig }));
  assert.match(r.message, /64 hexadecimal characters \(it has 40\)/);
});
test("a signature that is not hexadecimal", () => {
  const r = parseSignedDecision(JSON.stringify({ decision: "REJECTED", public_key_hex: key, signature_hex: "z".repeat(128) }));
  assert.match(r.message, /128 hexadecimal.*not hex/);
});
test("a braces character inside a string does not confuse the scan", () => {
  const tricky = JSON.stringify({ decision: "APPROVED", public_key_hex: key, signature_hex: sig, note: "a } and a { inside" });
  assert.equal(parseSignedDecision(tricky).ok, true);
});
console.log(`${n} tests passed`);
