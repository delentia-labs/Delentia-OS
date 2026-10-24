/**
 * The Desk's menu as data: five groups for the full (Advanced) menu and a short list for Simple mode.
 * Pure (no React), so a node test can check that every page is reachable and listed exactly once.
 */
export type NavKey =
  | "chat" | "sessions" | "subagents" | "cron" | "checkpoints"
  | "approvals" | "signatures" | "fdia" | "governance" | "audit" | "safety" | "sovereignty" | "hooks" | "jitna"
  | "memory" | "skills" | "growth" | "learning" | "law" | "forge" | "algorithms" | "experiments"
  | "models" | "tools" | "channels"
  | "identity"
  | "status";                                   // Status is shown on its own above the groups and is in none of them

export type NavGroupId = "work" | "gates" | "memory" | "connect" | "system";
export type NavItem = { href: string; key: NavKey };
export type NavGroup = { id: NavGroupId; items: NavItem[] };

// Work: what the agent is doing for you. Gates: what stands between the agent and an effect, and the proof afterwards.
// Memory and learning: what it knows and has learned. Connect: where it gets models, tools and messages. System: who may use it.
export const GROUPS: NavGroup[] = [
  { id: "work", items: [
    { href: "/chat", key: "chat" }, { href: "/sessions", key: "sessions" }, { href: "/subagents", key: "subagents" },
    { href: "/cron", key: "cron" }, { href: "/checkpoints", key: "checkpoints" },
  ] },
  { id: "gates", items: [
    { href: "/approvals", key: "approvals" }, { href: "/signatures", key: "signatures" }, { href: "/fdia", key: "fdia" },
    { href: "/governance", key: "governance" }, { href: "/audit", key: "audit" }, { href: "/safety", key: "safety" },
    { href: "/sovereignty", key: "sovereignty" }, { href: "/hooks", key: "hooks" }, { href: "/jitna", key: "jitna" },
  ] },
  { id: "memory", items: [
    { href: "/memory", key: "memory" }, { href: "/skills", key: "skills" }, { href: "/growth", key: "growth" },
    { href: "/learning", key: "learning" }, { href: "/law", key: "law" }, { href: "/forge", key: "forge" },
    { href: "/algorithms", key: "algorithms" }, { href: "/experiments", key: "experiments" },
  ] },
  { id: "connect", items: [
    { href: "/llm", key: "models" }, { href: "/tools", key: "tools" }, { href: "/channels", key: "channels" },
  ] },
  { id: "system", items: [{ href: "/identity", key: "identity" }] },
];

/** What Simple mode shows besides Status: the things a person needs to use the agent and to stay in control of it. Nothing about safety is hidden:
 *  approvals are in the list, and the Inspector on the chat page still shows every gate verdict. */
export const SIMPLE: NavItem[] = [
  { href: "/chat", key: "chat" }, { href: "/sessions", key: "sessions" }, { href: "/approvals", key: "approvals" },
  { href: "/memory", key: "memory" }, { href: "/llm", key: "models" },
];

export type DeskMode = "simple" | "advanced";

export function allItems(): NavItem[] {
  return GROUPS.flatMap((g) => g.items);
}

/** The group a path belongs to, or null (Status, Settings and unknown paths belong to none). */
export function groupOf(pathname: string): NavGroupId | null {
  const hit = allItems().find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  if (!hit) return null;
  return GROUPS.find((g) => g.items.includes(hit))?.id ?? null;
}

export function parseMode(value: string | null | undefined): DeskMode {
  return value === "advanced" ? "advanced" : "simple";        // anything else, including nothing saved, is Simple
}
