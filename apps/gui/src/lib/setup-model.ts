/**
 * The Setup assistant's logic, with no React and no network, so plain node can test it.
 *
 *  - what the browser can do about approving with a device (the check that used to need the developer console),
 *  - signing a decision with an approver key FILE inside the person's own browser (the private key is read from the file the person picks, used in memory and never sent anywhere;
 *    only the signature and the public key go to the server — the same two values `delentia approvals sign` prints),
 *  - the protection levels a person can choose, and which step to show next.
 */

export type Lang = "th" | "en";
export type BrowserFacts = { hostname: string; protocol: string; port?: string; hasApi: boolean; platformAvailable: boolean | null };
export type BrowserVerdict = { level: "ok" | "warn" | "fail"; text: string; fix: string };

/** What this browser can do for "approve with this device". `platformAvailable` is the answer of PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(), or null when it could not be asked. */
export function browserVerdict(f: BrowserFacts, lang: Lang = "en"): BrowserVerdict {
  const th = lang === "th";
  if (!f.hasApi) {
    return { level: "fail", text: th ? "เบราว์เซอร์นี้ยืนยันด้วยอุปกรณ์ไม่ได้" : "This browser can not confirm with a device.",
      fix: th ? "เปิดหน้านี้ด้วย Microsoft Edge หรือ Google Chrome รุ่นใหม่" : "Open this page in a recent Microsoft Edge or Google Chrome." };
  }
  const isNumber = /^\d+\.\d+\.\d+\.\d+$/.test(f.hostname) || f.hostname.includes(":");
  if (f.hostname !== "localhost") {
    const port = f.port ? `:${f.port}` : "";
    return { level: "fail",
      text: th ? `หน้านี้เปิดด้วย ${isNumber ? "ตัวเลข" : "ชื่ออื่น"} (${f.hostname}) อุปกรณ์ยืนยันไม่ได้` : `This page was opened as ${f.hostname}, and a device can not confirm there.`,
      fix: th ? `เปิดเป็น ${f.protocol}//localhost${port} แทน` : `Open ${f.protocol}//localhost${port} instead.` };
  }
  if (f.platformAvailable === false) {
    return { level: "warn",
      text: th ? "คอมพิวเตอร์เครื่องนี้ยังไม่ได้ตั้ง Windows Hello (ใบหน้า ลายนิ้วมือ หรือ PIN)" : "Windows Hello (face, fingerprint or PIN) is not set up on this computer.",
      fix: th ? "เปิด Windows Settings → Accounts → Sign-in options แล้วตั้ง PIN อย่างน้อยหนึ่งแบบ จากนั้นกด “ตรวจอีกครั้ง” (ถ้าไม่ตั้ง ยังใช้กุญแจ approver แทนได้)" : "Open Windows Settings → Accounts → Sign-in options and set up a PIN at least. Then press “Check again”. (Without it you can still use an approver key file.)" };
  }
  if (f.platformAvailable === null) {
    return { level: "warn", text: th ? "ตรวจไม่ได้ว่าเครื่องนี้มี Windows Hello หรือไม่" : "Could not tell whether this computer has Windows Hello.", fix: th ? "ลองเพิ่มอุปกรณ์ในขั้นต่อไป ถ้าไม่ขึ้นหน้าต่าง Windows Hello ให้ใช้กุญแจ approver แทน" : "Try adding the device in the next step. If no Windows Hello window appears, use an approver key file." };
  }
  return { level: "ok", text: th ? "เบราว์เซอร์และเครื่องนี้พร้อมยืนยันด้วย Windows Hello" : "This browser and computer are ready to confirm with Windows Hello.", fix: "" };
}

// ---------------------------------------------------------------- signing with a key file, in the browser

/** The exact bytes the server verifies (approvals.approval_message): delentia-approval:v1:<id>:<action_sha256>:<DECISION>. */
export function approvalMessage(approvalId: string, actionSha256: string, decision: "APPROVED" | "REJECTED"): string {
  return `delentia-approval:v1:${approvalId}:${actionSha256}:${decision}`;
}

