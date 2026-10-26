/**
 * The browser side of approving with a device (Windows Hello, Touch ID, a phone, a security key).
 * Everything that can be decided without a browser is a pure function here so plain node can test it; only the small wrappers at the bottom touch navigator.credentials.
 * The server never trusts anything in this file: it re-checks the challenge, the site, the user-verification flag and the signature itself.
 */

export function toBase64Url(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  for (let i = 0; i < view.length; i++) binary += String.fromCharCode(view[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromBase64Url(text: string): Uint8Array {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

type Json = Record<string, unknown>;

/** The server's registration options carry base64url strings; the browser wants byte buffers. */
export function creationOptions(server: Json): Json {
  const user = server.user as Json;
  return { ...server, challenge: fromBase64Url(String(server.challenge)), user: { ...user, id: fromBase64Url(String(user.id)) } };
}

/** The server's assertion options: the challenge and each allowed credential id become byte buffers. */
export function requestOptions(server: Json): Json {
  const allow = (server.allowCredentials as Json[] | undefined) ?? [];
  return { ...server, challenge: fromBase64Url(String(server.challenge)), allowCredentials: allow.map((c) => ({ ...c, id: fromBase64Url(String(c.id)) })) };
}

type CredentialLike = { id: string; rawId: ArrayBuffer; type: string; response: Record<string, ArrayBuffer | null | undefined> };

/** What the server expects back: every buffer as base64url. */
export function serializeCredential(cred: CredentialLike): Json {
  const response: Json = {};
  for (const [name, value] of Object.entries(cred.response)) response[name] = value ? toBase64Url(value) : null;
  return { id: cred.id, rawId: toBase64Url(cred.rawId), type: cred.type, response };
}

export type Place = { protocol: string; hostname: string; port?: string };

/**
 * A passkey is tied to a site NAME. The Desk is served on localhost; opened as 127.0.0.1 (an address, not a name) the browser refuses it, with a message that means nothing to most people.
 * Returns null when this page can use a device, else a sentence saying what to do.
 */
export function placeProblem(place: Place, hasApi: boolean, lang: "th" | "en" = "en"): string | null {
  const th = lang === "th";
  if (!hasApi) return th ? "เบราว์เซอร์นี้ไม่รองรับการยืนยันด้วยอุปกรณ์ (WebAuthn)" : "This browser can not confirm with a device (WebAuthn is not available).";
  if (place.hostname === "localhost") return null;
  if (/^\d+\.\d+\.\d+\.\d+$/.test(place.hostname) || place.hostname.includes(":")) {
    const port = place.port ? `:${place.port}` : "";
    return th
      ? `หน้านี้เปิดด้วยตัวเลข (${place.hostname}) อุปกรณ์ยืนยันไม่ได้ ให้เปิดเป็น ${place.protocol}//localhost${port} แทน`
      : `This page was opened by a number (${place.hostname}), and a device can not confirm there. Open ${place.protocol}//localhost${port} instead.`;
  }
  return th
    ? "อุปกรณ์ยืนยันใช้ได้เมื่อเปิดหน้านี้ที่ localhost หรือที่ชื่อเว็บซึ่งตั้งไว้ใน DELENTIA_PASSKEY_RP_ID"
    : "A device can confirm only when this page is opened at localhost, or at the site name set in DELENTIA_PASSKEY_RP_ID.";
}

/** Browser errors for a cancelled or failed ceremony, in words a person can act on. */
export function ceremonyMessage(err: unknown, lang: "th" | "en" = "en"): string {
  const th = lang === "th";
  const name = err instanceof Error ? err.name : "";
  if (name === "NotAllowedError") return th ? "ยกเลิก หรือหมดเวลา ไม่มีอะไรถูกบันทึก ลองใหม่อีกครั้งได้" : "Cancelled or timed out. Nothing was recorded; you can try again.";
  if (name === "InvalidStateError") return th ? "อุปกรณ์นี้ลงทะเบียนไว้แล้ว" : "This device is already registered.";
  if (name === "NotSupportedError") return th ? "อุปกรณ์หรือเบราว์เซอร์นี้ไม่รองรับวิธีนี้" : "This device or browser does not support this.";
  if (name === "SecurityError") return th ? "เบราว์เซอร์ปฏิเสธเพราะชื่อเว็บไม่ตรง ให้เปิดหน้านี้ที่ localhost" : "The browser refused because of the site name. Open this page at localhost.";
  return err instanceof Error ? err.message : String(err);
}

// ---- the calls that touch the browser (not unit-tested; they need a real authenticator) ---------------------------------------

export async function createCredential(serverOptions: Json): Promise<Json> {
  const cred = (await navigator.credentials.create({ publicKey: creationOptions(serverOptions) as unknown as PublicKeyCredentialCreationOptions })) as unknown as CredentialLike | null;
  if (!cred) throw new Error("no credential was created");
  return serializeCredential(cred);
}

export async function getAssertion(serverOptions: Json): Promise<Json> {
  const cred = (await navigator.credentials.get({ publicKey: requestOptions(serverOptions) as unknown as PublicKeyCredentialRequestOptions })) as unknown as CredentialLike | null;
  if (!cred) throw new Error("no confirmation was made");
  return serializeCredential(cred);
}

export function deviceSupport(): boolean {
  return typeof window !== "undefined" && typeof window.PublicKeyCredential !== "undefined" && !!navigator.credentials;
}
