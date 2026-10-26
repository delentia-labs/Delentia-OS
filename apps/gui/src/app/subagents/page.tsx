"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { describeReason } from "@/lib/reason-text";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

export default function SubagentsPage() {
  const { t, lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
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
      setMessage({ tone: ok === r.runs.length ? "ok" : "err", text: lang === "th" ? `${ok} จาก ${r.runs.length} subagent จบด้วยคำตอบที่ลงลายเซ็นและตรวจผ่าน` : `${ok} of ${r.runs.length} subagents finished with a verified signed answer.` });
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
          <Panel title={L("Start subagents", "เริ่ม subagent")}>
            <label className="block">
              <span className="text-[13px] text-dl-muted">{L("One goal per line (at most 3)", "หนึ่งเป้าหมายต่อบรรทัด (ไม่เกิน 3)")}</span>
              <textarea value={goals} onChange={(e) => setGoals(e.target.value)} rows={5} disabled={busy}
                placeholder={lang === "th" ? "สรุปบันทึกการออกรุ่นของ v2\nค้นหาคำว่า FDIA ในที่เก็บโค้ด" : "Summarise the release notes for v2\nSearch the repository for the word FDIA"}
                className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text placeholder:text-dl-muted/50" />
            </label>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={start} disabled={busy || list.length === 0}>{busy ? L("Running…", "กำลังทำงาน…") : lang === "th" ? `เริ่ม ${list.length || ""} subagent` : `Start ${list.length || ""} subagent${list.length === 1 ? "" : "s"}`}</Button>
              <span className="text-[12px] text-dl-muted">{L("Each runs the governed loop; risky actions still wait for a signed approval.", "แต่ละตัวรันวงจรที่มีการกำกับ การกระทำเสี่ยงยังต้องรอการอนุมัติที่ลงลายเซ็น")}</span>
            </div>
            {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
            <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
              {L("What the signatures prove: the answer is unaltered and belongs to the request it names. They do not make either key trusted; key pinning comes with the notary (", "ลายเซ็นพิสูจน์อะไร: คำตอบไม่ถูกแก้และเป็นของคำขอที่ระบุชื่อไว้ แต่ไม่ได้ทำให้กุญแจฝั่งใดน่าเชื่อถือ การปักหมุดกุญแจมากับ notary (")}<Code>delentia notary serve</Code>{L(").", ")")}
            </p>
          </Panel>

          <div className="min-w-0 space-y-4">
            {runs.error ? <ErrorNote error={runs.error} onRetry={runs.reload} /> : null}
            {runs.data && !runs.data.runs.length ? <Empty title={L("No subagent runs yet", "ยังไม่มีการรัน subagent")}>{L("Start one on the left, or call ", "เริ่มที่ฝั่งซ้าย หรือเรียก ")}<Code>delentia_delegate</Code>{L(" from an agent.", " จากเอเจนต์")}</Empty> : null}
            {runs.data?.runs.map((r) => (
              <Panel key={r.id} title={r.goal}
                aside={r.timed_out ? <Badge tone="rust">{L("timed out", "หมดเวลา")}</Badge> : r.jitna?.response_verified ? <Badge tone="leaf">{L("verified", "ตรวจผ่าน")}</Badge> : <Badge tone="rust">{L("not verified", "ตรวจไม่ผ่าน")}</Badge>}>
                {r.final_answer ? <p className="whitespace-pre-wrap break-words text-sm text-dl-text">{r.final_answer}</p> : null}
                {r.error ? <p className="text-sm text-dl-rust">{r.error}</p> : null}
                <div className="mt-3">
                  <Row label={L("Agent", "เอเจนต์")}>{r.agent_id}</Row>
                  <Row label={L("Ended with", "จบด้วย")}>{r.stopped_reason ? describeReason(r.stopped_reason, lang).label : "-"}</Row>
                  <Row label={L("Steps", "ขั้นตอน")}>{r.iterations ?? "-"}</Row>
                  <Row label={L("Request packet", "แพ็กเก็ตคำขอ")}>{r.jitna?.request_packet_id ? `${r.jitna.request_packet_id.slice(0, 13)}…` : L("unsigned (older run)", "ไม่มีลายเซ็น (การรันรุ่นเก่า)")}</Row>
                  <Row label={L("Request hash", "แฮชของคำขอ")}>{r.jitna?.request_hash ? `${r.jitna.request_hash.slice(0, 16)}…` : "-"}</Row>
                  {r.jitna && !r.jitna.response_verified ? <Row label={L("Why not verified", "ทำไมตรวจไม่ผ่าน")}>{r.jitna.reason ?? "-"}</Row> : null}
                  <Row label={L("When", "เมื่อ")}>{fmtTime(r.created_at)}</Row>
                </div>
              </Panel>
            ))}
          </div>
        </div>
      </PageBody>
    </>
  );
}
