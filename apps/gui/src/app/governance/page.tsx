"use client";

import Link from "next/link";
import { useLang } from "@/components/desk/i18n";
import { EventExplorer } from "@/components/desk/events";
import { Badge, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";
import { GOV_TH } from "@/lib/governance-text";

const SEVERITY = { bad: "rust", warn: "amber", info: "muted" } as const;

export default function GovernancePage() {
  const { lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
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
              <Panel title={lang === "th" ? `ด่านควบคุม: เปิด ${g.on} จาก ${g.total}` : `Controls: ${g.on} of ${g.total} on`}>
                <ul className="space-y-3">
                  {g.controls.map((c) => (
                    <li key={c.id} className="flex gap-3">
                      <Badge tone={!c.applicable ? "muted" : c.on ? "leaf" : "rust"}>{!c.applicable ? L("n/a", "ไม่เกี่ยวข้อง") : c.on ? L("on", "เปิด") : L("off", "ปิด")}</Badge>
                      <div className="min-w-0">
                        <p className="text-sm text-dl-text">{lang === "th" && GOV_TH[c.id] ? GOV_TH[c.id].name : c.name}{c.always_on ? <span className="desk-mono ml-2 text-[11px] text-dl-muted">{L("always on", "เปิดตลอด")}</span> : null}</p>
                        <p className="text-[12px] leading-relaxed text-dl-muted">{c.detail}</p>
                        {!c.on && c.how_to_change ? <p className="desk-mono mt-0.5 text-[11px] text-dl-leaf">{lang === "th" && GOV_TH[c.id]?.fix ? GOV_TH[c.id].fix : c.how_to_change}</p> : null}
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">{lang === "th" ? "ด่านแต่ละอันเปิดหรือปิด ไม่มีคะแนนรวม 'เปิด' หมายถึงตั้งค่าไว้บนเครื่องนี้ตอนนี้ ไม่ได้หมายความว่าเคยถูกโจมตีแล้วรับมือได้" : g.reading_this}</p>
              </Panel>

              <div className="space-y-6">
                <Panel title={`${L("Open gaps", "ช่องโหว่ที่ยังเปิด")} (${g.gaps.length})`}>
                  {g.gaps.length === 0 ? <p className="text-sm text-dl-muted">{L("Every control is on.", "ทุกด่านเปิดอยู่")}</p> : (
                    <ul className="space-y-3">
                      {g.gaps.map((x) => (
                        <li key={x.control} className="flex gap-3">
                          <Badge tone={SEVERITY[x.severity]}>{x.severity === "bad" ? L("fix", "ต้องแก้") : x.severity === "warn" ? L("weak", "อ่อน") : L("note", "หมายเหตุ")}</Badge>
                          <p className="text-[13px] leading-relaxed text-dl-text">{lang === "th" && GOV_TH[x.control] ? `${GOV_TH[x.control].name}: ${g.controls.find((c) => c.id === x.control)?.detail ?? ""}` : x.text}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
                <Panel title={L("Where to look next", "ดูต่อที่ไหน")}>
                  <ul className="space-y-1.5 text-sm">
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/fdia">{L("Owner policy", "นโยบายของเจ้าของ")}</Link> <span className="text-dl-muted">{L("rules, roles, signatures needed", "กฎ บทบาท และลายเซ็นที่ต้องใช้")}</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/signatures">{L("Signatures", "ลายเซ็น")}</Link> <span className="text-dl-muted">{L("who may sign, who signed, re-verified now", "ใครเซ็นได้ ใครเซ็นแล้ว ตรวจซ้ำตอนนี้")}</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/identity">{L("People", "ผู้ใช้")}</Link> <span className="text-dl-muted">{L("tokens and the role each person has", "โทเคนและบทบาทของแต่ละคน")}</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/audit">{L("Audit", "บันทึกตรวจสอบ")}</Link> <span className="text-dl-muted">{L("verify the chain, check the witness", "ตรวจโซ่ เช็กพยาน")}</span></li>
                    <li><Link className="desk-focus text-dl-leaf underline underline-offset-2" href="/sovereignty">{L("Sovereignty", "อธิปไตยข้อมูล")}</Link> <span className="text-dl-muted">{L("where data may go", "ข้อมูลไปที่ไหนได้บ้าง")}</span></li>
                  </ul>
                </Panel>
              </div>
            </div>

            {a ? (
              <Panel title={L("What the controls have done (all time, from the audit trail)", "สิ่งที่ด่านต่าง ๆ ทำไปแล้ว (ตลอดเวลา จากบันทึกตรวจสอบ)")}>
                <div className="grid gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
                  <div>
                    <Row label={L("Episodes run", "episode ที่รัน")}>{a.episodes}</Row>
                    <Row label={L("Goals blocked (CORD)", "เป้าหมายที่ถูกบล็อก (CORD)")}>{a.goals_blocked}</Row>
                    <Row label={L("Goals refused by the jury", "เป้าหมายที่คณะลูกขุนปฏิเสธ")}>{a.goals_refused_by_jury}</Row>
                    <Row label={L("Tool calls judged by FDIA", "การเรียกเครื่องมือที่ FDIA ตัดสิน")}>{a.tool_calls_judged}</Row>
                    <Row label={L("Tool calls blocked", "การเรียกเครื่องมือที่ถูกบล็อก")}>{a.tool_calls_blocked}</Row>
                  </div>
                  <div>
                    <Row label={L("Tool results withheld (injection)", "ผลเครื่องมือที่กักไว้ (การแทรกคำสั่ง)")}>{a.tool_results_withheld}</Row>
                    <Row label={L("Tool results passed with a warning", "ผลเครื่องมือที่ผ่านพร้อมคำเตือน")}>{a.tool_results_warned}</Row>
                    <Row label={L("Small model called it an attack", "โมเดลเล็กชี้ว่าเป็นการโจมตี")}>{a.second_opinion_attacks}</Row>
                    <Row label={L("Jury agreed / refused", "คณะลูกขุนเห็นพ้อง / ปฏิเสธ")}>{a.jury_agreed} / {a.jury_refused}</Row>
                    <Row label={L("Policy changes", "การเปลี่ยนนโยบาย")}>{a.policy_changes}</Row>
                  </div>
                  <div>
                    <Row label={L("Approvals", "การอนุมัติ")}>{Object.entries(a.approvals_by_status).map(([k, v]) => `${k.toLowerCase()} ${v}`).join(" · ") || L("none", "ไม่มี")}</Row>
                    <Row label={L("Model calls allowed / redacted / blocked", "การเรียกโมเดลที่อนุญาต / ปกปิด / บล็อก")}>{a.model_calls_allowed} / {a.model_calls_redacted} / {a.model_calls_blocked}</Row>
                    <Row label={L("Notary gaps", "ช่องว่างของ notary")}>{a.notary_gaps}</Row>
                    <Row label={L("Last policy change", "เปลี่ยนนโยบายล่าสุด")}>{g.last_policy_change ? `${fmtTime(g.last_policy_change.at)} ${L("by", "โดย")} ${g.last_policy_change.by}` : L("none", "ไม่มี")}</Row>
                  </div>
                </div>
                <p className="mt-3 text-[12px] text-dl-muted">{L("A zero here means the control has not had to act yet on this host, not that it was tested against an attack.", "ศูนย์ตรงนี้หมายถึงด่านยังไม่ต้องทำงานบนเครื่องนี้ ไม่ได้หมายความว่าเคยถูกทดสอบกับการโจมตี")}</p>
              </Panel>
            ) : null}

            <Panel title={L("Human decisions kept in RCTDB (the A in F = D^I × A)", "การตัดสินของมนุษย์ที่เก็บใน RCTDB (ตัว A ใน F = D^I × A)")}>
              {decisions.error ? <ErrorNote error={decisions.error} onRetry={decisions.reload} /> : null}
              {decisions.data && !decisions.data.decisions.length ? <p className="text-sm text-dl-muted">{L("No signed approval, rejection or policy change has been recorded yet.", "ยังไม่มีการอนุมัติ การปฏิเสธ หรือการเปลี่ยนนโยบายที่ลงลายเซ็นถูกบันทึกไว้")}</p> : null}
              <ul className="divide-y divide-dl-rule/60">
                {decisions.data?.decisions.map((d) => (
                  <li key={d.id} className="flex items-start gap-3 py-2">
                    <Badge tone={d.type === "signed_rejection" ? "rust" : d.type === "policy_change" ? "amber" : "leaf"}>{lang === "th" ? ({ signed_approval: "อนุมัติที่เซ็นแล้ว", signed_rejection: "ปฏิเสธที่เซ็นแล้ว", policy_change: "เปลี่ยนนโยบาย" } as Record<string, string>)[d.type] ?? d.type.replace("_", " ") : d.type.replace("_", " ")}</Badge>
                    <span className="min-w-0 flex-1 text-[13px] text-dl-text">{d.description}</span>
                    <span className="desk-mono shrink-0 text-[11px] text-dl-muted">{fmtTime(d.at)}</span>
                  </li>
                ))}
              </ul>
            </Panel>

            <EventExplorer initial="attention" title={L("Events", "เหตุการณ์")} />
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
