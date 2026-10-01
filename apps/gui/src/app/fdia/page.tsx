"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { ErrorNote, PageBody, PageHeader, useDeskData } from "@/components/desk/ui";
import { Learn, type Scenario } from "@/components/desk/fdia/Learn";
import { EMPTY_POLICY, Policy, type PolicyMessage } from "@/components/desk/fdia/Policy";
import { Try } from "@/components/desk/fdia/Try";
import { desk, type FdiaPolicy, type FdiaState } from "@/lib/desk-api";

type Tab = "learn" | "policy" | "try";

function Workspace({ state, reload, tab, setTab, message, setMessage }: {
  state: FdiaState; reload: () => void; tab: Tab; setTab: (t: Tab) => void; message: PolicyMessage; setMessage: (m: PolicyMessage) => void;
}) {
  const { lang } = useLang();
  const T = (en: string, th: string) => (lang === "th" ? th : en);
  const saved: FdiaPolicy = state.policy ?? EMPTY_POLICY;
  const [draft, setDraft] = useState<FdiaPolicy>(saved);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [tryKey, setTryKey] = useState(0);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);

  const tryIt = (s: Scenario) => { setScenario(s); setTryKey((k) => k + 1); setTab("try"); };
  const tabs: { id: Tab; label: string }[] = [
    { id: "learn", label: T("Understand", "เข้าใจสมการ") },
    { id: "policy", label: T("Set the rules for A", "ตั้งกฎของ A") },
    { id: "try", label: T("Try a call", "ทดลองเรียก") },
  ];

  return (
    <>
      <div role="tablist" aria-label="FDIA" className="mb-6 flex flex-wrap gap-2 border-b border-dl-rule pb-3">
        {tabs.map((x) => (
          <button key={x.id} role="tab" aria-selected={tab === x.id} onClick={() => setTab(x.id)}
            className={`desk-focus desk-mono rounded border px-3 py-1.5 text-[13px] ${tab === x.id ? "border-dl-fern bg-dl-pine/60 text-dl-text" : "border-dl-rule text-dl-muted hover:text-dl-text"}`}>
            {x.label}{x.id === "policy" && dirty ? " •" : ""}
          </button>
        ))}
      </div>
      {tab === "learn" ? <Learn T={T} onTry={tryIt} /> : null}
      {tab === "policy" ? <Policy state={state} draft={draft} setDraft={setDraft} dirty={dirty} reload={reload} message={message} setMessage={setMessage} T={T} /> : null}
      {tab === "try" ? <Try key={tryKey} state={state} draft={draft} dirty={dirty} initial={scenario} T={T} /> : null}
    </>
  );
}

export default function FdiaPage() {
  const { lang } = useLang();
  const fdia = useDeskData(() => desk.fdia(), []);
  // The tab lives here, not in Workspace: saving changes the policy digest, which remounts Workspace to reset the draft.
  const [tab, setTab] = useState<Tab>("learn");
  const [message, setMessage] = useState<PolicyMessage>(null);
  return (
    <>
      <PageHeader title="FDIA · F = D^I × A"
        lead={lang === "th"
          ? "สมการที่ตัดสินว่า agent ทำอะไรได้ อ่านว่าแต่ละตัวอักษรหมายถึงอะไรใน Delentia แล้วกำหนดกฎของ A ของคุณเอง: อะไรรันได้เลย อะไรต้องมีมนุษย์เซ็น ใครเซ็นได้ ต้องกี่คน และต้องมีคณะลูกขุนก่อนหรือไม่"
          : "The equation that decides what an agent may do. Learn what each letter means in Delentia, then write the rules for A yourself: what runs freely, what needs a human signature, who may sign, how many, and whether a jury must agree first."} />
      <PageBody>
        {fdia.error ? <ErrorNote error={fdia.error} onRetry={fdia.reload} /> : null}
        {fdia.data ? <Workspace key={fdia.data.digest ?? "none"} state={fdia.data} reload={fdia.reload} tab={tab} setTab={setTab} message={message} setMessage={setMessage} /> : null}
      </PageBody>
    </>
  );
}
