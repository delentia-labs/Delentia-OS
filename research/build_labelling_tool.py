"""Build the one-file labelling page for the Architect (offline, no network, nothing leaves the browser).

    python -m research.build_labelling_tool REQUEST_SHEET.md RESULT_SHEET.md OUT.html

The items come from the two sheets themselves (research/rct7_holdout.parse_sheet), so the page cannot disagree with the sheets. There is no answer key anywhere: the sheets have none.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from research import rct7_holdout as holdout

TEMPLATE = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ติดป้าย holdout RCT-7</title>
<style>
:root { --bg:#0e1611; --panel:#142019; --rule:#2b3f31; --text:#e4eedd; --muted:#93a88f; --leaf:#80c961; --amber:#e4b54a; --rust:#e2694c; }
@media (prefers-color-scheme: light) { :root { --bg:#f6f8f4; --panel:#ffffff; --rule:#cfd9c9; --text:#17231a; --muted:#566b57; --leaf:#2f7a1f; --amber:#9a6b00; --rust:#b3412a; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.55 system-ui, "Segoe UI", sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 16px; }
h1 { font-size: 20px; margin: 8px 0 4px; }
p, li { color: var(--muted); }
details { background: var(--panel); border:1px solid var(--rule); border-radius:8px; padding:10px 14px; margin:10px 0; }
summary { cursor:pointer; color: var(--text); }
.tabs { display:flex; gap:8px; margin:14px 0; flex-wrap:wrap; }
.tab { border:1px solid var(--rule); background:var(--panel); color:var(--text); border-radius:8px; padding:8px 14px; cursor:pointer; font-size:15px; }
.tab[aria-selected="true"] { border-color: var(--leaf); outline: 1px solid var(--leaf); }
.bar { height:8px; background:var(--rule); border-radius:99px; overflow:hidden; margin:6px 0 2px; }
.bar > div { height:100%; background:var(--leaf); width:0; transition: width .2s; }
.item { background:var(--panel); border:1px solid var(--rule); border-radius:10px; padding:14px; margin:12px 0; }
.item.done { border-left:4px solid var(--leaf); }
.num { color:var(--muted); font-size:13px; }
.q { font-size:18px; margin:4px 0 8px; color:var(--text); white-space:pre-wrap; }
.a { background: color-mix(in srgb, var(--rule) 40%, transparent); border-radius:8px; padding:8px 10px; margin:6px 0 10px; color:var(--text); white-space:pre-wrap; }
.label { color:var(--muted); font-size:13px; }
.btns { display:flex; gap:8px; flex-wrap:wrap; }
.btn { flex:1 1 130px; padding:10px 12px; border-radius:8px; border:1px solid var(--rule); background:transparent; color:var(--text); cursor:pointer; font-size:15px; }
.btn:hover { border-color: var(--leaf); }
.btn[aria-pressed="true"] { background: var(--leaf); color:#0e1611; border-color: var(--leaf); font-weight:600; }
.btn.q-mark[aria-pressed="true"] { background: var(--amber); border-color: var(--amber); }
input.note { width:100%; margin-top:8px; padding:8px 10px; border-radius:8px; border:1px solid var(--rule); background:var(--bg); color:var(--text); font-size:14px; }
textarea { width:100%; min-height:110px; padding:10px; border-radius:8px; border:1px solid var(--rule); background:var(--panel); color:var(--text); font:14px/1.5 ui-monospace, Consolas, monospace; }
.row { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }
.act { padding:10px 14px; border-radius:8px; border:1px solid var(--leaf); background:transparent; color:var(--leaf); cursor:pointer; font-size:15px; }
.warn { color: var(--amber); }
</style>
</head>
<body>
<main>
<h1>ติดป้าย holdout ของ RCT-7</h1>
<p>ทุกอย่างทำงานในเบราว์เซอร์ของคุณเท่านั้น ไม่ส่งข้อมูลไปไหน ผมไม่ได้เก็บเฉลยไว้ ป้ายเป็นของคุณทั้งหมด คำตอบถูกบันทึกในเบราว์เซอร์อัตโนมัติ ปิดแล้วเปิดใหม่ยังอยู่</p>
<details open>
<summary>อ่านก่อนเริ่ม (1 นาที)</summary>
<ol>
<li><b>ชุดที่ 1: คำขอ</b> ตัดสินแต่ละคำขอ โดยสมมติว่าคุณเป็น agent ที่รู้เฉพาะประโยคนั้น (ไม่มีไฟล์ ไม่มีประวัติแชท ไม่มีความจำ): <b>A</b> = ต้องถามก่อน เพราะขาดข้อมูลที่จำเป็น &nbsp; <b>B</b> = ลงมือได้เลยจากถ้อยคำและความรู้ทั่วไป &nbsp; <b>?</b> = ตัดสินไม่ได้</li>
<li><b>ชุดที่ 2: คำขอ + คำตอบ</b> ตัดสินว่าคำตอบทำสิ่งที่คำขอบอกหรือไม่ ไม่ต้องดูสำนวน ความยาว ความสุภาพ: <b>M</b> = ตรง &nbsp; <b>N</b> = ไม่ตรง (ขาดส่วนหนึ่ง/ผิด/ตอบเรื่องอื่น) &nbsp; <b>?</b> = ตัดสินไม่ได้</li>
<li>ตัดสินตามที่คุณเห็นว่าถูก <b>ไม่ต้องเดาว่าโมเดลจะตอบอะไร หรือผมอยากให้เป็นอะไร</b> ข้อที่ลังเลจริง ๆ ใส่ ? ได้ (ถูกตัดออกจากคะแนน)</li>
<li>ช่องหมายเหตุเป็นทางเลือก (เช่นข้อ A ขาดอะไร) กดจบแล้วไปที่ "ผลลัพธ์" ด้านล่างสุด คัดลอกข้อความส่งกลับมาในแชท</li>
</ol>
</details>
<div class="tabs" role="tablist">
<button class="tab" role="tab" id="tab-0" aria-selected="true" onclick="show(0)">ชุดที่ 1: คำขอ (<span id="count-0"></span>)</button>
<button class="tab" role="tab" id="tab-1" aria-selected="false" onclick="show(1)">ชุดที่ 2: คำขอ + คำตอบ (<span id="count-1"></span>)</button>
</div>
<div class="bar"><div id="bar"></div></div>
<div class="label" id="progress"></div>
<div id="items"></div>
<h2>ผลลัพธ์ (ส่งข้อความนี้กลับมาในแชท)</h2>
<div class="row"><button class="act" onclick="render()">สร้างผลลัพธ์</button><button class="act" onclick="copyOut()">คัดลอก</button><button class="act" onclick="download()">ดาวน์โหลดไฟล์</button><button class="act" style="border-color:var(--rust);color:var(--rust)" onclick="resetAll()">ล้างทั้งหมด</button></div>
<textarea id="out" readonly placeholder="กด &quot;สร้างผลลัพธ์&quot; เมื่อติดป้ายครบ (หรือเท่าที่ติดแล้ว)"></textarea>
<p id="missing" class="warn"></p>
</main>
<script>
const SHEETS = __DATA__;
const CHOICES = [["A","B","?"],["M","N","?"]];
const NAMES = {A:"A ต้องถามก่อน",B:"B ลงมือได้เลย",M:"M ตรงกับคำขอ",N:"N ไม่ตรง","?":"? ตัดสินไม่ได้"};
let state = {labels:[{},{}], notes:[{},{}]};
let current = 0;
try { const saved = localStorage.getItem("rct7-labels-v1"); if (saved) state = JSON.parse(saved); } catch (e) {}
function save() { try { localStorage.setItem("rct7-labels-v1", JSON.stringify(state)); } catch (e) {} }
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function show(i) { current = i; document.getElementById("tab-0").setAttribute("aria-selected", i===0); document.getElementById("tab-1").setAttribute("aria-selected", i===1); draw(); }
function setLabel(sheet, n, value) { if (state.labels[sheet][n] === value) delete state.labels[sheet][n]; else state.labels[sheet][n] = value; save(); draw(false); }
function setNote(sheet, n, value) { if (value) state.notes[sheet][n] = value; else delete state.notes[sheet][n]; save(); }
function counts(sheet) { return Object.keys(state.labels[sheet]).length; }
function draw(scroll) {
  const box = document.getElementById("items"); const y = window.scrollY; box.textContent = "";
  const items = SHEETS[current];
  items.forEach(it => {
    const card = el("div", "item" + (state.labels[current][it.n] ? " done" : ""));
    card.appendChild(el("div", "num", "ข้อ " + it.n));
    if (it.answer === undefined) card.appendChild(el("div", "q", it.request));
    else { card.appendChild(el("div", "label", "คำขอ")); card.appendChild(el("div", "q", it.request)); card.appendChild(el("div", "label", "คำตอบ")); card.appendChild(el("div", "a", it.answer)); }
    const row = el("div", "btns");
    CHOICES[current].forEach(c => { const b = el("button", "btn" + (c === "?" ? " q-mark" : ""), NAMES[c]); b.setAttribute("aria-pressed", state.labels[current][it.n] === c); b.onclick = () => setLabel(current, it.n, c); row.appendChild(b); });
    card.appendChild(row);
    const note = el("input", "note"); note.type = "text"; note.placeholder = current === 0 ? "ขาดอะไร (ไม่บังคับ)" : "ทำไม (ไม่บังคับ)"; note.value = state.notes[current][it.n] || ""; note.oninput = () => setNote(current, it.n, note.value); card.appendChild(note);
    box.appendChild(card);
  });
  document.getElementById("count-0").textContent = counts(0) + "/" + SHEETS[0].length;
  document.getElementById("count-1").textContent = counts(1) + "/" + SHEETS[1].length;
  const done = counts(current), total = SHEETS[current].length;
  document.getElementById("bar").style.width = (100 * done / total) + "%";
  document.getElementById("progress").textContent = "ชุดนี้ติดป้ายแล้ว " + done + " จาก " + total;
  if (scroll === false) window.scrollTo(0, y);
}
function compact(sheet) {
  const groups = {}; CHOICES[sheet].forEach(c => groups[c] = []);
  Object.keys(state.labels[sheet]).map(Number).sort((a,b)=>a-b).forEach(n => groups[state.labels[sheet][n]].push(n));
  return CHOICES[sheet].filter(c => groups[c].length).map(c => c + ": " + groups[c].join(",")).join("   ");
}
function render() {
  const lines = [];
  lines.push("ชุดที่ 1 (คำขอ, " + counts(0) + "/" + SHEETS[0].length + "): " + (compact(0) || "(ยังไม่ได้ติด)"));
  lines.push("ชุดที่ 2 (คำขอ+คำตอบ, " + counts(1) + "/" + SHEETS[1].length + "): " + (compact(1) || "(ยังไม่ได้ติด)"));
  [0,1].forEach(s => { const keys = Object.keys(state.notes[s]).map(Number).sort((a,b)=>a-b); if (keys.length) { lines.push(""); lines.push("หมายเหตุชุดที่ " + (s+1) + ":"); keys.forEach(k => lines.push("  " + k + ": " + state.notes[s][k])); } });
  document.getElementById("out").value = lines.join("\n");
  const miss = [0,1].map(s => SHEETS[s].length - counts(s));
  document.getElementById("missing").textContent = (miss[0] || miss[1]) ? ("ยังไม่ได้ติด: ชุดที่ 1 อีก " + miss[0] + " ข้อ, ชุดที่ 2 อีก " + miss[1] + " ข้อ (ส่งเท่าที่ติดแล้วก็ได้ ผมจะบอกว่าพอหรือไม่)") : "";
}
function copyOut() { render(); const t = document.getElementById("out"); t.select(); try { navigator.clipboard.writeText(t.value); } catch (e) { document.execCommand("copy"); } }
function download() { render(); const blob = new Blob([document.getElementById("out").value], {type:"text/plain;charset=utf-8"}); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "rct7_labels.txt"; a.click(); }
function resetAll() { if (confirm("ล้างป้ายทั้งหมดที่ติดไว้?")) { state = {labels:[{},{}], notes:[{},{}]}; save(); draw(); document.getElementById("out").value = ""; } }
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  const items = SHEETS[current]; const next = items.find(it => !state.labels[current][it.n]); if (!next) return;
  const key = e.key.toUpperCase(); const map = {"?":"?", "/":"?"};
  const choice = map[key] || key; if (CHOICES[current].includes(choice)) { setLabel(current, next.n, choice); }
});
draw();
</script>
</body>
</html>
"""


def build(request_sheet: Path, result_sheet: Path, out: Path) -> int:
    sheets = []
    for path in (request_sheet, result_sheet):
        rows = holdout.parse_sheet(path.read_text(encoding="utf-8"))
        sheets.append([{"n": n, **{k: v for k, v in r.items() if k in ("request", "answer")}} for n, r in sorted(rows.items())])
    if len(sheets[0]) < 20 or len(sheets[1]) < 20 or any("answer" in item for item in sheets[0]) or any("answer" not in item for item in sheets[1]):
        raise SystemExit("the first sheet must be a request sheet and the second a request+answer sheet, each with at least 20 items")
    out.write_text(TEMPLATE.replace("__DATA__", json.dumps(sheets, ensure_ascii=False)), encoding="utf-8")
    return len(sheets[0]) + len(sheets[1])


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    print(f"{build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))} items -> {sys.argv[3]}")
