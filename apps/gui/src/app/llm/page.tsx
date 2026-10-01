"use client";

import { useMemo, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type EndpointDecl, type ModelInfo, type ModelSetup, type PolicyVerdict, type ProbeResult, type ProviderPreset } from "@/lib/desk-api";

const OTHER = "__other__";
type Mode = "ollama" | "openrouter" | "endpoint";

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text placeholder:text-dl-muted/50 disabled:opacity-50";

function price(m: ModelInfo) {
  const p = m.prompt_price_per_mtok ?? 0;
  const c = m.completion_price_per_mtok ?? 0;
  return p === 0 && c === 0 ? "free" : `$${p.toFixed(2)} / $${c.toFixed(2)} per M tokens`;
}

function Verdict({ v, lang }: { v: PolicyVerdict | null | undefined; lang: string }) {
  if (!v) return null;
  if (!v.enforced) {
    return (
      <p className="rounded border border-dl-amber/50 bg-dl-amber/10 px-3 py-2 text-[13px] leading-relaxed text-dl-text">
        {lang === "th"
          ? "ยังไม่ได้ตั้งนโยบายตำแหน่งข้อมูล จึงไม่มีอะไรจำกัดว่า prompt จะถูกส่งไปที่ใด "
          : "No data-location policy is set, so nothing restricts where prompts go. "}
        <a className="underline" href="/sovereignty">{lang === "th" ? "ตั้งที่หน้า อธิปไตยข้อมูล" : "Set one on the Sovereignty page"}</a>
      </p>
    );
  }
  return (
    <p className={`rounded border px-3 py-2 text-[13px] leading-relaxed ${v.allowed ? "border-dl-leaf/50 text-dl-leaf" : "border-dl-rust/60 text-dl-rust"}`}>
      {v.allowed ? (lang === "th" ? "นโยบายอนุญาตปลายทางนี้: " : "The policy allows this endpoint: ") : (lang === "th" ? "นโยบายจะบล็อกปลายทางนี้: " : "The policy would block this endpoint: ")}
      <span className="text-dl-muted">{v.reason}</span>
    </p>
  );
}

// ---- Ollama / OpenRouter: pick from the provider's own catalog --------------------------------------------------

