"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtNum, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type Evolution, type IntentProfile } from "@/lib/desk-api";

function Mark({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-dl-muted">n/a</span>;
  return value ? <Badge tone="leaf">yes</Badge> : <Badge tone="muted">no</Badge>;
}

function EvolutionPanel({ e }: { e: Evolution }) {
  return (
    <Panel title={`Smarter, faster, cheaper · ${e.namespace}`} aside={<span className="desk-mono text-[11px] text-dl-muted">{e.goals_repeated} repeated goals</span>}>
      {!e.goals_repeated ? (
        <p className="text-sm leading-relaxed text-dl-muted">
          Nothing to compare yet: a goal needs at least two verified runs. Run the same kind of goal again in Chat and this fills in.
        </p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([["fewer steps", e.summary.fewer_steps], ["faster", e.summary.faster], ["cheaper", e.summary.cheaper], ["better informed", e.summary.better_informed]] as const).map(([label, n]) => (
              <div key={label} className="rounded border border-dl-rule px-3 py-2">
                <p className="desk-mono text-lg text-dl-text">{n}<span className="text-dl-muted">/{e.goals_repeated}</span></p>
                <p className="text-[12px] text-dl-muted">{label}</p>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="desk-mono w-full text-left text-[12px]">
              <thead className="text-dl-muted"><tr>
                <th className="py-1 pr-3 font-normal">goal</th><th className="pr-3 font-normal">runs</th><th className="pr-3 font-normal">steps</th>
                <th className="pr-3 font-normal">seconds</th><th className="pr-3 font-normal">D</th><th className="font-normal">fewer / faster / cheaper</th>
              </tr></thead>
              <tbody>
                {e.clusters.map((c) => (
                  <tr key={c.goal} className="border-t border-dl-rule/60 align-top">
                    <td className="max-w-[26ch] truncate py-1.5 pr-3 text-dl-text" title={c.goal}>{c.goal}</td>
                    <td className="pr-3">{c.verified_runs}</td>
                    <td className="pr-3">{c.first.steps ?? "-"} → {c.last.steps ?? "-"}</td>
                    <td className="pr-3">{fmtNum(c.first.seconds, 1)} → {fmtNum(c.last.seconds, 1)}</td>
                    <td className="pr-3">{fmtNum(c.first.D)} → {fmtNum(c.last.D)}</td>
                    <td><span className="inline-flex gap-1.5"><Mark value={c.fewer_steps} /><Mark value={c.faster} /><Mark value={c.cheaper} /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{e.note}</p>
        </>
      )}
    </Panel>
  );
}

function ProfilePanel({ p }: { p: IntentProfile }) {
  return (
    <Panel title={`Your intents · ${p.namespace}`} aside={<span className="desk-mono text-[11px] text-dl-muted">{p.episodes} episodes</span>}>
      {!p.episodes ? <p className="text-sm text-dl-muted">No episodes recorded for this user yet.</p> : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="overflow-x-auto">
            <table className="desk-mono w-full text-left text-[12px]">
              <thead className="text-dl-muted"><tr>
                <th className="py-1 pr-3 font-normal">kind</th><th className="pr-3 font-normal">episodes</th><th className="pr-3 font-normal">verified</th>
                <th className="pr-3 font-normal">blocked</th><th className="pr-3 font-normal">avg D</th><th className="font-normal">avg steps</th>
              </tr></thead>
              <tbody>
                {p.kinds.map((k) => (
                  <tr key={k.type} className="border-t border-dl-rule/60">
                    <td className="py-1.5 pr-3 text-dl-text">{k.type}</td><td className="pr-3">{k.episodes}</td><td className="pr-3">{k.verified}</td>
                    <td className={`pr-3 ${k.blocked ? "text-dl-rust" : ""}`}>{k.blocked}</td><td className="pr-3">{fmtNum(k.avg_D)}</td><td>{fmtNum(k.avg_steps, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <p className="desk-mono mb-2 text-[12px] text-dl-muted">goals that keep coming back</p>
            {p.recurring.length ? p.recurring.map((r) => (
              <p key={r.goal} className="border-t border-dl-rule/60 py-1.5 text-sm text-dl-text first:border-0">
                {r.goal} <span className="desk-mono text-[11px] text-dl-muted">· {r.runs} runs, {r.verified} verified</span>
              </p>
            )) : <p className="text-sm text-dl-muted">No goal has been asked twice yet.</p>}
          </div>
        </div>
      )}
    </Panel>
  );
}

export default function GrowthPage() {
  const { lang } = useLang();
  const g = useDeskData(() => desk.growth(), [], 20000);
  return (
    <>
      <PageHeader title={lang === "th" ? "การเติบโต" : "Growth"}
        lead={lang === "th"
          ? "MEE: G(t+1) = G(t)·(1 + M·Δ)·R ทุก episode ให้ค่า Δ ที่วัดได้ (ตรวจผ่าน + ตรงเจตนา + เร็ว/ถูก/สั้นกว่ารอบก่อนของเป้าหมายเดียวกัน) G เก็บแยกตามผู้ใช้และอยู่รอดข้ามการรีสตาร์ท หน้านี้วัดคำขวัญ “ยิ่งใช้ ยิ่งฉลาด ยิ่งเร็ว ยิ่งถูก” จากข้อมูลจริง"
          : "MEE: G(t+1) = G(t)·(1 + M·Δ)·R. Every episode yields a measured Δ (verified, matched the intent, and how much smaller, faster or cheaper than earlier verified runs of the same goal). G is kept per user and survives restarts. This page measures the motto - the more it is used, the smarter, faster and cheaper - from recorded runs."} />
      <PageBody>
        {g.error ? <ErrorNote error={g.error} onRetry={g.reload} /> : null}
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {g.data && !g.data.ledgers.length ? <div className="md:col-span-2 xl:col-span-3"><Empty title="No growth recorded yet">Run a goal in Chat (Agent mode). Each governed episode adds a step to its user&apos;s G.</Empty></div> : null}
            {g.data?.ledgers.map((l) => (
              <Panel key={l.namespace} title={l.namespace} aside={<Badge tone="leaf">G {fmtNum(l.G)}</Badge>}>
                <Row label="Growth ratio vs start">{fmtNum(l.growth_ratio)}×</Row>
                <Row label="Resilience R">{fmtNum(l.resilience, 3)}</Row>
                <Row label="Episodes / verified">{l.episodes} / {l.verified_episodes}</Row>
                <Row label="Last step">{fmtTime(l.updated_at)}</Row>
              </Panel>
            ))}
          </div>

          {g.data?.profiles.map((p) => <ProfilePanel key={p.namespace} p={p} />)}
          {g.data?.evolution.map((e) => <EvolutionPanel key={e.namespace} e={e} />)}

          <div className="grid gap-6 xl:grid-cols-2">
            <Panel title="Skills">
              {g.data ? (
                <>
                  <Row label="Kept">{g.data.skills.total}</Row>
                  <Row label="Reused at least once">{g.data.skills.reused}</Row>
                  <Row label="Repeats merged into one skill">{g.data.skills.merged_repeats}</Row>
                  <Row label="Archived after failing when reused">{g.data.skills.archived}</Row>
                  {g.data.skills.most_reliable.length ? (
                    <div className="mt-3 space-y-1.5 border-t border-dl-rule pt-3">
                      <p className="desk-mono text-[12px] text-dl-muted">most reliable when reused</p>
                      {g.data.skills.most_reliable.map((s) => (
                        <p key={s.id} className="text-sm text-dl-text">
                          <span className="desk-mono text-dl-leaf">{fmtNum(s.reliability)}</span> · {s.problem_statement}
                          <span className="desk-mono text-[11px] text-dl-muted"> ({s.successes}/{s.uses} reuses)</span>
                        </p>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}
            </Panel>
            <Panel title="Recent episodes">
              <div className="max-h-[360px] overflow-auto">
                <table className="desk-mono w-full text-left text-[12px]">
                  <thead className="text-dl-muted"><tr>
                    <th className="py-1 pr-3 font-normal">when</th><th className="pr-3 font-normal">D</th><th className="pr-3 font-normal">Δ</th>
                    <th className="pr-3 font-normal">G</th><th className="pr-3 font-normal">steps</th><th className="font-normal">verified</th>
                  </tr></thead>
                  <tbody>
                    {g.data?.recent.map((r) => (
                      <tr key={r.run_id} className="border-t border-dl-rule/60">
                        <td className="py-1 pr-3 text-dl-muted">{fmtTime(r.at)}</td>
                        <td className="pr-3">{fmtNum(r.D)}</td>
                        <td className={`pr-3 ${(r.growth_delta ?? 0) < 0 ? "text-dl-rust" : "text-dl-text"}`}>{fmtNum(r.growth_delta)}</td>
                        <td className="pr-3">{fmtNum(r.G)}</td>
                        <td className="pr-3">{r.iterations ?? "-"}</td>
                        <td>{r.finished === 1 && r.aligned === 1 ? <Badge tone="leaf">yes</Badge> : <Badge tone="muted">no</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </div>
      </PageBody>
    </>
  );
}
