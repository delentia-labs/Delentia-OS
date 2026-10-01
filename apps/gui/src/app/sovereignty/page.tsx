"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const TONE = { allow: "leaf", redact: "amber", block: "rust" } as const;

export default function SovereigntyPage() {
  const { lang } = useLang();
  const s = useDeskData(() => desk.sovereignty(), [], 20000);
  const d = s.data;
  return (
    <>
      <PageHeader title={lang === "th" ? "อธิปไตยข้อมูล" : "Data sovereignty"}
        lead={lang === "th"
          ? "ประเทศหรือองค์กรใดก็ใช้ AI ของตัวเองเสียบเข้ามาได้ และข้อมูลไม่ออกนอกขอบเขตที่กำหนด หน้านี้แสดงนโยบาย, โมเดลที่เลือกส่งข้อมูลไปที่ไหน และทุกการตัดสินใจก่อนส่ง prompt ที่บันทึกใน audit chain (ไม่เก็บข้อมูลส่วนบุคคลเอง เก็บแค่ชนิด จำนวน และ hash)"
          : "Any country or organisation can plug in its own AI and keep data inside the boundary it sets. This page shows the policy, where the selected model would send data, and every decision made before a prompt was sent, as recorded in the audit chain (never the personal data itself: kinds, counts and a hash)."} />
      <PageBody>
        {s.error ? <ErrorNote error={s.error} onRetry={s.reload} /> : null}
        {d ? (
          <div className="space-y-6">
            {!d.enforced ? (
              <div role="alert" className="rounded-md border border-dl-amber/60 bg-dl-amber/10 px-4 py-3 text-sm leading-relaxed text-dl-text">
                {d.warning} <Code>delentia sovereignty set --region TH</Code>
              </div>
            ) : null}
            <div className="grid gap-6 xl:grid-cols-2">
              <Panel title="Policy" aside={d.enforced ? <Badge tone="leaf">enforced</Badge> : <Badge tone="amber">not set</Badge>}>
                {d.policy ? (
                  <>
                    <Row label="Home region">{d.policy.home_region}</Row>
                    <Row label="Regions a call may reach">{d.policy.allowed_regions.join(", ")}</Row>
                    <Row label="Cross-border calls">{d.policy.allow_cross_border ? <Badge tone="amber">allowed</Badge> : <Badge tone="leaf">not allowed</Badge>}</Row>
                    <Row label="Personal data in a cross-border call">{d.policy.pii_policy}</Row>
                    <Row label="Legal basis recorded">{d.policy.legal_basis || "-"}</Row>
                  </>
                ) : <p className="text-sm text-dl-muted">No policy: nothing stops a prompt from going wherever the selected model runs.</p>}
                <p className="desk-mono mt-3 text-[11px] text-dl-muted">{d.config_path}</p>
              </Panel>
              <Panel title="Selected model" aside={d.would_be_allowed === null ? undefined : d.would_be_allowed ? <Badge tone="leaf">allowed</Badge> : <Badge tone="rust">would be blocked</Badge>}>
                <Row label="Model">{d.model}</Row>
                <Row label="Processes data">{d.hosting.kind} · {d.hosting.region}</Row>
                <Row label="Operator">{d.hosting.operator || "-"}</Row>
                {d.reason ? <p className="mt-2 text-[13px] leading-relaxed text-dl-muted">{d.reason}</p> : null}
                {d.hosting.note ? <p className="mt-1 text-[12px] text-dl-muted">{d.hosting.note}</p> : null}
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                  Plug in your own AI: <Code>delentia model set &lt;model&gt; --provider openai-compat --base-url &lt;url&gt; --kind in_region --region TH</Code>
                </p>
              </Panel>
            </div>
            <Panel title="Decisions" aside={<span className="desk-mono text-[11px] text-dl-muted">allowed {d.counts.allow} · redacted {d.counts.redact} · blocked {d.counts.block}</span>}>
              {d.decisions.length ? (
                <div className="overflow-x-auto">
                  <table className="desk-mono w-full text-left text-[12px]">
                    <thead className="text-dl-muted"><tr>
                      <th className="py-1 pr-3 font-normal">when</th><th className="pr-3 font-normal">user</th><th className="pr-3 font-normal">decision</th>
                      <th className="pr-3 font-normal">endpoint</th><th className="pr-3 font-normal">personal data</th><th className="font-normal">why</th>
                    </tr></thead>
                    <tbody>
                      {d.decisions.map((x) => (
                        <tr key={x.id} className="border-t border-dl-rule/60 align-top">
                          <td className="py-1.5 pr-3 text-dl-muted">{fmtTime(x.at)}</td><td className="pr-3">{x.namespace}</td>
                          <td className="pr-3"><Badge tone={TONE[x.action as keyof typeof TONE] ?? "muted"}>{x.action}</Badge></td>
                          <td className="pr-3">{x.hosting ? `${x.hosting.kind} · ${x.hosting.region}` : "-"}</td>
                          <td className="pr-3">{x.pii && Object.keys(x.pii).length ? Object.entries(x.pii).map(([k, n]) => `${k}×${n}`).join(", ") : "none"}</td>
                          <td className="max-w-[48ch] text-dl-muted">{x.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="text-sm text-dl-muted">No model call has been checked yet. With a policy set, every call the agent makes is recorded here.</p>}
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
