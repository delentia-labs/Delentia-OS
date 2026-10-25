"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type BoardTask, type ResumeAnswer } from "@/lib/desk-api";

/** One task: a DRAFT shows its plan as editable text (one step per line) and runs nothing until Start; a failed or cancelled task can be re-planned into a new draft. */
function TaskRow({ task: t, busy, act }: { task: BoardTask; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const th = useLang().lang === "th";
  const pendingText = t.steps.filter((s) => s.status === "pending").map((s) => s.text).join("\n");
  const [text, setText] = useState(pendingText);
  const editable = ["draft", "waiting", "waiting_approval"].includes(t.status) && !t.steps.some((s) => s.status === "running");
  const lines = () => text.split("\n").map((x) => x.trim()).filter(Boolean);
  return (
    <div className="border-b border-dl-rule/60 py-3 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] text-dl-text"><Code>{t.id}</Code> · {t.namespace} · {t.goal}</div>
        <div className="flex items-center gap-2">
          <Badge tone={t.status === "done" ? "leaf" : t.status === "failed" ? "rust" : "amber"}>{t.status}</Badge>
          {t.tainted ? <Badge tone="amber">{th ? "อ่านข้อความจากภายนอกแล้ว" : "read outside text"}</Badge> : null}
          {t.status === "draft" ? <Button disabled={busy || !lines().length} onClick={() => act(async () => { await desk.taskPlan(t.id, lines()); await desk.taskStart(t.id); })}>{th ? "บันทึกและเริ่ม" : "Save and start"}</Button> : null}
          {["failed", "cancelled"].includes(t.status) ? <Button tone="ghost" disabled={busy} onClick={() => act(() => desk.taskReplan(t.id))}>{th ? "วางแผนใหม่" : "Re-plan"}</Button> : null}
          {["running", "waiting", "waiting_approval", "draft"].includes(t.status) ? <Button tone="ghost" disabled={busy} onClick={() => act(() => desk.taskCancel(t.id))}>{th ? "ยกเลิก" : "Cancel"}</Button> : null}
        </div>
      </div>
      <p className="mt-1 text-[12px] text-dl-muted">{t.steps.map((s) => `${s.n}:${s.status}`).join("  ")}{t.note ? ` — ${t.note}` : ""}</p>
      {editable && t.steps.some((s) => s.status === "pending") ? (
        <div className="mt-2">
          <textarea className="w-full rounded border border-dl-rule bg-transparent p-2 text-[12px] text-dl-text" rows={Math.min(8, Math.max(3, lines().length + 1))} value={text} onChange={(ev) => setText(ev.target.value)} aria-label={th ? "ขั้นตอนที่ยังไม่ได้รัน บรรทัดละหนึ่งขั้น" : "Steps that have not run yet, one per line"} />
          <div className="mt-1 flex gap-2">
            <Button tone="ghost" disabled={busy || !lines().length || text === pendingText} onClick={() => act(() => desk.taskPlan(t.id, lines()))}>{th ? "บันทึกแผน" : "Save plan"}</Button>
            <span className="text-[11px] text-dl-muted self-center">{th ? "หนึ่งขั้นต่อหนึ่งบรรทัด ขั้นที่รันไปแล้วจะไม่เปลี่ยน" : "One step per line. Steps that already ran stay as they are."}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const LIMIT_LABELS_TH: Record<string, string> = {
  daily_usd: "วงเงินเงินต่อวัน ของทั้งระบบ (USD)", daily_tokens: "วงเงินโทเค็นต่อวัน ของทั้งระบบ", user_daily_usd: "วงเงินเงินต่อวัน ต่อคน (USD)",
  user_daily_tokens: "วงเงินโทเค็นต่อวัน ต่อคน", per_hour_per_user: "จำนวนงานต่อชั่วโมง ต่อคน", per_hour: "จำนวนงานต่อชั่วโมง ของทุกคนรวม", repeat_limit: "ทำขั้นเดิมซ้ำได้กี่ครั้งก่อนหยุด",
};
const LIMIT_LABELS: Record<string, string> = {
  daily_usd: "Runtime money limit per day (USD)", daily_tokens: "Runtime token limit per day", user_daily_usd: "Per-person money limit per day (USD)",
  user_daily_tokens: "Per-person token limit per day", per_hour_per_user: "Episodes per hour, per person", per_hour: "Episodes per hour, everyone", repeat_limit: "Identical steps before a stop",
};

export default function SafetyPage() {
  const { lang } = useLang();
  const th = lang === "th";
  const env = useDeskData(() => desk.envelope(), [], 8000);
  const hooks = useDeskData(() => desk.webhooks(), [], 15000);
  const board = useDeskData(() => desk.tasks(), [], 8000);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<ResumeAnswer | null>(null);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    try { await fn(); env.reload(); board.reload(); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const e = env.data;
  const noDaily = !!e && ["daily_usd", "daily_tokens", "user_daily_usd", "user_daily_tokens"].every((k) => !e.limits[k]);
  return (
    <>
      <PageHeader title={lang === "th" ? "ความปลอดภัยของงานไร้คนดู" : "Safety for unattended work"}
        lead={lang === "th"
          ? "ปุ่มหยุดฉุกเฉิน งบรายวัน เพดานต่อชั่วโมง ใครจะถูกแจ้งเมื่อ agent ต้องการลายเซ็น เวบฮุกที่เปิดอยู่ และงานที่ค้างอยู่ การหยุดทำได้เลยไม่ต้องเซ็น การต่อใหม่ต้องเซ็นเมื่อมี approver key"
          : "The pause switch, daily and hourly limits, who is told when the agent needs a signature, the webhooks that are open, and the work in progress. Pausing is free; lifting a pause needs a signature once an approver key exists."} />
      <PageBody>
        {env.error ? <ErrorNote error={env.error} onRetry={env.reload} /> : null}
        {message ? <p role="alert" className="mb-3 text-[13px] text-dl-rust">{message}</p> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel title={th ? "ปุ่มหยุดฉุกเฉิน" : "Pause switch"} aside={e ? (e.paused ? <Badge tone="rust">{th ? "หยุดอยู่" : "PAUSED"}</Badge> : <Badge tone="leaf">{th ? "ทำงานอยู่" : "running"}</Badge>) : undefined}>
            {e?.paused ? (
              <>
                <p className="text-[13px] text-dl-text">{th ? "ไม่มีอะไรเริ่มและไม่มีเครื่องมือทำงาน จากทุกช่องทาง (แชต งานตามเวลา เว็บฮุก งานยาว เอเจนต์ย่อย) หยุดโดย " : "Nothing starts and no tool runs, from any entry point (chat, scheduled jobs, webhooks, tasks, subagents). Paused by "}<Code>{e.paused.by}</Code>{e.paused.reason ? `: ${e.paused.reason}` : ""}.</p>
                <div className="mt-3 flex items-center gap-3">
                  <Button tone="amber" disabled={busy} onClick={() => act(async () => { const r = await desk.envelopeResume(); if (r.pending_signature) setPending(r); else setPending(null); })}>
                    {e.resume_needs_signature ? (th ? "กลับมาทำงาน (ต้องมีลายเซ็น)" : "Resume (needs a signature)") : (th ? "กลับมาทำงาน" : "Resume")}
                  </Button>
                </div>
                {pending?.pending_signature ? (
                  <div className="mt-3 text-[13px] text-dl-text">
                    <p>{th ? "เซ็นบนเครื่องที่เก็บกุญแจผู้อนุมัติของคุณ:" : "Sign it on the machine that holds your approver key:"}</p>
                    <p className="mt-1"><Code>delentia approvals approve {pending.approval_id} --key &lt;your key&gt;</Code></p>
                    <div className="mt-2"><Button tone="ghost" disabled={busy} onClick={() => act(async () => { await desk.envelopeResume(pending.approval_id); setPending(null); })}>{th ? "เซ็นแล้ว: กลับมาทำงานเลย" : "I signed it: resume now"}</Button></div>
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <p className="text-[13px] text-dl-text">{lang === "th" ? "หยุดทุกอย่างทันที: ไม่มี episode เริ่มและไม่มี tool ทำงาน จากทุกช่องทาง" : "Stop everything now: no episode starts and no tool runs, from every entry point."}</p>
                <div className="mt-3 flex items-center gap-3">
                  <input value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder={th ? "เหตุผล (ไม่บังคับ)" : "why (optional)"} className="w-64 rounded-md border border-dl-rule bg-dl-bg px-2 py-1 text-[13px]" />
                  <Button tone="amber" disabled={busy} onClick={() => act(() => desk.envelopePause(reason))}>{th ? "พักเอเจนต์" : "Pause the agent"}</Button>
                </div>
              </>
            )}
          </Panel>
          <Panel title={th ? "วงเงินและการใช้งาน" : "Limits and use"} aside={e ? (noDaily ? <Badge tone="amber">{th ? "ยังไม่มีวงเงินรายวัน" : "no daily limit"}</Badge> : <Badge tone="leaf">{th ? "ตั้งวงเงินรายวันแล้ว" : "daily limit set"}</Badge>) : undefined}>
            {e ? (
              <>
                {Object.entries(e.limits).map(([k, v]) => <Row key={k} label={(th ? LIMIT_LABELS_TH[k] : LIMIT_LABELS[k]) ?? k}>{v ?? (th ? "ไม่จำกัด" : "no limit")}</Row>)}
                <Row label={th ? "24 ชั่วโมงที่ผ่านมา" : "Last 24 hours"}>{e.last_24h.episodes ?? 0} {th ? "งาน" : "episodes"} · {e.last_24h.tokens ?? 0} {th ? "โทเค็น" : "tokens"} · ${e.last_24h.cost_usd ?? 0}</Row>
                <Row label={th ? "1 ชั่วโมงที่ผ่านมา" : "Last hour"}>{e.last_hour.episodes ?? 0} {th ? "งาน" : "episodes"}</Row>
                {noDaily ? <p className="mt-3 text-[12px] text-dl-muted">{th ? <>ตั้ง <Code>DELENTIA_DAILY_BUDGET_USD</Code>, <Code>DELENTIA_USER_DAILY_BUDGET_USD</Code> และ <Code>DELENTIA_EPISODES_PER_HOUR_PER_USER</Code> บนเครื่องโฮสต์ ถ้าไม่มีวงเงินรายวัน สิ่งเดียวที่จำกัดค่าใช้จ่ายเมื่อมีคำขอท่วมคือเพดานต่องาน</> : <>Set <Code>DELENTIA_DAILY_BUDGET_USD</Code>, <Code>DELENTIA_USER_DAILY_BUDGET_USD</Code> and <Code>DELENTIA_EPISODES_PER_HOUR_PER_USER</Code> on the host. Without a daily limit, only the per-episode cap bounds what a flood of requests can cost.</>}</p> : null}
              </>
            ) : null}
          </Panel>
          <Panel title={th ? "แจ้งเตือนเจ้าของ" : "Owner alerts"} aside={e ? (e.owner_alerts.targets.length ? <Badge tone="leaf">{e.owner_alerts.targets.length} {th ? "ผู้รับ" : "target"}</Badge> : <Badge tone="amber">{th ? "ยังไม่มีใครถูกแจ้ง" : "nobody is told"}</Badge>) : undefined}>
            {e?.owner_alerts.targets.map((t) => <Row key={`${t.channel}:${t.to}`} label={t.channel}>{t.to}</Row>)}
            {e?.owner_alerts.dropped.map((t) => <p key={`${t.channel}:${t.to}`} className="text-[13px] text-dl-rust">{t.channel}:{t.to} {th ? "ถูกตัดออก" : "was dropped"}: {t.why}</p>)}
            {e && !e.owner_alerts.configured ? <p className="text-[13px] text-dl-text">{th ? <>ตอนนี้งานที่ต้องการลายเซ็นของคุณจะรออยู่เงียบ ๆ จนกว่าคุณจะเปิดหน้านี้ ตั้ง <Code>DELENTIA_OWNER_NOTIFY=telegram:&lt;ไอดีของคุณ&gt;</Code> (และใส่ไอดีนั้นใน <Code>DELENTIA_TELEGRAM_ALLOWED_SENDERS</Code>) เพื่อให้แจ้งเตือน</> : <>Right now a request that needs your signature waits silently until you open this page. Set <Code>DELENTIA_OWNER_NOTIFY=telegram:&lt;your id&gt;</Code> (and list that id in <Code>DELENTIA_TELEGRAM_ALLOWED_SENDERS</Code>).</>}</p> : null}
            <p className="mt-2 text-[12px] text-dl-muted">{th ? `ข้อความมีแค่ชื่อเครื่องมือ ผู้ขอ และรหัส ไม่มีเป้าหมายหรืออาร์กิวเมนต์ อย่างมาก ${e?.owner_alerts.per_hour ?? 20} ข้อความต่อชั่วโมง` : `Messages carry the tool name, who asked and the code, never the goal or the arguments. At most ${e?.owner_alerts.per_hour ?? 20} an hour.`}</p>
          </Panel>
          <Panel title={th ? "เว็บฮุก (ให้ระบบอื่นสั่งงาน)" : "Webhooks"} aside={hooks.data ? <Badge>{hooks.data.routes.length} {th ? "เส้นทาง" : "route(s)"}</Badge> : undefined}>
            {hooks.error ? <ErrorNote error={hooks.error} onRetry={hooks.reload} /> : null}
            {hooks.data && !hooks.data.routes.length && !hooks.data.problems.length ? <Empty title={th ? "ยังไม่มีเส้นทางเว็บฮุก" : "No webhook route"}>{th ? <>เส้นทางอยู่ในไฟล์ <Code>{hooks.data.path}</Code> คำขอที่เซ็นถูกต้องจะเริ่มงานที่ถือว่า “อ่านข้อความจากภายนอก” ตั้งแต่ต้น</> : <>Routes live in <Code>{hooks.data.path}</Code>. A signed request starts an episode that begins tainted.</>}</Empty> : null}
            {hooks.data?.routes.map((r) => (
              <Row key={r.name} label={`POST /v1/webhooks/${r.name}`}>{r.open ? <Badge tone="leaf">{th ? "เปิด" : "open"}</Badge> : <Badge tone="rust">{th ? "ปิด: ตั้ง" : "closed: set"} {r.secret_env}</Badge>} {r.verify} · {r.mode}{r.events.length ? ` · ${r.events.join(", ")}` : ""}</Row>
            ))}
            {hooks.data?.problems.map((p) => <p key={p} className="text-[13px] text-dl-amber">{th ? "ไม่เปิดให้ใช้" : "Not served"}: {p}</p>)}
            {hooks.data?.recent.length ? <p className="mt-3 text-[12px] text-dl-muted">{th ? "ล่าสุด" : "Latest"}: {hooks.data.recent.slice(0, 5).map((r) => `${r.route} ${r.action}`).join(" · ")}</p> : null}
          </Panel>
        </div>
        <Panel title={lang === "th" ? "งานที่ค้างและงานเบื้องหลัง" : "Tasks and background jobs"} className="mt-4" aside={board.data ? <Badge>{board.data.tasks.length} {th ? "งานยาว" : "task(s)"} · {board.data.jobs.length} {th ? "งานเบื้องหลัง" : "job(s)"}</Badge> : undefined}>
          {board.error ? <ErrorNote error={board.error} onRetry={board.reload} /> : null}
          {board.data && !board.data.tasks.length && !board.data.jobs.length ? <Empty title={th ? "ไม่มีงานค้าง" : "Nothing in progress"}>{th ? <>งานยาวคือเป้าหมายที่แบ่งเป็นขั้น (<Code>delentia task create</Code>) งานเบื้องหลังคือการรันที่ไม่ต้องรอ (<Code>POST /v1/agent/jobs</Code>)</> : <>Tasks are goals in steps (<Code>delentia task create</Code>); jobs are background runs (<Code>POST /v1/agent/jobs</Code>).</>}</Empty> : null}
          {board.data?.tasks.map((t) => <TaskRow key={t.id} task={t} busy={busy} act={act} />)}
          {board.data?.jobs.map((j) => <Row key={j.id} label={`${j.id} · ${j.namespace}`}>{j.status}{j.stopped ? ` (${j.stopped})` : ""} · {j.steps} {th ? "ขั้น" : "step(s)"}{j.last_tool ? ` · ${th ? "ล่าสุด" : "last"}: ${j.last_tool}` : ""}</Row>)}
        </Panel>
      </PageBody>
    </>
  );
}
