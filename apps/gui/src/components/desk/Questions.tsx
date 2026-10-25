"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, ErrorNote, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type Clarification, type Rct7Stats } from "@/lib/desk-api";

const KIND = {
  before_act: { en: "Asked before acting", th: "ถามก่อนลงมือ" },
  mismatch: { en: "The result did not match what you asked", th: "ผลที่ได้ไม่ตรงกับที่ขอ" },
} as const;

function QuestionCard({ c, onChanged }: { c: Clarification; onChanged: () => void }) {
  const { lang } = useLang();
  const th = lang === "th";
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const send = async (action: "answer" | "cancel") => {
    setBusy(true);
    setMessage(null);
    try {
      if (action === "answer") {
        const done = await desk.answerClarification(c.clarification_id, answer.trim());
        setMessage({ tone: "ok", text: th ? `บันทึกคำตอบแล้ว (เจตนาฉบับที่ ${done.new_intent_version ?? "ใหม่"}) งานถัดไปจะใช้คำตอบนี้` : `Answer recorded (intent version ${done.new_intent_version ?? "new"}). The next run will use it.` });
        setAnswer("");
      } else {
        await desk.cancelClarification(c.clarification_id);
        setMessage({ tone: "ok", text: th ? "ยกเลิกคำถามแล้ว" : "Question cancelled." });
      }
      onChanged();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={th ? KIND[c.kind].th : KIND[c.kind].en} aside={<Badge tone="amber">{c.status}</Badge>}>
      <p className="whitespace-pre-wrap text-sm text-dl-text">{c.question}</p>
      <div className="mt-3">
        <Row wrap label={th ? "เป้าหมายเดิม" : "Original goal"}>{c.original_goal}</Row>
        {c.expected ? <Row wrap label={th ? "ที่คาดไว้" : "Expected"}>{c.expected}</Row> : null}
        {c.observed ? <Row wrap label={th ? "ที่เห็นจริง" : "Observed"}>{c.observed}</Row> : null}
        <Row label={th ? "เกณฑ์" : "Criterion"}>{c.criterion}</Row>
        <Row label={th ? "ถามเมื่อ" : "Asked"}>{fmtTime(c.created_at)}</Row>
        <Row label={th ? "หมดอายุ" : "Expires"}>{fmtTime(c.expires_at)}</Row>
      </div>
      <label className="mt-4 block">
        <span className="sr-only">{th ? "คำตอบของคุณ" : "Your answer"}</span>
        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={3}
          placeholder={th ? "พิมพ์คำตอบ (คำตอบนี้จะกลายเป็นเจตนาฉบับใหม่ ฉบับเดิมไม่ถูกแก้)" : "Type your answer (it becomes a new version of your intent; the original is never edited)"}
          className="desk-focus w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text placeholder:text-dl-muted/50" />
      </label>
      <div className="mt-2 flex gap-2">
        <Button onClick={() => send("answer")} disabled={busy || !answer.trim()}>{th ? "ส่งคำตอบ" : "Send answer"}</Button>
        <Button tone="ghost" onClick={() => send("cancel")} disabled={busy}>{th ? "ยกเลิกคำถาม" : "Cancel question"}</Button>
      </div>
      {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
    </Panel>
  );
}

/** Questions the person already answered whose request has not been sent again. The answer sticks to the exact request: sending it again attaches the answer once; accepting keeps the result. */
function AnsweredCard({ c, onChanged }: { c: Clarification; onChanged: () => void }) {
  const { lang } = useLang();
  const th = lang === "th";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const accept = async () => {
    setBusy(true);
    setError(null);
    try { await desk.acceptClarification(c.clarification_id); onChanged(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  };
  return (
    <Panel title={th ? "ตอบแล้ว รอคุณส่งคำขอเดิมอีกครั้ง" : "Answered: waiting for you to send the request again"} aside={<Badge tone="leaf">v{c.new_intent_version ?? "?"}</Badge>}>
      <Row wrap label={th ? "เป้าหมายเดิม" : "Original goal"}>{c.original_goal}</Row>
      <Row wrap label={th ? "คำตอบของคุณ" : "Your answer"}>{c.answer}</Row>
      <p className="mt-2 text-[12px] text-dl-muted">{th ? "ส่งคำขอเดิมอีกครั้ง (คำตอบจะแนบให้หนึ่งครั้ง) หรือเลือกเก็บผลเดิมไว้" : "Send the same request again (your answer is attached once), or keep the result as it is."}</p>
      <div className="mt-2 flex gap-2">
        <a className="desk-focus inline-flex items-center rounded border border-dl-leaf/60 px-3 py-1.5 text-[13px] text-dl-leaf hover:bg-dl-pine/30" href={`/chat?goal=${encodeURIComponent(c.original_goal)}`}>{th ? "เปิดในแชท" : "Open in chat"}</a>
        <Button tone="ghost" onClick={accept} disabled={busy}>{th ? "เก็บผลเดิมไว้" : "Keep the result as it is"}</Button>
      </div>
      {error ? <p role="status" className="mt-2 text-[13px] text-dl-rust">{error}</p> : null}
    </Panel>
  );
}

export function AnsweredSection({ list }: { list: ReturnType<typeof useDeskData<Clarification[]>> }) {
  const { lang } = useLang();
  const th = lang === "th";
  const open = (list.data ?? []).filter((c) => !c.continued_as);
  if (list.error || !open.length) return null;
  return (
    <section aria-label={th ? "คำถามที่ตอบแล้ว" : "Answered questions"} className="mb-6">
      <h2 className="desk-mono mb-3 text-[12px] uppercase tracking-[0.08em] text-dl-leaf">{th ? `ตอบแล้ว รอส่งซ้ำ (${open.length})` : `Answered, waiting to be sent again (${open.length})`}</h2>
      <div className="grid gap-5 xl:grid-cols-2">{open.map((c) => <AnsweredCard key={c.clarification_id} c={c} onChanged={list.reload} />)}</div>
    </section>
  );
}

/** Questions the system has put to the person and is waiting on. Approvals are separate (they need a signature);
 *  these need words. Questions about an acceptance contract are not listed here yet (they live in the contract store). */
export function QuestionsSection({ list, alsoReload }: { list: ReturnType<typeof useDeskData<Clarification[]>>; alsoReload?: () => void }) {
  const { lang } = useLang();
  const th = lang === "th";
  if (list.error) return <ErrorNote error={list.error} onRetry={list.reload} />;
  if (!list.data || !list.data.length) return null;
  return (
    <section aria-label={th ? "คำถามที่รอคำตอบจากคุณ" : "Questions waiting for you"} className="mb-6">
      <h2 className="desk-mono mb-3 text-[12px] uppercase tracking-[0.08em] text-dl-amber">
        {th ? `คำถามที่รอคำตอบจากคุณ (${list.data.length})` : `Questions waiting for you (${list.data.length})`}
      </h2>
      <div className="grid gap-5 xl:grid-cols-2">
        {list.data.map((c) => <QuestionCard key={c.clarification_id} c={c} onChanged={() => { list.reload(); alsoReload?.(); }} />)}
      </div>
    </section>
  );
}

const pct = (x: number | null) => (x === null ? "-" : `${Math.round(x * 100)}%`);

/** The stop-and-ask in numbers (read-only): how many questions, and what people did with them. `kept + cancelled` is only a PROXY for a question that was not needed, and the module says so;
 *  the panel shows that sentence and the module's own hint instead of a verdict of its own. */
export function QuestionStatsPanel({ stats }: { stats: ReturnType<typeof useDeskData<Rct7Stats>> }) {
  const { lang } = useLang();
  const th = lang === "th";
  if (stats.error) return <ErrorNote error={stats.error} onRetry={stats.reload} />;
  const d = stats.data;
  if (!d) return null;
  const kinds = Object.entries(d.by_kind).sort(([a], [b]) => a.localeCompare(b));
  return (
    <Panel title={th ? `สถิติการหยุดถาม ${d.days} วันล่าสุด` : `Stop-and-ask, last ${d.days} days`} className="mb-6">
      {d.total.asked === 0 ? (
        <p className="text-[13px] text-dl-muted">{th ? `ยังไม่เคยหยุดถามเลยใน ${d.episodes} งาน` : `It has not stopped to ask in ${d.episodes} episodes.`}</p>
      ) : (
        <>
          <div className="grid gap-x-8 sm:grid-cols-2">
            <Row label={th ? "งานทั้งหมด" : "Episodes"}>{d.episodes}</Row>
            <Row label={th ? "หยุดถาม" : "Stopped to ask"}>{d.stopped_to_ask}{d.asked_per_100_episodes !== null ? ` (${d.asked_per_100_episodes} ${th ? "ต่อ 100 งาน" : "per 100 episodes"})` : ""}</Row>
            <Row label={th ? "ตอบแล้ว" : "Answered"}>{d.total.answered}</Row>
            <Row label={th ? "รับตามที่เป็น" : "Kept as it was"}>{d.total.kept}</Row>
            <Row label={th ? "ยกเลิก" : "Cancelled"}>{d.total.cancelled}</Row>
            <Row label={th ? "หมดอายุ / รออยู่" : "Expired / waiting"}>{d.total.expired} / {d.total.waiting}</Row>
            <Row label={th ? "รับตามที่เป็น + ยกเลิก (ตัวแทนของคำถามที่ไม่จำเป็น)" : "Kept + cancelled (a proxy for an unneeded question)"}>{pct(d.kept_or_cancelled_share)}</Row>
          </div>
          {kinds.length ? (
            <table className="mt-3 w-full text-left text-[12px]">
              <caption className="sr-only">{th ? "แยกตามชนิดคำถาม" : "By kind of question"}</caption>
              <thead className="text-dl-muted"><tr><th scope="col" className="py-1 pr-3">{th ? "ชนิด" : "Kind"}</th><th scope="col" className="pr-3">{th ? "ถาม" : "Asked"}</th><th scope="col" className="pr-3">{th ? "ตอบ" : "Answered"}</th><th scope="col" className="pr-3">{th ? "รับตามเดิม" : "Kept"}</th><th scope="col" className="pr-3">{th ? "ยกเลิก" : "Cancelled"}</th><th scope="col">{th ? "รับ+ยกเลิก" : "Kept+cancelled"}</th></tr></thead>
              <tbody>
                {kinds.map(([key, b]) => (
                  <tr key={key} className="border-t border-dl-rule/60">
                    <td className="desk-mono py-1 pr-3">{key}</td><td className="pr-3">{b.asked}</td><td className="pr-3">{b.answered}</td><td className="pr-3">{b.kept}</td><td className="pr-3">{b.cancelled}</td><td>{pct(b.kept_or_cancelled_share)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <p className="mt-3 text-[13px] text-dl-text">{d.hint}</p>
          <p className="mt-1 text-[11px] text-dl-muted">{d.scope_note}</p>
        </>
      )}
    </Panel>
  );
}
