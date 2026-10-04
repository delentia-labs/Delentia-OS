"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity, BookOpen, Brain, FileCheck2, Hammer, Scale, Globe2, Clock, Cpu, FlaskConical, GitBranch, History, Layers, Link2, Menu, Radio,
  Settings, ShieldCheck, SquareTerminal, TrendingUp, UserCog, Wrench, X, Landmark, PenLine, Undo2, OctagonPause,
} from "lucide-react";
import { DelentiaMark } from "./mark";
import { LangProvider, useLang, type DictKey } from "./i18n";
import { useDeskData } from "./ui";
import { desk } from "@/lib/desk-api";

// Order follows Hermes' dashboard (chat first), with Delentia's own pages
// (approvals, audit, experiments) where Hermes has pairing, logs, analytics.
const PRIMARY: { href: string; key: DictKey; icon: typeof Activity }[] = [
  { href: "/", key: "status", icon: Activity },
  { href: "/chat", key: "chat", icon: SquareTerminal },
  { href: "/sessions", key: "sessions", icon: History },
  { href: "/subagents", key: "subagents", icon: GitBranch },
  { href: "/growth", key: "growth", icon: TrendingUp },
  { href: "/memory", key: "memory", icon: Brain },
  { href: "/algorithms", key: "algorithms", icon: Layers },
  { href: "/governance", key: "governance", icon: Landmark },
  { href: "/fdia", key: "fdia", icon: Scale },
  { href: "/forge", key: "forge", icon: Hammer },
  { href: "/safety", key: "safety", icon: OctagonPause },
  { href: "/approvals", key: "approvals", icon: ShieldCheck },
  { href: "/signatures", key: "signatures", icon: PenLine },
  { href: "/checkpoints", key: "checkpoints", icon: Undo2 },
  { href: "/identity", key: "identity", icon: UserCog },
  { href: "/sovereignty", key: "sovereignty", icon: Globe2 },
  { href: "/jitna", key: "jitna", icon: FileCheck2 },
  { href: "/audit", key: "audit", icon: Link2 },
  { href: "/llm", key: "models", icon: Cpu },
  { href: "/skills", key: "skills", icon: BookOpen },
  { href: "/tools", key: "tools", icon: Wrench },
  { href: "/cron", key: "cron", icon: Clock },
  { href: "/channels", key: "channels", icon: Radio },
  { href: "/experiments", key: "experiments", icon: FlaskConical },
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
