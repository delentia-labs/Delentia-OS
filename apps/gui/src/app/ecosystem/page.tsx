"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Search, Shield, ShieldCheck, ShieldAlert, Globe, Zap, Code2,
  Package, Cpu, FileText, DollarSign, Languages, BarChart3,
  MessageSquare, Github, RefreshCw, ExternalLink, ChevronRight,
  Lock, Unlock, Filter, SortAsc, LayoutGrid, List, Star,
  CheckCircle2, AlertCircle, Clock, Tag, Network, Bot,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface AdapterManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  jitna_channel: string;
  regional_support: string[];
  tags: string[];
  security_scan_passed: boolean;
  permissions: string[];
}
interface SkillManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  jitna_channel: string;
  tags: string[];
  security_scan_passed: boolean;
}
interface RegistryResponse {
  adapters: AdapterManifest[];
  skills: SkillManifest[];
}

// ─── Adapter icon map (inline SVG brand colors) ───────────────────────────────
const ADAPTER_META: Record<string, { color: string; bg: string; icon: string }> = {
  "line-adapter":      { color: "#06C755", bg: "rgba(6,199,85,0.12)",    icon: "💬" },
  "slack-adapter":     { color: "#4A154B", bg: "rgba(74,21,75,0.15)",    icon: "⚡" },
  "whatsapp-adapter":  { color: "#25D366", bg: "rgba(37,211,102,0.12)",  icon: "📱" },
  "telegram-adapter":  { color: "#2AABEE", bg: "rgba(42,171,238,0.12)",  icon: "✈️" },
  "discord-adapter":   { color: "#5865F2", bg: "rgba(88,101,242,0.12)",  icon: "🎮" },
  "github-adapter":    { color: "#e6edf3", bg: "rgba(230,237,243,0.08)", icon: "⚙️" },
  "notion-adapter":    { color: "#e6e6e6", bg: "rgba(230,230,230,0.08)", icon: "📝" },
};

const SKILL_META: Record<string, { color: string; bg: string; icon: string }> = {
  "thai-language-skill":    { color: "#3b82f6", bg: "rgba(59,130,246,0.12)",  icon: "🌏" },
  "legal-pdpa-skill":       { color: "#f59e0b", bg: "rgba(245,158,11,0.12)",  icon: "⚖️" },
  "thai-nlp-skill":         { color: "#10b981", bg: "rgba(16,185,129,0.12)",  icon: "🧠" },
  "web-search-skill":       { color: "#6366f1", bg: "rgba(99,102,241,0.12)",  icon: "🔍" },
  "document-summary-skill": { color: "#8b5cf6", bg: "rgba(139,92,246,0.12)", icon: "📄" },
  "financial-analysis-skill":{ color: "#ec4899", bg: "rgba(236,72,153,0.12)", icon: "📊" },
};

// ─── Permission Icon Map ──────────────────────────────────────────────────────
function PermIcon({ perm }: { perm: string }) {
  if (perm.includes("write")) return <Lock size={10} className="text-amber-400" />;
  if (perm.includes("read"))  return <Unlock size={10} className="text-emerald-400" />;
  if (perm.includes("execute")) return <Zap size={10} className="text-indigo-400" />;
  if (perm.includes("media")) return <FileText size={10} className="text-blue-400" />;
  return <Tag size={10} className="text-gray-500" />;
}

