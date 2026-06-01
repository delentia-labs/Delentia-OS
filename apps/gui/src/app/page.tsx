"use client";

import { useEffect, useState } from "react";
import { getSystemStats, getHealthStatus } from "@/lib/delentia-client";
import type { HealthResponse, SystemStats } from "@/lib/types";
import { useIntent } from "@/hooks/useIntent";

// ─── Stat Card ───────────────────────────────────────────────────────────────
function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-100 mt-1 font-mono">{value}</p>
    </div>
  );
}

// ─── Health dot ──────────────────────────────────────────────────────────────
function HealthDot({ status }: { status: "ok" | "degraded" | "offline" }) {
  const colors = {
    ok:       "bg-green-400",
    degraded: "bg-amber-400",
    offline:  "bg-red-400",
  };
  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status]} shadow-lg`} />
  );
}

// ─── Quick Intent Bar ────────────────────────────────────────────────────────
function QuickIntentBar() {
  const [input, setInput] = useState("");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";
  const { state, run } = useIntent({ apiKey, gateway });

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Quick Intent
      </h2>
      <div className="flex gap-2">
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
          placeholder="Type intent and press Enter…"
          disabled={state.status === "loading"}
          className="flex-1 bg-surface text-gray-100 placeholder-gray-600 border border-surface-border rounded-lg px-3 py-2 text-sm outline-none focus:border-delentia-500 transition disabled:opacity-50"
        />
        <button
          onClick={() => { run(input); setInput(""); }}
          disabled={state.status === "loading" || !input.trim()}
          className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-sm font-medium transition"
        >
          Run
        </button>
      </div>
      {state.status === "success" && (
        <p className="text-xs text-green-400 mt-2 line-clamp-2">
          {state.response.output.result}
        </p>
      )}
      {state.status === "error" && (
        <p className="text-xs text-red-400 mt-2">{state.message}</p>
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

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Delentia OS — Intent-Centric Constitutional AI</p>
        </div>
        <div className="flex items-center gap-2 bg-surface-card border border-surface-border rounded-lg px-3 py-1.5">
          <HealthDot status={healthStatus} />
          <span className="text-xs text-gray-400">
            {healthStatus === "offline"
              ? "Cannot connect to gateway"
              : `Gateway ${health?.version ?? ""} — ${health?.service ?? "Delentia OS"}`}
          </span>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Tests Passed" value={stats?.testCount?.toLocaleString() ?? "—"} />
        <StatCard label="Microservices" value={stats?.microserviceCount ?? "—"} />
        <StatCard label="HexaCore Models" value={stats?.hexaCoreCount ?? "—"} />
        <StatCard label="SLA" value={stats?.sla ?? "—"} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Algorithms" value={stats?.algorithmCount ?? "—"} />
        <StatCard label="Layers" value={stats?.layerCount ?? "—"} />
        <StatCard label="OS Version" value={stats?.version ?? "—"} />
        <StatCard label="Consensus Models" value={stats?.consensusModels ?? "—"} />
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
            className="bg-surface-card border border-surface-border hover:border-delentia-700 rounded-xl p-4 transition group"
          >
            <h3 className="font-semibold text-sm text-gray-200 group-hover:text-delentia-400 transition">
              {card.title} →
            </h3>
            <p className="text-xs text-gray-500 mt-1">{card.desc}</p>
          </a>
        ))}
      </div>
    </div>
  );
}
