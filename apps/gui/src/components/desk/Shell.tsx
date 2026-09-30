"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity, BookOpen, ChevronDown, Clock, Cpu, FlaskConical, GitBranch, History, Link2, Menu, Radio,
  Settings, ShieldCheck, SquareTerminal, Wrench, X,
} from "lucide-react";
import { DelentiaMark } from "./mark";
import { LangProvider, useLang, type DictKey } from "./i18n";
import { LegacyNotice } from "./LegacyNotice";
import { useDeskData } from "./ui";
import { desk } from "@/lib/desk-api";

// Order follows Hermes' dashboard (chat first), with Delentia's own pages
// (approvals, audit, experiments) where Hermes has pairing, logs, analytics.
const PRIMARY: { href: string; key: DictKey; icon: typeof Activity }[] = [
  { href: "/", key: "status", icon: Activity },
  { href: "/chat", key: "chat", icon: SquareTerminal },
  { href: "/sessions", key: "sessions", icon: History },
  { href: "/subagents", key: "subagents", icon: GitBranch },
  { href: "/approvals", key: "approvals", icon: ShieldCheck },
  { href: "/audit", key: "audit", icon: Link2 },
  { href: "/llm", key: "models", icon: Cpu },
  { href: "/skills", key: "skills", icon: BookOpen },
  { href: "/tools", key: "tools", icon: Wrench },
  { href: "/cron", key: "cron", icon: Clock },
  { href: "/channels", key: "channels", icon: Radio },
  { href: "/experiments", key: "experiments", icon: FlaskConical },
];

// Earlier Desk pages, kept reachable while they are reworked.
const LABS: { href: string; label: string }[] = [
  { href: "/memory", label: "Memory timeline" },
  { href: "/brains", label: "Brain slots" },
  { href: "/models", label: "Local SLM" },
  { href: "/workflow", label: "JITNA workflows" },
  { href: "/ecosystem", label: "Ecosystem" },
  { href: "/monitor", label: "Monitor" },
  { href: "/discovery", label: "Discovery" },
  { href: "/sandbox", label: "Living sandbox" },
  { href: "/profiler", label: "Deep profiler" },
  { href: "/enterprise", label: "Enterprise vault" },
  { href: "/billing", label: "Billing" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function SystemPanel() {
  const { t, lang, setLang } = useLang();
  const health = useDeskData(() => desk.health(), [], 15000);
  const overview = useDeskData(() => desk.overview(), [], 15000);
  const up = !health.error && !!health.data;
  const o = overview.data;
  const chain = o?.audit_verify?.status;

  return (
    <div className="border-t border-dl-rule px-5 py-4 text-[12px]">
      <p className="desk-mono mb-2 text-dl-muted">{t("system")}</p>
      <dl className="desk-mono space-y-1.5">
        <div className="flex justify-between gap-2">
          <dt className="text-dl-muted">API</dt>
          <dd className={up ? "text-dl-leaf" : "text-dl-rust"}>
            {health.loading && !health.data ? "…" : up ? `${t("api_up")} v${health.data?.version ?? "?"}` : t("api_down")}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-dl-muted">{t("daemon")}</dt>
          <dd className="text-dl-text">{o ? (o.daemon.running ? t("running") : t("stopped")) : "-"}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-dl-muted">{t("approvals")}</dt>
          <dd>
            {o && o.approvals_pending > 0 ? (
              <Link href="/approvals" className="desk-focus text-dl-amber underline underline-offset-2">
                {o.approvals_pending} {t("pending")}
              </Link>
            ) : (
              <span className="text-dl-text">{o ? 0 : "-"}</span>
            )}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-dl-muted">{t("chain")}</dt>
          <dd className={chain === "FAILED" ? "text-dl-rust" : "text-dl-text"} title={o?.audit_verify?.output ?? undefined}>
            {!o || !o.audit_verify ? "-" : chain === "SUCCESS" ? t("verified") : chain === "FAILED" ? t("broken") : t("not_checked")}
          </dd>
        </div>
      </dl>
      <div className="desk-mono mt-4 flex items-center justify-between text-[11px] text-dl-muted">
        <Link href="/settings" className="desk-focus inline-flex items-center gap-1.5 hover:text-dl-text">
          <Settings className="h-3.5 w-3.5" aria-hidden /> {t("settings")}
        </Link>
        <div role="group" aria-label="Language" className="flex overflow-hidden rounded border border-dl-rule">
          {(["th", "en"] as const).map((l) => (
            <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
              className={`desk-focus px-2 py-0.5 uppercase ${lang === l ? "bg-dl-pine text-dl-text" : "hover:text-dl-text"}`}>
              {l}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname() || "/";
  const { t } = useLang();
  const [labsOpen, setLabsOpen] = useState(LABS.some((l) => isActive(pathname, l.href)));

  return (
    <nav aria-label="Desk" className="min-h-0 flex-1 overflow-y-auto py-3">
      <ul>
        {PRIMARY.map(({ href, key, icon: Icon }) => (
          <li key={href}>
            <Link href={href} onClick={onNavigate} aria-current={isActive(pathname, href) ? "page" : undefined} className="desk-nav-link">
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {t(key)}
            </Link>
          </li>
        ))}
      </ul>
      <button onClick={() => setLabsOpen((v) => !v)} aria-expanded={labsOpen}
        className="desk-nav-link desk-focus mt-3 w-full justify-between">
        <span>{t("labs")}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${labsOpen ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {labsOpen ? (
        <ul className="pb-2">
          {LABS.map((item) => (
            <li key={item.href}>
              <Link href={item.href} onClick={onNavigate} aria-current={isActive(pathname, item.href) ? "page" : undefined}
                className="desk-focus block border-l-2 border-transparent py-1.5 pl-12 pr-4 text-[13px] text-dl-muted hover:text-dl-text aria-[current=page]:border-dl-leaf aria-[current=page]:text-dl-text">
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/" className="desk-focus flex items-center gap-3 px-5 py-5">
      <DelentiaMark size={34} />
      <span className="desk-mono text-[15px] font-semibold leading-[1.05] tracking-[0.14em] text-dl-text">
        DELENTIA<br />AGENT
      </span>
    </Link>
  );
}

function ShellInner({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="desk-root flex h-screen w-screen overflow-hidden">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-dl-rule bg-dl-panel md:flex">
        <Brand />
        <Nav />
        <SystemPanel />
      </aside>

      {open ? (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="flex w-72 flex-col border-r border-dl-rule bg-dl-panel">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label="Close menu" className="desk-focus p-2 text-dl-muted">
                <X className="h-5 w-5" />
              </button>
            </div>
            <Nav onNavigate={() => setOpen(false)} />
            <SystemPanel />
          </div>
          <button aria-label="Close menu" className="flex-1 bg-black/50" onClick={() => setOpen(false)} />
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-dl-rule bg-dl-panel px-4 py-2.5 md:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="desk-focus text-dl-muted">
            <Menu className="h-5 w-5" />
          </button>
          <DelentiaMark size={22} />
          <span className="desk-mono text-sm tracking-[0.14em]">DELENTIA</span>
        </div>
        <LegacyNotice />
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}

export function DeskShell({ children }: { children: React.ReactNode }) {
  return (
    <LangProvider>
      <ShellInner>{children}</ShellInner>
    </LangProvider>
  );
}