function CatalogPanel({ provider, current, onSaved, lang }: { provider: "ollama" | "openrouter"; current: ModelSetup | null; onSaved: () => void; lang: string }) {
  const [freeOnly, setFreeOnly] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "leaf" | "rust"; text: string } | null>(null);
  const list = useDeskData(() => desk.models(provider, provider === "openrouter" && freeOnly), [provider, freeOnly]);
  const sel = current?.selection;

  const choose = async (model: string) => {
    setSaving(model);
    setMessage(null);
    try {
      const r = await desk.saveModel({ provider, model, api_key: provider === "openrouter" && apiKey ? apiKey : undefined });
      setApiKey("");
      setMessage({ tone: "leaf", text: `Saved ${r.selection.model} (${r.selection.provider}).${r.key_note ? " " + r.key_note : ""}` });
      onSaved();
    } catch (err) {
      setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(null);
    }
  };

  return (
    <Panel title={provider === "ollama" ? (lang === "th" ? "โมเดลบนเครื่องนี้ (Ollama)" : "Models on this machine (Ollama)") : "OpenRouter"}
      aside={provider === "openrouter" ? (
        <label className="desk-mono flex items-center gap-1.5 text-[12px] text-dl-muted">
          <input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} className="accent-[var(--dl-leaf)]" /> free only
        </label>
      ) : undefined}>
      {provider === "openrouter" ? (
        <label className="mb-4 block">
          <span className="text-[13px] text-dl-muted">
            {lang === "th" ? "API key (ไม่จำเป็นถ้าตั้ง " : "API key (optional if "}<Code>OPENROUTER_API_KEY</Code>{lang === "th" ? " ไว้แล้ว)" : " is already set)"}
          </span>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" autoComplete="new-password" spellCheck={false}
            placeholder={current?.openrouter_key_present ? "a key is already present in the server" : "sk-or-…"} className={field} />
          <span className="mt-1 block text-[12px] text-dl-muted">
            {lang === "th" ? "เก็บในหน่วยความจำของเซิร์ฟเวอร์จนกว่าจะรีสตาร์ท ไม่เขียนลงไฟล์" : "Kept in the server's memory until it restarts. Never written to a file."}
          </span>
        </label>
      ) : null}
      {message ? <p role="status" className={`mb-3 text-[13px] ${message.tone === "leaf" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
      {list.loading && !list.data ? <p className="desk-mono text-sm text-dl-muted">Loading the catalog…</p> : null}
      {list.data?.catalog && !list.data.catalog.length ? <Empty title="No models found" /> : null}
      <ul className="divide-y divide-dl-rule/60">
        {list.data?.catalog?.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="desk-mono truncate text-[13px] text-dl-text">{m.id}</p>
              <p className="desk-mono text-[11px] text-dl-muted">{price(m)}{m.context_length ? ` · ${m.context_length.toLocaleString()} ctx` : ""}</p>
            </div>
            <div className="flex items-center gap-2">
              {m.supports_tools ? <Badge tone="fern">tools</Badge> : null}
              {sel && sel.model === m.id && sel.provider === provider ? <Badge tone="leaf">in use</Badge> : (
                <Button onClick={() => choose(m.id)} disabled={saving !== null}>{saving === m.id ? "Saving…" : "Use this model"}</Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// ---- your own AI: country -> provider -> model, "Other" at every step -------------------------------------------

function EndpointPanel({ setup, onSaved, lang }: { setup: ModelSetup; onSaved: () => void; lang: string }) {
  const { presets } = setup;
  const saved = setup.selection.provider === "openai-compat" ? setup.endpoint : null;
  const [country, setCountry] = useState<string>(OTHER);
  const [providerId, setProviderId] = useState<string>(OTHER);
  const [baseUrl, setBaseUrl] = useState(saved?.base_url ?? "");
  const [modelPick, setModelPick] = useState<string>(OTHER);
  const [modelText, setModelText] = useState(setup.selection.provider === "openai-compat" ? setup.selection.model : "");
  const [location, setLocation] = useState<EndpointDecl["kind"]>(saved?.kind ?? "cross_border");
  const [region, setRegion] = useState(saved?.region ?? "");
  const [operator, setOperator] = useState(saved?.operator ?? "");
  const [keyEnv, setKeyEnv] = useState(saved?.credential_env ?? "");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [profile, setProfile] = useState("");
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [message, setMessage] = useState<{ tone: "leaf" | "rust"; text: string } | null>(null);

  const providers = useMemo(() => presets.providers.filter((p) => p.country === country), [presets, country]);
  const preset: ProviderPreset | undefined = presets.providers.find((p) => p.id === providerId);
  const modelChoices = probe?.models?.length ? probe.models : preset?.models ?? [];
  // A pick that is no longer on offer (the provider changed, or the test returned a different list) counts as "Other".
  const pick = modelPick === OTHER || modelChoices.includes(modelPick) ? modelPick : OTHER;
  const model = pick === OTHER ? modelText.trim() : pick;

  // Choosing a provider fills in what the preset knows; every field stays editable afterwards.
  const pickProvider = (id: string) => {
    setProviderId(id);
    const next = presets.providers.find((p) => p.id === id);
    if (!next) { setModelPick(OTHER); setProbe(null); return; }
    setBaseUrl(next.base_url);
    setKeyEnv(next.credential_env);
    setOperator(next.name);
    setLocation(next.suggested_data_location);
    setRegion("");
    setProbe(null);
    setModelPick(next.models[0] ?? OTHER);
    setModelText("");
  };

  const decl = (): EndpointDecl => ({ base_url: baseUrl.trim(), kind: location, region: location === "in_region" ? region.trim().toUpperCase() : "",
    operator: operator.trim(), credential_env: keyEnv.trim() || undefined });

  const test = async () => {
    setBusy("test"); setMessage(null); setProbe(null);
    try {
      const r = await desk.testEndpoint(decl(), apiKey || undefined);
      setProbe(r);
      if (r.models.length && !r.models.includes(modelPick) && !(modelPick === OTHER && modelText.trim())) setModelPick(r.models[0]);
    } catch (err) {
      setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) });
    } finally { setBusy(null); }
  };

  const save = async () => {
    setBusy("save"); setMessage(null);
    try {
      const r = await desk.saveModel({ provider: "openai-compat", model, endpoint: decl(), profile: profile || undefined, api_key: apiKey || undefined });
      setApiKey("");
      setMessage({ tone: "leaf", text: `Saved ${model} at ${baseUrl.trim()}${profile ? ` for profile ${profile}` : " as the default"}.${r.key_note ? " " + r.key_note : ""}` });
      onSaved();
    } catch (err) {
      setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) });
    } finally { setBusy(null); }
  };

  const T = (en: string, th: string) => (lang === "th" ? th : en);
  const canSave = baseUrl.trim() !== "" && model !== "" && (location !== "in_region" || region.trim().length === 2);

  return (
    <Panel title={T("Plug in your own AI", "เสียบ AI ของคุณเอง")}>
      <p className="mb-4 text-[13px] leading-relaxed text-dl-muted">
        {T("Any server that speaks the OpenAI chat protocol: a national provider, vLLM, llama.cpp, LM Studio, or your organisation's gateway. Pick a starting point or choose Other and type it. Nothing here is saved until you press Save.",
           "เซิร์ฟเวอร์ใดก็ได้ที่ใช้โปรโตคอลแชทแบบ OpenAI: ผู้ให้บริการของประเทศ, vLLM, llama.cpp, LM Studio หรือ gateway ขององค์กร เลือกจุดเริ่มต้นหรือเลือก Other แล้วพิมพ์เอง ยังไม่มีอะไรถูกบันทึกจนกว่าจะกด Save")}
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("1 · Country of the provider", "1 · ประเทศของผู้ให้บริการ")}</span>
          <select value={country} onChange={(e) => { setCountry(e.target.value); setProviderId(OTHER); }} className={field} aria-label="Country">
            {presets.countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            <option value={OTHER}>{T("Other / not listed", "อื่นๆ / ไม่มีในรายการ")}</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("2 · Provider", "2 · ผู้ให้บริการ")}</span>
          <select value={providerId} onChange={(e) => pickProvider(e.target.value)} className={field} aria-label="Provider">
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            <option value={OTHER}>{T("Other (my own endpoint)", "อื่นๆ (endpoint ของฉันเอง)")}</option>
          </select>
        </label>
        <label className="block md:col-span-2">
          <span className="text-[13px] text-dl-muted">{T("Address (base URL)", "ที่อยู่ (base URL)")}</span>
          <input value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); setProbe(null); }} spellCheck={false} placeholder="https://llm.example.th/v1" className={field} aria-label="Base URL" />
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("3 · Model", "3 · โมเดล")}</span>
          <select value={pick} onChange={(e) => setModelPick(e.target.value)} className={field} aria-label="Model">
            {modelChoices.map((m) => <option key={m} value={m}>{m}</option>)}
            <option value={OTHER}>{T("Other (type the model id)", "อื่นๆ (พิมพ์ model id)")}</option>
          </select>
        </label>
        {pick === OTHER ? (
          <label className="block">
            <span className="text-[13px] text-dl-muted">{T("Model id", "model id")}</span>
            <input value={modelText} onChange={(e) => setModelText(e.target.value)} spellCheck={false} placeholder="typhoon-v2.5-30b-a3b-instruct" className={field} aria-label="Model id" />
          </label>
        ) : <div />}
      </div>

      <fieldset className="mt-5 rounded border border-dl-rule px-4 py-3">
        <legend className="px-1 text-[13px] text-dl-text">{T("Where does this endpoint process your data?", "endpoint นี้ประมวลผลข้อมูลของคุณที่ไหน")}</legend>
        <p className="mb-2 text-[12px] leading-relaxed text-dl-muted">
          {T("This is your declaration, taken from your agreement with the provider. A company's home country is not proof of where it processes data, so remote providers start as 'somewhere else'.",
             "นี่คือคำประกาศของคุณ ตามสัญญากับผู้ให้บริการ ประเทศของบริษัทไม่ได้พิสูจน์ว่าประมวลผลที่ไหน ผู้ให้บริการระยะไกลจึงเริ่มต้นเป็น 'ที่อื่น'")}
        </p>
        {([["local", T("On this machine or my own network", "บนเครื่องนี้หรือเครือข่ายของฉันเอง")],
           ["in_region", T("Inside a country (I confirmed it with the provider)", "ภายในประเทศหนึ่ง (ยืนยันกับผู้ให้บริการแล้ว)")],
           ["cross_border", T("Somewhere else, or I do not know", "ที่อื่น หรือไม่ทราบ")]] as const).map(([value, label]) => (
          <label key={value} className="flex items-center gap-2 py-1 text-[13px] text-dl-text">
            <input type="radio" name="location" checked={location === value} onChange={() => { setLocation(value); setProbe(null); }} className="accent-[var(--dl-leaf)]" /> {label}
          </label>
        ))}
        {location === "in_region" ? (
          <label className="mt-2 block max-w-[14rem]">
            <span className="text-[12px] text-dl-muted">{T("Country code (two letters)", "รหัสประเทศ (2 ตัวอักษร)")}</span>
            <input value={region} onChange={(e) => setRegion(e.target.value.slice(0, 2))} placeholder="TH" maxLength={2} className={field} aria-label="Country code" />
          </label>
        ) : null}
        <label className="mt-3 block">
          <span className="text-[12px] text-dl-muted">{T("Operator (recorded in the audit trail)", "ผู้ให้บริการ (บันทึกใน audit trail)")}</span>
          <input value={operator} onChange={(e) => setOperator(e.target.value)} className={field} aria-label="Operator" />
        </label>
      </fieldset>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("Name of the environment variable that holds the key", "ชื่อ environment variable ที่เก็บ key")}</span>
          <input value={keyEnv} onChange={(e) => setKeyEnv(e.target.value.toUpperCase())} spellCheck={false} placeholder="TYPHOON_API_KEY" className={field} aria-label="Key variable name" />
        </label>
        <label className="block">
          <span className="text-[13px] text-dl-muted">{T("API key (optional)", "API key (ไม่บังคับ)")}</span>
          <div className="flex gap-2">
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type={showKey ? "text" : "password"} autoComplete="new-password" spellCheck={false}
              placeholder={setup.credential_present && setup.credential_env === keyEnv ? "a key is already present" : ""} className={field} aria-label="API key" />
            <div className="mt-1"><Button tone="ghost" onClick={() => setShowKey((v) => !v)}>{showKey ? "Hide" : "Show"}</Button></div>
          </div>
        </label>
        <p className="text-[12px] leading-relaxed text-dl-muted md:col-span-2">
          {T("The key is kept in the server's memory until it restarts and is never written to a file or shown again. Only the variable's name is saved. To keep the key permanently, set that variable where the server starts.",
             "key ถูกเก็บในหน่วยความจำของเซิร์ฟเวอร์จนกว่าจะรีสตาร์ท ไม่เขียนลงไฟล์และไม่แสดงซ้ำ บันทึกเฉพาะชื่อตัวแปร ถ้าต้องการเก็บถาวรให้ตั้งตัวแปรนั้นตอนเริ่มเซิร์ฟเวอร์")}
          {preset?.note ? <span className="mt-1 block">{preset.note}{preset.docs ? <> · <a className="underline" href={preset.docs} target="_blank" rel="noreferrer noopener">docs</a></> : null}</span> : null}
        </p>
      </div>

      <div className="mt-5 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="text-[12px] text-dl-muted">{T("Use it for", "ใช้กับ")}</span>
          <select value={profile} onChange={(e) => setProfile(e.target.value)} className="desk-focus desk-mono mt-1 rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text" aria-label="Profile">
            <option value="">{T("everything (the default)", "ทุกอย่าง (ค่าเริ่มต้น)")}</option>
            {Object.keys(setup.profiles).map((p) => <option key={p} value={p}>{T("profile", "โปรไฟล์")} {p}</option>)}
          </select>
        </label>
        <Button tone="ghost" onClick={test} disabled={busy !== null || baseUrl.trim() === ""}>{busy === "test" ? "Testing…" : T("Test connection", "ทดสอบการเชื่อมต่อ")}</Button>
        <Button onClick={save} disabled={busy !== null || !canSave}>{busy === "save" ? "Saving…" : T("Save and use", "บันทึกและใช้")}</Button>
      </div>

      {probe ? (
        <div className="mt-4 space-y-2" role="status">
          {probe.contacted ? (
            <p className={`text-[13px] ${probe.reachable && !probe.error ? "text-dl-leaf" : "text-dl-rust"}`}>
              {probe.reachable && !probe.error ? T(`Reachable. The endpoint serves ${probe.models.length} model(s).`, `เชื่อมต่อได้ endpoint มี ${probe.models.length} โมเดล`) : probe.error}
            </p>
          ) : <p className="text-[13px] text-dl-rust">{probe.error}</p>}
          {probe.reachable && !probe.error && probe.models.length > 0 && model && !probe.models.includes(model) ? (
            <p className="text-[13px] text-dl-amber">{T(`The endpoint does not list the model "${model}". It serves: ${probe.models.slice(0, 6).join(", ")}${probe.models.length > 6 ? ", …" : ""}. Choose one from the Model list, or keep yours if the provider accepts ids it does not list.`,
              `endpoint ไม่ได้แสดงโมเดล "${model}" โมเดลที่มี: ${probe.models.slice(0, 6).join(", ")}${probe.models.length > 6 ? ", …" : ""} เลือกจากรายการโมเดล หรือคงของเดิมถ้าผู้ให้บริการรับ id ที่ไม่ได้แสดง`)}</p>
          ) : null}
          <Verdict v={probe.verdict} lang={lang} />
          <p className="text-[12px] text-dl-muted">{T("The test sends no prompt; it only asks which models the endpoint offers.", "การทดสอบไม่ส่ง prompt แค่ถามว่า endpoint มีโมเดลอะไร")}</p>
        </div>
      ) : null}
      {message ? <p role="status" className={`mt-3 text-[13px] ${message.tone === "leaf" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
    </Panel>
  );
}

// ---- the page ---------------------------------------------------------------------------------------------------

export default function ModelsPage() {
  const { t, lang } = useLang();
  const [picked, setMode] = useState<Mode | null>(null);
  const setup = useDeskData(() => desk.modelSetup(), []);
  const data = setup.data;
  const sel = data?.selection;
  // Until the operator clicks a tab, show the one that matches what is in use.
  const mode: Mode = picked ?? (sel?.provider === "ollama" ? "ollama" : sel?.provider === "openrouter" ? "openrouter" : "endpoint");

  return (
    <>
      <PageHeader title={t("models")}
        lead={lang === "th"
          ? "เลือกโมเดลที่ขับ agent loop จะใช้โมเดลบนเครื่อง, OpenRouter หรือ AI ของประเทศ/องค์กรคุณเองก็ได้ ค่าที่ตั้งจาก environment (DELENTIA_LLM_*) มีลำดับสูงกว่าค่าที่บันทึกที่นี่"
          : "Choose the model that drives the agent loop: one on this machine, OpenRouter, or your own country's or organisation's AI. Environment settings (DELENTIA_LLM_*) outrank what is saved here."} />
      <PageBody>
        {setup.error ? <ErrorNote error={setup.error} onRetry={setup.reload} /> : null}
        {data ? (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
            <div className="space-y-6">
              <Panel title={lang === "th" ? "ที่ใช้อยู่ตอนนี้" : "In use now"}>
                <Row label="Model">{data.selection.model}</Row>
                <Row label="Provider">{data.selection.provider}</Row>
                <Row label="Chosen by">{data.selection.model_source}</Row>
                {data.endpoint && data.selection.provider === "openai-compat" ? (
                  <>
                    <Row label="Address"><span className="break-all">{data.endpoint.base_url}</span></Row>
                    <Row label="Data is processed">{data.endpoint.kind === "local" ? "on this machine / network" : data.endpoint.kind === "in_region" ? `inside ${data.endpoint.region}` : "elsewhere / unknown"}</Row>
                  </>
                ) : null}
                {data.credential_env ? (
                  <Row label={`Key (${data.credential_env})`}>{data.credential_present ? <Badge tone="leaf">present</Badge> : <Badge tone="amber">not set</Badge>}</Row>
                ) : null}
                {data.profiles && Object.keys(data.profiles).length ? (
                  <Row label="Profiles">{Object.entries(data.profiles).map(([name, p]) => `${name}: ${p.model}`).join(", ")}</Row>
                ) : null}
                <div className="mt-3"><Verdict v={data.endpoint_verdict} lang={lang} /></div>
              </Panel>
              <Panel title={lang === "th" ? "key ไม่ถูกเก็บในไฟล์" : "Keys stay out of files"}>
                <p className="text-[13px] leading-relaxed text-dl-muted">
                  {lang === "th"
                    ? "ไฟล์ตั้งค่าเก็บเฉพาะ "
                    : "The config file stores only the "}<b className="text-dl-text">{lang === "th" ? "ชื่อ" : "name"}</b>{lang === "th"
                    ? " ของตัวแปรที่เก็บ key key ที่พิมพ์ในหน้านี้อยู่ในหน่วยความจำของเซิร์ฟเวอร์จนกว่าจะรีสตาร์ท และคำสั่งที่ agent รันใน sandbox จะไม่เห็นตัวแปรที่ชื่อเหมือน key/token/secret"
                    : " of the variable that holds the key. A key typed on this page lives in the server's memory until it restarts, and commands the agent runs in the sandbox cannot see variables named like a key, token or secret."}
                </p>
              </Panel>
              <Panel title={lang === "th" ? "ตรวจโมเดลก่อนใช้จริง" : "Check a model before relying on it"}>
                <p className="text-[13px] leading-relaxed text-dl-muted">
                  {lang === "th" ? "รันการทดสอบการเลือกเครื่องมือกับโมเดลที่เลือก (จากโฟลเดอร์ Delentia-OS):" : "Run the tool-selection acceptance test with the chosen model (from the Delentia-OS folder):"}
                </p>
                <div className="mt-2"><Code>python scripts/k1_5_formal_acceptance.py</Code></div>
              </Panel>
            </div>

            <div className="min-w-0 space-y-4">
              <div role="tablist" aria-label="Where the model runs" className="desk-mono flex flex-wrap overflow-hidden rounded border border-dl-rule text-[12px]">
                {([["endpoint", lang === "th" ? "AI ของประเทศ/องค์กร (OpenAI-compatible)" : "Your own AI (OpenAI-compatible)"],
                   ["ollama", lang === "th" ? "บนเครื่องนี้ (Ollama)" : "This machine (Ollama)"], ["openrouter", "OpenRouter"]] as const).map(([value, label]) => (
                  <button key={value} role="tab" aria-selected={mode === value} onClick={() => setMode(value)}
                    className={`desk-focus px-4 py-2 ${mode === value ? "bg-dl-pine text-dl-text" : "text-dl-muted hover:text-dl-text"}`}>{label}</button>
                ))}
              </div>
              {mode === "endpoint" ? <EndpointPanel setup={data} onSaved={setup.reload} lang={lang} />
                : <CatalogPanel provider={mode} current={data} onSaved={setup.reload} lang={lang} />}
            </div>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
