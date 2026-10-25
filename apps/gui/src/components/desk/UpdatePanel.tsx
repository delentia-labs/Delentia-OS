"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type UpdateState } from "@/lib/desk-api";

/** One sentence per state, in both languages. Pure so the wording can not drift from the states the server produces (status is one of disabled / unknown / current / available). */
export function updateSentence(state: UpdateState, th: boolean): string {
  switch (state.status) {
    case "available":
      return th ? `มีเวอร์ชันใหม่ ${state.latest?.version} (คุณใช้ ${state.current})` : `A newer version is available: ${state.latest?.version} (you have ${state.current})`;
    case "current":
      return th ? `คุณใช้เวอร์ชันล่าสุดแล้ว (${state.current})` : `You have the newest version (${state.current})`;
    case "disabled":
      return th ? `ปิดการตรวจเวอร์ชันใหม่อยู่ (คุณใช้ ${state.current})` : `Checking for new versions is off (you have ${state.current})`;
    default:
      return th ? `ตรวจเวอร์ชันใหม่ไม่ได้ตอนนี้ (คุณใช้ ${state.current})` : `The newest version could not be checked right now (you have ${state.current})`;
  }
}

/** A thin banner for the Status page: shown only when an update exists. It never starts an update; that is a command for the person at the keyboard, because it replaces the running program. */
export function UpdateBanner() {
  const { lang } = useLang();
  const th = lang === "th";
  const update = useDeskData(() => desk.update(), [], 6 * 3600 * 1000);
  const s = update.data;
  if (!s || s.status !== "available") return null;
  return (
    <div role="status" className="mb-6 rounded border border-dl-leaf/60 bg-dl-pine/20 px-4 py-3 text-sm text-dl-text">
      <p className="font-medium">{updateSentence(s, th)}</p>
      <p className="mt-1 text-[13px] text-dl-muted">
        {th ? "ปิดเอเจนต์ก่อน แล้วเปิดเมนู Start → “Update Delentia” หรือพิมพ์ " : "Close the agent first, then use Start → “Update Delentia”, or type "}<Code>delentia update --apply</Code>
        {th ? " (ระบบเช็คไฟล์ว่าตรงกับที่ผู้เผยแพร่ประกาศก่อนติดตั้ง)" : " (the file is checked against the digest the publisher announced before it is installed)."}{" "}
        <a href={s.releases_url} target="_blank" rel="noreferrer" className="text-dl-leaf underline">{th ? "ดูว่ามีอะไรเปลี่ยน" : "What changed"}</a>
      </p>
    </div>
  );
}

/** The Settings panel: the version, the last check, a button to check now and the switch for the daily check. */
export function UpdatePanel() {
  const { lang } = useLang();
  const th = lang === "th";
  const update = useDeskData(() => desk.update(), [], 600000);
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<UpdateState | null>(null);
  const s = fresh ?? update.data;

  const run = async (action: () => Promise<UpdateState>) => {
    setBusy(true);
    try {
      setFresh(await action());
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={th ? "เวอร์ชันและการอัปเดต" : "Version and updates"} aside={s ? <Badge tone={s.status === "available" ? "amber" : "muted"}>{s.current}</Badge> : null}>
      <p className="text-sm text-dl-text">{s ? updateSentence(s, th) : "…"}</p>
      {s?.checked_at ? <p className="mt-1 text-[12px] text-dl-muted">{th ? "ตรวจล่าสุด" : "Last checked"}: {fmtTime(s.checked_at)}</p> : null}
      {s?.error ? <p className="mt-1 text-[12px] text-dl-muted">{s.error}</p> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => run(() => desk.updateCheck())} disabled={busy || s?.status === "disabled"}>{th ? "ตรวจตอนนี้" : "Check now"}</Button>
        <Button tone="ghost" onClick={() => run(() => desk.updateSwitch(s?.status === "disabled"))} disabled={busy}>
          {s?.status === "disabled" ? (th ? "เปิดการตรวจรายวัน" : "Turn the daily check on") : (th ? "ปิดการตรวจรายวัน" : "Turn the daily check off")}
        </Button>
      </div>
      <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
        {th
          ? "การตรวจส่งคำขอเล็ก ๆ ไปที่ pypi.org วันละไม่เกินหนึ่งครั้ง ไม่ส่งข้อมูลของคุณ (เซิร์ฟเวอร์เห็นแค่ที่อยู่เครือข่ายและชื่อกับเวอร์ชันของโปรแกรม เหมือน pip install ทั่วไป) การอัปเดตจริงทำด้วยคำสั่ง หรือเมนู Start → Update Delentia โดยคนที่นั่งหน้าเครื่อง เพราะมันแทนที่โปรแกรมที่กำลังทำงาน"
          : "The check sends one small request to pypi.org at most once a day and none of your data (the server sees your network address and the program's name and version, like any pip install). Installing is done by the person at the keyboard with the command or Start → Update Delentia, because it replaces the running program."}
      </p>
    </Panel>
  );
}
