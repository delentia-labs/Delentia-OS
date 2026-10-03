"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function IdentityPage() {
  const { lang } = useLang();
  const ids = useDeskData(() => desk.govIdentities(), [], 30000);
  const d = ids.data;
  const perPerson = d?.mode === "per-person tokens";

  return (
    <>
      <PageHeader title={lang === "th" ? "ผู้ใช้และตัวตน" : "People"}
        lead={lang === "th"
          ? "ใครเข้า API ได้ และ role ของแต่ละคนใน owner policy ตัวตนมาจาก token ที่ server ตรวจ ไม่ใช่จากช่องในคำขอ หน้านี้แสดงชื่อและสถานะเท่านั้น ไม่เคยแสดงหรือกู้ token"
          : "Who can reach the API and the role each person has in the owner's policy. Identity comes from the token the server checks, never from a field in the request. This page lists names and state; it never shows or recovers a token."} />
      <PageBody>
        {ids.error ? <ErrorNote error={ids.error} onRetry={ids.reload} /> : null}
        {d ? (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
            <div className="space-y-6">
              <Panel title="How callers are identified" aside={<Badge tone={perPerson ? "leaf" : "amber"}>{d.mode}</Badge>}>
                <Row label="Mode">{d.mode}</Row>
                <Row label="Shared token (DELENTIA_API_TOKEN)">{d.shared_token_set ? "set" : "not set"}</Row>
                <Row label="Default role">{d.default_role ?? "no policy"}</Row>
                <Row label="Tokens file">{d.file}</Row>
                {d.problem ? <p role="alert" className="mt-3 text-sm text-dl-rust">{d.problem}</p> : null}
                {!perPerson ? (
                  <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                    Everyone who has the one shared token is the same person to the server, so roles in the policy are labels, not controls. Give each person their own token to make them real.
                  </p>
                ) : null}
              </Panel>
              <Panel title="Change who can get in">
                <p className="text-[13px] leading-relaxed text-dl-muted">Done on the host, on purpose: a page that could mint tokens would let anyone holding one token mint more. Each change leaves an audit row (the name and the action, never the token).</p>
                <ul className="mt-3 space-y-2 text-[13px]">
                  <li><Code>delentia tokens create alice</Code></li>
                  <li><Code>delentia tokens revoke alice</Code></li>
                  <li><Code>delentia tokens list</Code></li>
                </ul>
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">Roles come from the policy&apos;s <Code>roles.principals</Code> on the FDIA page.</p>
              </Panel>
            </div>
            <Panel title={`People (${d.users.length})`}>
              {!d.users.length ? <p className="text-sm text-dl-muted">No per-person tokens. {d.note}</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-left text-[13px]">
                    <thead className="desk-mono text-[11px] text-dl-muted">
                      <tr><th className="pb-2 font-normal">Name</th><th className="pb-2 font-normal">State</th><th className="pb-2 font-normal">Role</th><th className="pb-2 font-normal">Created</th></tr>
                    </thead>
                    <tbody className="desk-mono">
                      {d.users.map((u) => (
                        <tr key={u.name} className="border-t border-dl-rule/60">
                          <td className="py-1.5 pr-3 text-dl-text">{u.name}</td>
                          <td className="py-1.5 pr-3">{u.disabled ? <Badge tone="rust">revoked</Badge> : <Badge tone="leaf">active</Badge>}</td>
                          <td className="py-1.5 pr-3 text-dl-muted">{u.role ?? "-"}{u.role_is_default ? " (default)" : ""}</td>
                          <td className="py-1.5 text-dl-muted">{u.created_at ? fmtTime(new Date(u.created_at * 1000).toISOString()) : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
