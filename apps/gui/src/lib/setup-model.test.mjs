// Run with: npm run test:setup  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { LEVELS, LOCAL_NOTE, ONLINE_NOTE, STEP_IDS, approvalMessage, browserVerdict, cheapestToolModels, chatModels, modelAdvice, nextStep, pemToDer, signWithKeyFile } from "./setup-model.ts";

let n = 0;
const test = async (name, fn) => { await fn(); n++; console.log("ok -", name); };

// A throw-away key made from a fixed seed, built into a PEM at run time (no private-key text is kept in the repository).
const SEED = Uint8Array.from({ length: 32 }, (_, i) => i);
const PKCS8_PREFIX = Uint8Array.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
const der = new Uint8Array(PKCS8_PREFIX.length + 32);
der.set(PKCS8_PREFIX);
der.set(SEED, PKCS8_PREFIX.length);
const b64 = Buffer.from(der).toString("base64").match(/.{1,64}/g).join("\n");
const PEM = ["-----BEGIN", "PRIVATE KEY-----"].join(" ") + "\n" + b64 + "\n" + ["-----END", "PRIVATE KEY-----"].join(" ") + "\n";

// The values the Python side (approvals.sign_decision with the same seed) produced. Ed25519 is deterministic, so the two must agree byte for byte.
const ID = "ab12cd34ef56";
const SHA = "f".repeat(64);
const PUBLIC = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8";
const SIGNED = "cdb7b8df57d332e1391f56567de63606b6f866867e64b9723b69a2a409112f9fa4a7663568a70340121c1ff073d821e2690ddfcdd5863fe9d768a9e57314a409";
const REJECTED = "f861d2f4969ef873c2e98d24ee44eb87e19fa68fb7f55636d4657a1095ff87a5042444a66b9c6e1cea0a267bc09c084d365b0db5adba595cb25d3adacd36510a";

await test("the message is the one the server verifies", () => {
  assert.equal(approvalMessage(ID, SHA, "APPROVED"), `delentia-approval:v1:${ID}:${SHA}:APPROVED`);
});
await test("a signature made in the browser equals the one `delentia approvals sign` makes", async () => {
  const body = await signWithKeyFile(PEM, ID, SHA, "APPROVED");
  assert.deepEqual(body, { decision: "APPROVED", public_key_hex: PUBLIC, signature_hex: SIGNED });
  assert.equal((await signWithKeyFile(PEM, ID, SHA, "REJECTED")).signature_hex, REJECTED);
});
await test("the signature is for this action and this decision only", async () => {
  const other = await signWithKeyFile(PEM, ID, "e".repeat(64), "APPROVED");
  assert.notEqual(other.signature_hex, SIGNED);
  assert.notEqual((await signWithKeyFile(PEM, "ab12cd34ef57", SHA, "APPROVED")).signature_hex, SIGNED);
});
await test("what is not an approver private key is refused with a sentence, in both languages", async () => {
  for (const lang of ["en", "th"]) {
    await assert.rejects(() => signWithKeyFile("-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----", ID, SHA, "APPROVED", lang), /BEGIN PRIVATE KEY/);
    await assert.rejects(() => signWithKeyFile("-----BEGIN ENCRYPTED PRIVATE KEY-----\nAAAA\n-----END ENCRYPTED PRIVATE KEY-----", ID, SHA, "APPROVED", lang), lang === "en" ? /password-protected/ : /รหัสผ่าน/);
  }
  await assert.rejects(() => signWithKeyFile("-----BEGIN PRIVATE KEY-----\nAAAAAAAA\n-----END PRIVATE KEY-----", ID, SHA, "APPROVED"), /Ed25519/);
  assert.throws(() => pemToDer("not a key"), /BEGIN PRIVATE KEY/);
});
await test("the key text never appears in what is sent", async () => {
  const body = await signWithKeyFile(PEM, ID, SHA, "APPROVED");
  assert.ok(!JSON.stringify(body).includes(b64.slice(0, 20)) && !JSON.stringify(body).includes(Buffer.from(SEED).toString("hex")));
});

const base = { hostname: "localhost", protocol: "http:", port: "3010", hasApi: true, platformAvailable: true };
await test("a browser at localhost with Windows Hello is ready", () => {
  assert.equal(browserVerdict(base).level, "ok");
});
await test("every way the check can fail says what to do", () => {
  for (const lang of ["en", "th"]) {
    const noApi = browserVerdict({ ...base, hasApi: false }, lang);
    const ip = browserVerdict({ ...base, hostname: "127.0.0.1" }, lang);
    const noHello = browserVerdict({ ...base, platformAvailable: false }, lang);
    const unknown = browserVerdict({ ...base, platformAvailable: null }, lang);
    assert.equal(noApi.level, "fail"); assert.equal(ip.level, "fail"); assert.equal(noHello.level, "warn"); assert.equal(unknown.level, "warn");
    for (const v of [noApi, ip, noHello, unknown]) assert.ok(v.text && v.fix);
    assert.ok(ip.fix.includes("http://localhost:3010"));
  }
});
await test("an address that is neither localhost nor a number is refused too", () => {
  assert.equal(browserVerdict({ ...base, hostname: "mypc.local" }).level, "fail");
});

