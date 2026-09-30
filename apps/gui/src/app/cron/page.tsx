"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

function every(seconds: number) {
  if (seconds % 86400 === 0) return `every ${seconds / 86400} d`;
  if (seconds % 3600 === 0) return `every ${seconds / 3600} h`;
  if (seconds % 60 === 0) return `every ${seconds / 60} min`;
  return `every ${seconds} s`;
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
