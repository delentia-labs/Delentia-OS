"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Code, ErrorNote, Panel, Row, fmtTime, useDeskData } from "./ui";
import { desk, type GovCategory, type GovEvent, type GovEventDetail } from "@/lib/desk-api";

const CATEGORIES: { id: GovCategory; label: string; hint: string }[] = [
  { id: "attention", label: "Needs attention", hint: "blocked goals, withheld results, jury refusals, approvals, policy and token changes, blocked tool calls" },
  { id: "all", label: "Everything", hint: "every audit row" },
  { id: "blocked", label: "Blocked goals", hint: "goals CORD or the jury stopped before the model saw them" },
  { id: "screening", label: "Injection screen", hint: "tool results screened for hidden instructions, and the small model's second opinion" },
  { id: "gate", label: "FDIA gate", hint: "F = D^I x A for every risky tool call" },
  { id: "approvals", label: "Approvals", hint: "actions waiting for, or signed by, a human" },
  { id: "jury", label: "Jury", hint: "multi-model verdicts" },
  { id: "policy", label: "Policy", hint: "changes to the owner's policy" },
  { id: "sovereignty", label: "Sovereignty", hint: "model calls the data-residency policy allowed, redacted or blocked" },
  { id: "identity", label: "Identity", hint: "tokens created or revoked" },
  { id: "notary", label: "Notary", hint: "receipts from the separate notary process, and gaps" },
  { id: "episodes", label: "Episodes", hint: "start and end of every run" },
  { id: "steps", label: "Run steps", hint: "each step the agent took, the Intent Loop pillars, the algorithm pipeline" },
];

function tone(e: GovEvent): "leaf" | "amber" | "rust" | "muted" {
  const a = e.action;
  if (a === "goal_blocked" || a === "withheld" || a === "jury_refused" || a === "goal_refused_by_jury" || a === "block" || a === "attack" || a === "rejected" || a === "notary_gap") return "rust";
  if (e.entity_type === "notary_gap" || e.summary.includes("BLOCKED")) return "rust";
  if (a === "waiting" || a === "warned" || a === "redact" || a === "policy_saved" || a === "policy_disabled" || e.category === "identity") return "amber";
  if (a === "approved" || a === "execute" || a === "jury_agreed" || a === "allow") return "leaf";
  return "muted";
}

