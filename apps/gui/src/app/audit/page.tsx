"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { EventExplorer } from "@/components/desk/events";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type GovVerify, type WitnessesChecked } from "@/lib/desk-api";

export default function AuditPage() {
  const { t, lang } = useLang();
  const audit = useDeskData(() => desk.audit(), [], 60000);
  const a = audit.data;
  const [verify, setVerify] = useState<GovVerify | null>(null);
  const [witness, setWitness] = useState<WitnessesChecked | null>(null);
  const protection = useDeskData(() => desk.govWitnesses(), [], 30000);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const runVerify = async () => {
    setBusy(true);
    setNote("");
    try { setVerify(await desk.govVerify()); } catch (e) { setNote(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const runWitness = async () => {
    setBusy(true);
    setNote("");
    try { setWitness(await desk.govCheckWitnesses()); } catch (e) { setNote(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

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

            <div className="min-w-0 space-y-6">
              <Panel title="How well is the log protected right now?" aside={protection.data ? <Badge tone={protection.data.tamper_evident_against_host_compromise ? "leaf" : "rust"}>{protection.data.fresh_witnesses} of {protection.data.configured} witness(es) fresh</Badge> : undefined}>
                {protection.error ? <ErrorNote error={protection.error} onRetry={protection.reload} /> : null}
                {protection.data ? (
                  <>
                    <p className="text-[13px] leading-relaxed text-dl-text">{protection.data.plain}</p>
                    {protection.data.problem ? <p role="alert" className="mt-2 text-[13px] text-dl-rust">{protection.data.problem}</p> : null}
                    <Row label="Rows newer than the newest anchor">{protection.data.rows_not_yet_anchored}</Row>
                    {protection.data.witnesses.map((w) => (
                      <Row key={w.name} label={`${w.name} (${w.type})`}>
                        {w.fresh ? <Badge tone="leaf">fresh</Badge> : <Badge tone="amber">stale or never</Badge>} {w.last_anchored_entries ? `entry ${w.last_anchored_entries}` : "-"}
                        {w.last_anchored_age_s !== null ? ` · ${Math.round(w.last_anchored_age_s / 60)} min ago` : ""}
                      </Row>
                    ))}
                    <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">Configure witnesses with <Code>DELENTIA_AUDIT_WITNESSES</Code> (an http witness and a git witness are better than one). Give an auditor a proof they can check without trusting this host: <Code>delentia audit-chain export-proof --out proof.json</Code>, verified with <Code>scripts/verify_audit_bundle.py</Code>.</p>
                  </>
                ) : null}
              </Panel>
              <Panel title="Verify everything now">
                <p className="text-[13px] leading-relaxed text-dl-muted">Recomputes every link in the chain, checks the signatures with this host&apos;s key when it is known, and re-verifies the signature of every episode. The A3 check compares the chain with the heads the outside witness holds.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button onClick={runVerify} disabled={busy}>{busy ? "Working…" : "Verify chain and episodes"}</Button>
                  <Button tone="ghost" onClick={runWitness} disabled={busy || !(protection.data?.configured)}>Check against every witness (A3)</Button>
                </div>
                {note ? <p role="alert" className="mt-3 text-[13px] text-dl-rust">{note}</p> : null}
                {verify ? (
                  <div className="mt-4">
                    <Row label="Chain">{verify.chain.ok ? <Badge tone="leaf">intact</Badge> : <Badge tone="rust">broken at #{verify.chain.first_bad_seq}</Badge>}</Row>
                    {!verify.chain.ok ? <p className="text-[13px] text-dl-rust">{verify.chain.reason}</p> : null}
                    <Row label="Signatures">{verify.signature_check.startsWith("NOT") ? <Badge tone="amber">not checked</Badge> : <Badge tone="leaf">checked</Badge>}</Row>
                    <p className="pb-2 text-[12px] text-dl-muted">{verify.signature_check}</p>
                    <Row label="Episode signatures">{verify.episodes.signature_ok} ok · {verify.episodes.signature_bad} bad · {verify.episodes.unsigned} unsigned (of {verify.episodes.checked})</Row>
                    {verify.episodes.signature_bad ? <p className="text-[13px] text-dl-rust">Rows with a bad episode signature: {verify.episodes.bad_audit_ids.join(", ")}</p> : null}
                    <Row label="Notary receipts kept locally">{verify.notary.receipts_in_local_trail} (gaps: {verify.notary.gaps})</Row>
                    <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">{verify.episodes.note}</p>
                  </div>
                ) : null}
                {witness ? (
                  <div className="mt-4 space-y-2">
                    {witness.witnesses.map((w) => (
                      <div key={w.witness}>
                        <Row label={`Witness ${w.witness}`}>{!w.reachable ? <Badge tone="amber">unreachable</Badge> : w.ok ? <Badge tone="leaf">matches this chain ({w.checked} anchors)</Badge> : <Badge tone="rust">MISMATCH</Badge>}</Row>
                        {w.problems.map((pr) => <p key={pr} className="text-[13px] text-dl-rust">{pr}</p>)}
                      </div>
                    ))}
                    <p className={`text-[13px] ${witness.ok ? "text-dl-leaf" : "text-dl-rust"}`}>{witness.ok ? "Every witness agrees with this chain." : "At least one witness does not agree: treat the log as suspect until explained."}</p>
                  </div>
                ) : null}
              </Panel>
              <EventExplorer initial="all" title="Audit trail" />
            </div>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
