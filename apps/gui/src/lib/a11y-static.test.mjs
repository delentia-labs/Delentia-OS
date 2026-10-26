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
test("no box is sized w-screen: 100vw includes the scrollbar, so a page that scrolls would overflow sideways by the scrollbar's width (measured: 6 px on three pages at 375 px)", () => {
  const bad = lines.filter((l) => /\bw-screen\b/.test(l.text) && !/h-screen w-screen" style=/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("the bar shown at phone width is a <header>, so it is not content outside every landmark (axe: region)", () => {
  const shell = fs.readFileSync(path.join(root, "components/desk/Shell.tsx"), "utf8");
  assert.match(shell, /<header className="[^"]*md:hidden"/);
});
test("the menu buttons are named in the page's language, not always in English", () => {
  const bad = lines.filter((l) => /aria-label="(Open|Close) menu"/.test(l.text));
  assert.deepEqual(bad.map((l) => `${l.f}:${l.i}`), []);
});
test("a section title inside the inspector is a second-level heading (the page title is the first; axe: heading-order)", () => {
  const inspector = fs.readFileSync(path.join(root, "components/desk/Inspector.tsx"), "utf8");
  assert.doesNotMatch(inspector, /<h3\b/);
});
test("the small controls of the side panel are at least 24 x 24 CSS px (WCAG 2.2 target size; measured before: 46 x 17 and 29 x 20)", () => {
  const shell = fs.readFileSync(path.join(root, "components/desk/Shell.tsx"), "utf8");
  assert.match(shell, /href="\/settings" className="[^"]*min-h-\[24px\]/);
  assert.match(shell, /key=\{l\} onClick=\{\(\) => setLang\(l\)\}[^>]*min-h-\[24px\]/);
});
test("the scrolling page body is a named region (a screen reader hears the page title, not the first words of its text)", () => {
  const ui = fs.readFileSync(path.join(root, "components/desk/ui.tsx"), "utf8");
  assert.match(ui, /<div tabIndex=\{0\} role="region" aria-labelledby="desk-page-title"[^>]*overflow-y-auto/);
  assert.match(ui, /<h1 id="desk-page-title"/);
});
test("the two groups of the side panel are named for what they are, in the page's language", () => {
  const shell = fs.readFileSync(path.join(root, "components/desk/Shell.tsx"), "utf8");
  assert.doesNotMatch(shell, /role="group" aria-label="(Menu|Language)"/);
});
console.log(`${n} tests passed`);