function Detail({ id, onClose }: { id: number; onClose: () => void }) {
  const [d, setD] = useState<GovEventDetail | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    desk.govEvent(id).then((x) => live && setD(x)).catch((e) => live && setErr(e instanceof Error ? e.message : String(e)));
    return () => { live = false; };
  }, [id]);
  return (
    <Panel title={`Audit row #${id}`} aside={<Button tone="ghost" onClick={onClose}>Close</Button>}>
      {err ? <ErrorNote error={err} /> : null}
      {d ? (
        <div className="space-y-3">
          <p className="text-sm text-dl-text">{d.summary}</p>
          <div>
            <Row label="Type">{d.entity_type}</Row>
            <Row label="Action">{d.action}</Row>
            <Row label="Actor">{d.actor ?? "-"}</Row>
            <Row label="When">{fmtTime(d.at)}</Row>
            {d.chain ? (
              <>
                <Row label="Chain position">#{d.chain.seq}</Row>
                <Row label="Row hash">
                  {d.chain.row_hash.slice(0, 20)}… {d.chain.recomputed_matches ? <Badge tone="leaf">recomputed: matches</Badge> : <Badge tone="rust">recomputed: DIFFERENT, the row was edited</Badge>}
                </Row>
                <Row label="Previous hash">{d.chain.prev_hash.slice(0, 20)}…</Row>
                <Row label="Signature">{d.chain.signed ? `Ed25519, key ${d.chain.signer_fingerprint ?? "?"}` : "not signed"}</Row>
              </>
            ) : (
              <Row label="Chain position">before the chain existed (cannot be verified)</Row>
            )}
          </div>
          <details>
            <summary className="desk-focus desk-mono cursor-pointer text-[12px] text-dl-leaf">What was recorded (the exact JSON)</summary>
            <pre className="desk-mono mt-2 max-h-72 overflow-auto rounded border border-dl-rule bg-dl-ink p-3 text-[12px] text-dl-muted">{JSON.stringify(d.changes, null, 2)}</pre>
          </details>
          {d.related.length ? (
            <div>
              <p className="desk-mono text-[11px] text-dl-muted">Other rows about the same thing</p>
              <ul className="desk-mono mt-1 text-[12px] text-dl-muted">
                {d.related.map((r) => <li key={r.id}>#{r.id} {r.entity_type} · {r.action} · {fmtTime(r.at)}</li>)}
              </ul>
            </div>
          ) : null}
          <p className="text-[12px] text-dl-muted">Check the whole chain yourself: <Code>delentia audit-chain verify</Code></p>
        </div>
      ) : null}
    </Panel>
  );
}

/** The audit trail as people read it: filter by what happened, search, page back, open one row to see its place in the hash chain. */
export function EventExplorer({ initial = "attention", title = "Events" }: { initial?: GovCategory; title?: string }) {
  const [category, setCategory] = useState<GovCategory>(initial);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const key = `${category}|${applied}`;
  const first = useDeskData(() => desk.govEvents(category, applied), [category, applied]);
  // Older pages are kept with the filter they were fetched for, so changing the filter drops them without an effect.
  const [more, setMore] = useState<{ key: string; rows: GovEvent[]; next: number | null } | null>(null);
  const [moreError, setMoreError] = useState("");
  const [busy, setBusy] = useState(false);
  const extra = more && more.key === key ? more : null;
  const rows = [...(first.data?.events ?? []), ...(extra?.rows ?? [])];
  const next = extra ? extra.next : (first.data?.next_before_id ?? null);
  const error = first.error || moreError;

  const older = async () => {
    if (!next) return;
    setBusy(true);
    setMoreError("");
    try {
      const r = await desk.govEvents(category, applied, next);
      setMore({ key, rows: [...(extra?.rows ?? []), ...r.events], next: r.next_before_id });
    } catch (e) {
      setMoreError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const hint = CATEGORIES.find((c) => c.id === category)?.hint;

  return (
    <div className="space-y-4">
      <Panel title={title}
        aside={<form onSubmit={(e) => { e.preventDefault(); setApplied(query); }} className="flex gap-2">
          <label className="sr-only" htmlFor="ev-q">Search</label>
          <input id="ev-q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="search tool, actor, id…" maxLength={80}
            className="desk-focus desk-mono w-44 rounded border border-dl-rule bg-dl-ink px-2 py-1 text-[12px] text-dl-text placeholder:text-dl-muted/50" />
          <Button type="submit" tone="ghost">Search</Button>
        </form>}>
        <div role="group" aria-label="Category" className="mb-3 flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <button key={c.id} onClick={() => setCategory(c.id)} aria-pressed={category === c.id}
              className={`desk-focus desk-mono rounded border px-2 py-1 text-[11px] ${category === c.id ? "border-dl-fern bg-dl-pine text-dl-text" : "border-dl-rule text-dl-muted hover:text-dl-text"}`}>
              {c.label}
            </button>
          ))}
        </div>
        {hint ? <p className="mb-3 text-[12px] text-dl-muted">{hint}</p> : null}
        {error ? <ErrorNote error={error} onRetry={first.reload} /> : null}
        {!error && !rows.length && first.data ? <p className="text-sm text-dl-muted">Nothing recorded in this view yet.</p> : null}
        <ul className="divide-y divide-dl-rule/60">
          {rows.map((e) => (
            <li key={e.id}>
              <button onClick={() => setOpen(e.id)} className="desk-focus flex w-full items-start gap-3 py-2 text-left hover:bg-dl-ink/40">
                <span className="desk-mono w-12 shrink-0 text-[11px] text-dl-muted">#{e.id}</span>
                <Badge tone={tone(e)}>{e.category}</Badge>
                <span className="min-w-0 flex-1 text-[13px] text-dl-text">{e.summary}</span>
                <span className="desk-mono hidden shrink-0 text-[11px] text-dl-muted sm:block">{fmtTime(e.at)}</span>
                <span title={e.chain_seq ? `chain #${e.chain_seq}${e.signed ? ", signed" : ", not signed"}` : "before the chain"} className="desk-mono shrink-0 text-[11px] text-dl-muted">
                  {e.chain_seq ? (e.signed ? "⛓✓" : "⛓") : "·"}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {next ? <div className="mt-3"><Button tone="ghost" onClick={older} disabled={busy}>{busy ? "Loading…" : "Older rows"}</Button></div> : null}
      </Panel>
      {open !== null ? <Detail id={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
