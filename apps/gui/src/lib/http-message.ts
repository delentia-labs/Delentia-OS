// Round 101 (UX audit): what an HTTP failure means to a person. Pure, so a plain node test covers it.
/** What an HTTP failure means to a person, with the server's own words kept after it for whoever has to debug. */
export function httpMessage(status: number, detail: string, th: boolean): string {
  const head: Record<number, [string, string]> = {
    401: ["Not signed in: this server needs a token. Enter it under Settings.", "ยังไม่ได้ยืนยันตัวตน: เซิร์ฟเวอร์นี้ต้องใช้ token ใส่ได้ที่หน้าตั้งค่า"],
    403: ["Not allowed: this account may not do that.", "ไม่ได้รับอนุญาต: บัญชีนี้ทำสิ่งนี้ไม่ได้"],
    404: ["Not found: it may have been removed or already used.", "ไม่พบ: อาจถูกลบหรือถูกใช้ไปแล้ว"],
    409: ["Conflict: it changed while you were looking. Reload and try again.", "ข้อมูลเปลี่ยนไประหว่างที่ดูอยู่ โหลดหน้าใหม่แล้วลองอีกครั้ง"],
    429: ["Too many requests in a short time. Wait a moment.", "ส่งคำขอถี่เกินไป รอสักครู่"],
  };
  const known = head[status];
  if (known) return `${th ? known[1] : known[0]} (${status}: ${detail})`;
  if (status >= 500) return th ? `เซิร์ฟเวอร์ขัดข้อง (${status}: ${detail}) ลองใหม่ ถ้าเกิดซ้ำให้ดูบันทึกของเซิร์ฟเวอร์` : `The server had a problem (${status}: ${detail}). Try again; if it repeats, look at the server's log.`;
  return `${status}: ${detail}`;
}
