/**
 * Reads the JSON that `delentia approvals sign` prints, and says exactly what is wrong with it when it is wrong.
 * A pure function (no React, no network) so it can be tested with plain node.
 */
export type SignedDecision = { decision: "APPROVED" | "REJECTED"; public_key_hex: string; signature_hex: string };
export type ParseResult = { ok: true; body: SignedDecision } | { ok: false; message: string };

const HEX = /^[0-9a-fA-F]+$/;

/** Returns the end index (exclusive) of the first complete {...} object that starts at `start`, or -1. */
function endOfFirstObject(text: string, start: number): number {
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === "\\") i++;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

export function parseSignedDecision(text: string, lang: "th" | "en" = "en"): ParseResult {
  const th = lang === "th";
  const fail = (en: string, thai: string): ParseResult => ({ ok: false, message: th ? thai : en });
  const trimmed = text.trim();
  if (!trimmed) return fail("Paste the JSON printed by `delentia approvals sign`.", "วาง JSON ที่ `delentia approvals sign` พิมพ์ออกมา");

  const first = trimmed.indexOf("{");
  if (first < 0) return fail("No { found: this is not the JSON that `delentia approvals sign` prints.", "ไม่พบ { จึงไม่ใช่ JSON ที่ `delentia approvals sign` พิมพ์ออกมา");
  const end = endOfFirstObject(trimmed, first);
  if (end < 0) return fail("The JSON is cut off: a { is never closed. Copy the whole output, to the last }.", "JSON ขาดตอน: มี { ที่ไม่ปิด คัดลอกให้ครบจนถึง } ตัวสุดท้าย");
  const rest = trimmed.slice(end).trim();
  if (rest.includes("{")) {
    return fail("Two JSON objects were pasted one after the other (the signature was pasted twice?). Clear the box and paste it once.", "วาง JSON ซ้อนกันสองก้อน (วางลายเซ็นซ้ำหรือเปล่า) ล้างช่องแล้ววางครั้งเดียว");
  }
  if (rest) return fail(`There is text after the closing }: "${rest.slice(0, 30)}". Paste only the JSON.`, `มีข้อความหลัง } ปิด: "${rest.slice(0, 30)}" ให้วางเฉพาะ JSON`);

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(trimmed.slice(first, end));
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return fail(`Not valid JSON (${detail}). Use the straight quotes " that the command prints; a word processor may have changed them.`, `ไม่ใช่ JSON ที่ถูกต้อง (${detail}) ให้ใช้เครื่องหมาย " ตรง ๆ ตามที่คำสั่งพิมพ์ โปรแกรมพิมพ์เอกสารอาจแปลงให้เป็นแบบอื่น`);
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) return fail("The JSON must be an object { ... }.", "JSON ต้องเป็น object { ... }");

  const missing = ["decision", "public_key_hex", "signature_hex"].filter((k) => typeof body[k] !== "string" || !(body[k] as string).trim());
  if (missing.length) return fail(`Missing: ${missing.join(", ")}.`, `ขาดฟิลด์: ${missing.join(", ")}`);

  const decision = String(body.decision).toUpperCase();
  if (decision !== "APPROVED" && decision !== "REJECTED") return fail(`decision must be APPROVED or REJECTED, not "${body.decision}".`, `decision ต้องเป็น APPROVED หรือ REJECTED ไม่ใช่ "${body.decision}"`);

  const key = String(body.public_key_hex).trim();
  const sig = String(body.signature_hex).trim();
  if (!HEX.test(key) || key.length !== 64) return fail(`public_key_hex must be 64 hexadecimal characters (it has ${key.length}${HEX.test(key) ? "" : ", and some are not hex"}).`, `public_key_hex ต้องเป็นเลขฐานสิบหก 64 ตัว (ตอนนี้มี ${key.length} ตัว${HEX.test(key) ? "" : " และบางตัวไม่ใช่เลขฐานสิบหก"})`);
  if (!HEX.test(sig) || sig.length !== 128) return fail(`signature_hex must be 128 hexadecimal characters (it has ${sig.length}${HEX.test(sig) ? "" : ", and some are not hex"}).`, `signature_hex ต้องเป็นเลขฐานสิบหก 128 ตัว (ตอนนี้มี ${sig.length} ตัว${HEX.test(sig) ? "" : " และบางตัวไม่ใช่เลขฐานสิบหก"})`);

  return { ok: true, body: { decision, public_key_hex: key.toLowerCase(), signature_hex: sig.toLowerCase() } };
}
