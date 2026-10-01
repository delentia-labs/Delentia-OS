"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

// Ctrl/Cmd+K: jump to any Desk page. Every entry is a real route.
const ROUTES: { href: string; name: string; desc: string }[] = [
  { href: "/", name: "Status", desc: "API, daemon, pending approvals, audit chain" },
  { href: "/chat", name: "Chat", desc: "Run a goal through the governed loop" },
  { href: "/sessions", name: "Sessions", desc: "Every episode: cycle, D/I/F, plan, tool calls, pillars" },
  { href: "/subagents", name: "Subagents", desc: "Work split across signed, isolated subagents" },
  { href: "/growth", name: "Growth", desc: "MEE growth, D per episode, what got faster or cheaper" },
  { href: "/memory", name: "Memory", desc: "What the agent knows about you; add facts" },
  { href: "/algorithms", name: "Algorithms", desc: "The 41 algorithms as pipeline stages, measured" },
  { href: "/approvals", name: "Approvals", desc: "Signed human approvals that resume paused work" },
  { href: "/sovereignty", name: "Sovereignty", desc: "Where prompts may go: the data-residency policy and every decision" },
  { href: "/jitna", name: "JITNA", desc: "Check a signed .jitna file and read the intent it carries" },
  { href: "/audit", name: "Audit", desc: "Hash chain, notary, anchoring" },
  { href: "/llm", name: "Models", desc: "Choose the provider and model" },
  { href: "/skills", name: "Skills", desc: "What was learned, how reliable it has been" },
  { href: "/tools", name: "Tools", desc: "The tool registry and how each tool is gated" },
  { href: "/cron", name: "Cron", desc: "Daemon tasks" },
  { href: "/channels", name: "Channels", desc: "Messaging gateways and their allowlists" },
  { href: "/experiments", name: "Experiments", desc: "RCTDB runs grouped by goal" },
  { href: "/settings", name: "Settings", desc: "Gateway address and API token" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setIndex(0);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? ROUTES.filter((r) => `${r.name} ${r.desc}`.toLowerCase().includes(q)) : ROUTES;
  }, [query]);

  if (!open) return null;

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-start justify-center bg-black/60 px-4 pt-24"
      onMouseDown={(e) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); }}>
      <div ref={box} role="dialog" aria-label="Go to page" className="flex max-h-[420px] w-full max-w-lg flex-col overflow-hidden rounded-md border border-dl-rule bg-dl-panel shadow-2xl">
        <input autoFocus value={query} placeholder="Go to…" aria-label="Search pages"
          onChange={(e) => { setQuery(e.target.value); setIndex(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => (i + 1) % Math.max(shown.length, 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => (i - 1 + shown.length) % Math.max(shown.length, 1)); }
            if (e.key === "Enter" && shown[index]) { e.preventDefault(); go(shown[index].href); }
          }}
          className="desk-mono border-b border-dl-rule bg-transparent px-4 py-3 text-sm text-dl-text outline-none placeholder:text-dl-muted" />
        <ul className="min-h-0 flex-1 overflow-y-auto p-1">
          {shown.length === 0 ? <li className="px-3 py-6 text-center text-sm text-dl-muted">No page matches.</li> : null}
          {shown.map((r, i) => (
            <li key={r.href}>
              <button onClick={() => go(r.href)} onMouseEnter={() => setIndex(i)} aria-current={i === index ? "true" : undefined}
                className="flex w-full items-baseline justify-between gap-4 rounded px-3 py-2 text-left hover:bg-dl-pine/40 aria-[current=true]:bg-dl-pine/60">
                <span className="desk-mono text-sm text-dl-text">{r.name}</span>
                <span className="truncate text-xs text-dl-muted">{r.desc}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
