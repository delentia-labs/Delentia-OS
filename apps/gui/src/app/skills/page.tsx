"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Empty, ErrorNote, PageBody, PageHeader, Panel, fmtNum, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";


/** "read_repo_file → finish": what the skill does, before the raw record. */
function stepChain(solution: unknown): string | null {
  if (!Array.isArray(solution)) return null;
  const names = solution.map((st) => (st && typeof st === "object" && "tool_name" in st ? String((st as { tool_name?: unknown }).tool_name ?? "finish") : null))
    .filter((n): n is string => n !== null).map((n) => n.replace(/^delentia_/, ""));
  return names.length ? names.join(" → ") : null;
}


function ImportPanel({ onDone }: { onDone: () => void }) {
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [preview, setPreview] = useState<{ name: string; description: string; instructions: string; screen_findings: string[]; source: string } | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const show = async () => {
    setBusy(true);
    setMessage(null);
    try {
      setPreview((await desk.skillImportPreview(text, source || "pasted in the Desk")).preview);
    } catch (e) {
      setPreview(null);
      setMessage({ tone: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };
  const confirm = async () => {
    setBusy(true);
    try {
      const r = await desk.skillImport(text, source || "pasted in the Desk");
      setMessage({ tone: "ok", text: `${r.status}: ${r.skill_id}` });
      setPreview(null);
      setText("");
      onDone();
    } catch (e) {
      setMessage({ tone: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Import a skill (SKILL.md)" className="mb-6">
      <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">
        Skills in the open SKILL.md format (the one Hermes and other agents share). The model will read the text as guidance, so you read it first: the injection screen catches only some
        phrasings and is not the control, you are. The agent cannot import skills itself. Every tool a skill mentions still passes the same gates.
      </p>
      <textarea value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }} rows={7} maxLength={40000} placeholder={"---\nname: weekly-report\ndescription: Build the weekly status report\n---\n# Steps ..."}
        className="desk-focus desk-mono w-full rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-text placeholder:text-dl-muted/50" />
      <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="where it came from (a URL or a name)" maxLength={200}
        className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-[12px] text-dl-text" />
      <div className="mt-3"><Button onClick={show} disabled={busy || !text.trim()}>Show what would be imported</Button></div>
      {preview ? (
        <div className="mt-4 space-y-2 rounded border border-dl-amber/60 p-3">
          <p className="text-sm text-dl-text">{preview.name}: {preview.description}</p>
          <pre className="desk-mono max-h-64 overflow-auto whitespace-pre-wrap rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-muted">{preview.instructions}</pre>
          {preview.screen_findings.length ? <p className="text-[13px] text-dl-rust">The injection screen found {preview.screen_findings.join(", ")}: the import will be refused.</p> : <p className="text-[12px] text-dl-muted">The injection screen found nothing (which does not mean there is nothing).</p>}
          <Button tone="amber" onClick={confirm} disabled={busy}>I have read it and trust it: import</Button>
        </div>
      ) : null}
      {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
    </Panel>
  );
}

export default function SkillsPage() {
  const { t, lang } = useLang();
  const skills = useDeskData(() => desk.skills(), []);
  return (
    <>
      <PageHeader title={t("skills")}
        lead={lang === "th"
          ? "สกิลที่ agent เรียนรู้เอง เก็บเฉพาะจาก episode ที่ผ่าน VERIFY และผ่านเกณฑ์การเติบโตของ MEE เท่านั้น และถูกดึงเข้า prompt อัตโนมัติเมื่อเจอโจทย์ที่คล้ายกัน"
          : "Skills the agent learned by itself: kept only from episodes that passed VERIFY and the MEE growth gate, and recalled into the prompt when a similar goal arrives."} />
      <PageBody>
        <ImportPanel onDone={skills.reload} />
        {skills.error ? <ErrorNote error={skills.error} onRetry={skills.reload} /> : null}
        {skills.data && !skills.data.skills.length ? (
          <Empty title="No skills learned yet">A skill is kept when a verified episode shows real growth. Run the same kind of goal a few times in Chat and check Experiments.</Empty>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {skills.data?.skills.map((s) => (
            <Panel key={s.id} title={s.problem_statement}
              aside={s.archived ? <Badge tone="rust">archived</Badge> : s.governance_violation ? <Badge tone="rust">violation</Badge> : s.bundled ? <Badge tone="leaf">bundled starter</Badge> : s.imported ? <Badge tone="amber">imported</Badge> : <Badge tone="leaf">growth {fmtNum(s.growth_ratio)}</Badge>}>
              {stepChain(s.solution) ? <p className="desk-mono mb-2 text-[12px] text-dl-text">{stepChain(s.solution)}</p> : null}
              <pre className="desk-mono max-h-40 overflow-auto whitespace-pre-wrap rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-muted">
                {typeof s.solution === "string" ? s.solution : JSON.stringify(s.solution, null, 2)}
              </pre>
              <p className="desk-mono mt-2 text-[11px] text-dl-muted">
                {s.bundled ? "written by people and shipped with the runtime, not learned" : s.imported ? "somebody else's SKILL.md, imported by a person; third-party text" : <>MEE g {fmtNum(s.g_before)} → {fmtNum(s.g_after)} · Δ {fmtNum(s.delta)}</>} · {fmtTime(s.created_at)}
              </p>
              <p className="desk-mono mt-1 text-[11px] text-dl-muted">
                reuse: {s.successes} worked / {s.failures} did not of {s.uses} · reliability {fmtNum(s.reliability)} · solved {s.reinforced}×
              </p>
            </Panel>
          ))}
        </div>
      </PageBody>
    </>
  );
}
