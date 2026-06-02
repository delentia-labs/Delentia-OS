"use client";

import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SystemStats {
  fdia_avg?: number;
  total_intents?: number;
  active_sessions?: number;
  uptime_seconds?: number;
  helix_drift?: HelixDrift;
  services?: ServiceHealth[];
}

interface HelixDrift {
  score: number;
  dimensions: number[];
  status: "nominal" | "warning" | "critical";
  last_check: string;
}

interface ServiceHealth {
  name: string;
  port: number;
  status: "ok" | "degraded" | "offline";
  latency_ms?: number;
  version?: string;
}

// ── Spark Bar ─────────────────────────────────────────────────────────────────

function SparkBar({ values, color }: { values: number[]; color: string }) {
  const max = Math.max(...values, 0.01);
  return (
    <div className="flex items-end gap-0.5 h-8">
      {values.map((v, i) => (
        <div
          key={i}
          style={{ height: `${(v / max) * 100}%` }}
          className={`w-1.5 rounded-sm ${color} opacity-70`}
        />
      ))}
    </div>
  );
}

// ── Drift Gauge ───────────────────────────────────────────────────────────────

function DriftGauge({ drift }: { drift: HelixDrift }) {
  const pct = Math.min(drift.score * 100, 100);
  const colors = {
    nominal: "text-green-400",
    warning: "text-amber-400",
    critical: "text-red-400",
  };
  const bars = {
    nominal: "bg-green-500",
    warning: "bg-amber-500",
    critical: "bg-red-500",
  };

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Helix-TTD Drift Score
        </h2>
        <span className={`text-xs font-mono font-bold ${colors[drift.status]}`}>
          {drift.status.toUpperCase()}
        </span>
      </div>

      {/* Overall score */}
      <div className="flex items-end gap-3">
        <p className={`text-3xl font-bold font-mono ${colors[drift.status]}`}>
          {drift.score.toFixed(3)}
        </p>
        <p className="text-xs text-gray-500 mb-1">/ 1.000</p>
      </div>

      {/* Progress bar */}
      <div className="h-2 rounded-full bg-surface overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${bars[drift.status]}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* 8D dimensions */}
      <div>
        <p className="text-[10px] text-gray-500 mb-2">8-Dimensional Drift Vector</p>
        <div className="grid grid-cols-8 gap-1">
          {drift.dimensions.map((d, i) => (
            <div key={i} className="text-center">
              <div className="h-8 bg-surface rounded relative overflow-hidden flex items-end">
                <div
                  className={`w-full ${bars[drift.status]} opacity-60`}
                  style={{ height: `${Math.min(d * 100, 100)}%` }}
                />
              </div>
              <p className="text-[9px] text-gray-600 font-mono mt-0.5">D{i + 1}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Service Row ───────────────────────────────────────────────────────────────

function ServiceRow({ svc }: { svc: ServiceHealth }) {
  const colors = {
    ok: "bg-green-400",
    degraded: "bg-amber-400",
    offline: "bg-red-400",
  };
  const textColors = {
    ok: "text-green-400",
    degraded: "text-amber-400",
    offline: "text-red-400",
  };

  return (
    <div className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${colors[svc.status]}`} />
        <span className="text-sm text-gray-300">{svc.name}</span>
        <span className="text-[10px] text-gray-600 font-mono">:{svc.port}</span>
        {svc.version && (
          <span className="text-[10px] text-gray-600 font-mono">v{svc.version}</span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {svc.latency_ms !== undefined && (
          <span className="text-[10px] text-gray-500 font-mono">{svc.latency_ms}ms</span>
        )}
        <span className={`text-xs font-mono ${textColors[svc.status]}`}>
          {svc.status}
        </span>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const MOCK_FDIA_HISTORY = [0.82, 0.85, 0.88, 0.87, 0.91, 0.89, 0.93, 0.87, 0.90, 0.88, 0.92, 0.87];
const DEFAULT_SERVICES: ServiceHealth[] = [
  { name: "delentia-gateway", port: 8000, status: "offline", latency_ms: undefined },
  { name: "intent-loop", port: 8001, status: "offline" },
  { name: "analysearch", port: 8002, status: "offline" },
  { name: "qdrant", port: 8003, status: "offline" },
  { name: "crystallizer", port: 8004, status: "offline" },
  { name: "ecosystem-registry", port: 8090, status: "offline" },
];

export default function MonitorPage() {
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [services, setServices] = useState<ServiceHealth[]>(DEFAULT_SERVICES);
  const [fdiaHistory, setFdiaHistory] = useState<number[]>(MOCK_FDIA_HISTORY);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${gateway}/delentia/system/stats`);
      if (!res.ok) throw new Error();
      const data: SystemStats = await res.json();
      setStats(data);

      if (data.fdia_avg !== undefined) {
        setFdiaHistory((prev) => [...prev.slice(-11), data.fdia_avg!]);
      }

      if (data.services) {
        setServices(data.services);
      } else {
        // Probe each port
        const updated = await Promise.all(
          DEFAULT_SERVICES.map(async (svc) => {
            const start = Date.now();
            try {
              await fetch(`http://localhost:${svc.port}/health`, { signal: AbortSignal.timeout(1000) });
              return { ...svc, status: "ok" as const, latency_ms: Date.now() - start };
            } catch {
              return { ...svc, status: "offline" as const };
            }
          })
        );
        setServices(updated);
      }
      setLastUpdate(new Date());
    } catch {
      // Gateway offline — probe ports independently
      const updated = await Promise.all(
        DEFAULT_SERVICES.map(async (svc) => {
          const start = Date.now();
          try {
            await fetch(`http://localhost:${svc.port}/health`, { signal: AbortSignal.timeout(1000) });
            return { ...svc, status: "ok" as const, latency_ms: Date.now() - start };
          } catch {
            return { ...svc, status: "offline" as const };
          }
        })
      );
      setServices(updated);
      setLastUpdate(new Date());
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [gateway]);

  const mockDrift: HelixDrift = stats?.helix_drift ?? {
    score: 0.042,
    dimensions: [0.03, 0.05, 0.04, 0.06, 0.02, 0.08, 0.03, 0.05],
    status: "nominal",
    last_check: new Date().toISOString(),
  };

  const onlineCount = services.filter((s) => s.status === "ok").length;

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">System Monitor</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Real-time Helix-TTD drift, FDIA metrics, and service health.
          </p>
        </div>
        <div className="text-right">
          <button
            onClick={fetchStats}
            className="text-xs px-3 py-1.5 bg-surface-card border border-surface-border rounded-lg text-gray-400 hover:text-gray-100 transition"
          >
            ↻ Refresh
          </button>
          {lastUpdate && (
            <p className="text-[10px] text-gray-600 mt-1">
              Updated {lastUpdate.toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "FDIA Avg", value: stats?.fdia_avg?.toFixed(3) ?? "—", sub: "last 24h" },
          { label: "Total Intents", value: stats?.total_intents?.toLocaleString() ?? "—", sub: "all time" },
          { label: "Active Sessions", value: stats?.active_sessions ?? "—", sub: "live" },
          { label: "Services Online", value: `${onlineCount}/${services.length}`, sub: "health check" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="bg-surface-card border border-surface-border rounded-xl p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
            <p className="text-2xl font-bold text-gray-100 mt-1 font-mono">{value}</p>
            <p className="text-[10px] text-gray-600 mt-0.5">{sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Helix-TTD Drift */}
        <DriftGauge drift={mockDrift} />

        {/* FDIA history */}
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            FDIA Score History
          </h2>
          <SparkBar values={fdiaHistory} color="bg-delentia-500" />
          <div className="flex justify-between text-[10px] text-gray-600 font-mono">
            <span>min: {Math.min(...fdiaHistory).toFixed(3)}</span>
            <span>avg: {(fdiaHistory.reduce((a, b) => a + b, 0) / fdiaHistory.length).toFixed(3)}</span>
            <span>max: {Math.max(...fdiaHistory).toFixed(3)}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-surface-border">
            {[
              { label: "Auto-approve threshold", value: "0.700" },
              { label: "Block threshold", value: "0.000" },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-[10px] text-gray-600">{label}</p>
                <p className="text-sm font-mono text-gray-300">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Service health */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Service Health
        </h2>
        {services.map((svc) => (
          <ServiceRow key={svc.name} svc={svc} />
        ))}
      </div>
    </div>
  );
}
