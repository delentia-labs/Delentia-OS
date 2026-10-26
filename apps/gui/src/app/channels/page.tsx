"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const NAMES: Record<string, string> = { telegram: "Telegram", discord: "Discord", slack: "Slack", line: "LINE", whatsapp: "WhatsApp", signal: "Signal", email: "Email" };

export default function ChannelsPage() {
  const { t, lang } = useLang();
  const th = lang === "th";
  const channels = useDeskData(() => desk.channels(), [], 15000);
  const pairing = useDeskData(() => desk.pairing(), [], 10000);
  const [busy, setBusy] = useState(false);
  const revoke = async (channel: string, sender: string) => {
    setBusy(true);
    try { await desk.pairingRevoke(channel, sender); pairing.reload(); } finally { setBusy(false); }
  };
  const live = pairing.data?.grants.filter((g) => !g.revoked_at) ?? [];
  return (
    <>
      <PageHeader title={t("channels")}
        lead={lang === "th"
          ? "ช่องทางแชทที่ส่งงานให้ agent ได้ ทุกช่องทางปิดไว้โดยปริยาย: ถ้าไม่ตั้ง allowlist จะไม่มีใครส่งงานได้เลย"
          : "Chat channels that can hand work to the agent. Every channel fails closed: without an allowlist, nobody can send it work."} />
      <PageBody>
        {channels.error ? <ErrorNote error={channels.error} onRetry={channels.reload} /> : null}
        <Panel title={lang === "th" ? "การจับคู่ (DM pairing)" : "DM pairing"}
          aside={pairing.data ? (pairing.data.enabled ? <Badge tone="leaf">{th ? "เปิด" : "on"}</Badge> : <Badge>{th ? "ปิด" : "off"}</Badge>) : undefined} className="mb-4">
          {pairing.error ? <ErrorNote error={pairing.error} onRetry={pairing.reload} /> : null}
          <p className="text-[13px] leading-relaxed text-dl-text">
            {lang === "th"
              ? "คนที่ agent ยังไม่รู้จักจะได้รับรหัสสั้นๆ แทนการถูกเมินเฉย เจ้าของอนุมัติรหัสนั้นด้วยลายเซ็นจากอุปกรณ์ของตัวเอง (หน้า Approvals หรือ delentia approvals approve) ก่อนลงนาม agent จะไม่ทำอะไรให้คนนั้นเลย ยืนยันตัวตนผู้ถือรหัสนอกช่องทางนี้ก่อน (เช่น โทรอ่านรหัสให้ฟัง)"
              : "Someone the agent does not know yet is given a short code instead of being ignored. You let them in by signing that code on your own device (the Approvals page or delentia approvals approve). Until you sign, the agent does nothing for them. Confirm who holds the code out of band first (for example, have them read it to you on the phone)."}
          </p>
          {pairing.data && !pairing.data.enabled ? (
            <p className="mt-2 text-[12px] text-dl-muted">{th ? <>เปิดด้วย <Code>DELENTIA_PAIRING=1</Code> ถ้าปิดอยู่ คนที่ไม่รู้จักจะได้ข้อความปฏิเสธแบบตายตัวและไม่มีอะไรถูกสร้าง</> : <>Turn it on with <Code>DELENTIA_PAIRING=1</Code>. Off, an unknown sender gets the fixed refusal and nothing is created.</>}</p>
          ) : null}
          {pairing.data?.pending.length ? <h3 className="desk-mono mt-4 text-[12px] text-dl-muted">{th ? "รอลายเซ็นของคุณ" : "Waiting for your signature"}</h3> : null}
          {pairing.data?.pending.map((p) => (
            <Row key={p.code} label={`${NAMES[p.channel] ?? p.channel} · ${th ? "ผู้ส่ง" : "sender"} ${p.sender_id}`}>
              <Code>delentia approvals approve {p.code} --key &lt;your key&gt;</Code>
            </Row>
          ))}
          {live.length ? <h3 className="desk-mono mt-4 text-[12px] text-dl-muted">{th ? "คนที่อนุญาตแล้ว" : "Let in"}</h3> : null}
          {live.map((g) => (
            <Row key={`${g.channel}:${g.sender_id}`} label={`${NAMES[g.channel] ?? g.channel} · ${th ? "ผู้ส่ง" : "sender"} ${g.sender_id}`}>
              <Button tone="ghost" disabled={busy} onClick={() => revoke(g.channel, g.sender_id)}>{lang === "th" ? "เพิกถอน" : "Revoke"}</Button>
            </Row>
          ))}
          {pairing.data && !pairing.data.pending.length && !live.length ? <p className="mt-3 text-[12px] text-dl-muted">{lang === "th" ? "ยังไม่มีใครขอจับคู่" : "Nobody has asked yet."}</p> : null}
          <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
            {th
              ? <>ข้อจำกัด: หนึ่งคำขอต่อหนึ่งผู้ส่ง รอได้ {pairing.data?.limits.max_pending_per_channel ?? 5} รายการต่อช่องทาง และคนที่ถูกปฏิเสธจะขออีกไม่ได้ 24 ชั่วโมง การปิดประตูไม่ต้องเซ็น การเปิดประตูต้องเซ็นเสมอ คำสั่งแชตที่อ่านข้อมูลของคุณเองเท่านั้น: <Code>/help /whoami /status /jobs /approvals /search /model</Code></>
              : <>Limits: one request per sender, {pairing.data?.limits.max_pending_per_channel ?? 5} waiting per channel, and a refused sender cannot ask again for 24 hours. Closing a door needs no signature; opening one always does. Chat commands that only read your own data: <Code>/help /whoami /status /jobs /approvals /search /model</Code>.</>}
          </p>
        </Panel>
        <div className="grid gap-4 xl:grid-cols-2">
          {channels.data?.channels.map((c) => (
            <Panel key={c.channel} title={NAMES[c.channel] ?? c.channel}
              aside={c.running ? <Badge tone="leaf">{th ? "ทำงานอยู่" : "running"}</Badge> : c.token_present ? <Badge>{th ? "ตั้งค่าแล้ว" : "configured"}</Badge> : <Badge>{th ? "ยังไม่ได้ตั้งค่า" : "not set up"}</Badge>}>
              <Row label={th ? "มีโทเค็นบอทในระบบหรือไม่" : "Bot token in the environment"}>{c.token_present ? (th ? "มี" : "yes") : (th ? "ไม่มี" : "no")}</Row>
              <Row label={th ? "ใครส่งงานให้ได้" : "Who may send work"}>
                {c.allowlist === "everyone" ? <Badge tone="amber">{th ? "ทุกคน" : "everyone"}</Badge>
                  : c.allowlist === "nobody" ? (th ? "ไม่มีใครเลย" : "nobody") : th ? `${c.allowlist_count} ผู้ส่งในรายชื่อ` : `${c.allowlist_count} listed sender${c.allowlist_count === 1 ? "" : "s"}`}
              </Row>
              <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                {th
                  ? <>รายชื่ออนุญาต: <Code>{c.allowlist_env}</Code> (ไอดีผู้ส่งคั่นด้วยจุลภาค หรือ <Code>*</Code> สำหรับทุกคน) ไอดีผู้ส่งอยู่บนเครื่องโฮสต์เท่านั้น ไม่แสดงที่นี่</>
                  : <>Allowlist: <Code>{c.allowlist_env}</Code> (comma-separated sender ids, or <Code>*</Code> for everyone). Sender ids stay on the host and are not shown here.</>}
              </p>
            </Panel>
          ))}
        </div>
      </PageBody>
    </>
  );
}
