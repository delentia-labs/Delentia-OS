"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

type T = (en: string, th: string) => string;

const KIND_TONE: Record<string, "rust" | "amber" | "muted" | "fern"> = { weak: "rust", refusal: "rust", duplicate: "amber", stale: "muted" };

export default function LearningPage() {
  const { lang } = useLang();
  const T: T = (en, th) => (lang === "th" ? th : en);
  const curator = useDeskData(() => desk.curator(), [], 20000);
  const suggestions = useDeskData(() => desk.suggestions("pending"), [], 20000);
  const trajectories = useDeskData(() => desk.trajectories(), [], 20000);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const act = async (fn: () => Promise<string>) => {
    setBusy(true); setNote(null);
    try { setNote(await fn()); curator.reload(); suggestions.reload(); } catch (err) { setNote(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  };
  const c = curator.data;
  const s = suggestions.data;
  const t = trajectories.data;

  return (
    <>
      <PageHeader title={T("Learning", "การเรียนรู้")}
        lead={lang === "th"
          ? "สิ่งที่ระบบจะเรียนรู้หรือจำ และใครเป็นคนตัดสิน: สกิลที่เรียนรู้ถูกทบทวนด้วยหลักฐานและ archive (ไม่ลบ), สิ่งที่คนพูดถึงตัวเองถูกเสนอให้จำโดยต้องได้รับ yes จากคนนั้น, และบันทึกขั้นตอนของ episode สำหรับวัดโมเดล (ปิดโดยปริยาย อยู่ในเครื่อง ลบความลับก่อนเขียน)"
          : "What the system learns or remembers, and who decides: learned skills are reviewed from evidence and archived (never deleted), what people say about themselves is offered back and kept only when that person says yes, and the steps of episodes can be recorded to measure a model (off by default, local, secrets removed before writing)."} />
      <PageBody>
        {note ? <p role="status" className="mb-4 rounded border border-dl-fern bg-dl-pine/30 px-3 py-2 text-[13px] text-dl-text">{note}</p> : null}
        <div className="space-y-6">
          <Panel title={T("Skill curator", "ผู้ดูแลสกิล")} aside={c ? <Badge tone={c.proposals.length ? "amber" : "leaf"}>{c.proposals.length} {T("proposal(s)", "ข้อเสนอ")}</Badge> : undefined}>
            {curator.error ? <ErrorNote error={curator.error} onRetry={curator.reload} /> : null}
            {c ? (
              <>
                <p className="mb-3 text-[13px] text-dl-muted">{T(`${c.skills_reviewed} learned skill(s) reviewed; ${c.protected} starter or imported skill(s) are never touched. A weekly report is written to the audit trail by the daemon; nothing is archived without you.`,
                  `ทบทวนสกิลที่เรียนรู้ ${c.skills_reviewed} ตัว สกิลเริ่มต้นหรือนำเข้า ${c.protected} ตัวไม่ถูกแตะ daemon เขียนรายงานรายสัปดาห์ลง audit และไม่ archive อะไรโดยไม่มีคุณ`)}</p>
                {c.proposals.length ? (
                  <ul className="space-y-2">
                    {c.proposals.map((p) => (
                      <li key={p.id} className="rounded border border-dl-rule bg-dl-ink/40 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2"><Badge tone={KIND_TONE[p.kind] ?? "muted"}>{p.kind}</Badge><Code>{p.id}</Code><span className="text-[13px] text-dl-text">{p.problem}</span></div>
                        <p className="mt-1 text-[12px] text-dl-muted">{p.reason}</p>
                      </li>
                    ))}
                  </ul>
                ) : <Empty title={T("Nothing to archive", "ไม่มีอะไรต้อง archive")}>{T("No skill has evidence against it yet.", "ยังไม่มีสกิลที่มีหลักฐานว่าไม่ดี")}</Empty>}
                {c.proposals.length ? (
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <Button disabled={busy} onClick={() => act(async () => { const r = await desk.curatorApply(stale); return T(`Archived ${r.archived.length} skill(s). They can be offered again below.`, `archive ${r.archived.length} สกิลแล้ว คืนได้ด้านล่าง`); })}>{T("Archive the ones with evidence", "archive ตัวที่มีหลักฐาน")}</Button>
                    <label className="flex items-center gap-2 text-[12px] text-dl-muted"><input type="checkbox" checked={stale} onChange={(e) => setStale(e.target.checked)} />{T("also the stale ones (never reused in 90 days)", "รวมตัวที่ค้างด้วย (ไม่เคยถูกใช้ 90 วัน)")}</label>
                  </div>
                ) : null}
                {c.archived.length ? (
                  <div className="mt-4">
                    <p className="text-[12px] text-dl-muted">{T("Archived (kept, not offered)", "archive แล้ว (เก็บไว้ ไม่ถูกเสนอ)")}</p>
                    <ul className="mt-1 space-y-1">
                      {c.archived.slice(0, 20).map((a) => (
                        <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-dl-text">
                          <span><Code>{a.id}</Code> {a.problem_statement.slice(0, 80)} <span className="text-dl-muted">· {a.uses} {T("uses", "ครั้ง")}</span></span>
                          <Button tone="ghost" disabled={busy} onClick={() => act(async () => { await desk.curatorUnarchive(a.id); return T(`${a.id} is offered again.`, `${a.id} ถูกเสนออีกครั้ง`); })}>{T("Offer again", "เสนออีกครั้ง")}</Button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            ) : null}
          </Panel>

          <Panel title={T("Memory suggestions", "ข้อเสนอให้จำ")} aside={s ? <Badge tone={s.enabled ? "leaf" : "muted"}>{s.enabled ? T("on", "เปิด") : T("off", "ปิด")}</Badge> : undefined}>
            {suggestions.error ? <ErrorNote error={suggestions.error} onRetry={suggestions.reload} /> : null}
            {s ? (
              <>
                <p className="mb-3 text-[13px] text-dl-muted">{T("What the runtime offered to remember from people's own words. Only the person it came from can keep one (they answer /remember in chat); you can throw one away. Offers expire after 14 days.", "สิ่งที่ runtime เสนอให้จำจากคำพูดของคนนั้นเอง เก็บได้เฉพาะเจ้าของข้อความ (ตอบ /remember ในแชท) คุณทิ้งได้ ข้อเสนอหมดอายุใน 14 วัน")}</p>
                {s.suggestions.length ? (
                  <ul className="space-y-2">
                    {s.suggestions.map((x) => (
                      <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-dl-rule bg-dl-ink/40 px-3 py-2">
                        <span className="text-[13px] text-dl-text"><Badge tone="fern">{x.kind}</Badge> <span className="desk-mono text-dl-muted">{x.namespace}</span> {x.text}</span>
                        <Button tone="ghost" disabled={busy} onClick={() => act(async () => { await desk.suggestionDismiss(x.id); return T("Thrown away.", "ทิ้งแล้ว"); })}>{T("Throw away", "ทิ้ง")}</Button>
                      </li>
                    ))}
                  </ul>
                ) : <Empty title={T("Nothing waiting", "ไม่มีอะไรรออยู่")}>{s.enabled ? T("No one has said anything worth keeping that is still unanswered.", "ยังไม่มีคำพูดที่ควรจำและยังไม่ได้ตอบ") : T("Suggestions are off: set DELENTIA_MEMORY_NUDGE=1 (delentia serve does).", "ปิดอยู่: ตั้ง DELENTIA_MEMORY_NUDGE=1 (delentia serve ตั้งให้)")}</Empty>}
              </>
            ) : null}
          </Panel>

          <Panel title={T("Trajectories", "บันทึกขั้นตอน")} aside={t ? <Badge tone={t.recording ? "amber" : "muted"}>{t.recording ? T("recording", "กำลังบันทึก") : T("off", "ปิด")}</Badge> : undefined}>
            {trajectories.error ? <ErrorNote error={trajectories.error} onRetry={trajectories.reload} /> : null}
            {t ? (
              <>
                <p className="mb-3 text-[13px] text-dl-muted">{t.how}</p>
                <Row label={T("Episodes on disk", "episode ในเครื่อง")}>{t.stats.episodes} · {t.stats.verified} {T("verified", "ตรวจผ่าน")} · {t.stats.tainted} {T("read outside text", "อ่านข้อความนอก")}</Row>
                <Row label={T("Folder", "โฟลเดอร์")}><Code>{t.directory}</Code></Row>
                {t.recent.length ? (
                  <ul className="mt-3 space-y-1">
                    {t.recent.map((r) => (
                      <li key={r.id} className="text-[13px] text-dl-text">
                        <span className="desk-mono text-[11px] text-dl-muted">{fmtTime(new Date(r.at * 1000).toISOString())}</span> {r.goal} <span className="text-dl-muted">→ {r.tools.join(", ") || T("no tool", "ไม่ใช้ tool")}</span>{" "}
                        <Badge tone={r.verified ? "leaf" : "muted"}>{r.verified ? T("verified", "ตรวจผ่าน") : r.stopped_reason}</Badge>{r.tainted ? <> <Badge tone="amber">{T("outside text", "ข้อความนอก")}</Badge></> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : null}
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
