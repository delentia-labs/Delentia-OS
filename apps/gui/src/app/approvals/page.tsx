"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { AnsweredSection, QuestionStatsPanel, QuestionsSection } from "@/components/desk/Questions";
import { useDeviceProblem } from "@/components/desk/ApprovalDevices";
import { desk, type PendingAction } from "@/lib/desk-api";
import { parseSignedDecision } from "@/lib/signed-decision";
import { ceremonyMessage, getAssertion } from "@/lib/webauthn";

function statusTone(s: string) {
  if (s === "PENDING") return "amber" as const;
  if (s === "APPROVED" || s === "EXECUTED") return "leaf" as const;
  if (s === "REJECTED") return "rust" as const;
  return "muted" as const;
}

const KIND_LABEL: Record<string, { en: string; th: string }> = {
  delete: { en: "delete", th: "ลบ" },
  outward: { en: "send out", th: "ส่งออกนอก" },
  money: { en: "move money", th: "เงิน" },
  permissions: { en: "change permissions or users", th: "สิทธิ์/ผู้ใช้" },
  publish: { en: "publish or deploy", th: "เผยแพร่" },
  restore_cancel: { en: "cancel, restore or roll back", th: "ยกเลิก/กู้คืน/ย้อนกลับ" },
  move_shutdown: { en: "move or shut down", th: "ย้าย/ปิดระบบ" },
  document_edit: { en: "edit documents", th: "แก้เอกสาร" },
};

type PlanStep = { n: number; tool: string; kind: string; why?: string; args?: Record<string, unknown> };

function shortArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  const text = JSON.stringify(args);
  return text.length > 140 ? `${text.slice(0, 140)}…` : text;
}

// A plan is shown as the numbered steps it will run, in order, with the kind of each: confirming it once runs exactly these.
function PlanSteps({ a, lang }: { a: PendingAction; lang: "th" | "en" }) {
  const plan = (a.tool_args as { plan?: { steps?: PlanStep[]; counts?: Record<string, number>; digest?: string } }).plan;
  const steps = plan?.steps ?? [];
  return (
    <div className="mt-3 rounded border border-dl-rule bg-dl-ink p-3">
      <p className="text-[13px] font-medium text-dl-text">
        {lang === "th" ? `แผนนี้มี ${steps.length} ขั้น — ยืนยันครั้งเดียว แล้วระบบทำตามลำดับนี้เท่านั้น` : `This plan has ${steps.length} step(s). Confirm once and the system runs exactly these, in this order.`}
      </p>
      <ol className="mt-2 space-y-2">
        {steps.map((step) => (
          <li key={step.n} className="text-[13px] leading-relaxed text-dl-text">
            <span className="desk-mono text-dl-muted">{step.n}.</span>{" "}
            <Badge tone={step.kind === "document_edit" ? "muted" : "amber"}>{(KIND_LABEL[step.kind]?.[lang]) ?? step.kind}</Badge>{" "}
            <span className="desk-mono">{step.tool}</span>
            <div className="desk-mono ml-5 break-all text-[12px] text-dl-muted">{shortArgs(step.args)}</div>
            {step.why ? <div className="ml-5 text-[12px] text-dl-muted">{step.why}</div> : null}
          </li>
        ))}
      </ol>
      <p className="mt-2 text-[12px] text-dl-muted">
        {lang === "th" ? "ถ้าขั้นใดล้มเหลวหรือถูกกฎปฏิเสธ ขั้นที่เหลือจะไม่ถูกรัน" : "If a step fails or a rule refuses it, the steps after it do not run."}
      </p>
    </div>
  );
}

