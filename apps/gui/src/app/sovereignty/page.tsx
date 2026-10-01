"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type SovereigntyInfo } from "@/lib/desk-api";

const TONE = { allow: "leaf", redact: "amber", block: "rust" } as const;
const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text placeholder:text-dl-muted/50";

function PolicyForm({ info, onSaved, lang }: { info: SovereigntyInfo; onSaved: () => void; lang: string }) {
  const p = info.policy;
  const [home, setHome] = useState(p?.home_region ?? "");
  const [extra, setExtra] = useState((p?.allowed_regions ?? []).filter((r) => r !== p?.home_region).join(", "));
  const [cross, setCross] = useState(p?.allow_cross_border ?? false);
  const [pii, setPii] = useState<"block" | "redact" | "allow">((p?.pii_policy as "block" | "redact" | "allow") ?? "block");
  const [basis, setBasis] = useState(p?.legal_basis ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "leaf" | "rust"; text: string } | null>(null);
  const T = (en: string, th: string) => (lang === "th" ? th : en);
  const save = async () => {
    setBusy(true); setMessage(null);
    try {
      await desk.setSovereignty({ home_region: home.trim(), allowed_regions: extra.split(/[ ,]+/).filter(Boolean), allow_cross_border: cross, pii_policy: pii, legal_basis: basis });
      setMessage({ tone: "leaf", text: T("Policy saved. It applies to the next model call.", "บันทึกนโยบายแล้ว มีผลกับการเรียกโมเดลครั้งถัดไป") });
      onSaved();
    } catch (err) {
      setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) });
    } finally { setBusy(false); }
  };
  return (
    <Panel title={T("Set the policy", "ตั้งนโยบาย")}>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("Home country (two letters)", "ประเทศหลัก (2 ตัวอักษร)")}</span>
          <input value={home} onChange={(e) => setHome(e.target.value.toUpperCase().slice(0, 2))} placeholder="TH" maxLength={2} className={field} aria-label="Home country" />
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("Other countries a call may reach", "ประเทศอื่นที่อนุญาตให้ส่งไปถึง")}</span>
          <input value={extra} onChange={(e) => setExtra(e.target.value.toUpperCase())} placeholder="JP, SG" className={field} aria-label="Other countries" />
        </label>
        <label className="flex items-start gap-2 text-[13px] text-dl-text md:col-span-2">
          <input type="checkbox" checked={cross} onChange={(e) => setCross(e.target.checked)} className="mt-1 accent-[var(--dl-leaf)]" />
          <span>{T("Allow calls to endpoints outside those countries (cross-border).", "อนุญาตให้เรียก endpoint นอกประเทศเหล่านี้ (ข้ามพรมแดน)")}
            <span className="block text-[12px] text-dl-muted">{T("Off is the strict choice: nothing leaves. On needs a rule for personal data below and a legal basis.", "ปิดคือเข้มที่สุด: ไม่มีอะไรออก เปิดต้องกำหนดการจัดการข้อมูลส่วนบุคคลและฐานทางกฎหมาย")}</span></span>
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("Personal data in a cross-border call", "ข้อมูลส่วนบุคคลในการเรียกข้ามพรมแดน")}</span>
          <select value={pii} onChange={(e) => setPii(e.target.value as "block" | "redact" | "allow")} disabled={!cross} className={field} aria-label="Personal data rule">
            <option value="block">{T("block the call", "บล็อกการเรียก")}</option>
            <option value="redact">{T("replace it with placeholders", "แทนที่ด้วย placeholder")}</option>
            <option value="allow">{T("allow it (recorded)", "อนุญาต (บันทึกไว้)")}</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("Legal basis recorded with each decision", "ฐานทางกฎหมายที่บันทึกกับทุกการตัดสินใจ")}</span>
          <input value={basis} onChange={(e) => setBasis(e.target.value)} placeholder="PDPA s.28: consent + safeguards" className={field} aria-label="Legal basis" />
        </label>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button onClick={save} disabled={busy || home.trim().length !== 2}>{busy ? "Saving…" : T("Save policy", "บันทึกนโยบาย")}</Button>
        <span className="text-[12px] text-dl-muted">{T("This writes the same file as ", "เขียนไฟล์เดียวกับ ")}<Code>delentia sovereignty set</Code>. {T("It is not legal advice.", "ไม่ใช่คำปรึกษาทางกฎหมาย")}</span>
      </div>
      {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "leaf" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
    </Panel>
  );
}

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
            <PolicyForm key={JSON.stringify(d.policy)} info={d} onSaved={s.reload} lang={lang} />
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
