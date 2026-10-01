"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtNum, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const STAGES = ["understand", "recall", "plan", "act", "verify", "compress", "record", "evolve"];

export default function AlgorithmsPage() {
  const { lang } = useLang();
  const p = useDeskData(() => desk.pipeline(), [], 20000);
  const data = p.data;

  const stats = new Map<string, { ok: number; na: number; err: number; ms: number | null; effect?: string }>();
  for (const a of data?.by_algorithm ?? []) {
    stats.set(`${a.algo_id}:${a.stage}`, { ok: a.ok, na: a.not_triggered, err: a.error, ms: a.mean_ms, effect: a.effect });
  }

  return (
    <>
      <PageHeader title={lang === "th" ? "อัลกอริทึม" : "Algorithms"}
        lead={lang === "th"
          ? "อัลกอริทึมทั้ง 41 ตัวเป็นขั้นตอนของ pipeline รอบ episode ทุกตัวมี adapter ที่แปลงเป้าหมายและข้อมูลของผู้ใช้เป็น input จริง ตารางนี้แสดงสิ่งที่ถูกบันทึกจริงในแต่ละรอบ: รันได้ไหม ใช้เวลาเท่าไร และผลไปอยู่ที่ไหน ตัวที่ต้องมี URL วิดีโอ หรือการเรียกโมเดล จะบอกเหตุผลเมื่อไม่ได้รัน"
          : "The 41 algorithms as stages of a pipeline around each episode. Each has an adapter that turns the goal and the user's own data into a real input. The table shows what was actually recorded: did it run, how long it took and where its output went. Algorithms that need a URL, a video or a model call say why when they did not run."} />
      <PageBody>
        {p.error ? <ErrorNote error={p.error} onRetry={p.reload} /> : null}
        {data ? (
          <div className="space-y-6">
            <Panel title="Pipeline" aside={data.enabled ? <Badge tone="leaf">on</Badge> : <Badge tone="amber">off</Badge>}>
              <Row label="Algorithms with an adapter">{data.algorithms} of 41</Row>
              <Row label="Episodes recorded">{data.runs.length}</Row>
              <Row label="Latest total time">{data.runs[0] ? `${fmtNum(data.runs[0].total_ms, 0)} ms` : "-"}</Row>
              {!data.enabled ? (
                <p className="mt-3 text-[13px] leading-relaxed text-dl-muted">
                  The pipeline runs around every episode when <Code>DELENTIA_ALGORITHM_PIPELINE=1</Code>. <Code>delentia serve</Code> turns it on; it is off for one-off CLI runs and tests.
                </p>
              ) : null}
            </Panel>

            {STAGES.map((stage) => {
              const rows = data.adapters.filter((a) => a.stage === stage);
              if (!rows.length) return null;
              return (
                <Panel key={stage} title={stage} aside={<span className="desk-mono text-[11px] text-dl-muted">{rows.length} algorithms</span>}>
                  <div className="overflow-x-auto">
                    <table className="desk-mono w-full text-left text-[12px]">
                      <thead className="text-dl-muted"><tr>
                        <th className="py-1 pr-3 font-normal">id</th><th className="pr-3 font-normal">algorithm</th><th className="pr-3 font-normal">needs</th>
                        <th className="pr-3 font-normal">ran / skipped / failed</th><th className="pr-3 font-normal">mean ms</th><th className="font-normal">effect</th>
                      </tr></thead>
                      <tbody>
                        {rows.map((a) => {
                          const s = stats.get(`${a.algo_id}:${a.stage}`);
                          return (
                            <tr key={`${a.algo_id}:${a.stage}`} className="border-t border-dl-rule/60 align-top">
                              <td className="py-1.5 pr-3 text-dl-leaf">{a.algo_id}</td>
                              <td className="pr-3 text-dl-text">{a.name}</td>
                              <td className="pr-3">
                                <span className="inline-flex gap-1">
                                  {a.needs_llm ? <Badge tone="amber">model</Badge> : null}
                                  {a.needs_network ? <Badge tone="amber">network</Badge> : null}
                                  {a.writes_files ? <Badge tone="amber">files</Badge> : null}
                                  {!a.needs_llm && !a.needs_network && !a.writes_files ? <span className="text-dl-muted">-</span> : null}
                                </span>
                              </td>
                              <td className="pr-3">{s ? `${s.ok} / ${s.na} / ${s.err}` : <span className="text-dl-muted">not recorded</span>}</td>
                              <td className="pr-3">{s?.ms != null ? fmtNum(s.ms) : "-"}</td>
                              <td className="max-w-[44ch] text-dl-muted">{s?.effect ?? ""}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              );
            })}

            <Panel title="Recent pipeline runs">
              {data.runs.length ? (
                <table className="desk-mono w-full text-left text-[12px]">
                  <thead className="text-dl-muted"><tr>
                    <th className="py-1 pr-3 font-normal">when</th><th className="pr-3 font-normal">user</th><th className="pr-3 font-normal">ran</th>
                    <th className="pr-3 font-normal">skipped</th><th className="pr-3 font-normal">failed</th><th className="pr-3 font-normal">ms</th><th className="font-normal">advice lines</th>
                  </tr></thead>
                  <tbody>
                    {data.runs.map((r) => (
                      <tr key={r.id} className="border-t border-dl-rule/60">
                        <td className="py-1 pr-3 text-dl-muted">{fmtTime(r.at)}</td><td className="pr-3">{r.namespace}</td><td className="pr-3">{r.ok}</td>
                        <td className="pr-3">{r.not_triggered}</td><td className={`pr-3 ${r.errors ? "text-dl-rust" : ""}`}>{r.errors}</td>
                        <td className="pr-3">{fmtNum(r.total_ms, 0)}</td><td>{r.advice_lines}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="text-sm text-dl-muted">No pipeline run recorded yet.</p>}
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
