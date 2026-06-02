"use client";

import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

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

interface RegistryResponse {
  adapters: AdapterManifest[];
  skills: SkillManifest[];
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

// ── Adapter Card ──────────────────────────────────────────────────────────────

function AdapterCard({ adapter }: { adapter: AdapterManifest }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm text-gray-100">{adapter.name}</p>
          <p className="text-[10px] font-mono text-gray-500">
            {adapter.id} · v{adapter.version}
          </p>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full font-mono shrink-0 ${
            adapter.security_scan_passed
              ? "bg-green-900/50 text-green-400 border border-green-700/50"
              : "bg-amber-900/50 text-amber-400 border border-amber-700/50"
          }`}
        >
          {adapter.security_scan_passed ? "✓ Verified" : "⚠ Pending"}
        </span>
      </div>
      <p className="text-xs text-gray-400 line-clamp-2">{adapter.description}</p>
      <div className="flex flex-wrap gap-1 mt-1">
        {adapter.regional_support.map((r) => (
          <span
            key={r}
            className="text-[10px] px-1.5 py-0.5 rounded bg-delentia-900/40 text-delentia-400 border border-delentia-700/30"
          >
            {r}
          </span>
        ))}
        {adapter.tags.slice(0, 3).map((t) => (
          <span
            key={t}
            className="text-[10px] px-1.5 py-0.5 rounded bg-surface text-gray-500 border border-surface-border"
          >
            {t}
          </span>
        ))}
      </div>
      <div className="mt-auto pt-2 border-t border-surface-border flex items-center justify-between">
        <span className="text-[10px] text-gray-600 font-mono">
          channel: {adapter.jitna_channel}
        </span>
        <span className="text-[10px] text-gray-600">
          {adapter.permissions.length} permissions
        </span>
      </div>
    </div>
  );
}

// ── Skill Card ────────────────────────────────────────────────────────────────

function SkillCard({ skill }: { skill: SkillManifest }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm text-gray-100">{skill.name}</p>
          <p className="text-[10px] font-mono text-gray-500">
            {skill.id} · v{skill.version}
          </p>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full font-mono shrink-0 ${
            skill.security_scan_passed
              ? "bg-green-900/50 text-green-400 border border-green-700/50"
              : "bg-amber-900/50 text-amber-400 border border-amber-700/50"
          }`}
        >
          {skill.security_scan_passed ? "✓ Verified" : "⚠ Pending"}
        </span>
      </div>
      <p className="text-xs text-gray-400 line-clamp-2">{skill.description}</p>
      <div className="flex flex-wrap gap-1 mt-auto pt-2 border-t border-surface-border">
        {skill.tags.slice(0, 4).map((t) => (
          <span
            key={t}
            className="text-[10px] px-1.5 py-0.5 rounded bg-surface text-gray-500 border border-surface-border"
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function EcosystemPage() {
  const ecosystemUrl =
    process.env.NEXT_PUBLIC_ECOSYSTEM_URL ?? "http://localhost:8090";
  const [adapters, setAdapters] = useState<AdapterManifest[]>([]);
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"adapters" | "skills">("adapters");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const fetchRegistry = async () => {
      setLoading(true);
      setError(null);
      try {
        // Try fetching from ecosystem registry API
        const res = await fetch(`${ecosystemUrl}/registry`);
        if (!res.ok) throw new Error(`Registry API returned ${res.status}`);
        const data: RegistryResponse = await res.json();
        setAdapters(data.adapters ?? []);
        setSkills(data.skills ?? []);
      } catch {
        // Fallback: show static count from known manifests
        setError(
          "Ecosystem registry offline (port 8090). Showing offline manifest data."
        );
        setAdapters([
          { id: "line-adapter", name: "LINE Messaging Adapter", version: "1.0.0", description: "Connects LINE Messaging API to Delentia OS", jitna_channel: "line", regional_support: ["TH", "JP", "TW"], tags: ["messaging", "line"], security_scan_passed: false, permissions: ["intent:read", "intent:execute"] },
          { id: "slack-adapter", name: "Slack Adapter", version: "1.0.0", description: "Connects Slack to Delentia OS via JITNA v3", jitna_channel: "slack", regional_support: ["GLOBAL"], tags: ["messaging", "slack"], security_scan_passed: false, permissions: ["intent:read", "intent:execute"] },
          { id: "whatsapp-adapter", name: "WhatsApp Business Adapter", version: "1.0.0", description: "Connects WhatsApp Business Cloud API to Delentia OS", jitna_channel: "whatsapp", regional_support: ["TH", "BR", "IN", "US"], tags: ["messaging", "whatsapp"], security_scan_passed: true, permissions: ["intent:read", "intent:execute", "media:read"] },
          { id: "telegram-adapter", name: "Telegram Bot Adapter", version: "1.0.0", description: "Connects Telegram Bot API to Delentia OS", jitna_channel: "telegram", regional_support: ["GLOBAL"], tags: ["messaging", "telegram"], security_scan_passed: true, permissions: ["intent:read", "intent:execute"] },
          { id: "discord-adapter", name: "Discord Bot Adapter", version: "1.0.0", description: "Connects Discord to Delentia OS via slash commands", jitna_channel: "discord", regional_support: ["GLOBAL"], tags: ["discord", "developer"], security_scan_passed: true, permissions: ["intent:read", "intent:execute"] },
          { id: "github-adapter", name: "GitHub App Adapter", version: "1.0.0", description: "Connects GitHub webhooks to Delentia OS", jitna_channel: "github", regional_support: ["GLOBAL"], tags: ["github", "ci-cd"], security_scan_passed: true, permissions: ["intent:read", "intent:execute", "data:write"] },
          { id: "notion-adapter", name: "Notion Integration Adapter", version: "1.0.0", description: "Connects Notion workspace to Delentia OS", jitna_channel: "notion", regional_support: ["GLOBAL"], tags: ["notion", "enterprise"], security_scan_passed: true, permissions: ["intent:read", "intent:execute", "data:read", "data:write"] },
        ]);
        setSkills([
          { id: "thai-language-skill", name: "Thai Language Constitutional Skill", version: "1.0.0", description: "PDPA compliance checking and Thai legal document parsing", jitna_channel: "thai-language", tags: ["thai", "pdpa", "legal"], security_scan_passed: false },
          { id: "legal-pdpa-skill", name: "Legal PDPA Skill", version: "1.0.0", description: "Thai PDPA legal compliance engine", jitna_channel: "legal-pdpa", tags: ["legal", "pdpa"], security_scan_passed: false },
          { id: "thai-nlp-skill", name: "Thai NLP Advanced Skill", version: "1.0.0", description: "PyThaiNLP + Typhoon v2 ML-powered Thai text processing", jitna_channel: "thai-nlp", tags: ["thai", "nlp", "ml"], security_scan_passed: true },
          { id: "web-search-skill", name: "Web Search Skill", version: "1.0.0", description: "Real-time web search via Tavily API", jitna_channel: "web-search", tags: ["search", "retrieval"], security_scan_passed: true },
          { id: "document-summary-skill", name: "Document Summary Skill", version: "1.0.0", description: "PDF/DOCX intelligent summarization (EN/TH)", jitna_channel: "document-summary", tags: ["documents", "summary"], security_scan_passed: true },
          { id: "financial-analysis-skill", name: "Financial Analysis Skill (TH)", version: "1.0.0", description: "Thai GAAP financial analysis + SET compliance", jitna_channel: "financial-analysis", tags: ["financial", "thai-gaap"], security_scan_passed: true },
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchRegistry();
  }, [ecosystemUrl]);

  const filteredAdapters = adapters.filter(
    (a) =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.id.toLowerCase().includes(search.toLowerCase()) ||
      a.tags.some((t) => t.includes(search.toLowerCase()))
  );

  const filteredSkills = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase()) ||
      s.tags.some((t) => t.includes(search.toLowerCase()))
  );

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Ecosystem Registry</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Adapters and skills registered in the Delentia OS ecosystem (port 8090).
          </p>
        </div>
        <a
          href="https://github.com/delentia-labs/delentia-ecosystem"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs px-3 py-1.5 bg-surface-card border border-surface-border rounded-lg text-gray-400 hover:text-gray-100 transition"
        >
          GitHub Registry →
        </a>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-2.5 text-xs text-amber-300">
          ⚠ {error}
        </div>
      )}

      {/* Stats bar */}
      <div className="flex gap-3">
        {[
          { label: "Adapters", value: adapters.length },
          { label: "Skills", value: skills.length },
          { label: "Verified", value: [...adapters, ...skills].filter((x) => x.security_scan_passed).length },
        ].map(({ label, value }) => (
          <div key={label} className="bg-surface-card border border-surface-border rounded-lg px-4 py-2 text-center min-w-[80px]">
            <p className="text-lg font-bold text-gray-100 font-mono">{value}</p>
            <p className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</p>
          </div>
        ))}
      </div>

      {/* Search + Tabs */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search adapters, skills, tags…"
          className="flex-1 bg-surface text-gray-100 placeholder-gray-600 border border-surface-border rounded-lg px-3 py-1.5 text-sm outline-none focus:border-delentia-500 transition"
        />
        <div className="flex border border-surface-border rounded-lg overflow-hidden">
          {(["adapters", "skills"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 text-xs capitalize transition ${
                activeTab === tab
                  ? "bg-delentia-600 text-white"
                  : "text-gray-400 hover:text-gray-100 bg-surface-card"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Content grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="bg-surface-card border border-surface-border rounded-xl p-4 h-36 animate-pulse"
            />
          ))}
        </div>
      ) : activeTab === "adapters" ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {filteredAdapters.map((a) => (
            <AdapterCard key={a.id} adapter={a} />
          ))}
          {filteredAdapters.length === 0 && (
            <p className="col-span-3 text-sm text-gray-500 text-center py-8">
              No adapters match &ldquo;{search}&rdquo;
            </p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {filteredSkills.map((s) => (
            <SkillCard key={s.id} skill={s} />
          ))}
          {filteredSkills.length === 0 && (
            <p className="col-span-3 text-sm text-gray-500 text-center py-8">
              No skills match &ldquo;{search}&rdquo;
            </p>
          )}
        </div>
      )}
    </div>
  );
}
