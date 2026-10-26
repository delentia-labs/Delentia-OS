"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type GovApproval } from "@/lib/desk-api";

const STATUSES = ["ALL", "PENDING", "APPROVED", "REJECTED", "EXECUTED"] as const;
const STATUS_TH = { ALL: "ทั้งหมด", PENDING: "รออนุมัติ", APPROVED: "อนุมัติแล้ว", REJECTED: "ปฏิเสธ", EXECUTED: "ดำเนินการแล้ว" } as const;

function unix(t: number | null) {
  return t ? fmtTime(new Date(t * 1000).toISOString()) : "-";
}

function statusTone(s: string) {
  if (s === "PENDING") return "amber" as const;
  if (s === "APPROVED" || s === "EXECUTED") return "leaf" as const;
  if (s === "REJECTED") return "rust" as const;
  return "muted" as const;
}

function Card({ a }: { a: GovApproval }) {
  const { lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
  return (
    <Panel title={a.tool_name} aside={<Badge tone={statusTone(a.status)}>{STATUS_TH[a.status as keyof typeof STATUS_TH] && lang === "th" ? STATUS_TH[a.status as keyof typeof STATUS_TH] : a.status}</Badge>}>
      <p className="text-sm text-dl-text">{a.goal}</p>
      <div className="mt-3">
        <Row label={L("Signatures", "ลายเซ็น")}>{a.signatures_collected} {L("of", "จาก")} {a.required_signatures} {L("needed", "ที่ต้องการ")}</Row>
        {a.roles_required.length ? <Row label={L("Roles asked for", "บทบาทที่ขอ")}>{a.roles_required.join(", ")}</Row> : null}
        {a.status === "PENDING" && a.roles_missing.length ? <Row label={L("Still missing a role", "ยังขาดบทบาท")}>{a.roles_missing.join(", ")}</Row> : null}
        {a.policy_rule ? <Row label={L("Owner policy rule", "กฎในนโยบายของเจ้าของ")}>{a.policy_rule}</Row> : null}
        <Row label={L("Action digest", "ลายนิ้วมือของการกระทำ")}>{a.action_sha256.slice(0, 20)}…</Row>
        <Row label={L("Asked", "ขอเมื่อ")}>{unix(a.created_at)}</Row>
        {a.decided_at ? <Row label={L("Decided", "ตัดสินเมื่อ")}>{unix(a.decided_at)}</Row> : null}
        {a.executed_at ? <Row label={L("Ran (once)", "ทำงาน (ครั้งเดียว)")}>{unix(a.executed_at)}</Row> : null}
      </div>
      {a.signers.length ? (
        <ul className="mt-3 space-y-2">
          {a.signers.map((s, i) => (
            <li key={`${s.key_fingerprint}-${i}`} className="flex flex-wrap items-center gap-2 text-[13px]">
              <Badge tone={s.verifies_now ? "leaf" : "rust"}>{s.verifies_now ? L("verifies now", "ตรวจผ่านตอนนี้") : L("DOES NOT VERIFY", "ตรวจไม่ผ่าน")}</Badge>
              <span className="text-dl-text">{s.name ?? L("unknown key", "กุญแจที่ไม่รู้จัก")}</span>
              <span className="text-dl-muted">{s.role ?? L("no role", "ไม่มีบทบาท")} · {s.decision.toLowerCase()} · {L("key", "กุญแจ")} {s.key_fingerprint} · {L("sig", "ลายเซ็น")} {s.signature_prefix}…</span>
              {!s.key_still_trusted ? <Badge tone="amber">{L("key no longer on the trusted list", "กุญแจไม่อยู่ในรายการที่เชื่อถือแล้ว")}</Badge> : null}
            </li>
          ))}
        </ul>
      ) : <p className="mt-3 text-[12px] text-dl-muted">{L("No signature yet. Sign on your device with ", "ยังไม่มีลายเซ็น ให้เซ็นบนอุปกรณ์ของคุณด้วย ")}<Code>delentia approvals sign</Code>{L(", then submit it on the Approvals page.", " แล้วส่งในหน้าอนุมัติ")}</p>}
    </Panel>
  );
}

export default function SignaturesPage() {
  const { lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("ALL");
  const keys = useDeskData(() => desk.govApprovers(), [], 60000);
  const ledger = useDeskData(() => desk.govSignatures(status === "ALL" ? undefined : status), [status], 20000);

  return (
    <>
      <PageHeader title={lang === "th" ? "ลายเซ็น" : "Signatures"}
        lead={lang === "th"
          ? "ใครมีสิทธิ์เซ็น (กุญแจสาธารณะและ role) และทุก action ที่ต้องรอมนุษย์: ลายเซ็นแต่ละอันถูกตรวจซ้ำกับ digest ของ action ทุกครั้งที่เปิดหน้านี้ ถ้ามีใครแก้ฐานข้อมูล ลายเซ็นจะขึ้นว่า ตรวจไม่ผ่าน"
          : "Who may sign (public keys and roles) and every action that waited for a human. Each signature is re-checked against the action's digest every time this page loads, so an edited database shows as not verifying."}
        actions={
          <div role="group" aria-label={L("Status", "สถานะ")} className="desk-mono flex overflow-hidden rounded border border-dl-rule text-[12px]">
            {STATUSES.map((v) => (
              <button key={v} onClick={() => setStatus(v)} aria-pressed={status === v}
                className={`desk-focus px-3 py-1 ${status === v ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>{lang === "th" ? STATUS_TH[v] : v === "ALL" ? "All" : v.charAt(0) + v.slice(1).toLowerCase()}</button>
            ))}
          </div>
        } />
      <PageBody>
        <div className="space-y-6">
          <Panel title={L("Approver keys", "กุญแจผู้อนุมัติ")} aside={keys.data ? <Badge tone={keys.data.keys.length ? "leaf" : "rust"}>{keys.data.keys.length} {L("trusted", "ที่เชื่อถือ")}</Badge> : undefined}>
            {keys.error ? <ErrorNote error={keys.error} onRetry={keys.reload} /> : null}
            {keys.data?.problem ? <p role="alert" className="mb-3 text-sm text-dl-rust">{keys.data.problem}</p> : null}
            {keys.data && !keys.data.keys.length && !keys.data.problem ? (
              <p className="text-sm text-dl-muted">{L("No approver key is configured, so nothing that needs a human can be approved (it fails closed). Make a key on your own device with ", "ยังไม่ได้ตั้งกุญแจผู้อนุมัติ จึงอนุมัติสิ่งที่ต้องใช้คนไม่ได้เลย (ระบบปิดไว้ก่อน) สร้างกุญแจบนอุปกรณ์ของคุณด้วย ")}<Code>delentia approvals keygen</Code>{L(" and add only its public key to ", " แล้วเพิ่มเฉพาะกุญแจสาธารณะของมันลงใน ")}<Code>{keys.data.file}</Code>.</p>
            ) : null}
            {keys.data?.keys.length ? (
              <div tabIndex={0} className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-[13px]">
                  <thead className="desk-mono text-[11px] text-dl-muted">
                    <tr><th className="pb-2 font-normal">{L("Name", "ชื่อ")}</th><th className="pb-2 font-normal">{L("Role", "บทบาท")}</th><th className="pb-2 font-normal">{L("Key (SHA-256 prefix)", "กุญแจ (ต้นของ SHA-256)")}</th><th className="pb-2 font-normal">{L("Signed", "เซ็นแล้ว")}</th><th className="pb-2 font-normal">{L("Refused", "ปฏิเสธ")}</th><th className="pb-2 font-normal">{L("Last used", "ใช้ล่าสุด")}</th></tr>
                  </thead>
                  <tbody className="desk-mono">
                    {keys.data.keys.map((k) => (
                      <tr key={k.public_key} className="border-t border-dl-rule/60">
                        <td className="py-1.5 pr-3 text-dl-text">{k.name}</td>
                        <td className="py-1.5 pr-3 text-dl-muted">{k.role ?? L("none", "ไม่มี")}</td>
                        <td className="py-1.5 pr-3 text-dl-muted" title={k.public_key}>{k.fingerprint}</td>
                        <td className="py-1.5 pr-3 text-dl-muted">{k.approvals_signed}</td>
                        <td className="py-1.5 pr-3 text-dl-muted">{k.rejections_signed}</td>
                        <td className="py-1.5 text-dl-muted">{unix(k.last_signed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{L("Only public keys are listed. A private key never needs to be on this machine: sign on your own device. Keys are changed in the approvers file on the host, not from this page, so that whoever reaches the API cannot add themselves as an approver.",
              "แสดงเฉพาะกุญแจสาธารณะ กุญแจส่วนตัวไม่จำเป็นต้องอยู่บนเครื่องนี้: เซ็นบนอุปกรณ์ของคุณเอง การเปลี่ยนกุญแจทำในไฟล์ผู้อนุมัติบนเครื่องโฮสต์ ไม่ใช่จากหน้านี้ เพื่อไม่ให้ใครก็ตามที่เข้าถึง API ได้เพิ่มตัวเองเป็นผู้อนุมัติได้")}</p>
          </Panel>

          {ledger.error ? <ErrorNote error={ledger.error} onRetry={ledger.reload} /> : null}
          {ledger.data ? (
            <p className="text-sm" role="status">
              {ledger.data.approvals.length === 0 ? L("No actions in this view.", "ไม่มีการกระทำในมุมมองนี้") : ledger.data.all_signatures_verify
                ? <span className="text-dl-leaf">{L("Every signature shown verifies against its action now.", "ลายเซ็นทุกอันที่แสดงตรวจผ่านกับการกระทำของมันตอนนี้")}</span>
                : <span className="text-dl-rust">{L("At least one signature does NOT verify: the record was changed after it was signed. Treat that action as untrusted.", "มีลายเซ็นอย่างน้อยหนึ่งอันที่ตรวจไม่ผ่าน: บันทึกถูกแก้หลังจากเซ็น ให้ถือว่าการกระทำนั้นเชื่อถือไม่ได้")}</span>}
            </p>
          ) : null}
          <div className="grid gap-5 xl:grid-cols-2">
            {ledger.data?.approvals.map((a) => <Card key={a.approval_id} a={a} />)}
          </div>
        </div>
      </PageBody>
    </>
  );
}
