"use client";

import Link from "next/link";
import { useLang } from "./i18n";
import { PixelMark } from "./mark";
import type { CycleStatus, GateRow, Mood, RunState } from "@/lib/run-state";

const MOOD_TEXT: Record<Mood, { en: string; th: string; tone: string }> = {
  idle: { en: "Ready", th: "พร้อม", tone: "text-dl-muted" },
  thinking: { en: "Thinking", th: "กำลังคิด", tone: "text-dl-leaf" },
  acting: { en: "Using a tool", th: "กำลังใช้เครื่องมือ", tone: "text-dl-leaf" },
  waiting: { en: "Waiting for you", th: "รอคุณ", tone: "text-dl-amber" },
  blocked: { en: "Stopped by a gate", th: "ถูกประตูหยุดไว้", tone: "text-dl-rust" },
  done: { en: "Done", th: "เสร็จแล้ว", tone: "text-dl-leaf" },
};

const DOT: Record<CycleStatus, { glyph: string; tone: string; en: string; th: string }> = {
  done: { glyph: "●", tone: "text-dl-leaf", en: "done", th: "เสร็จ" },
  active: { glyph: "◐", tone: "text-dl-amber", en: "now", th: "กำลังทำ" },
  blocked: { glyph: "✕", tone: "text-dl-rust", en: "stopped", th: "ถูกหยุด" },
  unknown: { glyph: "○", tone: "text-dl-muted/50", en: "not reported", th: "ไม่มีรายงาน" },
};

const GATE: Record<GateRow["verdict"], { glyph: string; tone: string; en: string; th: string }> = {
  ran: { glyph: "●", tone: "text-dl-leaf", en: "ran", th: "รันแล้ว" },
  blocked: { glyph: "✕", tone: "text-dl-rust", en: "blocked", th: "ถูกบล็อก" },
  waiting: { glyph: "◷", tone: "text-dl-amber", en: "waits for a signature", th: "รอลายเซ็น" },
  not_run: { glyph: "✕", tone: "text-dl-rust", en: "not run", th: "ไม่ได้รัน" },
  unknown_tool: { glyph: "?", tone: "text-dl-amber", en: "no such tool", th: "ไม่มีเครื่องมือนี้" },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-dl-rule pt-3">
      <h3 className="desk-mono mb-2 text-[11px] uppercase tracking-[0.08em] text-dl-muted">{title}</h3>
      {children}
    </section>
  );
}

/** The Execution Inspector: what happened in this run, drawn only from what the runtime sent (see lib/run-state.ts).
 *  "not reported" is shown as such; the interface never fills a gap with a guess. */
