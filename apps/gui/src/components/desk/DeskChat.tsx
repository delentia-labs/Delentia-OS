"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { PixelMark } from "./mark";
import { useLang } from "./i18n";
import { useDeskData } from "./ui";
import { desk, streamUrl, type SessionSummary } from "@/lib/desk-api";

type Step = {
  iteration: number; kind: "tool" | "finish" | "blocked" | "pending" | "notary_down" | "unknown_tool";
  tool: string | null; args: Record<string, unknown>; thinking: string; result: string | null;
  F?: number; reason?: string; did_you_mean?: string[];
};
type Summary = {
  namespace: string; stopped_reason: string; iterations: number;
  route: { path?: string; reason?: string; max_iterations?: number };
  verification: { applicable?: boolean; aligned_with_intent?: boolean; similarity_score?: number };
  guard: { cord_verdict?: string; cord_findings?: { pattern_id: string }[] };
  notary: { enabled?: boolean; receipts?: number };
  approval_id?: string | null; rct7_steps: string[];
};
type Fdia = { D: number | null; I: number | null; A: number; F: number | null; signed: boolean; signature_hash: string };
type Entry =
  | { kind: "user"; text: string }
  | { kind: "step"; step: Step }
  | { kind: "answer"; text: string }
  | { kind: "summary"; summary: Summary; fdia?: Fdia; seconds: number }
  | { kind: "error"; text: string };

const CYCLE = ["GUARD", "THINK", "ROUTE", "ACT", "COMPRESS", "VERIFY", "RECORD", "LEARN"];

function argsLine(args: Record<string, unknown>) {
  const s = JSON.stringify(args);
  return s.length > 140 ? `${s.slice(0, 140)}…` : s;
}

function Banner({ version, model, tools, skills, chain, namespace }: {
  version?: string; model?: string; tools?: { count: number; approval: number; fdia: number };
  skills?: number; chain?: string; namespace?: string;
}) {
  return (
    <div className="grid gap-5 rounded-md border border-dl-fern/70 p-4 md:grid-cols-[auto_1fr]">
      <div className="flex flex-col items-start gap-3 md:border-r md:border-dl-rule md:pr-5">
        <PixelMark />
        <div className="desk-mono text-[12px] leading-relaxed text-dl-muted">
          <p className="text-dl-leaf">{model ?? "model: -"}</p>
          <p>{namespace ? `session ${namespace}` : "new session"}</p>
        </div>
      </div>
      <div className="desk-mono min-w-0 text-[13px] leading-relaxed">
        <p className="mb-3 text-dl-amber">Delentia Agent {version ? `v${version}` : ""}</p>
        <p className="text-dl-text">• Constitutional cycle</p>
        <p className="mb-2 break-words text-dl-muted">{CYCLE.join(" → ")}</p>
        <p className="text-dl-text">• Tools</p>
        <p className="mb-2 text-dl-muted">
          {tools ? `${tools.count} tools · ${tools.approval} need a signed approval · ${tools.fdia} go through the FDIA gate` : "-"}
        </p>
        <p className="text-dl-text">• Skills</p>
        <p className="mb-2 text-dl-muted">{skills === undefined ? "-" : `${skills} learned from verified episodes (MEE-gated)`}</p>
        <p className="text-dl-text">• Audit</p>
        <p className="text-dl-muted">{chain ?? "-"}</p>
      </div>
    </div>
  );
}

function StepView({ step }: { step: Step }) {
  return (
    <div className="desk-mono text-[13px] leading-relaxed">
      {step.thinking ? (
        <p className="text-dl-muted">
          <span className="text-dl-rule">└ </span>thinking · {step.thinking}
        </p>
      ) : null}
      {step.kind === "tool" ? (
        <div className="mt-1 rounded border border-dl-rule bg-dl-panel2/60 px-3 py-2">
          <p className="text-dl-text">
            <span className="text-dl-leaf">●</span> {step.tool} <span className="text-dl-muted">{argsLine(step.args)}</span>
          </p>
          {step.result ? <p className="mt-1 whitespace-pre-wrap break-words text-dl-muted">{step.result}</p> : null}
        </div>
      ) : null}
      {step.kind === "blocked" ? (
        <p className="mt-1 text-dl-rust">✕ FDIA gate blocked {step.tool} (F {step.F ?? "-"}): {step.reason}</p>
      ) : null}
      {step.kind === "pending" ? (
        <p className="mt-1 text-dl-amber">
          ◷ {step.tool} waits for a signed human approval · <Link href="/approvals" className="underline underline-offset-2">open Approvals</Link>
        </p>
      ) : null}
      {step.kind === "notary_down" ? <p className="mt-1 text-dl-rust">✕ not run: the audit notary could not record it</p> : null}
      {step.kind === "unknown_tool" ? (
        <p className="mt-1 text-dl-amber">? no tool named {step.tool}; closest: {(step.did_you_mean ?? []).join(", ") || "-"}</p>
      ) : null}
    </div>
  );
}

