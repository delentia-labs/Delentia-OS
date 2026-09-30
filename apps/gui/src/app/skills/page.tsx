"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Empty, ErrorNote, PageBody, PageHeader, Panel, fmtNum, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

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
        {skills.error ? <ErrorNote error={skills.error} onRetry={skills.reload} /> : null}
        {skills.data && !skills.data.skills.length ? (
          <Empty title="No skills learned yet">A skill is kept when a verified episode shows real growth. Run the same kind of goal a few times in Chat and check Experiments.</Empty>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {skills.data?.skills.map((s) => (
            <Panel key={s.id} title={s.problem_statement}
              aside={s.archived ? <Badge tone="rust">archived</Badge> : s.governance_violation ? <Badge tone="rust">violation</Badge> : <Badge tone="leaf">growth {fmtNum(s.growth_ratio)}</Badge>}>
              <pre className="desk-mono max-h-40 overflow-auto whitespace-pre-wrap rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-muted">
                {typeof s.solution === "string" ? s.solution : JSON.stringify(s.solution, null, 2)}
              </pre>
              <p className="desk-mono mt-2 text-[11px] text-dl-muted">
                MEE g {fmtNum(s.g_before)} → {fmtNum(s.g_after)} · Δ {fmtNum(s.delta)} · {fmtTime(s.created_at)}
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
