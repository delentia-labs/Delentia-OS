// Run with: npm run test:a11y  (node 22.6+, no test framework)
// Static guards for the accessibility findings axe-core made on the real pages (Round 101C): a scrolling box the keyboard can not reach, two landmarks with the same name, a label on a box with no role.
// It reads the sources; the real measurement (axe in a browser, every page) is in the Round 101C document.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : e.name.endsWith(".tsx") ? [path.join(dir, e.name)] : []));
}
const files = walk(path.join(root, "app")).concat(walk(path.join(root, "components")));
let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };
const lines = files.flatMap((f) => fs.readFileSync(f, "utf8").split("\n").map((text, i) => ({ f: path.relative(root, f), i: i + 1, text })));

test("a scrolling <pre> can be reached with the keyboard", () => {
  const bad = lines.filter((l) => /<pre\b/.test(l.text) && /overflow-(auto|x-auto|y-auto)/.test(l.text) && !/tabIndex/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("a horizontally scrolling table wrapper can be reached with the keyboard", () => {
  const bad = lines.filter((l) => /<div\b[^>]*overflow-x-auto/.test(l.text) && !/tabIndex/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("the page body, which scrolls, can be reached with the keyboard", () => {
  const ui = fs.readFileSync(path.join(root, "components/desk/ui.tsx"), "utf8");
  assert.match(ui, /<div tabIndex=\{0\}[^>]*overflow-y-auto/);
});
test("every <aside> landmark has its own name", () => {
  const bad = lines.filter((l) => /<aside\b/.test(l.text) && !/aria-label/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("a box with an aria-label has a role (a label on a bare <div> is ignored by screen readers)", () => {
  const bad = lines.filter((l) => /<div\b[^>]*aria-label/.test(l.text) && !/role=/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("every <img> has an alt text", () => {
  const bad = lines.filter((l) => /<img\b/.test(l.text) && !/\balt=/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("the mascot's motion stops under prefers-reduced-motion", () => {
  assert.match(fs.readFileSync(path.join(root, "app/globals.css"), "utf8"), /prefers-reduced-motion: reduce[\s\S]*animation: none/);
});
console.log(`${n} tests passed`);
