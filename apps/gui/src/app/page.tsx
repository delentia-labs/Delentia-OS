"use client";

import Link from "next/link";
import { useLang } from "@/components/desk/i18n";
import { milestoneLine } from "@/lib/milestone";
import { CycleStrip } from "@/components/desk/CycleStrip";
import { Badge, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtNum, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";
import { describeReason } from "@/lib/reason-text";
import { describeCheck } from "@/lib/readiness-text";
import { UpdateBanner } from "@/components/desk/UpdatePanel";

// Round 101 (UX audit): the home page answers three questions in this order: does anything need me, what did the agent last do (in words), and is the system healthy.
// The technical rows (hash chain, A1/A2/A3, daemon) are still here, folded under "Details", with their labels in both languages.
export default function StatusPage() {
  const { t, lang } = useLang();
  const T = (en: string, th: string) => (lang === "th" ? th : en);
  const health = useDeskData(() => desk.health(), [], 15000);
  const overview = useDeskData(() => desk.overview(), [], 15000);
  const sessions = useDeskData(() => desk.sessions(20), [], 20000);
  const audit = useDeskData(() => desk.audit(), [], 60000);
  const readiness = useDeskData(() => desk.readiness(), [], 20000);
  const latest = sessions.data?.sessions[0];
  const latestDetail = useDeskData(() => (latest ? desk.session(latest.id) : Promise.resolve(null)), [latest?.id]);

  const o = overview.data;
  const a = audit.data;
  const approvals = o?.approvals_pending ?? 0;
  const questions = o?.questions_pending ?? 0;
  const waiting = approvals + questions;
  const up = !health.error && !!health.data;
  const latestReason = latest ? describeReason(latest.stopped_reason, lang) : null;
  const chainOk = a ? a.chain.ok : null;

  return (
    <>
      <PageHeader
        title={t("status")}
        lead={T("What needs you, what the agent did last, and whether everything is working.", "สิ่งที่ต้องการคุณ สิ่งที่เอเจนต์ทำล่าสุด และระบบทำงานปกติหรือไม่")}
      />
      <PageBody>
        <UpdateBanner />
        {health.error ? <div className="mb-6"><ErrorNote error={health.error} onRetry={health.reload} /></div> : null}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
          <div className="space-y-6">
            {readiness.data && !readiness.data.all_done ? (
              <Panel title={readiness.data.ready ? T("One more step", "อีกขั้นเดียว") : T("Getting started", "เริ่มต้นใช้งาน")}
                aside={<Badge tone={readiness.data.ready ? "leaf" : "amber"}>{readiness.data.checks.filter((c) => c.ok).length} / {readiness.data.checks.length}</Badge>}>
                <ol className="space-y-3">
                  {readiness.data.checks.map((c) => {
                    const d = describeCheck(c, lang);
                    return (
                      <li key={c.id} className="flex gap-3 text-sm">
                        <span aria-hidden className={`mt-0.5 desk-mono ${c.ok ? "text-dl-leaf" : "text-dl-amber"}`}>{c.ok ? "✓" : "○"}</span>
                        <div className="min-w-0">
                          <p className={c.ok ? "text-dl-muted" : "font-medium text-dl-text"}>{d.label}</p>
                          {!c.ok ? (
                            <>
                              <p className="mt-0.5 text-[13px] text-dl-muted">{d.what}</p>
                              <p className="mt-0.5 text-[13px] text-dl-text">
                                {d.next}{" "}
                                {d.href ? <Link href={d.href} className="desk-focus text-dl-leaf underline">{T("Open", "เปิด")}</Link> : null}
                              </p>
                            </>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </Panel>
            ) : null}
            <Panel title={T("Needs you", "ต้องการคุณ")}>
              {o ? (
                waiting > 0 ? (
                  <div className="space-y-3">
                    {approvals > 0 ? (
                      <p className="text-sm text-dl-text">
                        <Badge tone="amber">{approvals}</Badge>{" "}
                        {T(approvals === 1 ? "action is waiting for your approval." : "actions are waiting for your approval.", "รายการรอให้คุณอนุมัติ")}
                      </p>
                    ) : null}
                    {questions > 0 ? (
                      <p className="text-sm text-dl-text">
                        <Badge tone="amber">{questions}</Badge>{" "}
                        {T(questions === 1 ? "question is waiting for your answer." : "questions are waiting for your answer.", "คำถามรอให้คุณตอบ")}
                      </p>
                    ) : null}
                    <Link href="/approvals" className="desk-focus inline-block rounded border border-dl-leaf px-3 py-1.5 text-sm text-dl-leaf hover:bg-dl-pine">
                      {T("Open and decide", "เปิดเพื่อตัดสินใจ")}
                    </Link>
                    <p className="text-[12px] text-dl-muted">{T("Nothing in the list has been done yet. The agent only acts after you approve.", "ยังไม่มีอะไรในรายการถูกทำ เอเจนต์จะลงมือหลังจากคุณอนุมัติเท่านั้น")}</p>
                  </div>
                ) : (
                  <p className="text-sm text-dl-text">{T("Nothing is waiting for you.", "ไม่มีอะไรรอคุณอยู่")}</p>
                )
              ) : <p className="text-sm text-dl-muted">…</p>}
            </Panel>

            <Panel title={T("Is it working?", "ระบบทำงานปกติไหม")}>
              <Row label={T("The service", "บริการ")}>{health.loading && !health.data ? "…" : up ? <Badge tone="leaf">{T("running", "ทำงานอยู่")}</Badge> : <Badge tone="rust">{T("not reachable", "ติดต่อไม่ได้")}</Badge>}</Row>
              <Row label={T("The model", "โมเดล")}>{o ? `${o.model.model} (${o.model.provider})` : "-"}</Row>
              <Row label={T("The record of what it did", "บันทึกสิ่งที่มันทำ")}>
                {chainOk === null ? "-" : chainOk ? <Badge tone="leaf">{T("intact", "สมบูรณ์")}</Badge> : <Badge tone="rust">{T("damaged: open Audit", "เสียหาย: เปิดหน้าตรวจสอบ")}</Badge>}
              </Row>
              <p className="mt-2 text-[12px] text-dl-muted">
                {T("Ask the agent something in ", "ลองสั่งงานเอเจนต์ที่หน้า ")}
                <Link href="/chat" className="text-dl-leaf underline">{T("Chat", "แชต")}</Link>.
              </p>
            </Panel>
          </div>

          <div className="min-w-0 space-y-6">
            <Panel title={T("What it did last", "สิ่งที่ทำล่าสุด")}
              aside={latest ? <Link href={`/sessions?id=${latest.id}`} className="desk-mono text-[11px] text-dl-leaf underline">{T("open", "เปิดดู")}</Link> : null}>
              {latest && latestReason ? (
                <div className="space-y-3">
                  <p className="text-sm text-dl-text">{latest.goal}</p>
                  <p className="text-sm">
                    <Badge tone={latestReason.tone}>{latestReason.label}</Badge>{" "}
                    <span className="text-dl-text">{latestReason.what}</span>
                  </p>
                  <p className="text-[13px] text-dl-muted">{latestReason.next}</p>
                  <details className="text-[12px] text-dl-muted">
                    <summary className="desk-focus cursor-pointer">{T("The steps it went through", "ขั้นตอนที่ผ่านมา")}</summary>
                    <div className="mt-2 space-y-2">
                      <CycleStrip s={latest} rct7Count={latestDetail.data?.rct7_steps.length} />
                      <p className="desk-mono">D {fmtNum(latest.D)} · I {fmtNum(latest.I)} · F {fmtNum(latest.goal_F)} · {fmtTime(latest.started_at)}</p>
                    </div>
                  </details>
                </div>
              ) : (
                <Empty title={T("Nothing has run yet", "ยังไม่เคยสั่งงาน")}>
                  {T("Type a request in ", "พิมพ์คำขอที่หน้า ")}<Link href="/chat" className="text-dl-leaf underline">{T("Chat", "แชต")}</Link>
                  {T(", for example: “Read README.md and summarise it in one sentence”.", " เช่น “อ่าน README.md แล้วสรุปเป็นหนึ่งประโยค”")}
                </Empty>
              )}
            </Panel>

            <Panel title={T("Recent requests", "คำขอล่าสุด")}>
              {sessions.error ? <ErrorNote error={sessions.error} onRetry={sessions.reload} /> : sessions.data?.sessions.length ? (
                <div tabIndex={0} className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-left text-sm">
                    <thead className="desk-mono text-[11px] text-dl-muted">
                      <tr><th className="pb-2 font-normal">{T("Request", "คำขอ")}</th><th className="pb-2 font-normal">{T("How it ended", "จบอย่างไร")}</th><th className="pb-2 font-normal">{T("When", "เมื่อไร")}</th></tr>
                    </thead>
                    <tbody>
                      {sessions.data.sessions.map((s) => {
                        const r = describeReason(s.stopped_reason, lang);
                        return (
                          <tr key={s.id} className="border-t border-dl-rule/60">
                            <td className="max-w-[320px] truncate py-2 pr-3">
                              <Link href={`/sessions?id=${s.id}`} className="desk-focus hover:text-dl-leaf">{s.goal ?? s.namespace}</Link>
                            </td>
                            <td className="py-2 pr-3" title={r.what}><Badge tone={r.tone}>{r.label}</Badge></td>
                            <td className="desk-mono py-2 text-[12px] text-dl-muted">{fmtTime(s.started_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : <Empty title={T("No requests yet", "ยังไม่มีคำขอ")} />}
            </Panel>

            <details className="rounded border border-dl-rule bg-dl-panel px-4 py-3 text-sm">
              <summary className="desk-focus cursor-pointer text-dl-muted">{T("Details for technical users", "รายละเอียดสำหรับผู้ใช้เชิงเทคนิค")}</summary>
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                <div>
                  <Row label="API">{health.data ? `v${health.data.version ?? "?"} · ${health.data.status}` : "-"}</Row>
                  {milestoneLine(health.data?.milestone, lang) && (
                    <Row label={T("Release stage", "ช่วงเปิดตัว")}>{milestoneLine(health.data?.milestone, lang)?.both}</Row>
                  )}
                  <Row label={T("Model chosen by", "โมเดลเลือกโดย")}>{o ? o.model.model_source : "-"}</Row>
                  <Row label="Daemon">{o ? (o.daemon.running ? `${T("running", "ทำงาน")} · ${o.daemon.tasks} ${T("tasks", "งาน")}` : T("stopped", "หยุด")) : "-"}</Row>
                  <Row label={T("Episodes recorded", "episode ที่บันทึก")}>{o?.sessions_total ?? "-"}</Row>
                  <Row label={T("Skills learned", "ทักษะที่เรียนรู้")}>{o?.skills ?? "-"}</Row>
                </div>
                <div>
                  {audit.error ? <ErrorNote error={audit.error} /> : (
                    <>
                      <Row label={T("Hash chain", "ห่วงโซ่แฮช")}>{a ? (a.chain.ok ? <Badge tone="leaf">{T("intact", "สมบูรณ์")}</Badge> : <Badge tone="rust">{T("broken at", "ขาดที่")} {a.chain.first_bad_seq}</Badge>) : "-"}</Row>
                      <Row label={T("Rows chained / signed", "แถวที่ผูก / ลงนาม")}>{a ? `${a.chain.chained_rows} / ${a.chain.signed_rows}` : "-"}</Row>
                      <Row label={T("Signing key (A1)", "กุญแจลงนาม (A1)")}>{a ? (a.signing_key_configured ? T("configured", "ตั้งแล้ว") : T("not set", "ยังไม่ตั้ง")) : "-"}</Row>
                      <Row label={T("Separate record keeper (A2)", "ผู้บันทึกแยก (A2)")}>{a ? (a.notary.configured ? T("on", "เปิด") : T("off", "ปิด")) : "-"}</Row>
                      <Row label={T("Outside witness (A3)", "พยานภายนอก (A3)")}>{a ? (a.anchor.configured ? `${T("on", "เปิด")} · ${a.anchor.key_id}` : T("off", "ปิด")) : "-"}</Row>
                    </>
                  )}
                  <p className="mt-2 text-[12px]"><Link href="/audit" className="text-dl-leaf underline">{T("Open the audit page", "เปิดหน้าตรวจสอบ")}</Link></p>
                </div>
              </div>
            </details>
          </div>
        </div>
      </PageBody>
    </>
  );
}
