"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function SubagentsPage() {
  const { t, lang } = useLang();
  const runs = useDeskData(() => desk.subagents(), [], 20000);
  const [goals, setGoals] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const list = goals.split("\n").map((g) => g.trim()).filter(Boolean).slice(0, 3);

  const start = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await desk.runSubagents(list);
      const ok = r.runs.filter((x) => x.success).length;
      setMessage({ tone: ok === r.runs.length ? "ok" : "err", text: `${ok} of ${r.runs.length} subagents finished with a verified signed answer.` });
      setGoals("");
      runs.reload();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title={t("subagents")}
        lead={lang === "th"
          ? "งานที่แตกให้ subagent แยก process: คำสั่งถูกส่งเป็นแพ็กเก็ต JITNA ที่ลงลายเซ็น Ed25519 คำตอบส่งกลับเป็นแพ็กเก็ตที่ลงลายเซ็นและอ้างถึงคำสั่งเดิมด้วย hash และแต่ละตัวทำงานใน git worktree ของตัวเอง"
          : "Work split across separate subagent processes: each request is a signed JITNA packet, each answer a signed packet naming the exact request by hash, and each subagent works in its own git worktree."} />
      <PageBody>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
          <Panel title="Start subagents">
            <label className="block">
              <span className="text-[13px] text-dl-muted">One goal per line (at most 3)</span>
              <textarea value={goals} onChange={(e) => setGoals(e.target.value)} rows={5} disabled={busy}
                placeholder={"Summarise the release notes for v2\nSearch the repository for the word FDIA"}
                className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text placeholder:text-dl-muted/50" />
            </label>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={start} disabled={busy || list.length === 0}>{busy ? "Running…" : `Start ${list.length || ""} subagent${list.length === 1 ? "" : "s"}`}</Button>
              <span className="text-[12px] text-dl-muted">Each runs the governed loop; risky actions still wait for a signed approval.</span>
            </div>
            {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
            <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
              What the signatures prove: the answer is unaltered and belongs to the request it names. They do not make either key trusted;
              key pinning comes with the notary (<Code>delentia notary serve</Code>).
            </p>
          </Panel>

          <div className="min-w-0 space-y-4">
            {runs.error ? <ErrorNote error={runs.error} onRetry={runs.reload} /> : null}
            {runs.data && !runs.data.runs.length ? <Empty title="No subagent runs yet">Start one on the left, or call <Code>delentia_delegate</Code> from an agent.</Empty> : null}
            {runs.data?.runs.map((r) => (
              <Panel key={r.id} title={r.goal}
                aside={r.timed_out ? <Badge tone="rust">timed out</Badge> : r.jitna?.response_verified ? <Badge tone="leaf">verified</Badge> : <Badge tone="rust">not verified</Badge>}>
                {r.final_answer ? <p className="whitespace-pre-wrap break-words text-sm text-dl-text">{r.final_answer}</p> : null}
                {r.error ? <p className="text-sm text-dl-rust">{r.error}</p> : null}
                <div className="mt-3">
                  <Row label="Agent">{r.agent_id}</Row>
                  <Row label="Ended with">{r.stopped_reason ?? "-"}</Row>
                  <Row label="Steps">{r.iterations ?? "-"}</Row>
                  <Row label="Request packet">{r.jitna?.request_packet_id ? `${r.jitna.request_packet_id.slice(0, 13)}…` : "unsigned (older run)"}</Row>
                  <Row label="Request hash">{r.jitna?.request_hash ? `${r.jitna.request_hash.slice(0, 16)}…` : "-"}</Row>
                  {r.jitna && !r.jitna.response_verified ? <Row label="Why not verified">{r.jitna.reason ?? "-"}</Row> : null}
                  <Row label="When">{fmtTime(r.created_at)}</Row>
                </div>
              </Panel>
            ))}
          </div>
        </div>
      </PageBody>
    </>
  );
}
