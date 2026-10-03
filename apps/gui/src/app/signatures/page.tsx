"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type GovApproval } from "@/lib/desk-api";

const STATUSES = ["ALL", "PENDING", "APPROVED", "REJECTED", "EXECUTED"] as const;

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
  return (
    <Panel title={a.tool_name} aside={<Badge tone={statusTone(a.status)}>{a.status}</Badge>}>
      <p className="text-sm text-dl-text">{a.goal}</p>
      <div className="mt-3">
        <Row label="Signatures">{a.signatures_collected} of {a.required_signatures} needed</Row>
        {a.roles_required.length ? <Row label="Roles asked for">{a.roles_required.join(", ")}</Row> : null}
        {a.status === "PENDING" && a.roles_missing.length ? <Row label="Still missing a role">{a.roles_missing.join(", ")}</Row> : null}
        {a.policy_rule ? <Row label="Owner policy rule">{a.policy_rule}</Row> : null}
        <Row label="Action digest">{a.action_sha256.slice(0, 20)}…</Row>
        <Row label="Asked">{unix(a.created_at)}</Row>
        {a.decided_at ? <Row label="Decided">{unix(a.decided_at)}</Row> : null}
        {a.executed_at ? <Row label="Ran (once)">{unix(a.executed_at)}</Row> : null}
      </div>
      {a.signers.length ? (
        <ul className="mt-3 space-y-2">
          {a.signers.map((s, i) => (
            <li key={`${s.key_fingerprint}-${i}`} className="flex flex-wrap items-center gap-2 text-[13px]">
              <Badge tone={s.verifies_now ? "leaf" : "rust"}>{s.verifies_now ? "verifies now" : "DOES NOT VERIFY"}</Badge>
              <span className="text-dl-text">{s.name ?? "unknown key"}</span>
              <span className="text-dl-muted">{s.role ?? "no role"} · {s.decision.toLowerCase()} · key {s.key_fingerprint} · sig {s.signature_prefix}…</span>
              {!s.key_still_trusted ? <Badge tone="amber">key no longer on the trusted list</Badge> : null}
            </li>
          ))}
        </ul>
      ) : <p className="mt-3 text-[12px] text-dl-muted">No signature yet. Sign on your device with <Code>delentia approvals sign</Code>, then submit it on the Approvals page.</p>}
    </Panel>
  );
}

export default function SignaturesPage() {
  const { lang } = useLang();
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
          <div role="group" aria-label="Status" className="desk-mono flex overflow-hidden rounded border border-dl-rule text-[12px]">
            {STATUSES.map((v) => (
              <button key={v} onClick={() => setStatus(v)} aria-pressed={status === v}
                className={`desk-focus px-3 py-1 ${status === v ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>{v === "ALL" ? "All" : v.charAt(0) + v.slice(1).toLowerCase()}</button>
            ))}
          </div>
        } />
      <PageBody>
        <div className="space-y-6">
          <Panel title="Approver keys" aside={keys.data ? <Badge tone={keys.data.keys.length ? "leaf" : "rust"}>{keys.data.keys.length} trusted</Badge> : undefined}>
            {keys.error ? <ErrorNote error={keys.error} onRetry={keys.reload} /> : null}
            {keys.data?.problem ? <p role="alert" className="mb-3 text-sm text-dl-rust">{keys.data.problem}</p> : null}
            {keys.data && !keys.data.keys.length && !keys.data.problem ? (
              <p className="text-sm text-dl-muted">No approver key is configured, so nothing that needs a human can be approved (it fails closed). Make a key on your own device with <Code>delentia approvals keygen</Code> and add only its public key to <Code>{keys.data.file}</Code>.</p>
            ) : null}
            {keys.data?.keys.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-[13px]">
                  <thead className="desk-mono text-[11px] text-dl-muted">
                    <tr><th className="pb-2 font-normal">Name</th><th className="pb-2 font-normal">Role</th><th className="pb-2 font-normal">Key (SHA-256 prefix)</th><th className="pb-2 font-normal">Signed</th><th className="pb-2 font-normal">Refused</th><th className="pb-2 font-normal">Last used</th></tr>
                  </thead>
                  <tbody className="desk-mono">
                    {keys.data.keys.map((k) => (
                      <tr key={k.public_key} className="border-t border-dl-rule/60">
                        <td className="py-1.5 pr-3 text-dl-text">{k.name}</td>
                        <td className="py-1.5 pr-3 text-dl-muted">{k.role ?? "none"}</td>
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
            <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">Only public keys are listed. A private key never needs to be on this machine: sign on your own device. Keys are changed in the approvers file on the host, not from this page, so that whoever reaches the API cannot add themselves as an approver.</p>
          </Panel>

          {ledger.error ? <ErrorNote error={ledger.error} onRetry={ledger.reload} /> : null}
          {ledger.data ? (
            <p className="text-sm" role="status">
              {ledger.data.approvals.length === 0 ? "No actions in this view." : ledger.data.all_signatures_verify
                ? <span className="text-dl-leaf">Every signature shown verifies against its action now.</span>
                : <span className="text-dl-rust">At least one signature does NOT verify: the record was changed after it was signed. Treat that action as untrusted.</span>}
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