export function Inspector({ run, running, elapsed }: { run: RunState; running: boolean; elapsed: number }) {
  const { lang } = useLang();
  const th = lang === "th";
  const L = (en: string, thai: string) => (th ? thai : en);
  const mood = MOOD_TEXT[run.mood];

  return (
    <section className="space-y-4" aria-label={L("Execution inspector", "ตัวตรวจการทำงาน")}>
      <div className="flex items-center gap-3">
        <PixelMark mood={run.mood} size={56} />
        <div className="min-w-0">
          <p className={`desk-mono text-[13px] ${mood.tone}`} role="status">{th ? mood.th : mood.en}</p>
          <p className="desk-mono text-[11px] text-dl-muted">{running ? `${Math.round(elapsed)} s` : run.evidence.seconds !== null ? `${Math.round(run.evidence.seconds)} s` : "-"}</p>
        </div>
      </div>

      <Section title={L("Intent (your words)", "เจตนา (คำของคุณ)")}>
        <p className="break-words text-[13px] leading-snug text-dl-text">{run.intent ?? <span className="text-dl-muted">{L("No run yet", "ยังไม่มีงาน")}</span>}</p>
      </Section>

      <Section title={L("Constitutional cycle", "วงจรรัฐธรรมนูญ")}>
        <ol className="space-y-1">
          {run.cycle.map((c) => {
            const d = DOT[c.status];
            return (
              <li key={c.name} className="desk-mono text-[12px]" title={c.note || undefined}>
                <span className={d.tone} aria-hidden>{d.glyph}</span>{" "}
                <span className={c.status === "unknown" ? "text-dl-muted" : "text-dl-text"}>{c.name}</span>{" "}
                <span className="text-dl-muted">{th ? d.th : d.en}</span>
                {c.note && c.status !== "unknown" ? <span className="block pl-4 text-[11px] leading-snug text-dl-muted">{c.note}</span> : null}
              </li>
            );
          })}
        </ol>
      </Section>

      <Section title={L("Gate verdicts", "คำตัดสินของประตู")}>
        {run.gates.length === 0 ? (
          <p className="text-[12px] text-dl-muted">{L("No tool call yet", "ยังไม่มีการเรียกเครื่องมือ")}</p>
        ) : (
          <ul className="space-y-1.5">
            {run.gates.map((g, i) => {
              const d = GATE[g.verdict];
              return (
                <li key={i} className="desk-mono text-[12px]">
                  <span className={d.tone} aria-hidden>{d.glyph}</span> <span className="text-dl-text">{g.tool}</span>{" "}
                  <span className="text-dl-muted">{th ? d.th : d.en}{typeof g.F === "number" ? ` · F ${g.F}` : ""}</span>
                  {g.reason ? <span className="block pl-4 text-[11px] leading-snug text-dl-muted">{g.reason}</span> : null}
                </li>
              );
            })}
          </ul>
        )}
        {run.approvalId ? (
          <p className="desk-mono mt-2 text-[12px] text-dl-amber">
            {L("approval", "การอนุมัติ")} {run.approvalId} · <Link href="/approvals" className="underline underline-offset-2">{L("sign it", "ไปเซ็น")}</Link>
          </p>
        ) : null}
      </Section>

      <Section title={L("Verification against your intent", "ตรวจเทียบกับเจตนา")}>
        <p className="desk-mono text-[12px]">
          {run.verification.state === "aligned" ? <span className="text-dl-leaf">● {L("the answer matches", "คำตอบตรงกับเจตนา")}{typeof run.verification.score === "number" ? ` (${run.verification.score})` : ""}</span> : null}
          {run.verification.state === "not_aligned" ? <span className="text-dl-rust">✕ {L("the answer does NOT match", "คำตอบไม่ตรงกับเจตนา")}{typeof run.verification.score === "number" ? ` (${run.verification.score})` : ""}</span> : null}
          {run.verification.state === "not_applicable" ? <span className="text-dl-muted">○ {L("not applicable to this run", "ไม่เกี่ยวกับงานนี้")}</span> : null}
          {run.verification.state === "unknown" ? <span className="text-dl-muted">○ {L("not reported yet", "ยังไม่มีรายงาน")}</span> : null}
        </p>
        <p className="mt-1 text-[11px] leading-snug text-dl-muted">{L("A text check, not proof the answer is true.", "เป็นการตรวจข้อความ ไม่ใช่การพิสูจน์ว่าคำตอบเป็นจริง")}</p>
      </Section>

      <Section title={L("Evidence", "หลักฐาน")}>
        <dl className="desk-mono space-y-1 text-[12px]">
          <div className="flex justify-between gap-2"><dt className="text-dl-muted">{L("episode signed", "ลงลายเซ็น")}</dt><dd className={run.evidence.signed ? "text-dl-leaf" : "text-dl-muted"}>{run.evidence.signed ? `yes · ${(run.evidence.signatureHash ?? "").slice(0, 10)}…` : L("not reported", "ไม่มีรายงาน")}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-dl-muted">{L("notary receipts", "ใบรับรองจาก notary")}</dt><dd className="text-dl-text">{run.evidence.notaryReceipts === null ? L("notary off", "ไม่ได้เปิด notary") : run.evidence.notaryReceipts}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-dl-muted">{L("ended because", "จบเพราะ")}</dt><dd className="text-dl-text">{run.evidence.stoppedReason ?? "-"}</dd></div>
        </dl>
        <p className="mt-2 text-[11px] leading-snug text-dl-muted">
          <Link href="/audit" className="underline underline-offset-2">{L("Check the audit chain", "ตรวจสายบันทึก")}</Link>
          {" · "}
          <Link href="/sessions" className="underline underline-offset-2">{L("Replay in Sessions", "เปิดดูใน Sessions")}</Link>
        </p>
      </Section>
    </section>
  );
}