await test("the levels: two, the standard one changes nothing, the other lists what it loosens in both languages", () => {
  assert.deepEqual(LEVELS.map((l) => l.id), ["standard", "plan_first"]);
  assert.equal(LEVELS[0].changesEn.length, 0);
  assert.ok(LEVELS[1].changesEn.length === 2 && LEVELS[1].changesEn.length === LEVELS[1].changesTh.length);
  assert.deepEqual(LEVELS.map((l) => l.template), ["argaware", "planfirst"]);
});
await test("the next step is the first one not done", () => {
  const all = { browserOk: true, modelOk: true, hasApprover: true, policyChosen: true, checkupRan: true, practiceDone: true };
  assert.equal(nextStep(all), null);
  assert.equal(nextStep({ ...all, browserOk: false }), "browser");
  assert.equal(nextStep({ ...all, modelOk: false, practiceDone: false }), "model");
  assert.equal(nextStep({ ...all, hasApprover: false, practiceDone: false }), "approver");
  assert.equal(nextStep({ ...all, practiceDone: false }), "practice");
  assert.deepEqual([...STEP_IDS], ["browser", "model", "approver", "level", "checkup", "practice"]);
});
await test("every model state says what it means and what to do, in both languages", () => {
  for (const lang of ["en", "th"]) {
    for (const state of ["ready", "configured", "server_down", "model_missing", "no_key", "something_new"]) {
      const a = modelAdvice(state, "qwen3:8b", lang);
      assert.ok(a.text.length > 10 && ["ok", "warn", "fail"].includes(a.level), state);
      if (a.level !== "ok") assert.ok(a.fix.length > 5, state);
    }
    assert.equal(modelAdvice("server_down", "m", lang).level, "fail");
    assert.equal(modelAdvice("ready", "m", lang).level, "ok");
  }
  assert.ok(modelAdvice("configured", "m").fix.includes("not been called"));            // a key is not proof that the model answers
  assert.ok(modelAdvice("model_missing", "qwen3:8b").text.includes("qwen3:8b"));
});
await test("the notes say the true things: local is slow and weak at tools, online costs money and the key is not written to disk", () => {
  assert.ok(/slow/.test(LOCAL_NOTE.en) && /not yet been measured/.test(LOCAL_NOTE.en) && LOCAL_NOTE.th.length > 40);
  assert.ok(/costs money/.test(ONLINE_NOTE.en) && /never written to disk/.test(ONLINE_NOTE.en) && /spending limit/.test(ONLINE_NOTE.en) && ONLINE_NOTE.th.length > 40);
});
await test("only models that can answer are offered from the local list, never embedding or reranking ones", () => {
  const got = chatModels(["bge-m3:latest", "bonsai-27b:latest", "delentia-os:latest", "llama3.2:3b", "nomic-embed-text:latest", "qwen2.5:7b", "qwen2.5vl:3b", "qwen3:8b", "mxbai-embed-large", "snowflake-arctic-embed2", "bge-reranker-v2", "all-minilm"]);
  assert.deepEqual(got, ["bonsai-27b:latest", "delentia-os:latest", "llama3.2:3b", "qwen2.5:7b", "qwen2.5vl:3b", "qwen3:8b"]);
  assert.deepEqual(chatModels([]), []);
});
await test("the cheapest usable online models: tools and JSON needed, priced, cheapest first, free ones last, never more than asked", () => {
  const m = (id, p, tools = true, json = true) => ({ id, prompt_price_per_mtok: p, completion_price_per_mtok: p, supports_tools: tools, supports_json_mode: json });
  const got = cheapestToolModels([m("b/dear", 3), m("a/cheap", 0.1), m("z/free:free", 0), m("c/notools", 0.01, false), m("d/nojson", 0.01, true, false), m("e/unpriced", null), m("f/mid", 1)], 25);
  assert.deepEqual(got.map((x) => x.id), ["a/cheap", "f/mid", "b/dear", "z/free:free"]);
  assert.equal(cheapestToolModels(Array.from({ length: 40 }, (_, i) => m(`v/m${i}`, i)), 5).length, 5);
  assert.deepEqual(cheapestToolModels([]), []);
});
await test("the practice step runs only the approved action: it never calls the resume that continues with a model", async () => {
  const { readFileSync } = await import("node:fs");
  const page = readFileSync(new URL("../app/setup/page.tsx", import.meta.url), "utf8");
  assert.ok(page.includes("desk.runApproved(practice.approval_id)"));
  assert.ok(!/desk\.resume\(/.test(page));
  const client = readFileSync(new URL("./desk-api.ts", import.meta.url), "utf8");
  assert.ok(/runApproved:[\s\S]{0,200}continue: false/.test(client));
});
console.log(`${n} tests passed`);
