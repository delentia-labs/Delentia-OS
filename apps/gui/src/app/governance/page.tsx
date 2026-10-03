"use client";

import Link from "next/link";
import { useLang } from "@/components/desk/i18n";
import { EventExplorer } from "@/components/desk/events";
import { Badge, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const SEVERITY = { bad: "rust", warn: "amber", info: "muted" } as const;

export default function GovernancePage() {
  const { lang } = useLang();
  const gov = useDeskData(() => desk.governance(), [], 30000);
  const decisions = useDeskData(() => desk.govDecisions(), [], 60000);
  const g = gov.data;
  const a = g?.activity;

  return (
    <>
      <PageHeader title={lang === "th" ? "ธรรมาภิบาล" : "Governance"}
        lead={lang === "th"
          ? "หน้าเดียวที่ตอบว่า: ตอนนี้ระบบถูกควบคุมอะไรบ้าง อะไรยังปิดอยู่ ใครเซ็นอะไร และระบบได้ปฏิเสธอะไรไปแล้ว ทุกค่ามาจากสถานะจริงของ host นี้ ไม่มีคะแนนรวม: แต่ละมาตรการ เปิด หรือ ปิด พร้อมวิธีเปลี่ยน"
          : "One page for: which controls are on, which are still off, who signed what, and what the system has refused. Every value is read from this host. There is no overall score: each control is on or off, with how to change it."} />
      <PageBody>
        {gov.error ? <ErrorNote error={gov.error} onRetry={gov.reload} /> : null}
        {g ? (
          <div className="space-y-6">
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
              <Panel title={`Controls: ${g.on} of ${g.total} on`}>
                <ul className="space-y-3">
                  {g.controls.map((c) => (
                    <li key={c.id} className="flex gap-3">
                      <Badge tone={!c.applicable ? "muted" : c.on ? "leaf" : "rust"}>{!c.applicable ? "n/a" : c.on ? "on" : "off"}</Badge>
                      <div className="min-w-0">
                        <p className="text-sm text-dl-text">{c.name}{c.always_on ? <span className="desk-mono ml-2 text-[11px] text-dl-muted">always on</span> : null}</p>
                        <p className="text-[12px] leading-relaxed text-dl-muted">{c.detail}</p>
                        {!c.on && c.how_to_change ? <p className="desk-mono mt-0.5 text-[11px] text-dl-leaf">{c.how_to_change}</p> : null}
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">{g.reading_this}</p>
              </Panel>

              <div className="space-y-6">
                <Panel title={`Open gaps (${g.gaps.length})`}>
                  {g.gaps.length === 0 ? <p className="text-sm text-dl-muted">Every control is on.</p> : (
                    <ul className="space-y-3">
                      {g.gaps.map((x) => (
                        <li key={x.control} className="flex gap-3">
                          <Badge tone={SEVERITY[x.severity]}>{x.severity === "bad" ? "fix" : x.severity === "warn" ? "weak" : "note"}</Badge>
                          <p className="text-[13px] leading-relaxed text-dl-text">{x.text}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
                <Panel title="Where to look next">
                  <ul className="space-y-1.5 text-sm">
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/fdia">Owner policy</Link> <span className="text-dl-muted">rules, roles, signatures needed</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/signatures">Signatures</Link> <span className="text-dl-muted">who may sign, who signed, re-verified now</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/identity">People</Link> <span className="text-dl-muted">tokens and the role each person has</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/audit">Audit</Link> <span className="text-dl-muted">verify the chain, check the witness</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/sovereignty">Sovereignty</Link> <span className="text-dl-muted">where data may go</span></li>
                  </ul>
                </Panel>
              </div>
            </div>

            {a ? (
              <Panel title="What the controls have done (all time, from the audit trail)">
                <div className="grid gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
                  <div>
                    <Row label="Episodes run">{a.episodes}</Row>
                    <Row label="Goals blocked (CORD)">{a.goals_blocked}</Row>
                    <Row label="Goals refused by the jury">{a.goals_refused_by_jury}</Row>
                    <Row label="Tool calls judged by FDIA">{a.tool_calls_judged}</Row>
                    <Row label="Tool calls blocked">{a.tool_calls_blocked}</Row>
                  </div>
                  <div>
                    <Row label="Tool results withheld (injection)">{a.tool_results_withheld}</Row>
                    <Row label="Tool results passed with a warning">{a.tool_results_warned}</Row>
                    <Row label="Small model called it an attack">{a.second_opinion_attacks}</Row>
                    <Row label="Jury agreed / refused">{a.jury_agreed} / {a.jury_refused}</Row>
                    <Row label="Policy changes">{a.policy_changes}</Row>
                  </div>
                  <div>
                    <Row label="Approvals">{Object.entries(a.approvals_by_status).map(([k, v]) => `${k.toLowerCase()} ${v}`).join(" · ") || "none"}</Row>
                    <Row label="Model calls allowed / redacted / blocked">{a.model_calls_allowed} / {a.model_calls_redacted} / {a.model_calls_blocked}</Row>
                    <Row label="Notary gaps">{a.notary_gaps}</Row>
                    <Row label="Last policy change">{g.last_policy_change ? `${fmtTime(g.last_policy_change.at)} by ${g.last_policy_change.by}` : "none"}</Row>
                  </div>
                </div>
                <p className="mt-3 text-[12px] text-dl-muted">A zero here means the control has not had to act yet on this host, not that it was tested against an attack.</p>
              </Panel>
            ) : null}

            <Panel title="Human decisions kept in RCTDB (the A in F = D^I × A)">
              {decisions.error ? <ErrorNote error={decisions.error} onRetry={decisions.reload} /> : null}
              {decisions.data && !decisions.data.decisions.length ? <p className="text-sm text-dl-muted">No signed approval, rejection or policy change has been recorded yet.</p> : null}
              <ul className="divide-y divide-dl-rule/60">
                {decisions.data?.decisions.map((d) => (
                  <li key={d.id} className="flex items-start gap-3 py-2">
                    <Badge tone={d.type === "signed_rejection" ? "rust" : d.type === "policy_change" ? "amber" : "leaf"}>{d.type.replace("_", " ")}</Badge>
                    <span className="min-w-0 flex-1 text-[13px] text-dl-text">{d.description}</span>
                    <span className="desk-mono shrink-0 text-[11px] text-dl-muted">{fmtTime(d.at)}</span>
                  </li>
                ))}
              </ul>
            </Panel>

            <EventExplorer initial="attention" title="Events" />
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
