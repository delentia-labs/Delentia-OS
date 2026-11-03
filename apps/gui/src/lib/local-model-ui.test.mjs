// Run with: npm run test:localmodels  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { TRY_ONLY, evidenceText, fitText, formatGb, ollamaAdvice, orderRows, pullText } from "./local-model-ui.ts";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

const row = (tag, fits, extra = {}) => ({ tag, label: tag, size_gb: 2.5, tools: true, licence: "x", note_en: "n", note_th: "น", measured_en: "", measured_th: "", vendor_claim: false, estimated_memory_gb: 4.6, fits, installed: false, measured_here: false, ...extra });

test("each state of Ollama gets its own sentence and the one button that fits, in both languages", () => {
  for (const lang of ["en", "th"]) {
    assert.equal(ollamaAdvice("not_installed", false, lang).action, "open_download");
    assert.equal(ollamaAdvice("installed_not_running", false, lang).action, "start");
    assert.equal(ollamaAdvice("running", false, lang).action, "pick");
    assert.equal(ollamaAdvice("running", true, lang).action, "pick");
    assert.equal(ollamaAdvice(undefined, false, lang).action, "none");
  }
  assert.match(ollamaAdvice("not_installed", false, "en").text, /does not download or run an installer/);     // the system never installs by itself, and says so
  assert.match(ollamaAdvice("not_installed", false, "th").text, /ไม่ดาวน์โหลดหรือรันตัวติดตั้งให้เอง/);
  assert.notEqual(ollamaAdvice("running", true, "en").title, ollamaAdvice("running", false, "en").title);
});

test("no sentence tells the person to open a terminal for the ordinary path", () => {
  for (const lang of ["en", "th"]) for (const s of ["not_installed", "installed_not_running", "running"]) for (const m of [true, false]) {
    const a = ollamaAdvice(s, m, lang);
    assert.doesNotMatch(a.title + a.text, /open a terminal|type |ollama pull|เปิดเทอร์มินัล|พิมพ์/i);
  }
});

test("a fit is always said to be an estimate, and unknown memory gives no estimate", () => {
  assert.match(fitText(row("a", true), 16, "en").text, /not measured/);
  assert.match(fitText(row("a", false), 8, "en").text, /May not fit/);
  assert.equal(fitText(row("a", true), 16, "en").tone, "ok");
  assert.equal(fitText(row("a", false), 8, "en").tone, "warn");
  assert.equal(fitText(row("a", null), null, "en").tone, "muted");
  assert.match(fitText(row("a", true), 16, "th").text, /ยังไม่ได้วัด/);
});

test("evidence says whether this project measured the model, never more", () => {
  assert.match(evidenceText(row("a", true), "en"), /has not measured/);
  assert.match(evidenceText(row("q", true, { measured_here: true, measured_en: "4 of 5", measured_th: "4 จาก 5" }), "en"), /Measured by this project: 4 of 5/);
  assert.match(evidenceText(row("a", true), "th"), /ยังไม่ได้วัด/);
});

test("every local model is described as for trying, in both languages", () => {
  assert.match(TRY_ONLY.en, /for trying Delentia/);
  assert.match(TRY_ONLY.en, /online model is usually needed/);
  assert.match(TRY_ONLY.th, /ลองใช้ Delentia/);
});

test("rows are ordered by whether they probably fit, then in the catalog's own order; nothing is ordered by claimed quality and no row is recommended", () => {
  const rows = [row("big", false), row("a", true), row("unknown", null), row("first", true), row("b", true)];
  assert.deepEqual(orderRows(rows).map((r) => r.tag), ["a", "first", "b", "unknown", "big"]);
});

test("progress and sizes read plainly", () => {
  assert.equal(formatGb(1.6), "1.6 GB");
  assert.equal(formatGb(19), "19 GB");
  assert.match(pullText({ status: "downloading", percent: 42.4, message: "" }, "en"), /Downloading 42%/);
  assert.match(pullText({ status: "downloading", percent: null, message: "" }, "th"), /กำลังเตรียม/);
  assert.match(pullText({ status: "failed", percent: null, message: "no space" }, "en"), /failed: no space/);
  assert.equal(pullText({ status: "idle", percent: null, message: "" }, "en"), "");
});

console.log(`${n} tests passed`);
