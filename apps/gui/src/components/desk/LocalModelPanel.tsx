"use client";

import { useCallback, useEffect, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";
import { chatModels } from "@/lib/setup-model";
import { TRY_ONLY, evidenceText, fitText, formatGb, ollamaAdvice, orderRows, pullText } from "@/lib/local-model-ui";

/**
 * A local model without a terminal: what this computer can hold, Ollama's state with the one button that fits it, the models already installed, and a short list to download with a progress bar.
 * Everything it says about quality is "measured by this project" or "not measured"; a fit is an estimate.
 */
export function LocalModelPanel({ onUse, busy }: { onUse: (name: string) => void; busy: boolean }) {
  const { lang } = useLang();
  const th = lang === "th";
  const T = (en: string, thai: string) => (th ? thai : en);
  const view = useDeskData(() => desk.localModels(), [], 0);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const data = view.data;
  const pull = data?.pull;
  const downloading = pull?.status === "downloading";
  const reload = view.reload;

  // poll the download while it runs, and the state of Ollama while it is not yet running (a person installing it in another window)
  useEffect(() => {
    if (!downloading) return;
    const id = window.setInterval(() => void reload(), 1500);
    return () => window.clearInterval(id);
  }, [downloading, reload]);
  useEffect(() => {
    if (!data || data.ollama.state === "running") return;
    const id = window.setInterval(() => void reload(), 5000);
    return () => window.clearInterval(id);
  }, [data, reload]);

  const startOllama = useCallback(async () => {
    setWorking(true);
    setMessage(null);
    try {
      const r = await desk.ollamaStart();
      setMessage(r.started ? T("Ollama is running.", "Ollama ทำงานแล้ว") : r.message);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, th]);

  const download = async (tag: string) => {
    setConfirming(null);
    setMessage(null);
    try {
      await desk.ollamaPull(tag);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  if (!data) return <p className="desk-mono text-sm text-dl-muted">{view.error ?? T("Looking at this computer…", "กำลังตรวจเครื่องนี้…")}</p>;

  const installed = chatModels(data.ollama.models);
  const advice = ollamaAdvice(data.ollama.state, installed.length > 0, lang as "th" | "en");
  const ram = data.hardware.ram_gb;
  const rows = orderRows(data.recommendation.models, data.recommendation.try_first);

  return (
    <div className="text-[13px] leading-relaxed">
      <p className="text-dl-muted">
        {ram !== null ? T(`This computer has about ${ram} GB of memory and ${data.hardware.cpu_threads ?? "?"} processor threads. The graphics card is not looked at.`, `เครื่องนี้มีแรมราว ${ram} GB และ ${data.hardware.cpu_threads ?? "?"} เธรดของโปรเซสเซอร์ (ไม่ได้ตรวจการ์ดจอ)`) : T("The memory of this computer could not be read.", "อ่านขนาดแรมของเครื่องนี้ไม่ได้")}
      </p>
      <p className="mt-2 font-medium text-dl-text">{advice.title}</p>
      {advice.text ? <p className="text-dl-muted">{advice.text}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {advice.action === "open_download" ? (
          <a href={data.ollama.download_url} target="_blank" rel="noreferrer noopener" className="desk-focus inline-flex items-center rounded border border-dl-leaf px-3 py-1.5 text-xs text-dl-text hover:bg-dl-pine">
            {T("Open the Ollama download page", "เปิดหน้าดาวน์โหลด Ollama")}
          </a>
        ) : null}
        {advice.action === "start" ? <Button onClick={() => void startOllama()} disabled={working}>{working ? T("Starting…", "กำลังเริ่ม…") : T("Start Ollama", "เริ่ม Ollama")}</Button> : null}
        <Button tone="ghost" onClick={() => void reload()}>{T("Check again", "ตรวจอีกครั้ง")}</Button>
      </div>
      {message ? <p role="status" className="mt-2 text-dl-amber">{message}</p> : null}

      {data.ollama.running ? (
        <>
          {installed.length ? (
            <div className="mt-3">
              <p className="font-medium text-dl-text">{T("Already on this computer", "มีในเครื่องแล้ว")}</p>
              <ul className="mt-1 space-y-1">
                {installed.map((name) => (
                  <li key={name} className="flex items-center justify-between gap-2">
                    <span className="desk-mono text-[12px] text-dl-text">{name}</span>
                    <Button tone="ghost" onClick={() => onUse(name)} disabled={busy}>{T("Use this", "ใช้ตัวนี้")}</Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-3">
            <p className="font-medium text-dl-text">{T("Download a model", "ดาวน์โหลดโมเดล")}</p>
            <p className="text-dl-muted">{T(TRY_ONLY.en, TRY_ONLY.th)}</p>
            {pull && pull.status !== "idle" ? (
              <div className="mt-2 rounded border border-dl-rule p-2" role="group" aria-label={T("Download", "การดาวน์โหลด")}>
                <p className="desk-mono text-[12px] text-dl-text">{pull.name}</p>
                {downloading ? <progress className="mt-1 block h-2 w-full" max={100} value={pull.percent ?? undefined} aria-label={T("Download progress", "ความคืบหน้าการดาวน์โหลด")} /> : null}
                <p className="mt-1 text-dl-muted" role="status">{pullText(pull, lang as "th" | "en")}</p>
                {downloading ? <div className="mt-1"><Button tone="ghost" onClick={() => void desk.ollamaPullCancel().then(() => reload())}>{T("Cancel the download", "ยกเลิกการดาวน์โหลด")}</Button></div> : null}
                {pull.status === "done" ? <div className="mt-1"><Button onClick={() => onUse(pull.name)} disabled={busy}>{T("Use this model", "ใช้โมเดลนี้")}</Button></div> : null}
              </div>
            ) : null}
            <ul className="mt-2 divide-y divide-dl-rule/60">
              {rows.map((row) => {
                const fit = fitText(row, ram, lang as "th" | "en");
                const isFirst = row.tag === data.recommendation.try_first;
                return (
                  <li key={row.tag} className="py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="desk-mono text-[12px] text-dl-text">{row.label}</span>{" "}
                        <Code>{row.tag}</Code>{" "}
                        <span className="text-dl-muted">{formatGb(row.size_gb)} {T("download", "ดาวน์โหลด")}</span>
                        {isFirst ? <> <Badge tone="leaf">{T("to try first", "ลองตัวนี้ก่อน")}</Badge></> : null}
                        {row.installed ? <> <Badge tone="fern">{T("installed", "ติดตั้งแล้ว")}</Badge></> : null}
                      </div>
                      {!row.installed ? (
                        confirming === row.tag ? (
                          <span className="flex items-center gap-2">
                            <span>{T(`Download ${formatGb(row.size_gb)}?`, `ดาวน์โหลด ${formatGb(row.size_gb)} ใช่ไหม`)}</span>
                            <Button onClick={() => void download(row.tag)}>{T("Yes", "ใช่")}</Button>
                            <Button tone="ghost" onClick={() => setConfirming(null)}>{T("No", "ไม่")}</Button>
                          </span>
                        ) : (
                          <Button tone="ghost" onClick={() => setConfirming(row.tag)} disabled={downloading}>{T("Download", "ดาวน์โหลด")}</Button>
                        )
                      ) : null}
                    </div>
                    <p className="text-dl-muted">{th ? row.note_th : row.note_en}</p>
                    <p className={fit.tone === "ok" ? "text-dl-leaf" : fit.tone === "warn" ? "text-dl-amber" : "text-dl-muted"}>{fit.text}</p>
                    <p className="text-dl-muted">{evidenceText(row, lang as "th" | "en")}</p>
                  </li>
                );
              })}
            </ul>
            <p className="mt-1 text-[12px] text-dl-muted">{T(`The list was checked on ${data.recommendation.catalog_date} against each model's own Ollama page. Sizes and fit are estimates.`, `รายการนี้ตรวจกับหน้า Ollama ของแต่ละโมเดลเมื่อ ${data.recommendation.catalog_date} ขนาดและความพอดีเป็นค่าประมาณ`)}</p>
          </div>
        </>
      ) : null}

      <details className="mt-3">
        <summary className="cursor-pointer text-dl-muted">{T("Already use another program (LM Studio, llama.cpp, vLLM…)?", "ใช้โปรแกรมอื่นอยู่แล้ว (LM Studio, llama.cpp, vLLM…)?")}</summary>
        <p className="mt-1 text-dl-muted">
          {T("Programs that offer an OpenAI-style address can be used from the Models page (“your own address”). Delentia has not been tried with them yet, so they are not offered here; Ollama is the one that has been tried.",
             "โปรแกรมที่มีที่อยู่แบบ OpenAI ใช้ได้จากหน้า Models (“ที่อยู่ของคุณเอง”) Delentia ยังไม่เคยลองกับโปรแกรมเหล่านั้น จึงยังไม่เสนอไว้ที่นี่ ตัวที่ลองแล้วคือ Ollama")}
        </p>
      </details>
    </div>
  );
}
