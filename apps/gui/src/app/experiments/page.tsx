"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Empty, ErrorNote, PageBody, PageHeader, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const METRICS = ["finished", "iterations", "tool_calls", "aligned_with_intent", "skills_injected", "duration_s", "route_path", "stopped_reason"] as const;

function Runs({ id }: { id: string }) {
  const runs = useDeskData(() => desk.experiment(id), [id]);
  if (runs.error) return <ErrorNote error={runs.error} />;
  if (!runs.data) return <p className="desk-mono text-sm text-dl-muted">Loading…</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-[12px]">
        <thead className="desk-mono text-[11px] text-dl-muted">
          <tr><th className="pb-2 pr-3 font-normal">Run</th>{METRICS.map((m) => <th key={m} className="pb-2 pr-3 font-normal">{m}</th>)}</tr>
        </thead>
        <tbody className="desk-mono">
          {runs.data.runs.map((r) => (
            <tr key={r.id} className="border-t border-dl-rule/60">
              <td className="py-1.5 pr-3 text-dl-muted">{fmtTime(r.timestamp)}</td>
              {METRICS.map((m) => <td key={m} className="py-1.5 pr-3 text-dl-text">{r.metrics[m] === null || r.metrics[m] === undefined ? "-" : String(r.metrics[m])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ExperimentsPage() {
  const { t, lang } = useLang();
  const list = useDeskData(() => desk.experiments(), [], 30000);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHeader title={t("experiments")}
        lead={lang === "th"
          ? "ทุก episode ถูกบันทึกเป็น experiment run ใน RCTDB และจัดกลุ่มตามเป้าหมาย เพื่อดูว่าการทำโจทย์เดิมซ้ำดีขึ้นจริงหรือไม่ (เกณฑ์ข้อ 6: การเรียนรู้วัดผลได้)"
          : "Every episode is an RCTDB experiment run, grouped by goal, so you can see whether repeating a goal really gets better (finish-line criterion 6: measurable learning)."} />
      <PageBody>
        {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
        {list.data && !list.data.experiments.length ? <Empty title="No experiments yet">Each agent episode adds a run here.</Empty> : null}
        <div className="space-y-4">
          {list.data?.experiments.map((e) => (
            <Panel key={e.id} title={e.name}
              aside={<button onClick={() => setOpen(open === e.id ? null : e.id)} aria-expanded={open === e.id} className="desk-focus desk-mono text-[11px] text-dl-leaf underline">{open === e.id ? "hide runs" : `${e.runs} runs`}</button>}>
              <p className="desk-mono text-[12px] text-dl-muted">
                {e.runs} runs · last {fmtTime(e.last_run)}
                {e.compare ? "" : " · needs two runs to compare"}
              </p>
              {e.compare && Object.keys(e.compare).length ? (
                <ul className="desk-mono mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
                  {Object.entries(e.compare as Record<string, { first: number; last: number; delta: number }>).map(([k, v]) => (
                    <li key={k} className="text-dl-muted">
                      {k} {v.first} → <span className="text-dl-text">{v.last}</span>{" "}
                      <span>({v.delta > 0 ? "+" : ""}{Math.round(v.delta * 1000) / 1000})</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {open === e.id ? <div className="mt-3"><Runs id={e.id} /></div> : null}
            </Panel>
          ))}
        </div>
      </PageBody>
    </>
  );
}
