/**
 * "Can I use this yet?" in words (Round 101, UX audit). The server answers with checks and states (rct_control_plane/readiness.py); this file turns each state into a label, what it means, and the next step,
 * in both languages. Pure (no React, no network) so a plain node test checks every state has both texts and that the next step names a page the person can open.
 */
export type Lang = "th" | "en";
export type CheckId = "model" | "approver" | "first_request";
export interface ReadinessCheck {
  id: CheckId; essential: boolean; ok: boolean; state: string;
  provider?: string; model?: string; installed?: string[]; keys?: number; devices?: number; episodes?: number;
}
export interface ReadinessText { label: string; what: string; next: string; href: string | null }

type Pair = { en: string; th: string };
const P = (en: string, th: string): Pair => ({ en, th });

/** Every (check, state) the server can produce. */
export const STATES: Record<string, (c: ReadinessCheck) => { label: Pair; what: Pair; next: Pair; href: string | null }> = {
  "model:ready": (c) => ({ label: P(`The model is ready: ${c.model}`, `โมเดลพร้อม: ${c.model}`), what: P("The local model service answers and has this model.", "บริการโมเดลในเครื่องตอบและมีโมเดลนี้แล้ว"), next: P("Nothing to do.", "ไม่ต้องทำอะไร"), href: null }),
  "model:configured": (c) => ({ label: P(`A model is chosen: ${c.model} (${c.provider})`, `เลือกโมเดลแล้ว: ${c.model} (${c.provider})`), what: P("It has not been tested from here, but its key is in place.", "ยังไม่ได้ทดสอบจากหน้านี้ แต่มีกุญแจพร้อมแล้ว"), next: P("Ask something in Chat to see it work.", "ลองสั่งงานที่หน้าแชตเพื่อดูว่าทำงานไหม"), href: "/chat" }),
  "model:server_down": () => ({ label: P("The local model service is not running", "บริการโมเดลในเครื่องยังไม่ทำงาน"), what: P("The agent thinks with a model; without one it can not do anything.", "เอเจนต์คิดด้วยโมเดล ถ้าไม่มีก็ทำอะไรไม่ได้"), next: P("Start Ollama and wait a moment, or choose an online model on the Models page.", "เปิดโปรแกรม Ollama แล้วรอสักครู่ หรือเลือกโมเดลออนไลน์ที่หน้าโมเดล"), href: "/llm" }),
  "model:model_missing": (c) => ({ label: P(`The model ${c.model} is not downloaded`, `ยังไม่ได้ดาวน์โหลดโมเดล ${c.model}`), what: P(`The model service is running but does not have it${c.installed?.length ? ` (it has: ${c.installed.slice(0, 4).join(", ")})` : ""}.`, `บริการโมเดลทำงานอยู่แต่ไม่มีโมเดลนี้${c.installed?.length ? ` (ที่มี: ${c.installed.slice(0, 4).join(", ")})` : ""}`), next: P("Open the Models page and choose one it has, or download this one with Ollama.", "ไปที่หน้าโมเดลเพื่อเลือกตัวที่มีอยู่ หรือดาวน์โหลดตัวนี้ด้วย Ollama"), href: "/llm" }),
  "model:no_key": (c) => ({ label: P(`The key for ${c.provider} is missing`, `ยังไม่มีกุญแจ (API key) ของ ${c.provider}`), what: P("An online model needs the key from its provider. It is kept in the server's memory only.", "โมเดลออนไลน์ต้องใช้กุญแจจากผู้ให้บริการ เก็บไว้ในหน่วยความจำของเซิร์ฟเวอร์เท่านั้น"), next: P("Enter it on the Models page.", "ใส่ที่หน้าโมเดล"), href: "/llm" }),
  "approver:ready": (c) => ({ label: P(`Someone can approve (${c.keys ?? 0} key, ${c.devices ?? 0} device)`, `มีผู้อนุมัติแล้ว (${c.keys ?? 0} กุญแจ, ${c.devices ?? 0} เครื่อง)`), what: P("Risky actions will stop and wait for that person.", "งานเสี่ยงจะหยุดรอคนนั้น"), next: P("Nothing to do.", "ไม่ต้องทำอะไร"), href: null }),
  "approver:nobody": () => ({ label: P("Nobody can approve yet", "ยังไม่มีใครอนุมัติงานได้"), what: P("Risky actions (delete, send out, money, publish) would wait forever, because nothing can approve them.", "งานเสี่ยง (ลบ ส่งออก เงิน เผยแพร่) จะหยุดรอตลอดไป เพราะไม่มีใครอนุมัติได้"), next: P("Create the first approver key once with `delentia setup --approver-key-here`, then add this computer under Settings so Windows Hello can confirm.", "สร้างกุญแจผู้อนุมัติครั้งแรกด้วย `delentia setup --approver-key-here` แล้วเพิ่มเครื่องนี้ที่หน้าตั้งค่า เพื่อให้ Windows Hello ยืนยันได้"), href: "/settings" }),
  "first_request:done": (c) => ({ label: P(`You have run ${c.episodes} request(s)`, `คุณสั่งงานไปแล้ว ${c.episodes} ครั้ง`), what: P("The record of what it did is on the Sessions page.", "บันทึกสิ่งที่ทำอยู่ที่หน้าเซสชัน"), next: P("Nothing to do.", "ไม่ต้องทำอะไร"), href: null }),
  "first_request:not_yet": () => ({ label: P("Try a first request", "ลองสั่งงานแรก"), what: P("Nothing has been run yet. A small read-only request is a safe start.", "ยังไม่เคยสั่งงาน เริ่มด้วยคำขอเล็ก ๆ ที่ไม่แก้อะไรจะปลอดภัย"), next: P("Open Chat and ask it to read a file and summarise it.", "เปิดหน้าแชตแล้วให้มันอ่านไฟล์และสรุป"), href: "/chat" }),
};

export function describeCheck(check: ReadinessCheck, lang: Lang): ReadinessText {
  const entry = STATES[`${check.id}:${check.state}`];
  if (!entry) return { label: `${check.id}: ${check.state}`, what: lang === "th" ? "สถานะนี้ยังไม่มีคำอธิบาย" : "This state has no description yet.", next: lang === "th" ? "ดูหน้า Governance" : "See the Governance page.", href: null };
  const e = entry(check);
  return { label: e.label[lang], what: e.what[lang], next: e.next[lang], href: e.href };
}

export function knownStates(): string[] {
  return Object.keys(STATES);
}
