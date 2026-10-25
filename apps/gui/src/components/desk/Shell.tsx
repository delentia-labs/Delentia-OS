"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity, BookOpen, Brain, FileCheck2, Hammer, Scale, Globe2, Clock, Cpu, FlaskConical, GitBranch, History, Layers, Link2, Menu, Radio,
  Settings, ShieldCheck, SquareTerminal, TrendingUp, UserCog, Wrench, X, Landmark, PenLine, Undo2, OctagonPause, Anchor, GraduationCap, Gavel,
} from "lucide-react";
import { DelentiaMark } from "./mark";
import { LangProvider, useLang, type DictKey } from "./i18n";
import { useDeskData } from "./ui";
import { desk } from "@/lib/desk-api";
import { loadLocalConfig } from "@/lib/local-config";
import { MODE_EVENT, MODE_KEY } from "./mode";
import { GROUPS, SIMPLE, groupOf, parseMode, type DeskMode, type NavItem } from "@/lib/nav-model";

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
  { href: "/hooks", key: "hooks", icon: Anchor },
  { href: "/learning", key: "learning", icon: GraduationCap },
  { href: "/law", key: "law", icon: Gavel },
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

function SystemPanel({ mode, setMode }: { mode: DeskMode; setMode: (m: DeskMode) => void }) {
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
          <dt className="text-dl-muted">{t("questions")}</dt>
          <dd>
            {o && (o.questions_pending ?? 0) > 0 ? (
              <Link href="/approvals" className="desk-focus text-dl-amber underline underline-offset-2">
                {o.questions_pending} {t("pending")}
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
      <div role="group" aria-label="Menu" className="desk-mono mt-4 flex overflow-hidden rounded border border-dl-rule text-[11px] text-dl-muted">
        {(["simple", "advanced"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
            className={`desk-focus flex-1 px-2 py-1 ${mode === m ? "bg-dl-pine text-dl-text" : "hover:text-dl-text"}`}>
            {t(`mode_${m}` as DictKey)}
          </button>
        ))}
      </div>
      <div className="desk-mono mt-3 flex items-center justify-between text-[11px] text-dl-muted">
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

const ICON_OF: Record<string, typeof Activity> = Object.fromEntries(PRIMARY.map((p) => [p.href, p.icon]));

function NavLink({ item, pathname, onNavigate }: { item: NavItem; pathname: string; onNavigate?: () => void }) {
  const { t } = useLang();
  const Icon = ICON_OF[item.href] ?? Activity;
  return (
    <li>
      <Link href={item.href} onClick={onNavigate} aria-current={isActive(pathname, item.href) ? "page" : undefined} className="desk-nav-link">
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        {t(item.key)}
      </Link>
    </li>
  );
}

/** Simple mode: Status and five pages, flat. Advanced: Status, then five groups (the group that holds the current page is open; the others are folded). */
function Nav({ mode, onNavigate }: { mode: DeskMode; onNavigate?: () => void }) {
  const pathname = usePathname() || "/";
  const { t } = useLang();
  const activeGroup = groupOf(pathname);
  const [opened, setOpened] = useState<Record<string, boolean>>({ work: true });

  return (
    <nav aria-label="Desk" className="min-h-0 flex-1 overflow-y-auto py-3">
      <ul>
        <NavLink item={{ href: "/", key: "status" }} pathname={pathname} onNavigate={onNavigate} />
      </ul>
      {mode === "simple" ? (
        <ul>
          {SIMPLE.map((item) => <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />)}
        </ul>
      ) : (
        GROUPS.map((g) => {
          const isOpen = g.id === activeGroup || !!opened[g.id];
          return (
            <section key={g.id} className="mt-2">
              <button type="button" aria-expanded={isOpen} onClick={() => setOpened((o) => ({ ...o, [g.id]: !isOpen }))}
                className="desk-focus desk-mono flex w-full items-center justify-between px-5 py-1.5 text-[11px] uppercase tracking-[0.1em] text-dl-muted hover:text-dl-text">
                <span>{t(`group_${g.id}` as DictKey)}</span>
                <span aria-hidden>{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen ? <ul>{g.items.map((item) => <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />)}</ul> : null}
            </section>
          );
        })
      )}
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
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  // Simple is the default (a first visit, a cleared browser, or a browser that refuses storage all start in Simple).
  const [mode, setModeState] = useState<DeskMode>(() => {
    try { return parseMode(window.localStorage.getItem(MODE_KEY)); } catch { return "simple"; }
  });
  const setMode = (m: DeskMode) => {
    setModeState(m);
    try { window.localStorage.setItem(MODE_KEY, m); } catch { /* the choice just is not remembered */ }
    window.dispatchEvent(new Event(MODE_EVENT));            // pages that read the mode (the chat welcome) follow the sidebar at once
  };
  return (
    <div className="desk-root flex h-screen w-screen overflow-hidden">
      <aside aria-label={lang === "th" ? "เมนู Delentia" : "Delentia menu"} className="hidden w-64 shrink-0 flex-col border-r border-dl-rule bg-dl-panel md:flex">
        <Brand />
        <Nav mode={mode} />
        <SystemPanel mode={mode} setMode={setMode} />
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
            <Nav mode={mode} onNavigate={() => setOpen(false)} />
            <SystemPanel mode={mode} setMode={setMode} />
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
  // Round 92: when the one-click launcher serves this page it also hands over the host address and the owner's token; nothing may call the API before that has been read.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    void loadLocalConfig().finally(() => {
      if (alive) setReady(true);
    });
    return () => {
      alive = false;
    };
  }, []);
  if (!ready) return <div className="h-screen w-screen" style={{ background: "var(--dl-ink)" }} />;
  return (
    <LangProvider>
      <ShellInner>{children}</ShellInner>
    </LangProvider>
  );
}
