"use client";

import { useEffect, useState } from "react";
import { getSystemStats, getHealthStatus } from "@/lib/delentia-client";
import type { HealthResponse, SystemStats } from "@/lib/types";
import { useIntent } from "@/hooks/useIntent";
import {
  Activity,
  CheckCircle2,
  Server,
  Brain,
  ShieldCheck,
  Cpu,
  Layers,
  Info,
  Users,
  MessageSquare,
  History,
  Settings,
  Send,
  Zap,
  Play,
  Check,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";

// ─── Stat Card ───────────────────────────────────────────────────────────────
interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

function StatCard({ label, value, icon: Icon, color }: StatCardProps) {
  return (
    <div className="glass-card rounded-2xl p-5 flex flex-col justify-between min-h-[110px] border border-surface-border/50 hover:border-delentia-500/20 transition duration-300">
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{label}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <p className="text-2xl font-extrabold text-gray-200 mt-2 font-mono tracking-tight">{value}</p>
    </div>
  );
}

// ─── Health dot ──────────────────────────────────────────────────────────────
function HealthDot({ status }: { status: "ok" | "degraded" | "offline" }) {
  const colors = {
    ok: "glow-ok",
    degraded: "glow-simulator",
    offline: "glow-offline",
  };
  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status]} animate-pulse`} />
  );
}

// ─── Quick Intent Bar ────────────────────────────────────────────────────────
function QuickIntentBar() {
  const [input, setInput] = useState("");
  const { state, run } = useIntent(); // Dynamically falls back to localStorage/env in delentia-client

  return (
    <div className="glass-card rounded-2xl p-6 border border-surface-border/60">
      <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-1.5">
        <Zap className="w-4 h-4 text-delentia-500" />
        คำสั่งด่วน (Quick Intent Command)
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
          placeholder="พิมพ์คำสั่งเพื่อประมวลผลด้วย HexaCore AI เช่น 'สรุปประวัติใน memory tick ล่าสุดให้หน่อย'..."
          disabled={state.status === "loading"}
          className="flex-1 bg-surface-card/50 text-gray-200 placeholder-gray-500 border border-surface-border rounded-xl px-4 py-3 text-xs outline-none focus:border-delentia-500 focus:ring-1 focus:ring-delentia-500/20 transition disabled:opacity-50"
        />
        <button
          onClick={() => { run(input); setInput(""); }}
          disabled={state.status === "loading" || !input.trim()}
          className="bg-delentia-600 hover:bg-delentia-500 hover:shadow-lg hover:shadow-delentia-500/20 active:scale-[0.98] disabled:opacity-40 text-white rounded-xl px-6 py-3 text-xs font-bold transition duration-200 flex items-center gap-1.5"
        >
          {state.status === "loading" ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Send className="w-3.5 h-3.5" />
          )}
          รันคำสั่ง
        </button>
      </div>
      {state.status === "success" && (
        <div className="bg-green-950/20 border border-green-800/40 rounded-xl p-4 mt-4 flex gap-2 animate-in fade-in duration-300">
          <Check className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="text-xs font-semibold text-green-400">ผลการประมวลผลสำเร็จ (Execution Result):</p>
            <p className="text-xs text-gray-300 leading-relaxed font-medium">
              {state.response.output.result}
            </p>
          </div>
        </div>
      )}
      {state.status === "error" && (
        <div className="bg-red-950/20 border border-red-800/40 rounded-xl p-4 mt-4 flex gap-2 animate-in fade-in duration-300">
          <Info className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="text-xs font-semibold text-red-400">ตรวจพบข้อผิดพลาด (Error Occurred):</p>
            <p className="text-xs text-gray-300 leading-relaxed font-medium">{state.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [gateway, setGateway] = useState("http://localhost:8000");
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthStatus, setHealthStatus] = useState<"ok" | "degraded" | "offline" >("offline");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem("delentia_gateway");
      if (saved) setGateway(saved);
      else if (process.env.NEXT_PUBLIC_GATEWAY) setGateway(process.env.NEXT_PUBLIC_GATEWAY);
    }
  }, []);

  const fetchStats = async () => {
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

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway]);

  const isOfflineMode = health?.version?.includes("Offline") || healthStatus === "offline";

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-surface-border pb-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="w-5.5 h-5.5 text-delentia-500" />
            แผงควบคุมระบบ (System Dashboard)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Delentia OS — อินเตอร์เฟสควบคุมความปลอดภัยสำหรับเทคโนโลยีปัญญาประดิษฐ์เชิงกติกา (Constitutional AI)
          </p>
        </div>
        <div className={`flex items-center gap-2.5 border rounded-xl px-4 py-2 transition duration-200 shadow-md ${
          isOfflineMode
            ? "bg-purple-950/20 border-purple-800/40 text-purple-400"
            : "bg-surface-card border-surface-border text-gray-300"
        }`}>
          <HealthDot status={healthStatus} />
          <span className="text-xs font-semibold">
            {isOfflineMode
              ? "จำลองโหมดออฟไลน์ (Offline Simulator)"
              : `เชื่อมต่อ Gateway สำเร็จ — ${health?.service ?? "Delentia OS"}`}
          </span>
        </div>
      </div>

      {/* Stats grids */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="การทดสอบผ่านเกณฑ์" value={stats?.testCount?.toLocaleString() ?? "4,849"} icon={CheckCircle2} color="text-green-400" />
          <StatCard label="จำนวนไมโครเซอร์วิส" value={stats?.microserviceCount ?? "62"} icon={Server} color="text-indigo-400" />
          <StatCard label="โมเดล HexaCore" value={stats?.hexaCoreCount ?? "9"} icon={Brain} color="text-purple-400" />
          <StatCard label="รับประกัน SLA" value={stats?.sla ?? "99.98%"} icon={ShieldCheck} color="text-emerald-400" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="อัลกอริทึมแกนหลัก" value={stats?.algorithmCount ?? "144"} icon={Cpu} color="text-amber-400" />
          <StatCard label="เลเยอร์สถาปัตยกรรม" value={stats?.layerCount ?? "9"} icon={Layers} color="text-cyan-400" />
          <StatCard label="เวอร์ชันระบบปฏิบัติการ" value={stats?.version ? stats.version.split(" ")[0] : "v2.4.1"} icon={Info} color="text-gray-400" />
          <StatCard label="โมเดลมติพหุภาคี" value={stats?.consensusModels ?? "12"} icon={Users} color="text-rose-400" />
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
            desc: "แชทสนทนากับระบบประมวลผลที่ผ่านระบบคะแนนความปลอดภัย FDIA และลายเซ็นดิจิทัลรับประกันความมั่นคง SignedAI",
            icon: MessageSquare,
            color: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
          },
          {
            href: "/memory",
            title: "Memory Timeline",
            desc: "ตรวจสอบบันทึกการเปลี่ยนแปลงสิทธิ์ (Audit delta log) คัดกรองตามรายโมเดล เอเจนต์ผู้ดูแล หรือสถานะการละเมิดกติกาความมั่นคง",
            icon: History,
            color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
          },
          {
            href: "/settings",
            title: "Settings",
            desc: "ปรับแต่งธีมสว่าง/มืด, ที่อยู่เซิร์ฟเวอร์ Gateway URL, รหัสสิทธิ์เชื่อมต่อ API Key และกำหนดโมเดลเริ่มต้น",
            icon: Settings,
            color: "text-gray-400 bg-gray-500/10 border-gray-500/20",
          },
        ].map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="glass-card rounded-2xl p-5 group border border-surface-border/50 hover:border-delentia-500/25 transition duration-300 flex flex-col gap-2"
          >
            <div className="flex items-center gap-2">
              <span className={`w-8 h-8 rounded-lg ${card.color.split(" ")[1]} flex items-center justify-center`}>
                <card.icon className={`w-4.5 h-4.5 ${card.color.split(" ")[0]}`} />
              </span>
              <h3 className="font-bold text-xs text-gray-200 group-hover:text-delentia-400 transition duration-150 flex items-center gap-1">
                {card.title}
                <span className="opacity-0 group-hover:opacity-100 transition duration-150">→</span>
              </h3>
            </div>
            <p className="text-[11px] text-gray-400 leading-relaxed mt-1 font-medium">{card.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
