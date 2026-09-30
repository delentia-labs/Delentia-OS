"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, ErrorNote, PageBody, PageHeader, useDeskData } from "@/components/desk/ui";
import { desk, type Tool } from "@/lib/desk-api";

const GATE: Record<Tool["gate"], { label: string; tone: "amber" | "fern" | "muted"; note: string }> = {
  approval: { label: "signed approval", tone: "amber", note: "Always pauses for a human signature, whatever the FDIA score." },
  fdia: { label: "FDIA gate", tone: "fern", note: "Runs only when F = D^I × A reaches the threshold (0.5)." },
  open: { label: "open", tone: "muted", note: "Read-only or low-risk: runs without a gate, still recorded." },
};

export default function ToolsPage() {
  const { t, lang } = useLang();
  const tools = useDeskData(() => desk.tools(), []);
  const [q, setQ] = useState("");
  const shown = tools.data?.tools.filter((x) => !q || x.name.includes(q.toLowerCase()) || x.description.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader title={t("tools")}
        lead={lang === "th"
          ? "เครื่องมือทั้งหมดที่ agent ใช้ได้ พร้อมบอกว่าแต่ละตัวต้องผ่านด่านใดก่อนรัน"
          : "Every tool the agent can call, and the gate each one passes before it runs."}
        actions={
          <label className="block">
            <span className="sr-only">Search tools</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tools"
              className="desk-focus desk-mono w-56 rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/60" />
          </label>
        } />
      <PageBody>
        {tools.error ? <ErrorNote error={tools.error} onRetry={tools.reload} /> : null}
        <div className="mb-5 flex flex-wrap gap-x-6 gap-y-2">
          {(Object.keys(GATE) as Tool["gate"][]).map((g) => (
            <p key={g} className="flex items-center gap-2 text-[12px] text-dl-muted"><Badge tone={GATE[g].tone}>{GATE[g].label}</Badge>{GATE[g].note}</p>
          ))}
        </div>
        <ul className="divide-y divide-dl-rule/60 rounded-md border border-dl-rule bg-dl-panel">
          {shown?.map((tool) => (
            <li key={tool.name} className="grid gap-1 px-4 py-3 md:grid-cols-[280px_1fr_auto] md:items-center md:gap-4">
              <p className="desk-mono text-[13px] text-dl-text">{tool.name}</p>
              <p className="line-clamp-2 text-[13px] text-dl-muted">{tool.description.split("\n")[0]}</p>
              <Badge tone={GATE[tool.gate].tone}>{GATE[tool.gate].label}</Badge>
            </li>
          ))}
        </ul>
      </PageBody>
    </>
  );
}
