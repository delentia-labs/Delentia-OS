"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { AnsweredSection, QuestionStatsPanel, QuestionsSection } from "@/components/desk/Questions";
import { desk, type PendingAction } from "@/lib/desk-api";
import { parseSignedDecision } from "@/lib/signed-decision";

function statusTone(s: string) {
  if (s === "PENDING") return "amber" as const;
  if (s === "APPROVED" || s === "EXECUTED") return "leaf" as const;
  if (s === "REJECTED") return "rust" as const;
  return "muted" as const;
}

function ActionCard({ a, onChanged }: { a: PendingAction; onChanged: () => void }) {
  const { lang } = useLang();
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

  const run = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await desk.resume(a.approval_id);
      setMessage({ tone: "ok", text: "Ran the approved action once and continued the episode. See Sessions." });
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
      <pre className="desk-mono mt-3 max-h-48 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] text-dl-muted">
        {JSON.stringify(a.tool_args, null, 2)}
      </pre>
      <div className="mt-3">
        <Row label="Why it waits">{a.reason}</Row>
        {a.required_signatures && a.required_signatures > 1 ? <Row label="Signatures">{a.signatures_collected ?? 0} of {a.required_signatures} (distinct keys)</Row> : null}
        {a.approver_roles?.length ? <Row label="Roles asked for">{a.approver_roles.join(", ")}</Row> : null}
        {a.policy_rule ? <Row label="Owner policy rule">{a.policy_rule}</Row> : null}
        <Row label="Action digest (SHA-256)">{`${a.action_sha256.slice(0, 20)}…`}</Row>
        <Row label="Requested">{fmtTime(a.created_at)}</Row>
        {a.approver_public_key ? <Row label="Signed by key">{`${a.approver_public_key.slice(0, 16)}…`}</Row> : null}
      </div>

      {a.status === "PENDING" ? (
        <div className="mt-4 space-y-2">
          {a.required_signatures && a.required_signatures > 1 ? (
            <p className="text-[13px] leading-relaxed text-dl-amber">
              This action needs {a.required_signatures} signatures from distinct keys ({a.signatures_collected ?? 0} collected). Each signer repeats the steps below; it runs only after the last one.
            </p>
          ) : null}
          <p className="text-[13px] leading-relaxed text-dl-muted">
            Sign on the device that holds your approver key (it never needs to be on this machine), then paste the printed JSON:
          </p>
          <Code>{signCmd}</Code>
          <label className="block">
            <span className="sr-only">Signed decision JSON</span>
            <textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={4} placeholder='{"public_key_hex": "…", "signature_hex": "…", "decision": "APPROVED"}'
              className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-text placeholder:text-dl-muted/50" />
          </label>
          <Button onClick={submit} disabled={busy || !pasted.trim()}>Submit signed decision</Button>
        </div>
      ) : null}
      {a.status === "APPROVED" ? (
        <div className="mt-4">
          <Button tone="amber" onClick={run} disabled={busy}>{busy ? "Running…" : "Run the approved action"}</Button>
          <p className="mt-2 text-[12px] text-dl-muted">Runs exactly once; the signature is checked again first.</p>
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
  const questions = useDeskData(() => desk.clarifications("PENDING"), [], 15000);
  const questionStats = useDeskData(() => desk.rct7Stats(14), [], 60000);
  const answered = useDeskData(() => desk.clarifications("ANSWERED"), [], 15000);
  const nothingWaiting = !!list.data && !list.data.length && !(questions.data && questions.data.length) && !(answered.data && answered.data.some((c) => !c.continued_as));

  return (
    <>
      <PageHeader title={t("approvals")}
        lead={lang === "th"
          ? "action ที่ agent หยุดรอมนุษย์ (เช่น การเขียนไฟล์): อนุมัติได้ด้วยลายเซ็น Ed25519 ของคุณเท่านั้น และรันได้ครั้งเดียว ตรงตัวแปร A ในสมการ FDIA"
          : "Actions the agent paused for a human (file writes, for example). Only your Ed25519 signature approves them, and each runs once: the A in FDIA."}
        actions={
          <div role="group" aria-label="Filter" className="desk-mono flex overflow-hidden rounded border border-dl-rule text-[12px]">
            {(["PENDING", "ALL"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                className={`desk-focus px-3 py-1 ${view === v ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>
                {v === "PENDING" ? "Waiting" : "All"}
              </button>
            ))}
          </div>
        } />
      <PageBody>
        <QuestionsSection list={questions} alsoReload={answered.reload} />
        <AnsweredSection list={answered} />
        <QuestionStatsPanel stats={questionStats} />
        {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
        {nothingWaiting ? (
          <Empty title={view === "PENDING" ? "Nothing is waiting for you" : "No approvals yet"}>
            File writes and medium-risk commands pause here. No approver key configured means nothing can be approved: create one with <code>delentia approvals keygen</code>.
          </Empty>
        ) : null}
        <div className="grid gap-5 xl:grid-cols-2">
          {list.data?.map((a) => <ActionCard key={a.approval_id} a={a} onChanged={list.reload} />)}
        </div>
      </PageBody>
    </>
  );
}
