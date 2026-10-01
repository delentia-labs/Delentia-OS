"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function AuditPage() {
  const { t, lang } = useLang();
  const audit = useDeskData(() => desk.audit(), [], 60000);
  const a = audit.data;

  const tiers = a ? [
    { tier: "A1", name: "Chained and signed on this host", on: a.chain.ok && a.signing_key_configured,
      note: a.signing_key_configured ? "DELENTIA_AUDIT_SIGNING_KEY is set" : "rows are chained but not signed: create a key with `delentia audit-chain keygen`" },
    { tier: "A2", name: "Signed by a separate notary process", on: a.notary.configured,
      note: a.notary.configured ? `notary at ${a.notary.url}` : "off: run `delentia notary serve` as another OS user and set DELENTIA_NOTARY_URL" },
    { tier: "A3", name: "Chain head anchored at an outside witness", on: a.anchor.configured,
      note: a.anchor.configured ? `anchoring as ${a.anchor.key_id}` : "off: set DELENTIA_AUDIT_ANCHOR_URL and DELENTIA_AUDIT_ANCHOR_KEY_ID on the host" },
  ] : [];

  return (
    <>
      <PageHeader title={t("audit")}
        lead={lang === "th"
          ? "ทุกแถวของ audit trail ถูกเชื่อมเป็น hash chain หน้านี้ตรวจทั้ง chain ใหม่ทุกครั้งที่เปิด และบอกตรงๆ ว่าการป้องกันระดับใดเปิดอยู่"
          : "Every audit row is linked into a hash chain. This page re-verifies the whole chain each time it loads and says plainly which protection tiers are on."} />
      <PageBody>
        {audit.error ? <ErrorNote error={audit.error} onRetry={audit.reload} /> : null}
        {a ? (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
            <div className="space-y-6">
              <Panel title="Hash chain" aside={a.chain.ok ? <Badge tone="leaf">intact</Badge> : <Badge tone="rust">broken</Badge>}>
                <Row label="Chained rows">{a.chain.chained_rows}</Row>
                <Row label="Signed rows">{a.chain.signed_rows}</Row>
                <Row label="Rows from before the chain">{a.chain.legacy_unchained_rows}</Row>
                <Row label="Head">{a.head ? `#${a.head.seq} · ${a.head.row_hash.slice(0, 16)}…` : "-"}</Row>
                {!a.chain.ok ? <p className="mt-3 text-sm text-dl-rust">First break at #{a.chain.first_bad_seq}: {a.chain.reason}</p> : null}
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">Check it yourself: <Code>delentia audit-chain verify</Code></p>
              </Panel>

              <Panel title="Protection tiers">
                <ul className="space-y-3">
                  {tiers.map((x) => (
                    <li key={x.tier} className="flex gap-3">
                      <Badge tone={x.on ? "leaf" : "muted"}>{x.tier}</Badge>
                      <div className="min-w-0">
                        <p className="text-sm text-dl-text">{x.name}</p>
                        <p className="text-[12px] leading-relaxed text-dl-muted">{x.note}</p>
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
                  Until A2 and A3 both run on the host, these logs are tamper-evident for single-row edits, not tamper-proof.
                </p>
              </Panel>
            </div>

            <Panel title={`Latest rows (${a.recent.length})`}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-[13px]">
                  <thead className="desk-mono text-[11px] text-dl-muted">
                    <tr><th className="pb-2 font-normal">#</th><th className="pb-2 font-normal">Type</th><th className="pb-2 font-normal">Action</th><th className="pb-2 font-normal">Actor</th><th className="pb-2 font-normal">When</th></tr>
                  </thead>
                  <tbody className="desk-mono">
                    {a.recent.map((r) => (
                      <tr key={r.id} className="border-t border-dl-rule/60">
                        <td className="py-1.5 pr-3 text-dl-muted">{r.id}</td>
                        <td className="py-1.5 pr-3 text-dl-text">{r.entity_type}</td>
                        <td className="py-1.5 pr-3 text-dl-muted">{r.action}</td>
                        <td className="max-w-[180px] truncate py-1.5 pr-3 text-dl-muted">{r.actor}</td>
                        <td className="py-1.5 text-dl-muted">{fmtTime(r.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
