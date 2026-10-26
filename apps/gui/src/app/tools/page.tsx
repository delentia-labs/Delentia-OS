"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, ErrorNote, PageBody, PageHeader, useDeskData } from "@/components/desk/ui";
import { desk, type Tool } from "@/lib/desk-api";
import { TOOL_TH } from "@/lib/tool-text";

const GATE: Record<Tool["gate"], { label: string; tone: "amber" | "fern" | "muted"; note: string; labelTh: string; noteTh: string }> = {
  approval: { label: "signed approval", tone: "amber", note: "Always pauses for a human signature, whatever the FDIA score.", labelTh: "ต้องเซ็นอนุมัติ", noteTh: "หยุดรอลายเซ็นของมนุษย์เสมอ ไม่ว่าคะแนน FDIA จะเป็นเท่าใด" },
  fdia: { label: "FDIA gate", tone: "fern", note: "Runs only when F = D^I × A reaches the threshold (0.5).", labelTh: "ด่าน FDIA", noteTh: "รันเมื่อ F = D^I × A ถึงเกณฑ์ (0.5) เท่านั้น" },
  open: { label: "open", tone: "muted", note: "Read-only or low-risk: runs without a gate, still recorded.", labelTh: "เปิด", noteTh: "อ่านอย่างเดียวหรือเสี่ยงต่ำ: รันโดยไม่มีด่าน แต่ยังถูกบันทึก" },
};

export default function ToolsPage() {
  const { t, lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
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
            <span className="sr-only">{L("Search tools", "ค้นหาเครื่องมือ")}</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={L("Search tools", "ค้นหาเครื่องมือ")}
              className="desk-focus desk-mono w-56 rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/60" />
          </label>
        } />
      <PageBody>
        {tools.error ? <ErrorNote error={tools.error} onRetry={tools.reload} /> : null}
        <div className="mb-5 flex flex-wrap gap-x-6 gap-y-2">
          {(Object.keys(GATE) as Tool["gate"][]).map((g) => (
            <p key={g} className="flex items-center gap-2 text-[12px] text-dl-muted"><Badge tone={GATE[g].tone}>{lang === "th" ? GATE[g].labelTh : GATE[g].label}</Badge>{lang === "th" ? GATE[g].noteTh : GATE[g].note}</p>
          ))}
        </div>
        <ul className="divide-y divide-dl-rule/60 rounded-md border border-dl-rule bg-dl-panel">
          {shown?.map((tool) => (
            <li key={tool.name} className="grid gap-1 px-4 py-3 md:grid-cols-[280px_1fr_auto] md:items-center md:gap-4">
              <p className="desk-mono text-[13px] text-dl-text">{tool.name}</p>
              <p className="line-clamp-2 text-[13px] text-dl-muted">{lang === "th" && TOOL_TH[tool.name] ? TOOL_TH[tool.name] : tool.description.split("\n")[0]}</p>
              <Badge tone={GATE[tool.gate].tone}>{lang === "th" ? GATE[tool.gate].labelTh : GATE[tool.gate].label}</Badge>
            </li>
          ))}
        </ul>
      </PageBody>
    </>
  );
}
