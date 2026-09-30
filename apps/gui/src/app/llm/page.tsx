"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type ModelInfo } from "@/lib/desk-api";

function price(m: ModelInfo) {
  const p = m.prompt_price_per_mtok ?? 0;
  const c = m.completion_price_per_mtok ?? 0;
  return p === 0 && c === 0 ? "free" : `$${p.toFixed(2)} / $${c.toFixed(2)} per M tokens`;
}

export default function ModelsPage() {
  const { t, lang } = useLang();
  const [catalog, setCatalog] = useState<"openrouter" | "ollama">("ollama");
  const [freeOnly, setFreeOnly] = useState(true);
  const current = useDeskData(() => desk.models(), []);
  const list = useDeskData(() => desk.models(catalog, catalog === "openrouter" && freeOnly), [catalog, freeOnly]);
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const choose = async (model: string) => {
    setSaving(model);
    setMessage(null);
    try {
      const r = await desk.setModel(catalog, model);
      setMessage(`Saved ${r.selection.model} (${r.selection.provider}) as the default in ${r.saved}.`);
      current.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const sel = current.data?.selection;
  return (
    <>
      <PageHeader title={t("models")}
        lead={lang === "th"
          ? "เลือกโมเดลที่ขับ agent loop โมเดลต้องรองรับ JSON mode จึงจะอยู่ในรายการ ค่าที่ตั้งจาก environment (DELENTIA_LLM_*) มีลำดับสูงกว่าค่าที่บันทึกที่นี่"
          : "Choose the model that drives the agent loop. Only models with JSON mode are listed. Environment settings (DELENTIA_LLM_*) outrank what is saved here."} />
      <PageBody>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <div className="space-y-6">
            <Panel title="In use now">
              {current.error ? <ErrorNote error={current.error} /> : sel ? (
                <>
                  <Row label="Model">{sel.model}</Row>
                  <Row label="Provider">{sel.provider}</Row>
                  <Row label="Chosen by">{sel.model_source}</Row>
                  <Row label="OpenRouter key in the API's environment">{current.data?.openrouter_key_present ? "yes" : "no"}</Row>
                </>
              ) : null}
            </Panel>
            <Panel title="Keys stay out of files">
              <p className="text-[13px] leading-relaxed text-dl-muted">
                The OpenRouter key is read from the environment of the process that runs <Code>delentia serve</Code>. It is never written to the model config, and this page cannot set it.
              </p>
            </Panel>
            <Panel title="Check a model before relying on it">
              <p className="text-[13px] leading-relaxed text-dl-muted">
                Run the tool-selection acceptance test with the chosen model (from the Delentia-OS folder):
              </p>
              <div className="mt-2"><Code>python scripts/k1_5_formal_acceptance.py</Code></div>
            </Panel>
          </div>

          <Panel title="Catalog" aside={
            <div className="flex items-center gap-2">
              <div role="group" aria-label="Provider" className="desk-mono flex overflow-hidden rounded border border-dl-rule text-[12px]">
                {(["ollama", "openrouter"] as const).map((c) => (
                  <button key={c} onClick={() => setCatalog(c)} aria-pressed={catalog === c}
                    className={`desk-focus px-3 py-1 ${catalog === c ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>{c}</button>
                ))}
              </div>
              {catalog === "openrouter" ? (
                <label className="desk-mono flex items-center gap-1.5 text-[12px] text-dl-muted">
                  <input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} className="accent-[var(--dl-leaf)]" /> free only
                </label>
              ) : null}
            </div>
          }>
            {message ? <p role="status" className="mb-3 text-[13px] text-dl-leaf">{message}</p> : null}
            {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
            {list.loading && !list.data ? <p className="desk-mono text-sm text-dl-muted">Loading the catalog…</p> : null}
            {list.data?.catalog && !list.data.catalog.length ? <Empty title="No models found" /> : null}
            <ul className="divide-y divide-dl-rule/60">
              {list.data?.catalog?.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <p className="desk-mono truncate text-[13px] text-dl-text">{m.id}</p>
                    <p className="desk-mono text-[11px] text-dl-muted">
                      {price(m)}{m.context_length ? ` · ${m.context_length.toLocaleString()} ctx` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {m.supports_tools ? <Badge tone="fern">tools</Badge> : null}
                    {sel && sel.model === m.id ? <Badge tone="leaf">in use</Badge> : (
                      <Button onClick={() => choose(m.id)} disabled={saving !== null}>{saving === m.id ? "Saving…" : "Use this model"}</Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
