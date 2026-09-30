"use client";

import Link from "next/link";
import { useLang } from "@/components/desk/i18n";
import { CycleStrip } from "@/components/desk/CycleStrip";
import { Badge, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtNum, fmtTime, reasonTone, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function StatusPage() {
  const { t, lang } = useLang();
  const health = useDeskData(() => desk.health(), [], 15000);
  const overview = useDeskData(() => desk.overview(), [], 15000);
  const sessions = useDeskData(() => desk.sessions(20), [], 20000);
  const audit = useDeskData(() => desk.audit(), [], 60000);
  const latest = sessions.data?.sessions[0];
  const latestDetail = useDeskData(() => (latest ? desk.session(latest.id) : Promise.resolve(null)), [latest?.id]);

  const o = overview.data;
  const a = audit.data;
  return (
    <>
      <PageHeader
        title={t("status")}
        lead={lang === "th"
          ? "ภาพรวมของ runtime จากข้อมูลจริงของระบบ: โมเดลที่ใช้, daemon, audit chain และ episode ล่าสุดที่ผ่านวงจร Constitutional Cycle"
          : "The runtime as it is right now: the model, the daemon, the audit chain, and the latest episode through the Constitutional Cycle."}
      />
      <PageBody>
        {health.error ? <div className="mb-6"><ErrorNote error={health.error} onRetry={health.reload} /></div> : null}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <div className="space-y-6">
            <Panel title="Runtime">
              <Row label="API">{health.data ? `v${health.data.version ?? "?"} · ${health.data.status}` : "-"}</Row>
              <Row label="Model">{o ? `${o.model.model} (${o.model.provider})` : "-"}</Row>
              <Row label="Model chosen by">{o ? o.model.model_source : "-"}</Row>
              <Row label="Daemon">{o ? (o.daemon.running ? `running · ${o.daemon.tasks} tasks` : "stopped") : "-"}</Row>
              <Row label="Episodes recorded">{o?.sessions_total ?? "-"}</Row>
              <Row label="Skills learned">{o?.skills ?? "-"}</Row>
              <Row label="Approvals waiting">
                {o && o.approvals_pending > 0 ? <Link href="/approvals" className="text-dl-amber underline">{o.approvals_pending}</Link> : (o ? 0 : "-")}
              </Row>
            </Panel>

            <Panel title="Audit" aside={<Link href="/audit" className="desk-mono text-[11px] text-dl-leaf underline">details</Link>}>
              {audit.error ? <ErrorNote error={audit.error} /> : (
                <>
                  <Row label="Hash chain">{a ? (a.chain.ok ? <Badge tone="leaf">intact</Badge> : <Badge tone="rust">broken at {a.chain.first_bad_seq}</Badge>) : "-"}</Row>
                  <Row label="Rows chained / signed">{a ? `${a.chain.chained_rows} / ${a.chain.signed_rows}` : "-"}</Row>
                  <Row label="Signing key (A1)">{a ? (a.signing_key_configured ? "configured" : "not set") : "-"}</Row>
                  <Row label="Notary (A2)">{a ? (a.notary.configured ? "on" : "off") : "-"}</Row>
                  <Row label="Anchoring (A3)">{a ? (a.anchor.configured ? `on · ${a.anchor.key_id}` : "off") : "-"}</Row>
                </>
              )}
            </Panel>
          </div>

          <div className="min-w-0 space-y-6">
            <Panel title="Latest episode through the cycle"
              aside={latest ? <Link href={`/sessions?id=${latest.id}`} className="desk-mono text-[11px] text-dl-leaf underline">open</Link> : null}>
              {latest ? (
                <div className="space-y-3">
                  <p className="text-sm text-dl-text">{latest.goal}</p>
                  <CycleStrip s={latest} rct7Count={latestDetail.data?.rct7_steps.length} />
                  <p className="desk-mono text-[12px] text-dl-muted">
                    D {fmtNum(latest.D)} · I {fmtNum(latest.I)} · F(goal) {fmtNum(latest.goal_F)} · {fmtTime(latest.started_at)}
                  </p>
                </div>
              ) : (
                <Empty title="No episodes yet">
                  Run a goal in <Link href="/chat" className="text-dl-leaf underline">Chat</Link> (Agent mode) or with <code>delentia agent</code>.
                </Empty>
              )}
            </Panel>

            <Panel title="Recent sessions">
              {sessions.error ? <ErrorNote error={sessions.error} onRetry={sessions.reload} /> : sessions.data?.sessions.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-left text-sm">
                    <thead className="desk-mono text-[11px] text-dl-muted">
                      <tr><th className="pb-2 font-normal">Goal</th><th className="pb-2 font-normal">Result</th><th className="pb-2 font-normal">Route</th><th className="pb-2 font-normal">Steps</th><th className="pb-2 font-normal">When</th></tr>
                    </thead>
                    <tbody>
                      {sessions.data.sessions.map((s) => (
                        <tr key={s.id} className="border-t border-dl-rule/60">
                          <td className="max-w-[320px] truncate py-2 pr-3">
                            <Link href={`/sessions?id=${s.id}`} className="desk-focus hover:text-dl-leaf">{s.goal ?? s.namespace}</Link>
                          </td>
                          <td className="py-2 pr-3"><Badge tone={reasonTone(s.stopped_reason)}>{s.stopped_reason}</Badge></td>
                          <td className="desk-mono py-2 pr-3 text-[12px] text-dl-muted">{s.route ?? "-"}</td>
                          <td className="desk-mono py-2 pr-3 text-[12px] text-dl-muted">{s.iterations ?? "-"}</td>
                          <td className="desk-mono py-2 text-[12px] text-dl-muted">{fmtTime(s.started_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <Empty title="No sessions recorded" />}
            </Panel>
          </div>
        </div>
      </PageBody>
    </>
  );
}