function SummaryView({ summary, fdia, seconds }: { summary: Summary; fdia?: Fdia; seconds: number }) {
  const v = summary.verification;
  const parts = [
    summary.stopped_reason,
    summary.route?.path ? `route ${summary.route.path}` : null,
    v?.applicable ? `verify ${v.aligned_with_intent ? "pass" : "fail"} ${v.similarity_score ?? ""}` : null,
    fdia && typeof fdia.F === "number" ? `F ${fdia.F.toFixed(2)}` : null,
    fdia?.signed ? "JITNA signed" : null,
    summary.notary?.enabled ? `notary ${summary.notary.receipts}` : null,
    `${summary.iterations} steps`,
    `${Math.round(seconds)} s`,
  ].filter(Boolean);
  return (
    <div className="desk-mono text-[12px] text-dl-muted">
      <p>── {parts.join(" · ")}</p>
      {summary.guard?.cord_verdict === "rejected" ? (
        <p className="text-dl-rust">GUARD stopped this request (CORD: {(summary.guard.cord_findings ?? []).map((f) => f.pattern_id).join(", ")})</p>
      ) : null}
      {summary.rct7_steps?.length ? (
        <details className="mt-1">
          <summary className="desk-focus cursor-pointer hover:text-dl-text">RCT-7 plan ({summary.rct7_steps.length} steps)</summary>
          <ol className="mt-1 space-y-0.5 pl-4">
            {summary.rct7_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </details>
      ) : null}
      {summary.approval_id ? (
        <p className="text-dl-amber">approval {summary.approval_id} · <Link href="/approvals" className="underline underline-offset-2">sign it in Approvals</Link></p>
      ) : null}
    </div>
  );
}

export function DeskChat() {
  const { t } = useLang();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"agent" | "standard">("agent");
  const [budget, setBudget] = useState(5);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [namespace, setNamespace] = useState<string | undefined>();
  const [lastFdia, setLastFdia] = useState<Fdia | undefined>();
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(0);

  const health = useDeskData(() => desk.health(), [], 15000);
  const overview = useDeskData(() => desk.overview(), [], 20000);
  const tools = useDeskData(() => desk.tools(), []);
  const sessions = useDeskData(() => desk.sessions(12), [], 20000);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setElapsed((Date.now() - startedRef.current) / 1000), 500);
    return () => window.clearInterval(id);
  }, [running]);

  const model = overview.data?.model;
  const modelLabel = model ? `${model.model} (${model.provider})` : undefined;
  const toolInfo = tools.data
    ? { count: tools.data.count, approval: tools.data.tools.filter((x) => x.gate === "approval").length, fdia: tools.data.tools.filter((x) => x.gate === "fdia").length }
    : undefined;
  const chainStatus = overview.data?.audit_verify?.status;
  const chainLine = overview.data
    ? `chain ${chainStatus === "SUCCESS" ? "verified" : chainStatus === "FAILED" ? "BROKEN" : "not checked yet"} · ${overview.data.approvals_pending} approvals pending`
    : undefined;

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setRunning(false);
  }, []);

  const send = useCallback(() => {
    const goal = input.trim();
    if (!goal || running) return;
    setInput("");
    setEntries((prev) => [...prev, { kind: "user", text: goal }]);
    setRunning(true);
    setElapsed(0);
    startedRef.current = Date.now();

    let chatText = "";
    let pendingSummary: Summary | null = null;
    let gotAny = false;
    const ws = new WebSocket(streamUrl());
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ intent: goal, mode, max_iterations: budget, structured: true }));
    ws.onmessage = (msg) => {
      gotAny = true;
      let ev: { type: string; data: unknown };
      try {
        ev = JSON.parse(msg.data as string);
      } catch {
        return;
      }
      if (ev.type === "start") setNamespace((ev.data as { namespace: string }).namespace);
      else if (ev.type === "step") setEntries((p) => [...p, { kind: "step", step: ev.data as Step }]);
      else if (ev.type === "answer") {
        const text = (ev.data as { text: string | null }).text;
        if (text) setEntries((p) => [...p, { kind: "answer", text }]);
      } else if (ev.type === "summary") pendingSummary = ev.data as Summary;
      else if (ev.type === "token") {
        chatText += ev.data as string;
        const snapshot = chatText;
        setEntries((p) => {
          const last = p[p.length - 1];
          if (last && last.kind === "answer" && mode !== "agent") return [...p.slice(0, -1), { kind: "answer", text: snapshot }];
          return [...p, { kind: "answer", text: snapshot }];
        });
      } else if (ev.type === "fdia") {
        const f = ev.data as Fdia;
        setLastFdia(f);
        if (pendingSummary) {
          const s = pendingSummary;
          setEntries((p) => [...p, { kind: "summary", summary: s, fdia: f, seconds: (Date.now() - startedRef.current) / 1000 }]);
          pendingSummary = null;
        }
      } else if (ev.type === "error") setEntries((p) => [...p, { kind: "error", text: String(ev.data) }]);
      if (ev.type === "done" || ev.type === "error") {
        ws.close();
        setRunning(false);
        sessions.reload();
        overview.reload();
      }
    };
    ws.onerror = () => {
      if (!gotAny) setEntries((p) => [...p, { kind: "error", text: "The Delentia API is not reachable, so nothing ran. Start it with `delentia serve`." }]);
    };
    ws.onclose = (e) => {
      setRunning(false);
      if (!gotAny && e.code === 4401) {
        setEntries((p) => [...p, { kind: "error", text: "The API refused the connection (API token missing or wrong). Set it in Settings." }]);
      }
    };
  }, [input, running, mode, budget, sessions, overview]);

  const newChat = () => {
    stop();
    setEntries([]);
    setNamespace(undefined);
    setLastFdia(undefined);
  };

  const apiUp = !health.error && !!health.data;
  const statusParts = [
    running ? `working ${Math.round(elapsed)} s` : "ready",
    modelLabel ?? "model -",
    mode === "agent" ? `agent · ${budget} steps` : "chat · no tools",
    lastFdia && typeof lastFdia.F === "number" ? `F ${lastFdia.F.toFixed(2)}` : null,
    `${overview.data?.sessions_total ?? "-"} sessions`,
  ].filter(Boolean);

  return (
    <div className="flex min-h-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-dl-rule px-4 py-3 md:px-6">
          <h1 className="desk-mono truncate text-[15px] font-medium tracking-wide">
            {entries.find((e) => e.kind === "user")?.kind === "user"
              ? (entries.find((e) => e.kind === "user") as { text: string }).text
              : t("chat")}
          </h1>
          <label className="lg:hidden">
            <span className="sr-only">Mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as "agent" | "standard")} disabled={running}
              className="desk-focus desk-mono rounded border border-dl-rule bg-dl-ink px-2 py-1 text-[12px] text-dl-text">
              <option value="agent">Agent</option>
              <option value="standard">Chat</option>
            </select>
          </label>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-6">
          <div className="mx-auto flex max-w-[980px] flex-col gap-4 rounded-md border border-dl-rule bg-[#0a110d] p-4">
            <Banner version={health.data?.version} model={modelLabel} tools={toolInfo} skills={overview.data?.skills}
              chain={chainLine} namespace={namespace} />

            {entries.length === 0 ? (
              <p className="desk-mono text-[13px] text-dl-muted">
                {mode === "agent"
                  ? "Agent mode runs real tools. Every risky action passes the FDIA gate; file writes wait for your signed approval."
                  : "Chat mode is a conversation with the local model. It runs no tools."}
              </p>
            ) : null}

            {entries.map((e, i) => (
              <div key={i}>
                {e.kind === "user" ? <p className="desk-mono text-[14px] text-dl-text"><span className="text-dl-leaf">› </span>{e.text}</p> : null}
                {e.kind === "step" ? <StepView step={e.step} /> : null}
                {e.kind === "answer" ? (
                  <div className="flex gap-3">
                    <span className="desk-mono select-none text-dl-rule">⋮</span>
                    <p className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-dl-text">{e.text}</p>
                  </div>
                ) : null}
                {e.kind === "summary" ? <SummaryView summary={e.summary} fdia={e.fdia} seconds={e.seconds} /> : null}
                {e.kind === "error" ? <p role="alert" className="desk-mono text-[13px] text-dl-rust">✕ {e.text}</p> : null}
              </div>
            ))}

            <form onSubmit={(ev) => { ev.preventDefault(); send(); }} className="desk-mono flex items-start gap-2 text-[14px]">
              <span className="pt-1 text-dl-leaf">›</span>
              <label htmlFor="desk-input" className="sr-only">Message</label>
              <textarea id="desk-input" rows={1} value={input} disabled={running}
                onChange={(ev) => setInput(ev.target.value)}
                onKeyDown={(ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(); } }}
                placeholder={running ? "" : "Type a goal and press Enter"}
                className="desk-focus min-h-[1.75rem] flex-1 resize-none bg-transparent py-1 text-dl-text placeholder:text-dl-muted/60 focus:outline-none" />
              {running ? <span className="desk-cursor mt-1.5" aria-hidden /> : null}
            </form>
            <div ref={bottomRef} />
          </div>
        </div>

        <footer className="desk-mono flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-dl-rule bg-dl-panel px-6 py-2 text-[12px] text-dl-muted">
          <span className={apiUp ? "text-dl-leaf" : "text-dl-rust"}>●</span>
          {statusParts.map((p, i) => (
            <span key={i} className="flex items-center gap-3">
              {i > 0 ? <span className="text-dl-rule">|</span> : null}
              {p}
            </span>
          ))}
          {running ? (
            <button onClick={stop} className="desk-focus ml-auto rounded border border-dl-rust/60 px-2 py-0.5 text-dl-rust">Stop</button>
          ) : null}
        </footer>
      </section>

      <aside className="hidden w-72 shrink-0 flex-col gap-5 overflow-y-auto border-l border-dl-rule bg-dl-panel p-4 lg:flex">
        <div className="rounded-md border border-dl-rule p-3">
          <div className="desk-mono flex items-center justify-between text-[11px] text-dl-muted">
            <span>{t("models").toUpperCase()}</span>
            <span className={`rounded border px-1.5 ${apiUp ? "border-dl-leaf/60 text-dl-leaf" : "border-dl-rust/60 text-dl-rust"}`}>{apiUp ? "live" : "offline"}</span>
          </div>
          <p className="desk-mono mt-1.5 truncate text-[13px] text-dl-text" title={modelLabel}>{modelLabel ?? "-"}</p>
          <Link href="/llm" className="desk-focus desk-mono mt-1 inline-block text-[11px] text-dl-leaf underline underline-offset-2">change model</Link>
        </div>

        <label className="block rounded-md border border-dl-rule p-3">
          <span className="desk-mono text-[11px] text-dl-muted">MODE</span>
          <select value={mode} onChange={(e) => setMode(e.target.value as "agent" | "standard")} disabled={running}
            className="desk-focus desk-mono mt-1.5 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1 text-[13px] text-dl-text">
            <option value="agent">Agent (governed, real tools)</option>
            <option value="standard">Chat (no tools)</option>
          </select>
        </label>

        <label className="block rounded-md border border-dl-rule p-3">
          <span className="desk-mono text-[11px] text-dl-muted">STEP BUDGET</span>
          <select value={budget} onChange={(e) => setBudget(Number(e.target.value))} disabled={running || mode !== "agent"}
            className="desk-focus desk-mono mt-1.5 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1 text-[13px] text-dl-text">
            {[3, 5, 8, 12].map((n) => <option key={n} value={n}>{n} steps</option>)}
          </select>
          <span className="mt-1.5 block text-[11px] leading-snug text-dl-muted">ROUTE may lower it to 3 for a low-risk, narrow goal.</span>
        </label>

        <div>
          <div className="desk-mono mb-2 flex items-center justify-between text-[11px] text-dl-muted">
            <span>{t("sessions").toUpperCase()}</span>
            <button onClick={() => sessions.reload()} className="desk-focus hover:text-dl-text" aria-label="Refresh sessions">↻</button>
          </div>
          <button onClick={newChat} className="desk-focus desk-mono mb-3 w-full rounded border border-dl-fern px-3 py-1.5 text-[12px] text-dl-text hover:bg-dl-pine/50">
            + {t("new_chat")}
          </button>
          {sessions.data?.sessions.length ? (
            <ul className="space-y-1">
              {sessions.data.sessions.map((s: SessionSummary) => (
                <li key={s.id}>
                  <Link href={`/sessions?id=${s.id}`} className="desk-focus block rounded px-2 py-1.5 hover:bg-dl-pine/40">
                    <p className="truncate text-[12px] text-dl-text">{s.goal ?? s.namespace}</p>
                    <p className="desk-mono text-[10px] text-dl-muted">{s.stopped_reason} · {s.route ?? "-"}</p>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-center text-[12px] text-dl-muted">{sessions.error ? "-" : "No sessions yet"}</p>
          )}
        </div>
      </aside>
    </div>
  );
}
