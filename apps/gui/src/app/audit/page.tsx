"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { EventExplorer } from "@/components/desk/events";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type GovVerify, type WitnessesChecked } from "@/lib/desk-api";

export default function AuditPage() {
  const { t, lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
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
    { tier: "A1", name: L("Chained and signed on this host", "เชื่อมเป็นโซ่และลงลายเซ็นบนเครื่องนี้"), on: a.chain.ok && a.signing_key_configured,
      note: a.signing_key_configured ? L("DELENTIA_AUDIT_SIGNING_KEY is set", "ตั้ง DELENTIA_AUDIT_SIGNING_KEY แล้ว") : L("rows are chained but not signed: create a key with `delentia audit-chain keygen`", "แถวถูกเชื่อมเป็นโซ่แต่ยังไม่ลงลายเซ็น: สร้างกุญแจด้วย `delentia audit-chain keygen`") },
    { tier: "A2", name: L("Signed by a separate notary process", "ลงลายเซ็นโดยโปรเซส notary ที่แยกต่างหาก"), on: a.notary.configured,
      note: a.notary.configured ? `${L("notary at", "notary ที่")} ${a.notary.url}` : L("off: run `delentia notary serve` as another OS user and set DELENTIA_NOTARY_URL", "ปิด: รัน `delentia notary serve` ด้วยบัญชีผู้ใช้ระบบปฏิบัติการอีกบัญชี แล้วตั้ง DELENTIA_NOTARY_URL") },
    { tier: "A3", name: L("Chain head held by an outside witness", "ปลายโซ่ถูกเก็บไว้กับพยานภายนอก"), on: !!protection.data?.tamper_evident_against_host_compromise,
      note: protection.data ? (protection.data.tamper_evident_against_host_compromise ? protection.data.plain : `${L("off", "ปิด")}: ${protection.data.plain}. ${L("Set DELENTIA_AUDIT_WITNESSES on the host.", "ตั้ง DELENTIA_AUDIT_WITNESSES บนเครื่องโฮสต์")}`)
        : L("checking the witnesses…", "กำลังตรวจพยาน…") },
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
              <Panel title={L("Hash chain", "โซ่แฮช")} aside={a.chain.ok ? <Badge tone="leaf">{L("intact", "สมบูรณ์")}</Badge> : <Badge tone="rust">{L("broken", "ขาด")}</Badge>}>
                <Row label={L("Chained rows", "แถวที่เชื่อมเป็นโซ่")}>{a.chain.chained_rows}</Row>
                <Row label={L("Signed rows", "แถวที่ลงลายเซ็น")}>{a.chain.signed_rows}</Row>
                <Row label={L("Rows from before the chain", "แถวจากก่อนมีโซ่")}>{a.chain.legacy_unchained_rows}</Row>
                <Row label={L("Head", "ปลายโซ่")}>{a.head ? `#${a.head.seq} · ${a.head.row_hash.slice(0, 16)}…` : "-"}</Row>
                {!a.chain.ok ? <p className="mt-3 text-sm text-dl-rust">{L("First break at", "ขาดครั้งแรกที่")} #{a.chain.first_bad_seq}: {a.chain.reason}</p> : null}
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{L("Check it yourself: ", "ตรวจเองได้: ")}<Code>delentia audit-chain verify</Code></p>
              </Panel>

              <Panel title={L("Protection tiers", "ระดับการป้องกัน")}>
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
                  {L("Until A2 and A3 both run on the host, these logs are tamper-evident for single-row edits, not tamper-proof.", "จนกว่า A2 และ A3 จะทำงานบนเครื่องโฮสต์ทั้งคู่ บันทึกเหล่านี้ทำให้เห็นร่องรอยเมื่อมีการแก้ทีละแถว แต่ยังไม่ใช่กันการแก้ได้ทั้งหมด")}
                </p>
              </Panel>
            </div>

            <div className="min-w-0 space-y-6">
              <Panel title={L("How well is the log protected right now?", "ตอนนี้บันทึกถูกป้องกันดีแค่ไหน")} aside={protection.data ? <Badge tone={protection.data.tamper_evident_against_host_compromise ? "leaf" : "rust"}>{protection.data.fresh_witnesses} {L("of", "จาก")} {protection.data.configured} {L("witness(es) fresh", "พยานที่ยังสด")}</Badge> : undefined}>
                {protection.error ? <ErrorNote error={protection.error} onRetry={protection.reload} /> : null}
                {protection.data ? (
                  <>
                    <p className="text-[13px] leading-relaxed text-dl-text">{protection.data.plain}</p>
                    {protection.data.problem ? <p role="alert" className="mt-2 text-[13px] text-dl-rust">{protection.data.problem}</p> : null}
                    <Row label={L("Rows newer than the newest anchor", "แถวที่ใหม่กว่าหมุดล่าสุด")}>{protection.data.rows_not_yet_anchored}</Row>
                    {protection.data.witnesses.map((w) => (
                      <Row key={w.name} label={`${w.name} (${w.type})`}>
                        {w.fresh ? <Badge tone="leaf">{L("fresh", "ยังสด")}</Badge> : <Badge tone="amber">{L("stale or never", "เก่าหรือไม่เคย")}</Badge>} {w.last_anchored_entries ? `${L("entry", "รายการที่")} ${w.last_anchored_entries}` : "-"}
                        {w.last_anchored_age_s !== null ? ` · ${Math.round(w.last_anchored_age_s / 60)} ${L("min ago", "นาทีที่แล้ว")}` : ""}
                      </Row>
                    ))}
                    <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{L("Configure witnesses with ", "ตั้งพยานด้วย ")}<Code>DELENTIA_AUDIT_WITNESSES</Code>{L(" (an http witness and a git witness are better than one). Give an auditor a proof they can check without trusting this host: ", " (พยานแบบ http คู่กับแบบ git ดีกว่าอันเดียว) ให้ผู้ตรวจสอบมีหลักฐานที่ตรวจได้โดยไม่ต้องเชื่อเครื่องนี้: ")}<Code>delentia audit-chain export-proof --out proof.json</Code>, verified with <Code>scripts/verify_audit_bundle.py</Code>.</p>
                  </>
                ) : null}
              </Panel>
              <Panel title={L("Verify everything now", "ตรวจทุกอย่างเดี๋ยวนี้")}>
                <p className="text-[13px] leading-relaxed text-dl-muted">{L("Recomputes every link in the chain, checks the signatures with this host's key when it is known, and re-verifies the signature of every episode. The A3 check compares the chain with the heads the outside witness holds.", "คำนวณทุกข้อต่อของโซ่ใหม่ ตรวจลายเซ็นด้วยกุญแจของเครื่องนี้เมื่อรู้จัก และตรวจลายเซ็นของทุก episode ซ้ำ การตรวจ A3 เทียบโซ่กับปลายโซ่ที่พยานภายนอกถือไว้")}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button onClick={runVerify} disabled={busy}>{busy ? L("Working…", "กำลังทำงาน…") : L("Verify chain and episodes", "ตรวจโซ่และ episode")}</Button>
                  <Button tone="ghost" onClick={runWitness} disabled={busy || !(protection.data?.configured)}>{L("Check against every witness (A3)", "เทียบกับพยานทุกคน (A3)")}</Button>
                </div>
                {note ? <p role="alert" className="mt-3 text-[13px] text-dl-rust">{note}</p> : null}
                {verify ? (
                  <div className="mt-4">
                    <Row label={L("Chain", "โซ่")}>{verify.chain.ok ? <Badge tone="leaf">{L("intact", "สมบูรณ์")}</Badge> : <Badge tone="rust">{L("broken at", "ขาดที่")} #{verify.chain.first_bad_seq}</Badge>}</Row>
                    {!verify.chain.ok ? <p className="text-[13px] text-dl-rust">{verify.chain.reason}</p> : null}
                    <Row label={L("Signatures", "ลายเซ็น")}>{verify.signature_check.startsWith("NOT") ? <Badge tone="amber">{L("not checked", "ยังไม่ได้ตรวจ")}</Badge> : <Badge tone="leaf">{L("checked", "ตรวจแล้ว")}</Badge>}</Row>
                    <p className="pb-2 text-[12px] text-dl-muted">{verify.signature_check}</p>
                    <Row label={L("Episode signatures", "ลายเซ็นของ episode")}>{verify.episodes.signature_ok} {L("ok", "ผ่าน")} · {verify.episodes.signature_bad} {L("bad", "เสีย")} · {verify.episodes.unsigned} {L("unsigned", "ไม่มีลายเซ็น")} ({L("of", "จาก")} {verify.episodes.checked})</Row>
                    {verify.episodes.signature_bad ? <p className="text-[13px] text-dl-rust">{L("Rows with a bad episode signature: ", "แถวที่ลายเซ็น episode เสีย: ")}{verify.episodes.bad_audit_ids.join(", ")}</p> : null}
                    <Row label={L("Notary receipts kept locally", "ใบรับของ notary ที่เก็บไว้ในเครื่อง")}>{verify.notary.receipts_in_local_trail} ({L("gaps", "ช่องว่าง")}: {verify.notary.gaps})</Row>
                    <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">{verify.episodes.note}</p>
                  </div>
                ) : null}
                {witness ? (
                  <div className="mt-4 space-y-2">
                    {witness.witnesses.map((w) => (
                      <div key={w.witness}>
                        <Row label={`${L("Witness", "พยาน")} ${w.witness}`}>{!w.reachable ? <Badge tone="amber">{L("unreachable", "ติดต่อไม่ได้")}</Badge> : w.ok ? <Badge tone="leaf">{L("matches this chain", "ตรงกับโซ่นี้")} ({w.checked} {L("anchors", "หมุด")})</Badge> : <Badge tone="rust">{L("MISMATCH", "ไม่ตรงกัน")}</Badge>}</Row>
                        {w.problems.map((pr) => <p key={pr} className="text-[13px] text-dl-rust">{pr}</p>)}
                      </div>
                    ))}
                    <p className={`text-[13px] ${witness.ok ? "text-dl-leaf" : "text-dl-rust"}`}>{witness.ok ? L("Every witness agrees with this chain.", "พยานทุกคนเห็นตรงกับโซ่นี้") : L("At least one witness does not agree: treat the log as suspect until explained.", "มีพยานอย่างน้อยหนึ่งคนที่ไม่เห็นตรงกัน: ให้ถือว่าบันทึกน่าสงสัยจนกว่าจะอธิบายได้")}</p>
                  </div>
                ) : null}
              </Panel>
              <EventExplorer initial="all" title={L("Audit trail", "บันทึกตรวจสอบ")} />
            </div>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
