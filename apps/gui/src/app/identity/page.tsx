"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function IdentityPage() {
  const { lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
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
              <Panel title={L("How callers are identified", "วิธีระบุตัวผู้เรียก")} aside={<Badge tone={perPerson ? "leaf" : "amber"}>{d.mode}</Badge>}>
                <Row label={L("Mode", "โหมด")}>{d.mode}</Row>
                <Row label={L("Shared token (DELENTIA_API_TOKEN)", "โทเคนร่วม (DELENTIA_API_TOKEN)")}>{d.shared_token_set ? L("set", "ตั้งแล้ว") : L("not set", "ยังไม่ได้ตั้ง")}</Row>
                <Row label={L("Default role", "บทบาทเริ่มต้น")}>{d.default_role ?? L("no policy", "ไม่มีนโยบาย")}</Row>
                <Row label={L("Tokens file", "ไฟล์โทเคน")}>{d.file}</Row>
                {d.problem ? <p role="alert" className="mt-3 text-sm text-dl-rust">{d.problem}</p> : null}
                {!perPerson ? (
                  <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                    {L("Everyone who has the one shared token is the same person to the server, so roles in the policy are labels, not controls. Give each person their own token to make them real.",
                       "ทุกคนที่ถือโทเคนร่วมอันเดียวกันเป็นคนเดียวกันในสายตาของเซิร์ฟเวอร์ ดังนั้นบทบาทในนโยบายเป็นเพียงป้ายชื่อ ไม่ใช่การควบคุม ให้โทเคนแยกของแต่ละคนเพื่อให้บทบาทมีผลจริง")}
                  </p>
                ) : null}
              </Panel>
              <Panel title={L("Change who can get in", "เปลี่ยนว่าใครเข้าได้")}>
                <p className="text-[13px] leading-relaxed text-dl-muted">{L("Done on the host, on purpose: a page that could mint tokens would let anyone holding one token mint more. Each change leaves an audit row (the name and the action, never the token).",
                  "ทำบนเครื่องโฮสต์โดยตั้งใจ: หน้าเว็บที่สร้างโทเคนได้จะทำให้ใครก็ตามที่ถือโทเคนอันหนึ่งสร้างเพิ่มได้ ทุกการเปลี่ยนแปลงทิ้งแถวบันทึกตรวจสอบไว้ (ชื่อและการกระทำ ไม่มีตัวโทเคน)")}</p>
                <ul className="mt-3 space-y-2 text-[13px]">
                  <li><Code>delentia tokens create alice</Code></li>
                  <li><Code>delentia tokens revoke alice</Code></li>
                  <li><Code>delentia tokens list</Code></li>
                </ul>
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{L("Roles come from the policy's ", "บทบาทมาจาก ")}<Code>roles.principals</Code>{L(" on the FDIA page.", " ของนโยบายในหน้า FDIA")}</p>
              </Panel>
            </div>
            <Panel title={`${L("People", "ผู้ใช้")} (${d.users.length})`}>
              {!d.users.length ? <p className="text-sm text-dl-muted">{L("No per-person tokens.", "ยังไม่มีโทเคนรายบุคคล")} {d.note}</p> : (
                <div tabIndex={0} className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-left text-[13px]">
                    <thead className="desk-mono text-[11px] text-dl-muted">
                      <tr><th className="pb-2 font-normal">{L("Name", "ชื่อ")}</th><th className="pb-2 font-normal">{L("State", "สถานะ")}</th><th className="pb-2 font-normal">{L("Role", "บทบาท")}</th><th className="pb-2 font-normal">{L("Created", "สร้างเมื่อ")}</th></tr>
                    </thead>
                    <tbody className="desk-mono">
                      {d.users.map((u) => (
                        <tr key={u.name} className="border-t border-dl-rule/60">
                          <td className="py-1.5 pr-3 text-dl-text">{u.name}</td>
                          <td className="py-1.5 pr-3">{u.disabled ? <Badge tone="rust">{L("revoked", "เพิกถอนแล้ว")}</Badge> : <Badge tone="leaf">{L("active", "ใช้งานอยู่")}</Badge>} {u.owner ? <Badge tone="amber" title={L("may use the Desk, the audit trail, policies and the MCP gateway", "ใช้ Desk บันทึกตรวจสอบ นโยบาย และเกตเวย์ MCP ได้")}>{L("owner", "เจ้าของ")}</Badge> : <Badge tone="muted" title={L("may talk to the agent and manage their own jobs, tasks, approvals and memory", "คุยกับเอเจนต์และจัดการงาน ภารกิจ การอนุมัติ และความจำของตนเองได้")}>{L("person", "ผู้ใช้ทั่วไป")}</Badge>}</td>
                          <td className="py-1.5 pr-3 text-dl-muted">{u.role ?? "-"}{u.role_is_default ? ` (${L("default", "ค่าเริ่มต้น")})` : ""}</td>
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
