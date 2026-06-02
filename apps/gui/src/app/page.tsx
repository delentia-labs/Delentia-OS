"use client";

import { useEffect, useState } from "react";
import { getSystemStats, getHealthStatus } from "@/lib/delentia-client";
import type { HealthResponse, SystemStats } from "@/lib/types";
import { useIntent } from "@/hooks/useIntent";

// ─── Stat Card ───────────────────────────────────────────────────────────────
function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="glass-card rounded-2xl p-5 flex flex-col justify-between min-h-[110px]">
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{label}</p>
      <p className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-gray-100 to-gray-400 mt-2 font-mono tracking-tight">{value}</p>
    </div>
  );
}

// ─── Health dot ──────────────────────────────────────────────────────────────
function HealthDot({ status }: { status: "ok" | "degraded" | "offline" }) {
  const colors = {
    ok:       "glow-ok",
    degraded: "glow-simulator",
    offline:  "glow-offline",
  };
  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status]} animate-pulse`} />
  );
}

// ─── Quick Intent Bar ────────────────────────────────────────────────────────
function QuickIntentBar() {
  const [input, setInput] = useState("");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";
  const { state, run } = useIntent({ apiKey, gateway });

  return (
    <div className="glass-card rounded-2xl p-6">
      <h2 className="text-xs font-bold text-gray-300 uppercase tracking-widest mb-4">
        Quick Intent Command
      </h2>
      <div className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && input.trim()) {
              run(input);
              setInput("");
            }
          }}
          placeholder="พิมพ์คำสั่งเพื่อส่งวิเคราะห์ด้วย HexaCore AI เช่น 'ช่วยสรุปรายงานให้หน่อย'..."
          disabled={state.status === "loading"}
          className="flex-1 bg-black/40 text-gray-100 placeholder-gray-500 border border-white/5 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20 transition disabled:opacity-50"
        />
        <button
          onClick={() => { run(input); setInput(""); }}
          disabled={state.status === "loading" || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 hover:shadow-lg hover:shadow-indigo-500/20 active:scale-[0.98] disabled:opacity-40 text-white rounded-xl px-6 py-3 text-sm font-semibold transition duration-150"
        >
          Run
        </button>
      </div>
      {state.status === "success" && (
        <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4 mt-4">
          <p className="text-xs font-semibold text-emerald-400">Execution Result:</p>
          <p className="text-xs text-gray-300 mt-1 leading-relaxed">
            {state.response.output.result}
          </p>
        </div>
      )}
      {state.status === "error" && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4 mt-4">
          <p className="text-xs font-semibold text-red-400">Error Occurred:</p>
          <p className="text-xs text-gray-300 mt-1">{state.message}</p>
        </div>
      )}
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthStatus, setHealthStatus] = useState<"ok" | "degraded" | "offline">("offline");

  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";

  useEffect(() => {
    const fetch = async () => {
      try {
        const [s, h] = await Promise.all([
          getSystemStats(gateway),
          getHealthStatus(gateway),
        ]);
        setStats(s);
        setHealth(h);
        setHealthStatus(h.status);
      } catch {
        setHealthStatus("offline");
      }
    };
    fetch();
    const interval = setInterval(fetch, 30_000);
    return () => clearInterval(interval);
  }, [gateway]);

  const isOfflineMode = health?.version?.includes("Offline");

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white bg-clip-text">
            Dashboard
          </h1>
          <p className="text-sm text-gray-400 mt-1.5">Delentia OS — Visual Control Surface for Constitutional AI</p>
        </div>
        <div className={`flex items-center gap-3 border rounded-xl px-4 py-2.5 transition duration-200 shadow-md ${
          isOfflineMode 
            ? "bg-purple-950/10 border-purple-500/30 text-purple-400"
            : "bg-black/30 border-white/5 text-gray-300"
        }`}>
          <HealthDot status={healthStatus} />
          <span className="text-xs font-medium">
            {isOfflineMode
              ? "Offline Simulator Mode"
              : `Gateway Live — ${health?.service ?? "Delentia OS"}`}
          </span>
        </div>
      </div>

      {/* Stats grids */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Tests Passed" value={stats?.testCount?.toLocaleString() ?? "—"} />
          <StatCard label="Microservices" value={stats?.microserviceCount ?? "—"} />
          <StatCard label="HexaCore Models" value={stats?.hexaCoreCount ?? "—"} />
          <StatCard label="SLA Guarantee" value={stats?.sla ?? "—"} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Core Algorithms" value={stats?.algorithmCount ?? "—"} />
          <StatCard label="OS Architecture Layers" value={stats?.layerCount ?? "—"} />
          <StatCard label="System Version" value={stats?.version ?? "—"} />
          <StatCard label="Consensus Models" value={stats?.consensusModels ?? "—"} />
        </div>
      </div>

      {/* Quick intent bar */}
      <QuickIntentBar />

      {/* Nav cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            href: "/chat",
            title: "Intent Chat",
            desc: "Interactive chat with FDIA scoring and SignedAI verification on every response.",
          },
          {
            href: "/memory",
            title: "Memory Timeline",
            desc: "Browse and audit delta state changes. Filter by agent, outcome, or governance violation.",
          },
          {
            href: "/settings",
            title: "Settings",
            desc: "Configure gateway URL, API key, default HexaCore role, and connection.",
          },
        ].map((card) => (
          <a
            key={card.href}
            href={card.href}
            className="glass-card rounded-2xl p-5 group transition"
          >
            <h3 className="font-bold text-sm text-gray-200 group-hover:text-indigo-400 transition duration-150">
              {card.title} →
            </h3>
            <p className="text-xs text-gray-400 mt-2 leading-relaxed">{card.desc}</p>
          </a>
        ))}
      </div>
    </div>
  );
}
