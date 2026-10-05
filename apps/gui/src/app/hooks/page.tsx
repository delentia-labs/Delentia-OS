"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type HookRecord } from "@/lib/desk-api";

type T = (en: string, th: string) => string;

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/50";
const label = "text-[12px] text-dl-muted";
const EXAMPLE = `def pre_tool_call(tool_name, args):
    if "secret" in str(args).lower():
        return {"action": "block", "reason": "the call names something secret"}
    return None
`;

function tone(status: string): "leaf" | "amber" | "rust" | "muted" | "fern" {
  if (status === "ACTIVE") return "leaf";
  if (status === "PROPOSED") return "fern";
  if (status === "AWAITING_APPROVAL") return "amber";
  if (status === "REJECTED") return "rust";
  return "muted";
}

function HookCard({ h, T, reload, say }: { h: HookRecord; T: T; reload: () => void; say: (m: string) => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    try { say(await fn()); reload(); } catch (err) { say(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  };
  const toggle = async () => {
    setOpen(!open);
    if (!code) { try { setCode((await desk.hook(h.name)).code ?? ""); } catch (err) { say(err instanceof Error ? err.message : String(err)); } }
  };
  const approved = h.approval?.status === "APPROVED";
  return (
    <div className="rounded border border-dl-rule bg-dl-ink/40">
      <button type="button" onClick={toggle} aria-expanded={open} className="desk-focus flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="desk-mono text-[13px] text-dl-text">{h.name}</span><Badge tone={tone(h.status)}>{h.status}</Badge>
          {h.points.map((p) => <Badge key={p} tone="muted">{p}</Badge>)}
        </span>
        <span className="desk-mono text-[11px] text-dl-muted">{fmtTime(new Date(h.created_at * 1000).toISOString())}</span>
      </button>
      {open ? (
        <div className="space-y-3 border-t border-dl-rule px-3 py-3">
          <p className="text-[13px] text-dl-muted">{h.description || T("(no description)", "(ไม่มีคำอธิบาย)")}</p>
          {(h.verification.problems ?? []).length ? <ul className="list-disc pl-5 text-[13px] text-dl-rust">{(h.verification.problems ?? []).map((x) => <li key={x}>{x}</li>)}</ul> : null}
          {code !== null ? <pre className="desk-mono max-h-64 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] leading-relaxed text-dl-text">{code}</pre> : null}
          <Row label={T("Hash a person signs", "hash ที่คนเซ็น")}>{h.code_sha256.slice(0, 24)}…</Row>
          {h.approval ? <Row label={T("Signature", "ลายเซ็น")}>{h.approval.status} · {h.approval.signatures_collected}/{h.approval.required_signatures}</Row> : null}
          <div className="flex flex-wrap items-center gap-2">
            {h.status === "PROPOSED" ? <Button disabled={busy} onClick={() => run(async () => { const r = await desk.hookRequest(h.name); return `${T("Signature requested.", "ขอลายเซ็นแล้ว")} ${r.how}`; })}>{T("Ask for a signature", "ขอลายเซ็น")}</Button> : null}
            {h.status === "AWAITING_APPROVAL" && h.approval_id ? (
              <Button disabled={busy || !approved} onClick={() => run(async () => { const r = await desk.hookActivate(h.approval_id as string); return T(`Switched on ${r.name}.`, `เปิด ${r.name} แล้ว`); })}>
                {approved ? T("Switch on (signed)", "เปิดใช้ (เซ็นแล้ว)") : T("Switch on (waiting for the signature)", "เปิดใช้ (รอลายเซ็น)")}
              </Button>
            ) : null}
            {h.status === "ACTIVE" ? <Button tone="amber" disabled={busy} onClick={() => run(async () => { await desk.hookDisable(h.name); return T(`Switched ${h.name} off. The record stays.`, `ปิด ${h.name} แล้ว บันทึกยังอยู่`); })}>{T("Switch off", "ปิด")}</Button> : null}
            {h.approval_id && h.status === "AWAITING_APPROVAL" ? <span className="text-[12px] text-dl-muted">{T("Sign with ", "เซ็นด้วย ")}<Code>delentia approvals approve {h.approval_id} --key …</Code></span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function HooksPage() {
  const { lang } = useLang();
  const T: T = (en, th) => (lang === "th" ? th : en);
  const state = useDeskData(() => desk.hooks(), [], 15000);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(EXAMPLE);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = state.data;

  const propose = async () => {
    setBusy(true); setNote(null);
    try {
      const r = await desk.hookPropose({ name: name.trim(), code, description: description.trim() });
      setNote(r.status === "PROPOSED" ? T(`${r.name} passed the checks. Ask for a signature below.`, `${r.name} ผ่านการตรวจ ขอลายเซ็นด้านล่าง`) : T(`${r.name} was rejected: ${(r.verification.problems ?? []).join("; ")}`, `${r.name} ถูกปฏิเสธ: ${(r.verification.problems ?? []).join("; ")}`));
      state.reload();
    } catch (err) { setNote(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Hooks"
        lead={lang === "th"
          ? "โค้ดของคุณที่แทรกในลูปได้ แต่ทำให้ระบบเข้มขึ้นอย่างเดียว: pre_tool_call บล็อกหรือขอลายเซ็นก่อนเรียก tool, transform_tool_result ลบหรือปิดบังข้อมูลในผลของ tool ห้ามอนุญาตสิ่งที่ gate ปฏิเสธ ห้ามข้ามลายเซ็น ห้ามแก้ args ทุกอย่างที่ผิดพลาดจะลงเอยที่ขอลายเซ็น และต้องมีคนเซ็น hash ของโค้ดก่อนใช้"
          : "Your own code at two points of the loop that can only make the system stricter: pre_tool_call blocks a call or asks for a signature, transform_tool_result deletes or redacts parts of a tool's result. It cannot allow what the gate refuses, skip a signature or change arguments. Every failure ends as a request for a signature, and a person signs the code's hash before it runs."} />
      <PageBody>
        {state.error ? <ErrorNote error={state.error} onRetry={state.reload} /> : null}
        {note ? <p role="status" className="mb-4 rounded border border-dl-fern bg-dl-pine/30 px-3 py-2 text-[13px] text-dl-text">{note}</p> : null}
        {d ? (
          <div className="space-y-6">
            {!d.enabled ? <p role="alert" className="rounded border border-dl-amber px-3 py-2 text-[13px] text-dl-text">{T("Hooks are switched off on this host (DELENTIA_HOOKS=off): nothing below runs.", "hooks ถูกปิดบนโฮสต์นี้ (DELENTIA_HOOKS=off): ไม่มีอะไรด้านล่างทำงาน")}</p> : null}
            <Panel title={T("Propose a hook", "เสนอ hook")}>
              <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">
                {T(`A pure function in at most ${d.limits.max_code_chars} characters, defining ${d.limits.points.join(" and/or ")}; imports only from ${d.limits.allowed_imports.join(", ")}; it runs in its own process for at most ${d.limits.run_timeout_s} s with no files, no network and no secrets.`,
                  `ฟังก์ชันล้วนไม่เกิน ${d.limits.max_code_chars} ตัวอักษร นิยาม ${d.limits.points.join(" และ/หรือ ")} import ได้เฉพาะ ${d.limits.allowed_imports.join(", ")} รันใน process แยกนานไม่เกิน ${d.limits.run_timeout_s} วินาที ไม่มีไฟล์ ไม่มีเครือข่าย ไม่มีความลับ`)}
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block"><span className={label}>{T("Name (lowercase, digits, _)", "ชื่อ (ตัวพิมพ์เล็ก ตัวเลข _)")}</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="no_secrets" className={field} aria-label="Hook name" /></label>
                <label className="block"><span className={label}>{T("What it does", "ทำอะไร")}</span><input value={description} onChange={(e) => setDescription(e.target.value)} className={field} aria-label="Hook description" /></label>
              </div>
              <label className="mt-3 block"><span className={label}>{T("Code", "โค้ด")}</span><textarea value={code} onChange={(e) => setCode(e.target.value)} rows={9} className={field} aria-label="Hook code" /></label>
              <div className="mt-3 flex items-center gap-3">
                <Button onClick={propose} disabled={busy || !name.trim() || !code.trim()}>{busy ? T("Checking…", "กำลังตรวจ…") : T("Check it", "ตรวจ")}</Button>
                <span className="text-[12px] text-dl-muted">{T("Nothing runs from this step. A person signs the exact code first.", "ขั้นนี้ยังไม่รันอะไร ต้องมีคนเซ็นโค้ดนี้ก่อน")}</span>
              </div>
            </Panel>
            <Panel title={T("Hooks", "Hooks")} aside={<span className="desk-mono text-[11px] text-dl-muted">{d.hooks.length}</span>}>
              {d.hooks.length ? <div className="space-y-2">{d.hooks.map((h) => <HookCard key={h.name} h={h} T={T} reload={state.reload} say={setNote} />)}</div>
                : <p className="text-[13px] text-dl-muted">{T("None yet.", "ยังไม่มี")}</p>}
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
