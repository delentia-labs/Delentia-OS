// Round 101E: every page of the built Desk, opened in a real headless Chrome/Edge at phone and desktop width, in Thai and in English, checked with axe-core (WCAG 2.0/2.1/2.2 A and AA + best practice),
// and checked for sideways scrolling. Run after `npm run build`:   node scripts/a11y-e2e.mjs [--out out] [--widths 375,1280] [--langs th,en]
// No new dependency: axe-core is already installed (it comes with the ESLint plugin), Node 22+ has a WebSocket, and the browser is the one on the machine (CHROME_PATH overrides the search).
// The API is not running, so the pages show their "cannot reach the agent" states: that is also a state a person sees, and it needs no data. It does NOT replace a screen reader, a Tab walk by a person or the
// pages' states with real data; it keeps the defects that axe can see (and the 6 px sideways scroll) from coming back.
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith("--") ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const OUT = path.resolve(args.out || "out");
const WIDTHS = (args.widths || "375,1280").split(",").map(Number);
const LANGS = (args.langs || "th,en").split(",");
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findBrowser() {
  const candidates = [
    process.env.CHROME_PATH,
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ];
  const found = candidates.find((c) => c && fs.existsSync(c));
  if (!found) throw new Error("no Chrome or Edge found; set CHROME_PATH");
  return found;
}

function staticServer(root) {
  const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json", ".txt": "text/plain" };
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    const tries = [url, url + ".html", path.join(url, "index.html")];
    for (const t of tries) {
      const file = path.join(root, t);
      if (file.startsWith(root) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
        return fs.createReadStream(file).pipe(res);
      }
    }
    res.writeHead(404).end("not found");
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("cannot open the browser's debugging socket")); });
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
    } else listeners.forEach((l) => l(msg));
  };
  return {
    send: (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); }),
    on: (fn) => listeners.push(fn),
    close: () => ws.close(),
  };
}

async function launch(browser, profile) {
  const flags = ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--disable-extensions", "about:blank"];
  if (process.env.CI) flags.unshift("--no-sandbox");
  const child = spawn(browser, flags, { stdio: "ignore" });
  const portFile = path.join(profile, "DevToolsActivePort");
  for (let i = 0; i < 100 && !fs.existsSync(portFile); i++) await sleep(100);
  if (!fs.existsSync(portFile)) { child.kill(); throw new Error("the browser did not start"); }
  const port = fs.readFileSync(portFile, "utf8").split("\n")[0].trim();
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch { /* not ready */ }
    if (!target) await sleep(100);
  }
  if (!target) { child.kill(); throw new Error("the browser has no page to drive"); }
  return { child, cdp: await connect(target.webSocketDebuggerUrl) };
}

function routesOf(root) {
  const pages = fs.readdirSync(root).filter((f) => f.endsWith(".html") && !["404.html", "_not-found.html"].includes(f)).map((f) => (f === "index.html" ? "/" : "/" + f.replace(/\.html$/, "")));
  return pages.sort();
}

async function main() {
  if (!fs.existsSync(path.join(OUT, "index.html"))) throw new Error(`${OUT} has no index.html: run \`npm run build\` first`);
  const axeSource = fs.readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
  const server = await staticServer(OUT);
  const base = `http://127.0.0.1:${server.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "desk-a11y-"));
  const { child, cdp } = await launch(findBrowser(), profile);
  const routes = routesOf(OUT);
  const problems = [];
  let loads = 0;
  try {
    await cdp.send("Page.enable");
    let loaded = null;
    cdp.on((m) => { if (m.method === "Page.loadEventFired" && loaded) loaded(); });
    for (const lang of LANGS) {
      const { identifier } = await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: `try { localStorage.setItem("delentia-desk-lang", "${lang}"); localStorage.setItem("delentia_desk_mode", "advanced"); } catch (e) {}` });
      for (const width of WIDTHS) {
        await cdp.send("Emulation.setDeviceMetricsOverride", { width, height: 800, deviceScaleFactor: 1, mobile: false });
        for (const route of routes) {
          const done = new Promise((r) => { loaded = r; setTimeout(r, 15000); });
          await cdp.send("Page.navigate", { url: base + route });
          await done;
          await sleep(1500);                                          // client rendering and the failed API calls settle
          await cdp.send("Runtime.evaluate", { expression: axeSource });
          const result = await cdp.send("Runtime.evaluate", {
            awaitPromise: true, returnByValue: true,
            expression: `axe.run(document, { runOnly: { type: "tag", values: ${JSON.stringify(TAGS)} } }).then((r) => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, lang: document.documentElement.lang, v: r.violations.map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, sample: x.nodes[0].target.join(" ").slice(0, 90) })) }))`,
          });
          const r = result.result.value;
          loads++;
          if (!r) { problems.push(`${lang}/${width} ${route}: axe did not run (${JSON.stringify(result.exceptionDetails || {}).slice(0, 120)})`); continue; }
          if (r.overflow > 0) problems.push(`${lang}/${width} ${route}: scrolls sideways by ${r.overflow}px`);
          if (r.lang !== lang) problems.push(`${lang}/${width} ${route}: <html lang> is "${r.lang}"`);
          for (const v of r.v) problems.push(`${lang}/${width} ${route}: ${v.id} (${v.impact}) x${v.n} e.g. ${v.sample}`);
        }
      }
      await cdp.send("Page.removeScriptToEvaluateOnNewDocument", { identifier });
    }
  } finally {
    cdp.close();
    child.kill();
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* a browser still holds a file: the temp folder is left to the system */ }
  }
  console.log(`${loads} page loads (${routes.length} pages x ${LANGS.join("/")} x ${WIDTHS.join("/")} px)`);
  if (problems.length) {
    console.error(`${problems.length} problem(s):\n  ` + problems.join("\n  "));
    process.exit(1);
  }
  console.log("ok - no axe violation and no sideways scroll on any page");
}

main().catch((e) => { console.error(e.message || e); process.exit(2); });
