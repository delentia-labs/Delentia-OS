"use client";

import { useEffect, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type CronJob, type CronPreview } from "@/lib/desk-api";

function every(seconds: number) {
  if (seconds % 86400 === 0) return `every ${seconds / 86400} d`;
  if (seconds % 3600 === 0) return `every ${seconds / 3600} h`;
  if (seconds % 60 === 0) return `every ${seconds / 60} min`;
  return `every ${seconds} s`;
}


function when(epoch: number | null) {
  return epoch ? fmtTime(new Date(epoch * 1000).toISOString()) : "-";
}

function Jobs() {
  const { lang } = useLang();
  const jobs = useDeskData(() => desk.cronJobs(), [], 15000);
  const [goal, setGoal] = useState("");
  const [schedule, setSchedule] = useState("");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("");
  const [to, setTo] = useState("");
  const [preview, setPreview] = useState<{ ok: boolean; text: string; runs: string[] } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  // Show what the schedule means, as the server understands it, before anything is saved. The request is made from a timer, not from an effect body.
  useEffect(() => {
    if (!schedule.trim()) return;
    const handle = window.setTimeout(() => {
      desk.cronPreview(schedule).then((p: CronPreview) => setPreview({ ok: true, text: p.meaning, runs: p.upcoming }))
        .catch((e) => setPreview({ ok: false, text: e instanceof Error ? e.message : String(e), runs: [] }));
    }, 400);
    return () => window.clearTimeout(handle);
  }, [schedule]);

  const create = async () => {
    setBusy("create");
    setMessage(null);
    try {
      const r = await desk.cronCreate({ goal, schedule, name: name || undefined, deliver: channel && to ? { channel, to } : null });
      setMessage({ tone: "ok", text: `Created ${r.job.id}: ${r.job.schedule_meaning}` });
      setGoal(""); setSchedule(""); setName(""); setTo(""); setChannel(""); setPreview(null);
      jobs.reload();
    } catch (e) {
      setMessage({ tone: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const act = async (job: CronJob, action: "enable" | "pause" | "run" | "delete") => {
    setBusy(`${job.id}:${action}`);
    setMessage(null);
    try {
      if (action === "delete") await desk.cronDelete(job.id);
      else await desk.cronAction(job.id, action);
      jobs.reload();
    } catch (e) {
      setMessage({ tone: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const d = jobs.data;
  const recipients = d && channel ? d.delivery[channel] ?? [] : [];
  return (
    <div className="mb-8 space-y-5">
      <Panel title={lang === "th" ? "งานตามเวลาของคุณ (ถาวร)" : "Your recurring jobs (persistent)"}
        aside={d ? <Badge>{d.jobs.length} of {d.limits.max_jobs}</Badge> : undefined}>
        <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">
          {lang === "th"
            ? "เป้าหมายที่ agent รันเองตามเวลาเป็น episode ที่ผ่าน gate ปกติทุกอย่าง (CORD, นโยบายเจ้าของ, ลายเซ็นสำหรับการเขียน) ผลเก็บไว้ในงานและส่งเข้าแชทที่คุณระบุได้ (เฉพาะคนที่อยู่ใน allowlist) เขียนเวลาแบบที่พูดได้ ไทยหรืออังกฤษ"
            : "Goals the agent runs on its own schedule as ordinary governed episodes (CORD, your policy, signatures for writes). The result is kept in the job and can be delivered to a listed person in a chat. Write the time the way you say it, in English or Thai."}
        </p>
        {jobs.error ? <ErrorNote error={jobs.error} onRetry={jobs.reload} /> : null}
        {message ? <p role="status" className={`mb-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
        {d && !d.jobs.length ? <p className="mb-3 text-sm text-dl-muted">No jobs yet.</p> : null}
        <ul className="divide-y divide-dl-rule/60">
          {d?.jobs.map((j) => (
            <li key={j.id} className="py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-dl-text">{j.name}</span>
                <Badge tone={j.enabled ? "leaf" : "muted"}>{j.enabled ? "on" : "off"}</Badge>
                {j.last_status ? <Badge tone={j.last_status === "llm_finished" ? "leaf" : j.last_status === "pending_approval" ? "amber" : "rust"}>{j.last_status}</Badge> : null}
                {j.fail_streak ? <Badge tone="rust">{j.fail_streak} failed in a row</Badge> : null}
              </div>
              <p className="desk-mono mt-1 text-[12px] text-dl-muted">{j.schedule_meaning} · next {when(j.next_run_at)} · {j.run_count} run(s){j.deliver ? ` · to ${j.deliver.channel}:${j.deliver.to}` : ""}</p>
              <p className="mt-1 text-[13px] text-dl-text">{j.goal}</p>
              {j.last_result ? <details className="mt-1"><summary className="desk-focus desk-mono cursor-pointer text-[12px] text-dl-leaf">Last result ({when(j.last_run_at)})</summary>
                <pre className="desk-mono mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-muted">{j.last_result}</pre></details> : null}
              <div className="mt-2 flex flex-wrap gap-2">
                <Button tone="ghost" onClick={() => act(j, "run")} disabled={busy !== null}>{busy === `${j.id}:run` ? "Running…" : "Run now"}</Button>
                <Button tone="ghost" onClick={() => act(j, j.enabled ? "pause" : "enable")} disabled={busy !== null}>{j.enabled ? "Pause" : "Resume"}</Button>
                <Button tone="amber" onClick={() => act(j, "delete")} disabled={busy !== null}>Delete</Button>
              </div>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="New job">
        <div className="space-y-3">
          <label className="block"><span className="desk-mono text-[12px] text-dl-muted">What should the agent do?</span>
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} maxLength={2000}
              className="desk-focus mt-1 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text" placeholder="Summarise the overnight audit log and flag anything unusual" /></label>
          <label className="block"><span className="desk-mono text-[12px] text-dl-muted">When? (timezone: {d?.timezone ?? "…"})</span>
            <input value={schedule} onChange={(e) => setSchedule(e.target.value)} maxLength={200}
              className="desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-[13px] text-dl-text" placeholder="every weekday at 8:30  ·  ทุกวันจันทร์ 9 โมงเช้า  ·  in 20 minutes" /></label>
          {schedule.trim() && preview ? (
            <div role="status" className={`rounded border px-3 py-2 text-[13px] ${preview.ok ? "border-dl-leaf/50" : "border-dl-rust/50"}`}>
              <p className={preview.ok ? "text-dl-leaf" : "text-dl-rust"}>{preview.ok ? `Understood: ${preview.text}` : preview.text}</p>
              {preview.ok ? <p className="desk-mono mt-1 text-[12px] text-dl-muted">next: {preview.runs.join("  ·  ")}</p> : null}
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block"><span className="desk-mono text-[12px] text-dl-muted">Name (optional)</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} className="desk-focus mt-1 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-[13px] text-dl-text" /></label>
            <label className="block"><span className="desk-mono text-[12px] text-dl-muted">Deliver the result to</span>
              <select value={channel} onChange={(e) => { setChannel(e.target.value); setTo(""); }} className="desk-focus mt-1 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-[13px] text-dl-text">
                <option value="">keep it in the job</option>
                {d ? Object.keys(d.delivery).map((c) => <option key={c} value={c}>{c}</option>) : null}
              </select></label>
            <label className="block"><span className="desk-mono text-[12px] text-dl-muted">Recipient</span>
              <select value={to} onChange={(e) => setTo(e.target.value)} disabled={!channel} className="desk-focus mt-1 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-[13px] text-dl-text disabled:opacity-50">
                <option value="">{channel && !recipients.length ? "nobody is listed for this channel" : "choose"}</option>
                {recipients.map((r) => <option key={r} value={r}>{r}</option>)}
              </select></label>
          </div>
          <p className="text-[12px] text-dl-muted">Only people on the channel&apos;s allowlist can receive results (set <Code>DELENTIA_TELEGRAM_ALLOWED_SENDERS</Code> and the like on the host), so a tricked agent cannot send your data to a stranger. Shortest interval {d?.limits.min_interval_s ?? 60} s; a job that fails {d?.limits.fails_before_off ?? 3} times in a row switches itself off.</p>
          <Button onClick={create} disabled={busy !== null || !goal.trim() || !schedule.trim() || (preview !== null && !preview.ok)}>{busy === "create" ? "Saving…" : "Create job"}</Button>
        </div>
      </Panel>
    </div>
  );
}

export default function CronPage() {
  const { t, lang } = useLang();
  const daemon = useDeskData(() => desk.daemon(), [], 10000);
  const [running, setRunning] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runNow = async (taskId: string) => {
    setRunning(taskId);
    setMessage(null);
    try {
      const r = await desk.runTask(taskId);
      setMessage(`${taskId}: ${r.status} ${r.output ?? r.error ?? ""}`);
      daemon.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  };

  const d = daemon.data;
  return (
    <>
      <PageHeader title={t("cron")}
        lead={lang === "th"
          ? "งานที่ daemon รันเองตามเวลา: ตรวจ audit chain, ฝาก head ของ chain กับพยานภายนอก (A3) และจับเตือนความจำที่ถึงเวลา"
          : "Work the daemon does on its own schedule: verify the audit chain, anchor its head at the outside witness (A3), fire due reminders."} />
      <PageBody>
        <Jobs />
        {daemon.error ? <ErrorNote error={daemon.error} onRetry={daemon.reload} /> : null}
        {d && !d.running ? (
          <div className="mb-6">
            <Empty title="The daemon is not running">Start the API with <Code>delentia serve</Code>; it turns the scheduler on. Tasks below show their last state.</Empty>
          </div>
        ) : null}
        {message ? <p role="status" className="desk-mono mb-4 text-[13px] text-dl-leaf">{message}</p> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {d?.tasks.map((task) => (
            <Panel key={task.task_id} title={task.name}
              aside={!task.is_enabled ? <Badge>off</Badge> : task.last_status === "SUCCESS" ? <Badge tone="leaf">ok</Badge>
                : task.last_status === "FAILED" ? <Badge tone="rust">failed</Badge> : <Badge>{task.last_status.toLowerCase()}</Badge>}>
              <p className="mb-2 text-[13px] leading-relaxed text-dl-muted">{task.description}</p>
              <Row label="Schedule">{every(task.interval_seconds)}</Row>
              <Row label="Last run">{fmtTime(task.last_run_at)}</Row>
              <Row label="Runs">{task.run_count}</Row>
              {task.last_output ? <p className="desk-mono mt-2 break-words text-[12px] text-dl-text">{task.last_output}</p> : null}
              <div className="mt-3">
                <Button onClick={() => runNow(task.task_id)} disabled={!d.running || running !== null}>
                  {running === task.task_id ? "Running…" : "Run now"}
                </Button>
              </div>
            </Panel>
          ))}
        </div>
      </PageBody>
    </>
  );
}
