"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DeskError } from "@/lib/desk-api";

/** Fetch runtime data, optionally re-polling. Errors are kept, never replaced
 *  by placeholder data. */
export function useDeskData<T>(load: () => Promise<T>, deps: unknown[] = [], intervalMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  const reload = useCallback(async () => {
    try {
      const next = await loadRef.current();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof DeskError || err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    if (!intervalMs) return;
    const id = window.setInterval(reload, intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs]);

  return { data, error, loading, reload };
}

export function PageHeader({ title, lead, actions }: { title: string; lead?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-dl-rule px-6 py-5 md:px-8">
      <div className="min-w-0">
        <h1 className="desk-mono text-xl font-semibold tracking-wide text-dl-text">{title}</h1>
        {lead ? <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-dl-muted">{lead}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function PageBody({ children }: { children: React.ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 md:px-8">{children}</div>;
}

type Tone = "leaf" | "fern" | "amber" | "rust" | "muted";
const TONE: Record<Tone, string> = {
  leaf: "border-dl-leaf/50 text-dl-leaf",
  fern: "border-dl-fern text-dl-text",
  amber: "border-dl-amber/60 text-dl-amber",
  rust: "border-dl-rust/60 text-dl-rust",
  muted: "border-dl-rule text-dl-muted",
};

export function Badge({ tone = "muted", children, title }: { tone?: Tone; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className={`desk-mono inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function Panel({ title, children, className = "", aside }: { title?: string; children: React.ReactNode; className?: string; aside?: React.ReactNode }) {
  return (
    <section className={`rounded-md border border-dl-rule bg-dl-panel ${className}`}>
      {title ? (
        <div className="flex items-center justify-between gap-3 border-b border-dl-rule px-4 py-2.5">
          <h2 className="desk-mono text-[13px] font-medium text-dl-text">{title}</h2>
          {aside}
        </div>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-dl-rule/60 py-2 last:border-0">
      <span className="text-sm text-dl-muted">{label}</span>
      <span className="desk-mono min-w-0 truncate text-right text-sm text-dl-text">{children}</span>
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-dl-rust/50 bg-dl-rust/10 px-4 py-3 text-sm text-dl-text">
      <p>{error}</p>
      {onRetry ? (
        <button onClick={onRetry} className="desk-focus desk-mono mt-2 text-xs text-dl-leaf underline underline-offset-2">
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-dl-rule px-5 py-8 text-center">
      <p className="desk-mono text-sm text-dl-text">{title}</p>
      {children ? <div className="mx-auto mt-2 max-w-[60ch] text-sm leading-relaxed text-dl-muted">{children}</div> : null}
    </div>
  );
}

export function Code({ children }: { children: React.ReactNode }) {
  return <code className="desk-mono rounded bg-dl-ink px-1.5 py-0.5 text-[12px] text-dl-leaf">{children}</code>;
}

export function Button({ children, onClick, disabled, tone = "fern", type = "button" }: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean; tone?: "fern" | "ghost" | "amber"; type?: "button" | "submit";
}) {
  const styles = {
    fern: "border-dl-fern bg-dl-pine/60 text-dl-text hover:bg-dl-pine",
    ghost: "border-dl-rule text-dl-muted hover:text-dl-text",
    amber: "border-dl-amber/60 text-dl-amber hover:bg-dl-amber/10",
  }[tone];
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`desk-focus desk-mono rounded border px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  );
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Explicit day-month-year: the browser's default for a Thai locale is the Buddhist-era year
  // ("1/10/69"), which reads as 1969 or 2069 to anyone who does not expect it.
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(digits) : "-";
}

/** Badge tone for an episode's stopped_reason. */
export function reasonTone(r: string): Tone {
  if (r === "llm_finished") return "leaf";
  if (r === "pending_approval") return "amber";
  if (r === "fdia_blocked" || r === "guard_blocked" || r === "notary_unavailable") return "rust";
  return "muted";
}