function ActionCard({ a, onChanged, devices }: { a: PendingAction; onChanged: (notice?: string) => void; devices: number }) {
  const { lang } = useLang();
  const th = lang === "th";
  const deviceProblem = useDeviceProblem();
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const signCmd = `delentia approvals sign ${a.approval_id} --digest ${a.action_sha256} --key <path to your approver key>`;

  const submit = async () => {
    setMessage(null);
    const parsed = parseSignedDecision(pasted, lang);     // says exactly what is wrong (pasted twice, cut off, wrong length...)
    if (!parsed.ok) {
      setMessage({ tone: "err", text: parsed.message });
      return;
    }
    const body = parsed.body;
    setBusy(true);
    try {
      await desk.decide(a.approval_id, body);
      setMessage({ tone: "ok", text: lang === "th" ? `บันทึกแล้ว: ${body.decision}` : `Recorded: ${body.decision}.` });
      setPasted("");
      onChanged();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  // Confirm (or refuse) with this computer's own device: Windows Hello asks the person, the server checks the answer belongs to THIS action and THIS decision.
  // An approved action is then run at once, so one touch is enough; an action that still needs more signatures just waits.
  const withDevice = async (decision: "APPROVED" | "REJECTED") => {
    setBusy(true);
    setMessage(null);
    try {
      const asked = await desk.deviceOptions(a.approval_id, decision);
      const assertion = await getAssertion(asked.options);
      const decided = await desk.deviceDecide(a.approval_id, decision, assertion);
      if (decided.status === "APPROVED") {
        await desk.resume(a.approval_id);
        onChanged(th ? "ยืนยันแล้ว และรันงานนี้หนึ่งครั้งแล้ว ดูผลที่หน้า Sessions" : "Confirmed, and the action ran once. See Sessions.");
        return;
      } else if (decided.status === "REJECTED") {
        onChanged(th ? "ปฏิเสธแล้ว งานนี้จะไม่ถูกรัน" : "Refused. The action will not run.");
        return;
      } else {
        setMessage({ tone: "ok", text: th ? `บันทึกลายเซ็นแล้ว (${decided.signatures} จาก ${decided.required}) ต้องรอผู้เซ็นคนถัดไป` : `Recorded (${decided.signatures} of ${decided.required}). Waiting for the next signer.` });
      }
      onChanged();
    } catch (err) {
      setMessage({ tone: "err", text: ceremonyMessage(err, lang as "th" | "en") });
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await desk.resume(a.approval_id);
      setMessage({ tone: "ok", text: th ? "รันงานที่อนุมัติแล้วหนึ่งครั้ง ดูผลที่หน้าเซสชัน" : "Ran the approved action once and continued the episode. See Sessions." });
      onChanged();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={`${a.tool_name}`} aside={<Badge tone={statusTone(a.status)}>{a.status}</Badge>}>
      <p className="text-sm text-dl-text">{a.goal}</p>
      {a.tool_name === "delentia_plan" ? <PlanSteps a={a} lang={lang as "th" | "en"} /> : null}
      <pre className="desk-mono mt-3 max-h-48 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] text-dl-muted">
        {JSON.stringify(a.tool_args, null, 2)}
      </pre>
      <div className="mt-3">
        <Row label={th ? "ทำไมจึงรอ" : "Why it waits"}>{a.reason}</Row>
        {a.required_signatures && a.required_signatures > 1 ? <Row label={th ? "ลายเซ็น" : "Signatures"}>{a.signatures_collected ?? 0} {th ? "จาก" : "of"} {a.required_signatures} {th ? "(ต้องเป็นคนละกุญแจ/เครื่อง)" : "(distinct keys)"}</Row> : null}
        {a.approver_roles?.length ? <Row label={th ? "บทบาทที่ต้องการ" : "Roles asked for"}>{a.approver_roles.join(", ")}</Row> : null}
        {a.policy_rule ? <Row label={th ? "กฎของเจ้าของที่ใช้" : "Owner policy rule"}>{a.policy_rule}</Row> : null}
        <Row label={th ? "รหัสของงาน (SHA-256)" : "Action digest (SHA-256)"}>{`${a.action_sha256.slice(0, 20)}…`}</Row>
        <Row label={th ? "ขอเมื่อ" : "Requested"}>{fmtTime(a.created_at)}</Row>
        {a.approver_public_key ? <Row label={th ? "เซ็นด้วยกุญแจ" : "Signed by key"}>{`${a.approver_public_key.slice(0, 16)}…`}</Row> : null}
      </div>

      {a.status === "PENDING" ? (
        <div className="mt-4 space-y-2">
          {a.required_signatures && a.required_signatures > 1 ? (
            <p className="text-[13px] leading-relaxed text-dl-amber">
              This action needs {a.required_signatures} signatures from distinct keys ({a.signatures_collected ?? 0} collected). Each signer repeats the steps below; it runs only after the last one.
            </p>
          ) : null}
          {devices > 0 ? (
            <div className="rounded border border-dl-fern/50 bg-dl-pine/20 p-3">
              <p className="text-[13px] leading-relaxed text-dl-text">
                {th ? "ยืนยันด้วยเครื่องนี้ (Windows Hello / ลายนิ้วมือ / มือถือ): อ่านรายละเอียดด้านบนให้ครบก่อน แล้วกดปุ่ม เครื่องจะถามตัวคุณ" : "Confirm with this computer (Windows Hello / fingerprint / phone): read the details above first, then press the button; the device asks you."}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button onClick={() => withDevice("APPROVED")} disabled={busy || !!deviceProblem}>{busy ? (th ? "รอเครื่องยืนยัน…" : "Waiting for the device…") : th ? "อนุมัติด้วยเครื่องนี้" : "Approve with this device"}</Button>
                <Button tone="ghost" onClick={() => withDevice("REJECTED")} disabled={busy || !!deviceProblem}>{th ? "ปฏิเสธด้วยเครื่องนี้" : "Refuse with this device"}</Button>
              </div>
              {deviceProblem ? <p className="mt-2 text-[12px] text-dl-amber">{deviceProblem}</p> : null}
            </div>
          ) : (
            <p className="text-[13px] leading-relaxed text-dl-muted">
              {th ? "อยากยืนยันด้วยปุ่มและ Windows Hello แทนการพิมพ์คำสั่ง? เพิ่มเครื่องนี้ที่หน้า Settings → อุปกรณ์ยืนยัน (ทำครั้งเดียว) หรือดับเบิลคลิก SIGN_PENDING.bat เพื่อเซ็นทีละรายการ" : "Prefer a button and Windows Hello over typing a command? Add this computer once under Settings → Approval devices, or double-click SIGN_PENDING.bat to sign one at a time."}
            </p>
          )}
          <p className="text-[13px] leading-relaxed text-dl-muted">
            {th ? "หรือเซ็นด้วยกุญแจ approver บนเครื่องที่เก็บกุญแจไว้ (ไม่จำเป็นต้องเป็นเครื่องนี้) แล้ววาง JSON ที่พิมพ์ออกมา:" : "Or sign on the device that holds your approver key (it never needs to be on this machine), then paste the printed JSON:"}
          </p>
          <Code>{signCmd}</Code>
          <label className="block">
            <span className="sr-only">Signed decision JSON</span>
            <textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={4} placeholder='{"public_key_hex": "…", "signature_hex": "…", "decision": "APPROVED"}'
              className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-text placeholder:text-dl-muted/50" />
          </label>
          <Button onClick={submit} disabled={busy || !pasted.trim()}>{th ? "ส่งลายเซ็น" : "Submit signed decision"}</Button>
        </div>
      ) : null}
      {a.status === "APPROVED" && a.tool_name === "passkey_enroll" ? (
        <p className="mt-4 text-[13px] leading-relaxed text-dl-muted">
          {th ? "ผู้อนุมัติเซ็นรับรองเครื่องนี้แล้ว ไปที่ Settings → อุปกรณ์ยืนยัน แล้วกด “เปิดใช้”" : "An approver has signed for this device. Go to Settings → Approval devices and press Activate."}
        </p>
      ) : null}
      {a.status === "APPROVED" && a.tool_name !== "passkey_enroll" ? (
        <div className="mt-4">
          <Button tone="amber" onClick={run} disabled={busy}>{busy ? (th ? "กำลังรัน…" : "Running…") : (th ? "รันงานที่อนุมัติแล้ว" : "Run the approved action")}</Button>
          <p className="mt-2 text-[12px] text-dl-muted">{th ? "รันครั้งเดียวเท่านั้น และตรวจลายเซ็นอีกรอบก่อนรัน" : "Runs exactly once; the signature is checked again first."}</p>
        </div>
      ) : null}
      {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
    </Panel>
  );
}

export default function ApprovalsPage() {
  const { t, lang } = useLang();
  const [view, setView] = useState<"PENDING" | "ALL">("PENDING");
  // "Waiting" = needs something from you: not yet signed, or signed but not yet run (it used to hide the second kind,
  // so an approved action vanished from the default tab and the Run button was found only under "All").
  const list = useDeskData(async () => {
    if (view === "ALL") return desk.approvals("ALL");
    const all = await desk.approvals("ALL");
    return all.filter((a) => a.status === "PENDING" || (a.status === "APPROVED" && !a.executed_at));
  }, [view], 15000);
  const deviceList = useDeskData(() => desk.devices(), [], 30000);
  const activeDevices = deviceList.data?.devices.filter((d) => d.status === "ACTIVE").length ?? 0;
  const questions = useDeskData(() => desk.clarifications("PENDING"), [], 15000);
  const questionStats = useDeskData(() => desk.rct7Stats(14), [], 60000);
  const answered = useDeskData(() => desk.clarifications("ANSWERED"), [], 15000);
  const [notice, setNotice] = useState<string | null>(null);
  const done = (text?: string) => {
    if (text) setNotice(text);
    list.reload();
  };
  const nothingWaiting = !!list.data && !list.data.length && !(questions.data && questions.data.length) && !(answered.data && answered.data.some((c) => !c.continued_as));

  return (
    <>
      <PageHeader title={t("approvals")}
        lead={lang === "th"
          ? "งานที่ agent หยุดรอมนุษย์เพราะเสี่ยงจริง (ลบ ส่งออก เงิน เผยแพร่ แผนหลายขั้น): ยืนยันได้ด้วยเครื่องของคุณ (Windows Hello) หรือลายเซ็นกุญแจ approver ทุกครั้งถูกบันทึกและรันได้ครั้งเดียว ตรงตัวแปร A ในสมการ FDIA"
          : "Actions the agent paused for a person because they are really risky (delete, send out, money, publish, multi-step plans). Confirm with your device (Windows Hello) or an approver-key signature; each is recorded and runs once: the A in FDIA."}
        actions={
          <div role="group" aria-label="Filter" className="desk-mono flex overflow-hidden rounded border border-dl-rule text-[12px]">
            {(["PENDING", "ALL"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                className={`desk-focus px-3 py-1 ${view === v ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>
                {v === "PENDING" ? (lang === "th" ? "รออยู่" : "Waiting") : (lang === "th" ? "ทั้งหมด" : "All")}
              </button>
            ))}
          </div>
        } />
      <PageBody>
        <QuestionsSection list={questions} alsoReload={answered.reload} />
        <AnsweredSection list={answered} />
        <QuestionStatsPanel stats={questionStats} />
        {notice ? <p role="status" className="mb-3 rounded border border-dl-leaf/50 bg-dl-pine/20 px-4 py-3 text-sm text-dl-leaf">{notice}</p> : null}
        {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
        {nothingWaiting ? (
          <Empty title={view === "PENDING" ? (lang === "th" ? "ไม่มีอะไรรอคุณอยู่" : "Nothing is waiting for you") : (lang === "th" ? "ยังไม่มีรายการอนุมัติ" : "No approvals yet")}>
            {lang === "th"
              ? <>งานที่เสี่ยง (เช่น แก้ไฟล์ ลบ ส่งออก) จะมาหยุดรอที่นี่ ถ้ายังไม่มีผู้อนุมัติ จะไม่มีใครอนุมัติได้ ดูวิธีตั้งที่หน้า Settings หรือสร้างกุญแจด้วย <code>delentia approvals keygen</code></>
              : <>File writes and medium-risk commands pause here. No approver key configured means nothing can be approved: add a device under Settings, or create a key with <code>delentia approvals keygen</code>.</>}
          </Empty>
        ) : null}
        <div className="grid gap-5 xl:grid-cols-2">
          {list.data?.map((a) => <ActionCard key={a.approval_id} a={a} onChanged={done} devices={activeDevices} />)}
        </div>
      </PageBody>
    </>
  );
}
