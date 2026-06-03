"use client";

import { useEffect, useState } from "react";
import { getHealthStatus } from "@/lib/delentia-client";
import {
  Activity,
  TrendingUp,
  Cpu,
  Database,
  Wifi,
  WifiOff,
  AlertTriangle,
  RefreshCw,
  Clock,
  Terminal,
  Server,
  Layers,
  LineChart,
} from "lucide-react";

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
    <div className="flex items-end gap-1 h-12 bg-surface/30 p-2 rounded-lg border border-surface-border/50">
      {values.map((v, i) => (
        <div
          key={i}
          style={{ height: `${(v / max) * 100}%` }}
          className={`flex-1 rounded-sm ${color} transition-all duration-300 hover:opacity-100`}
          title={`FDIA: ${v.toFixed(3)}`}
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
    nominal: "bg-green-500 shadow-[0_0_12px_#10b981]",
    warning: "bg-amber-500 shadow-[0_0_12px_#f59e0b]",
    critical: "bg-red-500 shadow-[0_0_12px_#ef4444]",
  };

  return (
    <div className="glass-card rounded-xl p-5 space-y-4 border border-surface-border/60">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
          <Layers className="w-4 h-4 text-delentia-500" />
          อัตราการดริฟต์ (Helix-TTD Drift Score)
        </h2>
        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-bold uppercase ${
          drift.status === "nominal" ? "bg-green-950/20 border-green-800/40 text-green-400" :
          drift.status === "warning" ? "bg-amber-950/20 border-amber-800/40 text-amber-400" :
          "bg-red-950/20 border-red-800/40 text-red-400"
        }`}>
          {drift.status}
        </span>
      </div>

      <div className="flex items-end gap-2">
        <p className={`text-4xl font-bold font-mono tracking-tight ${colors[drift.status]}`}>
          {drift.score.toFixed(3)}
        </p>
        <p className="text-xs text-gray-500 mb-1.5">/ 1.000 (ดัชนีเสถียรภาพ)</p>
      </div>

      <div className="h-2 rounded-full bg-surface border border-surface-border overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${bars[drift.status]}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div>
        <p className="text-[10px] text-gray-500 mb-2 flex items-center gap-1">
          <Terminal className="w-3 h-3 text-delentia-500" />
          โครงสร้างเวกเตอร์ดริฟต์ 8 มิติ (8-Dimensional Drift Vector)
        </p>
        <div className="grid grid-cols-8 gap-1.5">
          {drift.dimensions.map((d, i) => (
            <div key={i} className="text-center">
              <div className="h-12 bg-surface border border-surface-border/60 rounded-md relative overflow-hidden flex items-end">
                <div
                  className={`w-full ${bars[drift.status]} opacity-70 transition-all duration-500`}
                  style={{ height: `${Math.min(d * 100, 100)}%` }}
                  title={`มิติ D${i + 1}: ${d.toFixed(3)}`}
                />
              </div>
              <p className="text-[9px] text-gray-500 font-mono mt-1 font-semibold">D{i + 1}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Service Row ───────────────────────────────────────────────────────────────

function ServiceRow({ svc }: { svc: ServiceHealth }) {
  const glowClass = {
    ok: "glow-ok",
    degraded: "glow-degraded",
    offline: "glow-offline",
  }[svc.status];

  const textColors = {
    ok: "text-green-400",
    degraded: "text-amber-400",
    offline: "text-red-400",
  };

  return (
    <div className="flex items-center justify-between py-3 border-b border-surface-border/40 last:border-0 hover:bg-white/[0.01] px-2 rounded-lg transition duration-150">
      <div className="flex items-center gap-3">
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${glowClass}`} />
        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-gray-200">{svc.name}</span>
            <span className="text-[9px] text-gray-500 font-mono bg-surface px-1.5 py-0.5 rounded border border-surface-border/50">
              port {svc.port}
            </span>
          </div>
          {svc.version && (
            <p className="text-[9px] text-gray-500 font-mono mt-0.5">v{svc.version}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {svc.latency_ms !== undefined && (
          <span className="text-[10px] text-gray-500 font-mono flex items-center gap-1">
            <Clock className="w-3 h-3 text-gray-600" />
            {svc.latency_ms} ms
          </span>
        )}
        <span className={`text-[10px] font-bold uppercase tracking-wider font-mono ${textColors[svc.status]} bg-surface/30 px-2 py-0.5 rounded border border-surface-border/40`}>
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
  const [gateway, setGateway] = useState("http://localhost:8000");
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [services, setServices] = useState<ServiceHealth[]>(DEFAULT_SERVICES);
  const [fdiaHistory, setFdiaHistory] = useState<number[]>(MOCK_FDIA_HISTORY);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem("delentia_gateway");
      if (saved) setGateway(saved);
      else if (process.env.NEXT_PUBLIC_GATEWAY) setGateway(process.env.NEXT_PUBLIC_GATEWAY);
    }
  }, []);

  const fetchStats = async () => {
    setLoading(true);
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
        const updated = await Promise.all(
          DEFAULT_SERVICES.map(async (svc) => {
            const start = Date.now();
            try {
              const u = gateway.includes("localhost") ? `http://localhost:${svc.port}/health` : `${gateway.replace(":8000", `:${svc.port}`)}/health`;
              await fetch(u, { signal: AbortSignal.timeout(1000) });
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
      // Offline fallback: probe ports independently
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway]);

  const mockDrift: HelixDrift = stats?.helix_drift ?? {
    score: 0.042,
    dimensions: [0.03, 0.05, 0.04, 0.06, 0.02, 0.08, 0.03, 0.05],
    status: "nominal",
    last_check: new Date().toISOString(),
  };

  const onlineCount = services.filter((s) => s.status === "ok").length;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-surface-border pb-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Activity className="w-5 h-5 text-delentia-500 animate-pulse" />
            เฝ้าระวังระบบ (System Monitor)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            รายงานการดริฟต์สถิติโมเดลเชิงเวกเตอร์ Helix-TTD, ประสิทธิภาพการประเมินความปลอดภัย FDIA และสถานะพอร์ตการเชื่อมต่อไมโครเซอร์วิส
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="text-[10px] text-gray-500 flex items-center gap-1 font-mono">
              <Clock className="w-3.5 h-3.5" />
              อัปเดตล่าสุด: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchStats}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-card border border-surface-border hover:bg-white/5 text-gray-300 hover:text-white rounded-lg text-xs font-semibold transition disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            รีเฟรช
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          {
            label: "FDIA Avg (24 ชม.)",
            value: stats?.fdia_avg?.toFixed(3) ?? "0.942",
            sub: "ระดับเสถียรภาพความมั่นคง",
            icon: LineChart,
            color: "text-indigo-400",
          },
          {
            label: "จำนวนคำสั่งประมวลผล",
            value: stats?.total_intents?.toLocaleString() ?? "1,248",
            sub: "คำสั่ง Intent ที่ตอบรับแล้ว",
            icon: Database,
            color: "text-emerald-400",
          },
          {
            label: "เซสชันที่เชื่อมต่ออยู่",
            value: stats?.active_sessions ?? "2",
            sub: "จำนวนไคลเอนต์พอร์ตเชื่อมโยง",
            icon: Wifi,
            color: "text-blue-400",
          },
          {
            label: "ไมโครเซอร์วิสออนไลน์",
            value: `${onlineCount}/${services.length}`,
            sub: "สถานะการตอบสนองสุขภาพ",
            icon: Cpu,
            color: onlineCount === services.length ? "text-green-400" : "text-amber-400",
          },
        ].map(({ label, value, sub, icon: Icon, color }) => (
          <div key={label} className="glass-card rounded-xl p-4 space-y-1.5 border border-surface-border/50">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold block">{label}</span>
            <div className="flex items-center justify-between">
              <span className="text-2xl font-bold font-mono text-gray-200 tracking-tight">{value}</span>
              <Icon className={`w-5 h-5 ${color} shrink-0`} />
            </div>
            <span className="text-[9px] text-gray-500 block">{sub}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Helix-TTD Drift */}
        <DriftGauge drift={mockDrift} />

        {/* FDIA history */}
        <div className="glass-card rounded-xl p-5 space-y-4 border border-surface-border/60">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-delentia-500" />
              ประวัติความมั่นคง (FDIA History)
            </h2>
            <span className="text-[9px] font-mono text-gray-500 bg-surface px-2 py-0.5 rounded border border-surface-border">
              12 รอบประเมินย้อนหลัง
            </span>
          </div>

          <SparkBar values={fdiaHistory} color="bg-delentia-500" />
          
          <div className="flex justify-between text-[10px] text-gray-500 font-mono bg-surface/50 px-3 py-1.5 rounded-lg border border-surface-border/40">
            <span>min: {Math.min(...fdiaHistory).toFixed(3)}</span>
            <span>avg: {(fdiaHistory.reduce((a, b) => a + b, 0) / fdiaHistory.length).toFixed(3)}</span>
            <span>max: {Math.max(...fdiaHistory).toFixed(3)}</span>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2 border-t border-surface-border/40 text-[10px]">
            {[
              { label: "เกณฑ์การอนุมัติแบบอัตโนมัติ (Auto-Approve)", value: "≥ 0.700" },
              { label: "เกณฑ์การตรวจค้นบล็อกข้อมูล (Hard-Block)", value: "≤ 0.000" },
            ].map(({ label, value }) => (
              <div key={label} className="bg-surface/30 p-2 rounded-lg border border-surface-border/30">
                <p className="text-gray-500">{label}</p>
                <p className="text-xs font-mono font-bold text-gray-300 mt-0.5">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Service health */}
      <div className="glass-card rounded-xl p-5 border border-surface-border/60">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-1.5">
          <Server className="w-4 h-4 text-delentia-500" />
          สถานะไมโครเซอร์วิสฝั่งเซิร์ฟเวอร์ (Service Health Port Check)
        </h2>
        <div className="divide-y divide-surface-border/40 bg-surface/30 rounded-xl p-3 border border-surface-border/40">
          {services.map((svc) => (
            <ServiceRow key={svc.name} svc={svc} />
          ))}
        </div>
      </div>
    </div>
  );
}
