"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type ResumeAnswer } from "@/lib/desk-api";

const LIMIT_LABELS: Record<string, string> = {
  daily_usd: "Runtime money limit per day (USD)", daily_tokens: "Runtime token limit per day", user_daily_usd: "Per-person money limit per day (USD)",
  user_daily_tokens: "Per-person token limit per day", per_hour_per_user: "Episodes per hour, per person", per_hour: "Episodes per hour, everyone", repeat_limit: "Identical steps before a stop",
};

export default function SafetyPage() {
  const { lang } = useLang();
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
          <Panel title="Pause switch" aside={e ? (e.paused ? <Badge tone="rust">PAUSED</Badge> : <Badge tone="leaf">running</Badge>) : undefined}>
            {e?.paused ? (
              <>
                <p className="text-[13px] text-dl-text">Nothing starts and no tool runs, from any entry point (chat, scheduled jobs, webhooks, tasks, subagents). Paused by <Code>{e.paused.by}</Code>{e.paused.reason ? `: ${e.paused.reason}` : ""}.</p>
                <div className="mt-3 flex items-center gap-3">
                  <Button tone="amber" disabled={busy} onClick={() => act(async () => { const r = await desk.envelopeResume(); if (r.pending_signature) setPending(r); else setPending(null); })}>
                    {e.resume_needs_signature ? "Resume (needs a signature)" : "Resume"}
                  </Button>
                </div>
                {pending?.pending_signature ? (
                  <div className="mt-3 text-[13px] text-dl-text">
                    <p>Sign it on the machine that holds your approver key:</p>
                    <p className="mt-1"><Code>delentia approvals approve {pending.approval_id} --key &lt;your key&gt;</Code></p>
                    <div className="mt-2"><Button tone="ghost" disabled={busy} onClick={() => act(async () => { await desk.envelopeResume(pending.approval_id); setPending(null); })}>I signed it: resume now</Button></div>
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <p className="text-[13px] text-dl-text">{lang === "th" ? "หยุดทุกอย่างทันที: ไม่มี episode เริ่มและไม่มี tool ทำงาน จากทุกช่องทาง" : "Stop everything now: no episode starts and no tool runs, from every entry point."}</p>
                <div className="mt-3 flex items-center gap-3">
                  <input value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder="why (optional)" className="w-64 rounded-md border border-dl-rule bg-dl-bg px-2 py-1 text-[13px]" />
                  <Button tone="amber" disabled={busy} onClick={() => act(() => desk.envelopePause(reason))}>Pause the agent</Button>
                </div>
              </>
            )}
          </Panel>
          <Panel title="Limits and use" aside={e ? (noDaily ? <Badge tone="amber">no daily limit</Badge> : <Badge tone="leaf">daily limit set</Badge>) : undefined}>
            {e ? (
              <>
                {Object.entries(e.limits).map(([k, v]) => <Row key={k} label={LIMIT_LABELS[k] ?? k}>{v ?? "no limit"}</Row>)}
                <Row label="Last 24 hours">{e.last_24h.episodes ?? 0} episodes · {e.last_24h.tokens ?? 0} tokens · ${e.last_24h.cost_usd ?? 0}</Row>
                <Row label="Last hour">{e.last_hour.episodes ?? 0} episodes</Row>
                {noDaily ? <p className="mt-3 text-[12px] text-dl-muted">Set <Code>DELENTIA_DAILY_BUDGET_USD</Code>, <Code>DELENTIA_USER_DAILY_BUDGET_USD</Code> and <Code>DELENTIA_EPISODES_PER_HOUR_PER_USER</Code> on the host. Without a daily limit, only the per-episode cap bounds what a flood of requests can cost.</p> : null}
              </>
            ) : null}
          </Panel>
          <Panel title="Owner alerts" aside={e ? (e.owner_alerts.targets.length ? <Badge tone="leaf">{e.owner_alerts.targets.length} target</Badge> : <Badge tone="amber">nobody is told</Badge>) : undefined}>
            {e?.owner_alerts.targets.map((t) => <Row key={`${t.channel}:${t.to}`} label={t.channel}>{t.to}</Row>)}
            {e?.owner_alerts.dropped.map((t) => <p key={`${t.channel}:${t.to}`} className="text-[13px] text-dl-rust">{t.channel}:{t.to} was dropped: {t.why}</p>)}
            {e && !e.owner_alerts.configured ? <p className="text-[13px] text-dl-text">Right now a request that needs your signature waits silently until you open this page. Set <Code>DELENTIA_OWNER_NOTIFY=telegram:&lt;your id&gt;</Code> (and list that id in <Code>DELENTIA_TELEGRAM_ALLOWED_SENDERS</Code>).</p> : null}
            <p className="mt-2 text-[12px] text-dl-muted">Messages carry the tool name, who asked and the code, never the goal or the arguments. At most {e?.owner_alerts.per_hour ?? 20} an hour.</p>
          </Panel>
          <Panel title="Webhooks" aside={hooks.data ? <Badge>{hooks.data.routes.length} route(s)</Badge> : undefined}>
            {hooks.error ? <ErrorNote error={hooks.error} onRetry={hooks.reload} /> : null}
            {hooks.data && !hooks.data.routes.length && !hooks.data.problems.length ? <Empty title="No webhook route">Routes live in <Code>{hooks.data.path}</Code>. A signed request starts an episode that begins tainted.</Empty> : null}
            {hooks.data?.routes.map((r) => (
              <Row key={r.name} label={`POST /v1/webhooks/${r.name}`}>{r.open ? <Badge tone="leaf">open</Badge> : <Badge tone="rust">closed: set {r.secret_env}</Badge>} {r.verify} · {r.mode}{r.events.length ? ` · ${r.events.join(", ")}` : ""}</Row>
            ))}
            {hooks.data?.problems.map((p) => <p key={p} className="text-[13px] text-dl-amber">Not served: {p}</p>)}
            {hooks.data?.recent.length ? <p className="mt-3 text-[12px] text-dl-muted">Latest: {hooks.data.recent.slice(0, 5).map((r) => `${r.route} ${r.action}`).join(" · ")}</p> : null}
          </Panel>
        </div>
        <Panel title={lang === "th" ? "งานที่ค้างและงานเบื้องหลัง" : "Tasks and background jobs"} className="mt-4" aside={board.data ? <Badge>{board.data.tasks.length} task(s) · {board.data.jobs.length} job(s)</Badge> : undefined}>
          {board.error ? <ErrorNote error={board.error} onRetry={board.reload} /> : null}
          {board.data && !board.data.tasks.length && !board.data.jobs.length ? <Empty title="Nothing in progress">Tasks are goals in steps (<Code>delentia task create</Code>); jobs are background runs (<Code>POST /v1/agent/jobs</Code>).</Empty> : null}
          {board.data?.tasks.map((t) => (
            <div key={t.id} className="border-b border-dl-rule/60 py-3 last:border-0">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[13px] text-dl-text"><Code>{t.id}</Code> · {t.namespace} · {t.goal}</div>
                <div className="flex items-center gap-2">
                  <Badge tone={t.status === "done" ? "leaf" : t.status === "failed" ? "rust" : "amber"}>{t.status}</Badge>
                  {t.tainted ? <Badge tone="amber">read outside text</Badge> : null}
                  {["running", "waiting", "waiting_approval"].includes(t.status) ? <Button tone="ghost" disabled={busy} onClick={() => act(() => desk.taskCancel(t.id))}>Cancel</Button> : null}
                </div>
              </div>
              <p className="mt-1 text-[12px] text-dl-muted">{t.steps.map((s) => `${s.n}:${s.status}`).join("  ")}{t.note ? ` — ${t.note}` : ""}</p>
            </div>
          ))}
          {board.data?.jobs.map((j) => <Row key={j.id} label={`${j.id} · ${j.namespace}`}>{j.status}{j.stopped ? ` (${j.stopped})` : ""} · {j.steps} step(s){j.last_tool ? ` · last: ${j.last_tool}` : ""}</Row>)}
        </Panel>
      </PageBody>
    </>
  );
}
