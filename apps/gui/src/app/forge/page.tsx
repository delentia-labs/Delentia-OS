"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type ForgeGap, type ForgeProposal } from "@/lib/desk-api";

type T = (en: string, th: string) => string;

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/50";
const label = "text-[12px] text-dl-muted";

function statusTone(status: string): "leaf" | "amber" | "rust" | "muted" | "fern" {
  if (status === "ACTIVE") return "leaf";
  if (status === "VERIFIED") return "fern";
  if (status === "AWAITING_APPROVAL") return "amber";
  if (status.startsWith("REJECTED")) return "rust";
  return "muted";
}

function ProposeForm({ T, limits, prefill, onDone }: {
  T: T; limits: { allowed_imports: string[]; min_asserts: number }; prefill: ForgeGap | null; onDone: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [spec, setSpec] = useState(prefill ? `handle requests like: ${prefill.goals[0].slice(0, 160)}` : "");
  const [smoke, setSmoke] = useState("assert my_tool('input') == 'expected'\nassert my_tool('other') == 'expected other'");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const made = await desk.forgePropose({ name: name.trim(), spec: spec.trim(), smoke_test: smoke, ...(code.trim() ? { code } : {}), ...(prefill ? { gap: prefill } : {}) });
      onDone(made.status === "VERIFIED"
        ? T(`Proposal ${made.id} passed the checks. Review it below, then ask for a signature.`, `ข้อเสนอ ${made.id} ผ่านการตรวจ ตรวจดูด้านล่างแล้วขอลายเซ็น`)
        : T(`Proposal ${made.id} was rejected (${made.status}): ${(made.verification.problems ?? []).join("; ")}`, `ข้อเสนอ ${made.id} ถูกปฏิเสธ (${made.status}): ${(made.verification.problems ?? []).join("; ")}`));
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };

  return (
    <Panel title={T("Propose a tool", "เสนอเครื่องมือใหม่")}>
      <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">
        {T(`A pure function: text, numbers, dates. Imports only from ${limits.allowed_imports.join(", ")}. The smoke test needs at least ${limits.min_asserts} assertions that call the function; leave the code empty to have the configured model write it (one model call).`,
          `ฟังก์ชันล้วน: ข้อความ ตัวเลข วันที่ import ได้เฉพาะ ${limits.allowed_imports.join(", ")} smoke test ต้องมี assertion ที่เรียกฟังก์ชันอย่างน้อย ${limits.min_asserts} ข้อ ถ้าเว้นโค้ดว่าง ระบบจะให้โมเดลที่ตั้งไว้เขียนให้ (เรียกโมเดล 1 ครั้ง)`)}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block"><span className={label}>{T("Tool name (lowercase, digits, _)", "ชื่อเครื่องมือ (ตัวพิมพ์เล็ก ตัวเลข _)")}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="slugify" className={field} aria-label="Tool name" /></label>
        <label className="block"><span className={label}>{T("What it does (one sentence)", "ทำอะไร (หนึ่งประโยค)")}</span>
          <input value={spec} onChange={(e) => setSpec(e.target.value)} className={field} aria-label="Spec" /></label>
        <label className="block"><span className={label}>{T("Smoke test (assert lines)", "smoke test (บรรทัด assert)")}</span>
          <textarea value={smoke} onChange={(e) => setSmoke(e.target.value)} rows={5} className={field} aria-label="Smoke test" /></label>
        <label className="block"><span className={label}>{T("Code (optional: empty = the model writes it)", "โค้ด (ไม่บังคับ: ว่าง = ให้โมเดลเขียน)")}</span>
          <textarea value={code} onChange={(e) => setCode(e.target.value)} rows={5} className={field} aria-label="Code" /></label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={submit} disabled={busy || !name.trim() || !spec.trim()}>{busy ? T("Checking…", "กำลังตรวจ…") : T("Check it", "ตรวจ")}</Button>
        <span className="text-[12px] text-dl-muted">{T("Nothing is installed by this. A person signs the exact code first.", "ขั้นนี้ยังไม่ติดตั้งอะไร ต้องมีคนเซ็นโค้ดนี้ก่อน")}</span>
      </div>
      {error ? <p role="alert" className="mt-2 text-[13px] text-dl-rust">{error}</p> : null}
    </Panel>
  );
}

