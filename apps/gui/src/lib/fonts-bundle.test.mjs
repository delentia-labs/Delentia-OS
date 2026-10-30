// Run with: npm run test:fonts  (node 22.6+, no test framework)
// Round 106: the Desk's three fonts are bundled from npm packages, not downloaded while the Desk is built (a failed download on a CI runner failed the whole build, three times in a row).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "../../scripts/make-fonts-css.mjs";

const gui = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

test("src/app/fonts.css is exactly what the generator writes (run node scripts/make-fonts-css.mjs after changing it)", () => {
  assert.equal(fs.readFileSync(path.join(gui, "src/app/fonts.css"), "utf8").replace(/\r\n/g, "\n"), render());
});
test("no source file asks Google for a font while building", () => {
  const bad = [];
  const walk = (dir) => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) { const p = path.join(dir, e.name); if (e.isDirectory()) walk(p); else if (/\.(tsx?|css)$/.test(e.name) && /next\/font\/google|fonts\.googleapis/.test(fs.readFileSync(p, "utf8"))) bad.push(p); } };
  walk(path.join(gui, "src"));
  assert.deepEqual(bad, []);
});
test("the three families are the ones the Architect chose, and the variables point at them", () => {
  const css = fs.readFileSync(path.join(gui, "src/app/globals.css"), "utf8");
  assert.match(css, /--font-th:\s*"Prompt"/); assert.match(css, /--font-mono-en:\s*"JetBrains Mono"/); assert.match(css, /--font-doc:\s*"Sarabun"/);
});
test("Thai and Latin letters each have their own face (Prompt and Sarabun), mono is Latin only", () => {
  const css = render();
  assert.equal((css.match(/font-family: "Prompt"/g) || []).length, 8);
  assert.equal((css.match(/font-family: "Sarabun"/g) || []).length, 6);
  assert.equal((css.match(/font-family: "JetBrains Mono"/g) || []).length, 3);
  assert.match(css, /U\+0E01-0E5B/);
});
console.log(`${n} tests passed`);