// ─── Adapter Card ─────────────────────────────────────────────────────────────
function AdapterCard({ adapter, view }: { adapter: AdapterManifest; view: "grid" | "list" }) {
  const meta = ADAPTER_META[adapter.id] ?? { color: "#6366f1", bg: "rgba(99,102,241,0.12)", icon: "🔌" };

  if (view === "list") {
    return (
      <div className="group flex items-center gap-4 bg-surface-card border border-surface-border rounded-xl px-4 py-3 hover:border-white/15 transition-all duration-200 cursor-pointer">
        {/* Icon */}
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center text-lg shrink-0 transition-transform duration-200 group-hover:scale-110"
          style={{ background: meta.bg, border: `1px solid ${meta.color}30` }}
        >
          {meta.icon}
        </div>
        {/* Name + ID */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-gray-100 group-hover:text-white truncate">{adapter.name}</p>
            <span className="text-[9px] font-mono text-gray-600 shrink-0">v{adapter.version}</span>
          </div>
          <p className="text-[11px] text-gray-500 truncate">{adapter.description}</p>
        </div>
        {/* Channel */}
        <span className="text-[10px] font-mono px-2 py-1 rounded-lg shrink-0" style={{ color: meta.color, background: meta.bg }}>
          {adapter.jitna_channel}
        </span>
        {/* Regions */}
        <div className="hidden md:flex items-center gap-1 shrink-0">
          {adapter.regional_support.slice(0, 3).map((r) => (
            <span key={r} className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-900/30 text-indigo-400 border border-indigo-700/20">{r}</span>
          ))}
        </div>
        {/* Verified */}
        <div className="shrink-0">
          {adapter.security_scan_passed ? (
            <CheckCircle2 size={16} className="text-emerald-400" />
          ) : (
            <AlertCircle size={16} className="text-amber-400" />
          )}
        </div>
        <ChevronRight size={14} className="text-gray-700 group-hover:text-gray-400 shrink-0 transition" />
      </div>
    );
  }

  return (
    <div
      className="group bg-surface-card border border-surface-border rounded-2xl p-4 flex flex-col gap-3 hover:border-white/15 transition-all duration-200 cursor-pointer relative overflow-hidden"
      style={{ "--card-glow": meta.color } as React.CSSProperties}
    >
      {/* Subtle glow background on hover */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none rounded-2xl"
        style={{ background: `radial-gradient(ellipse at 0% 0%, ${meta.color}08 0%, transparent 60%)` }}
      />

      {/* Header */}
      <div className="flex items-start justify-between gap-2 relative">
        <div className="flex items-center gap-2.5">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0 transition-transform duration-200 group-hover:scale-110"
            style={{ background: meta.bg, border: `1px solid ${meta.color}30`, boxShadow: `0 0 12px ${meta.color}15` }}
          >
            {meta.icon}
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-100 group-hover:text-white transition leading-tight">{adapter.name}</p>
            <p className="text-[9px] font-mono text-gray-600">{adapter.id} · v{adapter.version}</p>
          </div>
        </div>

        {/* Security badge */}
        {adapter.security_scan_passed ? (
          <div className="flex items-center gap-1 text-[9px] px-2 py-1 rounded-full bg-emerald-900/30 text-emerald-400 border border-emerald-700/30 shrink-0">
            <ShieldCheck size={9} />
            <span>Verified</span>
          </div>
        ) : (
          <div className="flex items-center gap-1 text-[9px] px-2 py-1 rounded-full bg-amber-900/30 text-amber-400 border border-amber-700/30 shrink-0">
            <ShieldAlert size={9} />
            <span>Pending</span>
          </div>
        )}
      </div>

      {/* Description */}
      <p className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed relative">{adapter.description}</p>

      {/* JITNA Channel */}
      <div className="flex items-center gap-1.5 relative">
        <Network size={10} style={{ color: meta.color }} />
        <span className="text-[10px] font-mono" style={{ color: meta.color }}>{adapter.jitna_channel}</span>
      </div>

      {/* Regions + Tags */}
      <div className="flex flex-wrap gap-1 relative">
        {adapter.regional_support.map((r) => (
          <span key={r} className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-indigo-900/30 text-indigo-400 border border-indigo-700/20">
            <Globe size={8} />
            {r}
          </span>
        ))}
        {adapter.tags.slice(0, 2).map((t) => (
          <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-surface text-gray-600 border border-surface-border">{t}</span>
        ))}
      </div>

      {/* Footer */}
      <div className="pt-2 border-t border-surface-border flex items-center justify-between relative">
        <div className="flex items-center gap-1">
          {adapter.permissions.slice(0, 4).map((p) => (
            <div key={p} title={p} className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-black/20 border border-white/5">
              <PermIcon perm={p} />
              <span className="text-gray-600">{p.split(":")[0]}</span>
            </div>
          ))}
        </div>
        <button className="flex items-center gap-1 text-[10px] text-gray-600 hover:text-gray-300 transition group-hover:text-gray-400">
          <span>Details</span>
          <ExternalLink size={9} />
        </button>
      </div>
    </div>
  );
}

// ─── Skill Card ───────────────────────────────────────────────────────────────
function SkillCard({ skill, view }: { skill: SkillManifest; view: "grid" | "list" }) {
  const meta = SKILL_META[skill.id] ?? { color: "#8b5cf6", bg: "rgba(139,92,246,0.12)", icon: "✨" };

  if (view === "list") {
    return (
      <div className="group flex items-center gap-4 bg-surface-card border border-surface-border rounded-xl px-4 py-3 hover:border-white/15 transition-all duration-200 cursor-pointer">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg shrink-0 transition-transform duration-200 group-hover:scale-110"
          style={{ background: meta.bg, border: `1px solid ${meta.color}30` }}>
          {meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-gray-100 group-hover:text-white truncate">{skill.name}</p>
            <span className="text-[9px] font-mono text-gray-600 shrink-0">v{skill.version}</span>
          </div>
          <p className="text-[11px] text-gray-500 truncate">{skill.description}</p>
        </div>
        <div className="hidden md:flex gap-1 shrink-0">
          {skill.tags.slice(0, 3).map((t) => (
            <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-surface text-gray-600 border border-surface-border">{t}</span>
          ))}
        </div>
        <div className="shrink-0">
          {skill.security_scan_passed ? <CheckCircle2 size={16} className="text-emerald-400" /> : <AlertCircle size={16} className="text-amber-400" />}
        </div>
        <ChevronRight size={14} className="text-gray-700 group-hover:text-gray-400 shrink-0 transition" />
      </div>
    );
  }

  return (
    <div className="group bg-surface-card border border-surface-border rounded-2xl p-4 flex flex-col gap-3 hover:border-white/15 transition-all duration-200 cursor-pointer relative overflow-hidden">
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none rounded-2xl"
        style={{ background: `radial-gradient(ellipse at 0% 0%, ${meta.color}08 0%, transparent 60%)` }} />

      <div className="flex items-start justify-between gap-2 relative">
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0 transition-transform group-hover:scale-110"
            style={{ background: meta.bg, border: `1px solid ${meta.color}30`, boxShadow: `0 0 12px ${meta.color}15` }}>
            {meta.icon}
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-100 group-hover:text-white transition leading-tight">{skill.name}</p>
            <p className="text-[9px] font-mono text-gray-600">{skill.id} · v{skill.version}</p>
          </div>
        </div>
        {skill.security_scan_passed ? (
          <div className="flex items-center gap-1 text-[9px] px-2 py-1 rounded-full bg-emerald-900/30 text-emerald-400 border border-emerald-700/30 shrink-0">
            <ShieldCheck size={9} /><span>Verified</span>
          </div>
        ) : (
          <div className="flex items-center gap-1 text-[9px] px-2 py-1 rounded-full bg-amber-900/30 text-amber-400 border border-amber-700/30 shrink-0">
            <Clock size={9} /><span>Scanning</span>
          </div>
        )}
      </div>

      <p className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed relative">{skill.description}</p>

      <div className="flex items-center gap-1.5 relative">
        <Bot size={10} style={{ color: meta.color }} />
        <span className="text-[10px] font-mono" style={{ color: meta.color }}>{skill.jitna_channel}</span>
      </div>

      <div className="flex flex-wrap gap-1 mt-auto relative">
        {skill.tags.slice(0, 4).map((t) => (
          <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-surface text-gray-600 border border-surface-border">{t}</span>
        ))}
      </div>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, color, sub }: {
  icon: React.ElementType; label: string; value: number | string; color: string; sub?: string;
}) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex items-center gap-3 hover:border-white/10 transition">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${color}15`, border: `1px solid ${color}25` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <p className="text-xl font-extrabold font-mono tracking-tight" style={{ color }}>{value}</p>
        <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
        {sub && <p className="text-[9px] text-gray-700">{sub}</p>}
      </div>
    </div>
  );
}

// ─── Offline Banner ───────────────────────────────────────────────────────────
function OfflineBanner() {
  return (
    <div className="flex items-center gap-3 bg-amber-950/20 border border-amber-700/30 rounded-xl px-4 py-3">
      <AlertCircle size={15} className="text-amber-400 shrink-0" />
      <div className="flex-1">
        <p className="text-xs font-semibold text-amber-300">Registry Offline</p>
        <p className="text-[10px] text-amber-400/70">Ecosystem registry at port 8090 is unreachable. Displaying cached offline manifest data.</p>
      </div>
      <span className="text-[9px] px-2 py-1 rounded-full bg-amber-900/30 text-amber-400 border border-amber-700/30 font-mono shrink-0">
        OFFLINE MODE
      </span>
    </div>
  );
}

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const MOCK_ADAPTERS: AdapterManifest[] = [
  { id: "line-adapter",     name: "LINE Messaging",           version: "1.0.0", description: "Connects LINE Messaging API to Delentia OS for Thai user engagement", jitna_channel: "line", regional_support: ["TH","JP","TW"], tags: ["messaging","line","th"], security_scan_passed: false, permissions: ["intent:read","intent:execute"] },
  { id: "slack-adapter",    name: "Slack Workspace",          version: "1.0.0", description: "Full Slack integration via JITNA v3 with slash commands and events", jitna_channel: "slack", regional_support: ["GLOBAL"], tags: ["messaging","slack","enterprise"], security_scan_passed: false, permissions: ["intent:read","intent:execute"] },
  { id: "whatsapp-adapter", name: "WhatsApp Business",        version: "1.0.0", description: "WhatsApp Business Cloud API — media, template, and live chat support", jitna_channel: "whatsapp", regional_support: ["TH","BR","IN","US"], tags: ["messaging","whatsapp","business"], security_scan_passed: true, permissions: ["intent:read","intent:execute","media:read"] },
  { id: "telegram-adapter", name: "Telegram Bot",             version: "1.0.0", description: "Telegram Bot API — inline buttons, webhooks, and group management", jitna_channel: "telegram", regional_support: ["GLOBAL"], tags: ["messaging","telegram","bot"], security_scan_passed: true, permissions: ["intent:read","intent:execute"] },
  { id: "discord-adapter",  name: "Discord Bot",              version: "1.0.0", description: "Discord slash commands and thread-based intent routing", jitna_channel: "discord", regional_support: ["GLOBAL"], tags: ["discord","developer","gaming"], security_scan_passed: true, permissions: ["intent:read","intent:execute"] },
  { id: "github-adapter",   name: "GitHub App",               version: "1.0.0", description: "GitHub webhook events → JITNA pipeline for CI/CD automation", jitna_channel: "github", regional_support: ["GLOBAL"], tags: ["github","ci-cd","devops"], security_scan_passed: true, permissions: ["intent:read","intent:execute","data:write"] },
  { id: "notion-adapter",   name: "Notion Integration",       version: "1.0.0", description: "Notion workspace read/write with database and page synchronization", jitna_channel: "notion", regional_support: ["GLOBAL"], tags: ["notion","enterprise","productivity"], security_scan_passed: true, permissions: ["intent:read","intent:execute","data:read","data:write"] },
];

const MOCK_SKILLS: SkillManifest[] = [
  { id: "thai-language-skill",    name: "Thai Constitutional Language", version: "1.0.0", description: "PDPA compliance checking and Thai legal document parsing with constitutional AI", jitna_channel: "thai-language", tags: ["thai","pdpa","legal","constitutional"], security_scan_passed: false },
  { id: "legal-pdpa-skill",       name: "Legal PDPA Engine",           version: "1.0.0", description: "Full Thai PDPA legal compliance engine with article-level citation", jitna_channel: "legal-pdpa", tags: ["legal","pdpa","compliance"], security_scan_passed: false },
  { id: "thai-nlp-skill",         name: "Thai NLP Advanced",           version: "1.0.0", description: "PyThaiNLP + Typhoon v2 ML-powered Thai text analysis and generation", jitna_channel: "thai-nlp", tags: ["thai","nlp","ml","typhoon"], security_scan_passed: true },
  { id: "web-search-skill",       name: "Web Search & RAG",            version: "1.0.0", description: "Real-time web search via Tavily API with RAG-grounded retrieval", jitna_channel: "web-search", tags: ["search","retrieval","rag","tavily"], security_scan_passed: true },
  { id: "document-summary-skill", name: "Document Summarizer",         version: "1.0.0", description: "PDF/DOCX intelligent summarization with EN/TH bilingual output", jitna_channel: "document-summary", tags: ["documents","summary","pdf","bilingual"], security_scan_passed: true },
  { id: "financial-analysis-skill", name: "Thai Financial Analyst",    version: "1.0.0", description: "Thai GAAP financial analysis, SET compliance, and risk assessment", jitna_channel: "financial-analysis", tags: ["financial","thai-gaap","set","risk"], security_scan_passed: true },
];

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function EcosystemPage() {
  const ecosystemUrl = process.env.NEXT_PUBLIC_ECOSYSTEM_URL ?? "http://localhost:8090";

  const [adapters, setAdapters] = useState<AdapterManifest[]>([]);
  const [skills, setSkills]     = useState<SkillManifest[]>([]);
  const [loading, setLoading]   = useState(true);
  const [offline, setOffline]   = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | "adapters" | "skills">("all");
  const [search, setSearch]     = useState("");
  const [view, setView]         = useState<"grid" | "list">("grid");
  const [filterVerified, setFilterVerified] = useState<"all" | "verified" | "pending">("all");

  // Fetch
  useEffect(() => {
    const fetchRegistry = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${ecosystemUrl}/registry`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data: RegistryResponse = await res.json();
        setAdapters(data.adapters ?? []);
        setSkills(data.skills ?? []);
        setOffline(false);
      } catch {
        setOffline(true);
        setAdapters(MOCK_ADAPTERS);
        setSkills(MOCK_SKILLS);
      } finally {
        setLoading(false);
      }
    };
    fetchRegistry();
  }, [ecosystemUrl]);

  // Filter + search
  const { filteredAdapters, filteredSkills } = useMemo(() => {
    const q = search.toLowerCase();
    const matchAdapter = (a: AdapterManifest) => {
      const text = `${a.name} ${a.id} ${a.tags.join(" ")} ${a.description}`.toLowerCase();
      if (q && !text.includes(q)) return false;
      if (filterVerified === "verified" && !a.security_scan_passed) return false;
      if (filterVerified === "pending"  && a.security_scan_passed)  return false;
      return true;
    };
    const matchSkill = (s: SkillManifest) => {
      const text = `${s.name} ${s.id} ${s.tags.join(" ")} ${s.description}`.toLowerCase();
      if (q && !text.includes(q)) return false;
      if (filterVerified === "verified" && !s.security_scan_passed) return false;
      if (filterVerified === "pending"  && s.security_scan_passed)  return false;
      return true;
    };
    return {
      filteredAdapters: adapters.filter(matchAdapter),
      filteredSkills:   skills.filter(matchSkill),
    };
  }, [adapters, skills, search, filterVerified]);

  const totalVerified = [...adapters, ...skills].filter(x => x.security_scan_passed).length;
  const totalPending  = [...adapters, ...skills].filter(x => !x.security_scan_passed).length;

  const showAdapters = activeTab === "all" || activeTab === "adapters";
  const showSkills   = activeTab === "all" || activeTab === "skills";

  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-6 min-h-0 flex-1">

      {/* ── Page Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-teal-600/80 to-indigo-600/80 flex items-center justify-center shadow-md shadow-teal-900/30">
              <Package size={16} className="text-white" />
            </div>
            <h1 className="text-xl font-bold tracking-tight">Ecosystem Registry</h1>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-teal-900/40 text-teal-300 border border-teal-700/30 font-mono uppercase tracking-wider">
              JITNA v3
            </span>
          </div>
          <p className="text-xs text-gray-500">
            Official registry of{" "}
            <span className="text-indigo-400 font-medium">Adapters</span> and{" "}
            <span className="text-purple-400 font-medium">Skills</span> integrated into Delentia OS via JITNA v3 protocol
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => { setLoading(true); setTimeout(() => setLoading(false), 800); }}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 border border-surface-border rounded-lg px-3 py-2 hover:border-white/15 transition"
          >
            <RefreshCw size={12} />
            <span>Refresh</span>
          </button>
          <a
            href="https://github.com/delentia-labs/delentia-ecosystem"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-100 border border-surface-border rounded-lg px-3 py-2 hover:border-white/15 transition"
          >
            <Github size={12} />
            <span>GitHub</span>
            <ExternalLink size={10} />
          </a>
        </div>
      </div>

      {/* ── Offline Banner ── */}
      {offline && <OfflineBanner />}

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={Network}       label="Adapters"  value={adapters.length} color="#6366f1" />
        <StatCard icon={Cpu}           label="Skills"    value={skills.length}   color="#8b5cf6" />
        <StatCard icon={ShieldCheck}   label="Verified"  value={totalVerified}   color="#10b981" sub={`${Math.round(totalVerified / Math.max(1, adapters.length + skills.length) * 100)}% of total`} />
        <StatCard icon={ShieldAlert}   label="Pending"   value={totalPending}    color="#f59e0b" sub="Security scan in progress" />
      </div>

      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search adapters, skills, tags…"
            className="w-full bg-surface border border-surface-border rounded-xl pl-8 pr-3 py-2.5 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500/50 transition"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400">✕</button>
          )}
        </div>

        {/* Tab pills */}
        <div className="flex items-center gap-0.5 bg-black/20 p-1 rounded-xl border border-white/5">
          {([
            { id: "all",      label: "All",      icon: LayoutGrid },
            { id: "adapters", label: "Adapters", icon: Network },
            { id: "skills",   label: "Skills",   icon: Bot },
          ] as const).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                activeTab === tab.id ? "bg-indigo-600 text-white" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <tab.icon size={11} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Verified filter */}
        <div className="flex items-center gap-0.5 bg-black/20 p-1 rounded-xl border border-white/5">
          {([
            { id: "all",      label: "All" },
            { id: "verified", label: "✓ Verified" },
            { id: "pending",  label: "⚠ Pending" },
          ] as const).map((f) => (
            <button
              key={f.id}
              onClick={() => setFilterVerified(f.id)}
              className={`px-3 py-1.5 rounded-lg text-xs transition ${
                filterVerified === f.id ? "bg-indigo-600 text-white" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-0.5 bg-black/20 p-1 rounded-xl border border-white/5 ml-auto">
          <button onClick={() => setView("grid")} className={`p-1.5 rounded-lg transition ${view === "grid" ? "bg-indigo-600 text-white" : "text-gray-600 hover:text-gray-400"}`}>
            <LayoutGrid size={13} />
          </button>
          <button onClick={() => setView("list")} className={`p-1.5 rounded-lg transition ${view === "list" ? "bg-indigo-600 text-white" : "text-gray-600 hover:text-gray-400"}`}>
            <List size={13} />
          </button>
        </div>
      </div>

      {/* ── Loading Skeleton ── */}
      {loading && (
        <div className={view === "grid" ? "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" : "space-y-2"}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={`bg-surface-card border border-surface-border animate-pulse ${view === "grid" ? "rounded-2xl h-44" : "rounded-xl h-14"}`} />
          ))}
        </div>
      )}

      {/* ── Adapters Section ── */}
      {!loading && showAdapters && filteredAdapters.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Network size={13} className="text-indigo-400" />
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">
              Adapters
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/30 text-indigo-400 border border-indigo-700/20 font-mono">
              {filteredAdapters.length}
            </span>
          </div>
          <div className={view === "grid" ? "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" : "space-y-2"}>
            {filteredAdapters.map((a) => <AdapterCard key={a.id} adapter={a} view={view} />)}
          </div>
        </div>
      )}

      {/* ── Skills Section ── */}
      {!loading && showSkills && filteredSkills.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Bot size={13} className="text-purple-400" />
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">
              Skills
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-900/30 text-purple-400 border border-purple-700/20 font-mono">
              {filteredSkills.length}
            </span>
          </div>
          <div className={view === "grid" ? "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" : "space-y-2"}>
            {filteredSkills.map((s) => <SkillCard key={s.id} skill={s} view={view} />)}
          </div>
        </div>
      )}

      {/* ── Empty State ── */}
      {!loading && filteredAdapters.length === 0 && filteredSkills.length === 0 && (
        <div className="text-center py-20 bg-surface-card border border-surface-border rounded-2xl">
          <Search size={32} className="text-gray-700 mx-auto mb-3" />
          <p className="text-sm font-semibold text-gray-400">No results found</p>
          <p className="text-xs text-gray-600 mt-1">Try adjusting your search or filters</p>
          <button
            onClick={() => { setSearch(""); setFilterVerified("all"); setActiveTab("all"); }}
            className="mt-4 text-xs text-indigo-400 hover:text-indigo-300 transition"
          >
            Clear all filters
          </button>
        </div>
      )}

      {/* ── Integration Architecture Info ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            icon: Network,
            color: "#6366f1",
            title: "JITNA v3 Protocol",
            desc: "All adapters and skills communicate via JITNA v3 — a typed, compressed, and cryptographically-signed intent packet protocol with TTL-based hop routing.",
            tags: ["JITNA v3", "ZSTD", "ED25519"],
          },
          {
            icon: Shield,
            color: "#10b981",
            title: "Security Scanning",
            desc: "Every adapter and skill undergoes automated security scanning before deployment. Verified items pass static analysis, permission audit, and constitutional AI alignment checks.",
            tags: ["Static Analysis", "Permission Audit", "FDIA Gate"],
          },
          {
            icon: Globe,
            color: "#8b5cf6",
            title: "Regional Compliance",
            desc: "Adapters declare regional support for PDPA (Thailand), GDPR (EU), and other jurisdiction-specific compliance frameworks to ensure constitutional AI governance.",
            tags: ["PDPA TH", "GDPR EU", "Constitutional AI"],
          },
        ].map((card) => (
          <div key={card.title} className="bg-surface-card border border-surface-border rounded-xl p-4 hover:border-white/10 transition">
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${card.color}18`, border: `1px solid ${card.color}30` }}>
                <card.icon size={14} style={{ color: card.color }} />
              </div>
              <h3 className="text-sm font-semibold text-gray-200">{card.title}</h3>
            </div>
            <p className="text-xs text-gray-500 leading-relaxed">{card.desc}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {card.tags.map((tag) => (
                <span key={tag} className="text-[9px] px-2 py-0.5 rounded-full font-mono" style={{ color: card.color, background: `${card.color}12`, border: `1px solid ${card.color}25` }}>
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