function ProposalCard({ p, T, reload, say }: { p: ForgeProposal; T: T; reload: () => void; say: (m: string) => void }) {
  const [detail, setDetail] = useState<ForgeProposal | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setOpen(!open);
    if (!detail) { try { setDetail(await desk.forgeProposal(p.id)); } catch (err) { say(err instanceof Error ? err.message : String(err)); } }
  };
  const request = async () => {
    setBusy(true);
    try { const r = await desk.forgeRequest(p.id); say(`${T("Signature requested.", "ขอลายเซ็นแล้ว")} ${r.how}`); reload(); }
    catch (err) { say(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  const activate = async () => {
    if (!p.approval_id) return;
    setBusy(true);
    try { const r = await desk.forgeActivate(p.approval_id); say(T(`Installed ${r.name}.`, `ติดตั้ง ${r.name} แล้ว`)); reload(); }
    catch (err) { say(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  const approved = p.approval?.status === "APPROVED";

  return (
    <div className="rounded border border-dl-rule bg-dl-ink/40">
      <button type="button" onClick={toggle} aria-expanded={open} className="desk-focus flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="desk-mono text-[13px] text-dl-text">{p.name}</span><Badge tone={statusTone(p.status)}>{p.status}</Badge>
          {p.verification.code_source ? <Badge tone="muted">{p.verification.code_source === "model" ? T("written by the model", "โมเดลเขียน") : T("supplied", "คนใส่ให้")}</Badge> : null}
        </span>
        <span className="desk-mono text-[11px] text-dl-muted">{p.id} · {fmtTime(new Date(p.created_at * 1000).toISOString())}</span>
      </button>
      {open ? (
        <div className="space-y-3 border-t border-dl-rule px-3 py-3">
          <p className="text-[13px] text-dl-muted">{p.spec}</p>
          {p.gap?.goals?.length ? <p className="text-[12px] text-dl-muted">{T("Evidence of the gap: ", "หลักฐานช่องว่าง: ")}{p.gap.goals.slice(0, 2).join(" · ")}</p> : null}
          {(p.verification.problems ?? []).length ? (
            <ul className="list-disc pl-5 text-[13px] text-dl-rust">{(p.verification.problems ?? []).map((x) => <li key={x}>{x}</li>)}</ul>
          ) : p.verification.passed ? <p className="text-[13px] text-dl-leaf">{T("Static check passed and the smoke test ran in a separate process.", "ผ่านการตรวจโค้ดและ smoke test รันใน process แยกแล้ว")}</p> : null}
          {detail ? (
            <div className="grid gap-3 lg:grid-cols-2">
              <div><p className={label}>{T("Code", "โค้ด")}</p><pre className="desk-mono mt-1 max-h-64 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] leading-relaxed text-dl-text">{detail.code}</pre></div>
              <div><p className={label}>{T("Smoke test", "smoke test")}</p><pre className="desk-mono mt-1 max-h-64 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] leading-relaxed text-dl-text">{detail.smoke_test}</pre></div>
            </div>
          ) : null}
          <Row label={T("Hash a person signs (code + test)", "hash ที่คนเซ็น (โค้ด + เทส)")}>{p.code_sha256.slice(0, 24)}…</Row>
          {p.approval ? <Row label={T("Signature", "ลายเซ็น")}>{p.approval.status} · {p.approval.signatures_collected}/{p.approval.required_signatures}</Row> : null}
          <div className="flex flex-wrap items-center gap-2">
            {p.status === "VERIFIED" ? <Button onClick={request} disabled={busy}>{T("Ask for a signature", "ขอลายเซ็น")}</Button> : null}
            {p.status === "AWAITING_APPROVAL" ? <Button onClick={activate} disabled={busy || !approved}>{approved ? T("Install (signed)", "ติดตั้ง (เซ็นแล้ว)") : T("Install (waiting for the signature)", "ติดตั้ง (รอลายเซ็น)")}</Button> : null}
            {p.approval_id && p.status === "AWAITING_APPROVAL" ? <span className="text-[12px] text-dl-muted">{T("Sign with ", "เซ็นด้วย ")}<Code>delentia approvals approve {p.approval_id} --key …</Code></span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ToolCard({ name, spec, calls, active, T, reload, say }: { name: string; spec: string; calls: number; active: boolean; T: T; reload: () => void; say: (m: string) => void }) {
  const [args, setArgs] = useState("{}");
  const [out, setOut] = useState<string | null>(null);
  const run = async () => {
    try { setOut(JSON.stringify(await desk.forgeRun(name, JSON.parse(args || "{}")), null, 2)); }
    catch (err) { setOut(err instanceof Error ? err.message : String(err)); }
    reload();
  };
  const off = async () => {
    try { await desk.forgeOff(name); say(T(`Turned ${name} off. The record stays.`, `ปิด ${name} แล้ว บันทึกยังอยู่`)); reload(); }
    catch (err) { say(err instanceof Error ? err.message : String(err)); }
  };
  return (
    <div className="rounded border border-dl-rule bg-dl-ink/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2"><span className="desk-mono text-[13px] text-dl-text">{name}</span><Badge tone={active ? "leaf" : "muted"}>{active ? T("active", "ใช้งาน") : T("off", "ปิด")}</Badge></span>
        <span className="desk-mono text-[11px] text-dl-muted">{T("calls", "เรียก")} {calls}</span>
      </div>
      <p className="mt-1 text-[13px] text-dl-muted">{spec}</p>
      {active ? (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="min-w-[14rem] flex-1"><span className={label}>{T("Arguments (JSON)", "arguments (JSON)")}</span><input value={args} onChange={(e) => setArgs(e.target.value)} className={field} aria-label={`${name} arguments`} /></label>
          <Button onClick={run}>{T("Try", "ลอง")}</Button><Button tone="amber" onClick={off}>{T("Turn off", "ปิด")}</Button>
        </div>
      ) : null}
      {out ? <pre className="desk-mono mt-2 max-h-40 overflow-auto rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-text">{out}</pre> : null}
    </div>
  );
}

export default function ForgePage() {
  const { lang } = useLang();
  const T: T = (en, th) => (lang === "th" ? th : en);
  const forge = useDeskData(() => desk.forge(), [], 15000);
  const [prefill, setPrefill] = useState<ForgeGap | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const d = forge.data;

  return (
    <>
      <PageHeader title="Forge"
        lead={lang === "th"
          ? "ระบบหาช่องว่างของตัวเองจากหลักฐาน: เป้าหมายที่ agent จบแล้วแต่ไม่ตอบโจทย์ ซ้ำหลายครั้ง จากนั้นเสนอเครื่องมือใหม่ (ฟังก์ชันล้วน) ตรวจโค้ดและรัน smoke test ใน process แยก แล้วรอให้คนเซ็น hash ของโค้ดก่อนจะใช้ได้ ไม่มีอะไรถูกติดตั้งเองโดยไม่มีลายเซ็น"
          : "The system finds its own gaps from evidence: goals the agent finished without satisfying, more than once. It then proposes a new tool (a pure function), checks the code, runs the smoke test in a separate process, and waits for a person to sign the code's hash. Nothing is installed without a signature."} />
      <PageBody>
        {forge.error ? <ErrorNote error={forge.error} onRetry={forge.reload} /> : null}
        {note ? <p role="status" className="mb-4 rounded border border-dl-fern bg-dl-pine/30 px-3 py-2 text-[13px] text-dl-text">{note}</p> : null}
        {d ? (
          <div className="space-y-6">
            <Panel title={T("Gaps the evidence shows", "ช่องว่างที่หลักฐานแสดง")} aside={<span className="desk-mono text-[11px] text-dl-muted">{d.gaps.length}</span>}>
              {d.gaps.length ? (
                <ul className="space-y-3">
                  {d.gaps.map((g) => (
                    <li key={g.gap_id} className="rounded border border-dl-rule bg-dl-ink/40 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex items-center gap-2"><Badge tone="amber">×{g.count}</Badge><span className="desk-mono text-[12px] text-dl-muted">{g.users} {T("user(s)", "ผู้ใช้")} · {g.keywords.slice(0, 5).join(", ")}</span></span>
                        <Button tone="ghost" onClick={() => { setPrefill(g); setFormKey((k) => k + 1); }}>{T("Draft a proposal from this", "ร่างข้อเสนอจากช่องว่างนี้")}</Button>
                      </div>
                      <ul className="mt-1 list-disc pl-5 text-[13px] text-dl-muted">{g.goals.slice(0, 3).map((x) => <li key={x}>{x}</li>)}</ul>
                    </li>
                  ))}
                </ul>
              ) : <Empty title={T("No repeated unmet goal yet", "ยังไม่มีเป้าหมายที่ไม่สำเร็จซ้ำ")}>{T("A gap appears when the same kind of goal ends without a satisfying answer at least twice.", "ช่องว่างจะปรากฏเมื่อเป้าหมายแบบเดียวกันจบโดยไม่ตอบโจทย์อย่างน้อยสองครั้ง")}</Empty>}
            </Panel>

            <ProposeForm key={formKey} T={T} limits={d.limits} prefill={prefill} onDone={(m) => { setNote(m); forge.reload(); }} />

            <Panel title={T("Proposals", "ข้อเสนอ")} aside={<span className="desk-mono text-[11px] text-dl-muted">{d.proposals.length}</span>}>
              {d.proposals.length ? <div className="space-y-2">{d.proposals.map((p) => <ProposalCard key={p.id} p={p} T={T} reload={forge.reload} say={setNote} />)}</div>
                : <p className="text-[13px] text-dl-muted">{T("None yet. Rejected proposals are kept here too, with the reason.", "ยังไม่มี ข้อเสนอที่ถูกปฏิเสธก็เก็บไว้ที่นี่พร้อมเหตุผล")}</p>}
            </Panel>

            <Panel title={T("Forged tools", "เครื่องมือที่สร้างแล้ว")} aside={<span className="desk-mono text-[11px] text-dl-muted">{d.tools.length}</span>}>
              {d.tools.length ? <div className="space-y-2">{d.tools.map((t) => <ToolCard key={t.name} name={t.name} spec={t.spec} calls={t.calls} active={t.active} T={T} reload={forge.reload} say={setNote} />)}</div>
                : <p className="text-[13px] text-dl-muted">{T("None installed.", "ยังไม่มีที่ติดตั้ง")}</p>}
              <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                {T(`Each runs alone in its own process for at most ${d.limits.run_timeout_s} s with no files, no network and no environment secrets, and its file is checked against the signed hash on every call. The agent calls them through `, `แต่ละตัวรันแยก process นานไม่เกิน ${d.limits.run_timeout_s} วินาที ไม่มีไฟล์ ไม่มีเครือข่าย ไม่เห็นความลับใน environment และตรวจไฟล์กับ hash ที่เซ็นทุกครั้ง agent เรียกผ่าน `)}<Code>delentia_run_forged_tool</Code>.
              </p>
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