/** The DER bytes inside a PKCS#8 PEM ("-----BEGIN PRIVATE KEY-----"). Anything else (a public key, an RSA key, an encrypted key) is refused with a sentence. */
export function pemToDer(pem: string, lang: Lang = "en"): Uint8Array {
  const th = lang === "th";
  const text = pem.trim();
  if (text.includes("BEGIN ENCRYPTED PRIVATE KEY")) throw new Error(th ? "ไฟล์กุญแจนี้มีรหัสผ่านล็อกอยู่ ใช้ในหน้านี้ไม่ได้ ให้ใช้คำสั่ง delentia approvals sign แทน" : "This key file is password-protected, which this page can not use. Use `delentia approvals sign` instead.");
  const m = /-----BEGIN PRIVATE KEY-----([\s\S]+?)-----END PRIVATE KEY-----/.exec(text);
  if (!m) throw new Error(th ? "นี่ไม่ใช่ไฟล์กุญแจส่วนตัวของ approver (ต้องขึ้นต้นด้วย BEGIN PRIVATE KEY)" : "This is not an approver private key file (it must start with BEGIN PRIVATE KEY).");
  const binary = atob(m[1].replace(/\s+/g, ""));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

const hex = (bytes: Uint8Array) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

function fromB64Url(text: string): Uint8Array {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export type SignedBody = { decision: "APPROVED" | "REJECTED"; public_key_hex: string; signature_hex: string };

/** Signs a decision with an Ed25519 private key in PKCS#8 PEM, the way `delentia approvals sign` does. The key is imported non-extractable for signing only after its public half is read. */
export async function signWithKeyFile(pem: string, approvalId: string, actionSha256: string, decision: "APPROVED" | "REJECTED", lang: Lang = "en", subtle: SubtleCrypto = globalThis.crypto?.subtle): Promise<SignedBody> {
  const th = lang === "th";
  if (!subtle) throw new Error(th ? "เบราว์เซอร์นี้ไม่มี WebCrypto" : "This browser has no WebCrypto.");
  const der = pemToDer(pem, lang);
  let publicHex: string;
  let key: CryptoKey;
  try {
    // the public half comes out of an extractable copy that is thrown away at once; the key that signs can not be exported
    const probe = await subtle.importKey("pkcs8", der as unknown as BufferSource, { name: "Ed25519" } as unknown as AlgorithmIdentifier, true, ["sign"]);
    const jwk = await subtle.exportKey("jwk", probe);
    if (!jwk.x) throw new Error("no public half");
    publicHex = hex(fromB64Url(jwk.x));
    key = await subtle.importKey("pkcs8", der as unknown as BufferSource, { name: "Ed25519" } as unknown as AlgorithmIdentifier, false, ["sign"]);
  } catch {
    throw new Error(th ? "อ่านกุญแจนี้ไม่ได้: ต้องเป็นกุญแจ Ed25519 และเบราว์เซอร์ต้องรองรับ (Edge/Chrome รุ่นใหม่) หรือใช้คำสั่ง delentia approvals sign แทน" : "Could not read this key: it must be an Ed25519 key and the browser must support it (a recent Edge/Chrome), or use `delentia approvals sign` instead.");
  }
  const signature = await subtle.sign({ name: "Ed25519" } as unknown as AlgorithmIdentifier, key, new TextEncoder().encode(approvalMessage(approvalId, actionSha256, decision)));
  return { decision, public_key_hex: publicHex, signature_hex: hex(new Uint8Array(signature)) };
}

// ---------------------------------------------------------------- protection levels

export type LevelId = "standard" | "plan_first";
export type Level = { id: LevelId; template: "argaware" | "planfirst"; en: string; th: string; whyEn: string; whyTh: string; changesEn: string[]; changesTh: string[] };

/** What a person can choose in plain words. The rules themselves come from the server's templates; nothing here weakens a rule. "Strict" and hand-written rules stay on the FDIA / Policy page. */
export const LEVELS: Level[] = [
  { id: "standard", template: "argaware", en: "Standard", th: "มาตรฐาน",
    whyEn: "Risky work stops and asks you, one action at a time. This is what you have unless you change it.", whyTh: "งานเสี่ยงหยุดรอถามคุณทีละการกระทำ ค่านี้ใช้อยู่แล้วถ้าไม่เปลี่ยน",
    changesEn: [], changesTh: [] },
  { id: "plan_first", template: "planfirst", en: "Plan first (recommended if you want to see everything before it happens)", th: "แผนก่อน (แนะนำถ้าอยากเห็นทุกอย่างก่อนลงมือ)",
    whyEn: "For deleting, sending out, money, permissions, publishing, undoing and moving or shutting down, the agent shows the whole plan once and nothing runs until you confirm it.",
    whyTh: "สำหรับการลบ ส่งออก เงิน สิทธิ์ เผยแพร่ ย้อนกลับ ย้ายหรือปิดระบบ เอเจนต์แสดงแผนทั้งหมดให้ดูครั้งเดียว และไม่มีอะไรรันจนกว่าคุณยืนยัน",
    changesEn: ["A small edit of one file that you named in your request runs without asking (the change is saved first and can be undone).", "When the evidence is thin, you are asked instead of the request being refused."],
    changesTh: ["แก้ไฟล์เล็ก ๆ หนึ่งไฟล์ที่คุณระบุชื่อในคำขอ รันได้โดยไม่ถาม (บันทึกของเดิมไว้ก่อน ย้อนคืนได้)", "เมื่อหลักฐานบางเกินไป ระบบจะถามคุณ แทนที่จะปฏิเสธคำขอ"] },
];

// ---------------------------------------------------------------- the model step

export type ModelAdvice = { level: "ok" | "warn" | "fail"; text: string; fix: string };

/** What the readiness state of the chosen model means for a person, and what to do. The states are the ones the server names (readiness.py). */
export function modelAdvice(state: string, name: string, lang: Lang = "en"): ModelAdvice {
  const th = lang === "th";
  switch (state) {
    case "ready":
    case "configured":
      return { level: "ok", text: th ? `มีโมเดลที่เลือกไว้แล้ว: ${name}` : `A model is chosen: ${name}`, fix: state === "configured" ? (th ? "ยังไม่ได้ลองเรียกจริง คำขอแรกจะบอกว่าใช้ได้หรือไม่" : "It has not been called yet; your first request will show whether it works.") : "" };
    case "server_down":
      return { level: "fail", text: th ? "โปรแกรมโมเดลในเครื่อง (Ollama) ยังไม่ทำงาน" : "The model program on this computer (Ollama) is not running.",
        fix: th ? "ติดตั้งจาก ollama.com แล้วเปิดโปรแกรม จากนั้นกด “ตรวจอีกครั้ง” หรือเลือกโมเดลออนไลน์แทน" : "Install it from ollama.com and start it, then press “Check again”, or choose an online model instead." };
    case "model_missing":
      return { level: "fail", text: th ? `ยังไม่ได้ติดตั้งโมเดล ${name} ในเครื่อง` : `The model ${name} is not installed on this computer.`,
        fix: th ? "เลือกโมเดลที่ติดตั้งแล้วด้านล่าง หรือพิมพ์ ollama pull <ชื่อโมเดล> ในเทอร์มินัลหนึ่งครั้ง" : "Pick one that is installed below, or type ollama pull <model name> in a terminal once." };
    case "no_key":
      return { level: "fail", text: th ? "โมเดลที่เลือกต้องใช้คีย์" : "The chosen model needs a key.", fix: th ? "ใส่คีย์ด้านล่าง" : "Enter the key below." };
    default:
      return { level: "warn", text: th ? "ยังไม่ทราบสถานะของโมเดล" : "The state of the model is not known.", fix: th ? "กด “ตรวจอีกครั้ง”" : "Press “Check again”." };
  }
}

/** Said next to the local option, and said plainly: what was measured on this project's own tests with small local models on an ordinary computer. */
export const LOCAL_NOTE = {
  en: "Free and private, but small models on an ordinary computer are slow (often a minute or more per request) and make mistakes choosing tools. Good for trying Delentia; for real work an online model is usually needed. Delentia itself has not yet been measured with a strong online model.",
  th: "ฟรีและเป็นส่วนตัว แต่โมเดลขนาดเล็กบนคอมพิวเตอร์ทั่วไปช้า (มักนานหนึ่งนาทีขึ้นไปต่อคำขอ) และเลือกเครื่องมือผิดได้ เหมาะกับการลองใช้ Delentia งานจริงมักต้องใช้โมเดลออนไลน์ และตัว Delentia เองยังไม่เคยถูกวัดกับโมเดลออนไลน์ที่เก่ง",
};
export const ONLINE_NOTE = {
  en: "An online model costs money every time it is used. Before you paste a key, set a spending limit on the key at the provider (OpenRouter: Keys → credit limit). The key is kept in this program's memory only and is forgotten when it stops; it is never written to disk.",
  th: "โมเดลออนไลน์เสียเงินทุกครั้งที่ใช้ ก่อนวางคีย์ ให้ตั้งวงเงินของคีย์ที่ผู้ให้บริการ (OpenRouter: Keys → credit limit) คีย์ถูกเก็บในหน่วยความจำของโปรแกรมเท่านั้น และถูกลืมเมื่อโปรแกรมหยุด ไม่เคยเขียนลงดิสก์",
};

/** The installed Ollama models a person could chat with: embedding and reranking models are for memory search, not for answering, and picking one would make every request fail. */
export function chatModels(installed: string[]): string[] {
  return installed.filter((n) => !/(^|[-_/])(bge|embed|embedding|minilm|rerank|reranker)([-_:.]|$)|nomic-embed|mxbai-embed|snowflake-arctic-embed|arctic-embed/i.test(n));
}

export type CatalogModel = { id: string; prompt_price_per_mtok: number | null; completion_price_per_mtok: number | null; supports_json_mode: boolean; supports_tools: boolean };

/** The cheapest models that can take tools and a JSON reply (the loop needs both), by input price, free (":free") ones last because their limits make them poor for real work. */
export function cheapestToolModels(catalog: CatalogModel[], limit = 25): CatalogModel[] {
  const usable = catalog.filter((m) => m.supports_tools && m.supports_json_mode && typeof m.prompt_price_per_mtok === "number" && Number.isFinite(m.prompt_price_per_mtok) && m.prompt_price_per_mtok >= 0);
  const paid = usable.filter((m) => !m.id.endsWith(":free")).sort((a, b) => (a.prompt_price_per_mtok as number) - (b.prompt_price_per_mtok as number) || a.id.localeCompare(b.id));
  const free = usable.filter((m) => m.id.endsWith(":free")).sort((a, b) => a.id.localeCompare(b.id));
  return [...paid, ...free].slice(0, limit);
}

export type Facts = { browserOk: boolean; modelOk: boolean; hasApprover: boolean; policyChosen: boolean; checkupRan: boolean; practiceDone: boolean };
export const STEP_IDS = ["browser", "model", "approver", "level", "checkup", "practice"] as const;
export type StepId = (typeof STEP_IDS)[number];

/** The first step that is not done yet, or null when all are. The level step counts as done when a person has chosen one this visit or the system already has a policy file. */
export function nextStep(f: Facts): StepId | null {
  const done: Record<StepId, boolean> = { browser: f.browserOk, model: f.modelOk, approver: f.hasApprover, level: f.policyChosen, checkup: f.checkupRan, practice: f.practiceDone };
  return STEP_IDS.find((id) => !done[id]) ?? null;
}
