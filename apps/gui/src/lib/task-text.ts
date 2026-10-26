/**
 * What each background task of the daemon does, in both languages (Round 101C). The server describes its tasks in English and with round numbers for the developers; a person sees these instead.
 * An unknown task name (a task added later) falls back to the server's own description, so nothing is hidden.
 */
export type Lang = "th" | "en";
const TEXT: Record<string, { en: string; th: string }> = {
  audit_chain_verify: { en: "Re-checks every link and signature of the record of what the agent did.", th: "ตรวจซ้ำทุกข้อและทุกลายเซ็นของบันทึกสิ่งที่เอเจนต์ทำ ว่ายังไม่ถูกแก้" },
  audit_chain_anchor: { en: "Sends a fingerprint of the record to an outside witness, so a rewrite of the whole record can be noticed (needs the witness settings).", th: "ส่งลายนิ้วมือของบันทึกไปให้พยานภายนอก เพื่อให้รู้ถ้ามีการเขียนบันทึกใหม่ทั้งหมด (ต้องตั้งค่าพยานก่อน)" },
  tasks_advance: { en: "Gives each long task its next step, one at a time; a paused or over-limit system just holds them.", th: "ให้งานยาว ๆ ทำขั้นถัดไปทีละขั้น ถ้าระบบถูกพักหรือเกินวงเงิน งานจะรอไว้เฉย ๆ" },
  skill_curator_report: { en: "Once a week, reviews the learned skills and records what it WOULD archive. It archives nothing by itself.", th: "สัปดาห์ละครั้ง ตรวจทักษะที่เรียนรู้และบันทึกว่าอะไร “ควร” เก็บเข้าคลัง โดยไม่เก็บอะไรเอง" },
  reminder_poller: { en: "Fires the reminders that are due.", th: "เตือนเรื่องที่ถึงเวลา" },
  cron_dispatcher: { en: "Starts your recurring jobs when they are due; each runs as a normal governed episode and delivers its result.", th: "เริ่มงานตามเวลาของคุณเมื่อถึงเวลา แต่ละงานผ่านด่านปกติเหมือนงานทั่วไปและส่งผลลัพธ์" },
};

export function taskDescription(name: string, serverText: string, lang: Lang): string {
  const found = TEXT[name];
  return found ? found[lang] : serverText;
}

export function knownTasks(): string[] {
  return Object.keys(TEXT);
}
