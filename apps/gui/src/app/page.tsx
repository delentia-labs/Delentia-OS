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

  const isOfflineMode = health?.version === "offline" || healthStatus === "offline";

  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-6 min-h-0 flex-1">
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
              ? "ยังไม่ได้เชื่อมต่อ API (ไม่แสดงข้อมูลจำลอง)"
              : `เชื่อมต่อ Gateway สำเร็จ — ${health?.service ?? "Delentia OS"}`}
          </span>
        </div>
      </div>

      {/* Stats grids */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="การทดสอบผ่านเกณฑ์" value={stats?.testCount?.toLocaleString() ?? "-"} icon={CheckCircle2} color="text-green-400" />
          <StatCard label="จำนวนไมโครเซอร์วิส" value={stats?.microserviceCount ?? "-"} icon={Server} color="text-indigo-400" />
          <StatCard label="โมเดล HexaCore" value={stats?.hexaCoreCount ?? "-"} icon={Brain} color="text-purple-400" />
          <StatCard label="รับประกัน SLA" value={stats?.sla ?? "-"} icon={ShieldCheck} color="text-emerald-400" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="อัลกอริทึมแกนหลัก" value={stats?.algorithmCount ?? "-"} icon={Cpu} color="text-amber-400" />
          <StatCard label="เลเยอร์สถาปัตยกรรม" value={stats?.layerCount ?? "-"} icon={Layers} color="text-cyan-400" />
          <StatCard label="เวอร์ชันระบบปฏิบัติการ" value={stats?.version ? stats.version.split(" ")[0] : "-"} icon={Info} color="text-gray-400" />
          <StatCard label="โมเดลมติพหุภาคี" value={stats?.consensusModels ?? "-"} icon={Users} color="text-rose-400" />
        </div>
      </div>

      {/* Quick intent bar */}
      <QuickIntentBar />

      {/* 3 Core Monetizable MVPs Showcase Grid */}
      <div className="space-y-3">
        <div className="flex justify-between items-center">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            🚀 3 MONETIZABLE MVPS (พร้อมเปิดทดสอบและทำเงินจริง)
          </h2>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded">
            ALL ACTIVE (PORT 8000 & 3000)
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* MVP 1 Card */}
          <Link
            href="/sandbox"
            className="glass-card rounded-2xl p-5 group border border-cyan-500/30 hover:border-cyan-400 transition duration-300 flex flex-col justify-between space-y-3 bg-gradient-to-b from-cyan-950/20 to-transparent"
          >
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="px-2.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[10px] font-mono font-bold">
                  MVP 1: VIRAL B2C
                </span>
                <span className="text-xs">🎮</span>
              </div>
              <h3 className="font-bold text-sm text-white group-hover:text-cyan-300 transition duration-150">
                Stardew Living World & 2D Sandbox
              </h3>
              <p className="text-[11px] text-gray-400 leading-relaxed mt-1">
                โลกเสมือนจริง 100 NPCs ใน RAM (0 Token) ขับเคลื่อนด้วย WSE Decoupled และ BDI Causal Engine (Gate 10.6)
              </p>
            </div>
            <div className="pt-2 border-t border-slate-800 flex justify-between items-center text-[10px] font-mono text-cyan-400">
              <span>เปิด Sandbox จำลอง ➔</span>
              <span>100% Offline Free</span>
            </div>
          </Link>

          {/* MVP 2 Card */}
          <Link
            href="/profiler"
            className="glass-card rounded-2xl p-5 group border border-purple-500/30 hover:border-purple-400 transition duration-300 flex flex-col justify-between space-y-3 bg-gradient-to-b from-purple-950/20 to-transparent"
          >
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="px-2.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] font-mono font-bold">
                  MVP 2: SOLO-CREATOR
                </span>
                <span className="text-xs">🧠</span>
              </div>
              <h3 className="font-bold text-sm text-white group-hover:text-purple-300 transition duration-150">
                RCT-7 Deep Profiler & Blueprint
              </h3>
              <p className="text-[11px] text-gray-400 leading-relaxed mt-1">
                สกัดตัวตนด้วย Reverse Component Thinking และบีบอัดลง Delta Memory เพื่อสร้าง Digital Product Blueprint ใน 5 นาที
              </p>
            </div>
            <div className="pt-2 border-t border-slate-800 flex justify-between items-center text-[10px] font-mono text-purple-400">
              <span>เริ่ม Deep Profiling ➔</span>
              <span>Zero Context Drift</span>
            </div>
          </Link>

          {/* MVP 3 Card */}
          <Link
            href="/enterprise"
            className="glass-card rounded-2xl p-5 group border border-amber-500/30 hover:border-amber-400 transition duration-300 flex flex-col justify-between space-y-3 bg-gradient-to-b from-amber-950/20 to-transparent"
          >
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="px-2.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-mono font-bold">
                  MVP 3: ENTERPRISE B2B
                </span>
                <span className="text-xs">🛡️</span>
              </div>
              <h3 className="font-bold text-sm text-white group-hover:text-amber-300 transition duration-150">
                Sovereign Enterprise Offline Vault
              </h3>
              <p className="text-[11px] text-gray-400 leading-relaxed mt-1">
                ออกบิล PromptPay CRC-16, ตรวจสัญญา PDPA 2562 และประทับตรา SignedAI ED25519 แบบไม่ต้องต่อเน็ต
              </p>
            </div>
            <div className="pt-2 border-t border-slate-800 flex justify-between items-center text-[10px] font-mono text-amber-400">
              <span>เปิด Enterprise Vault ➔</span>
              <span>Air-Gapped Ready</span>
            </div>
          </Link>
        </div>
      </div>

      {/* Nav cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          {
            href: "/chat",
            title: "Intent Chat",
            desc: "แชทสนทนากับระบบประมวลผลผ่านคะแนน FDIA และ SignedAI",
            icon: MessageSquare,
            color: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
          },
          {
            href: "/billing",
            title: "Billing & Quotas",
            desc: "จัดการแพ็กเกจ Pro/Enterprise และชำระเงินผ่าน PromptPay QR",
            icon: ShieldCheck,
            color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
          },
          {
            href: "/brains/train",
            title: "LoRA Forge Studio",
            desc: "เทรนและปรับแต่ง N-Adapter ส่วนตัวผ่าน Multi-Format Upload",
            icon: Brain,
            color: "text-rose-400 bg-rose-500/10 border-rose-500/20",
          },
          {
            href: "/settings",
            title: "Settings",
            desc: "ปรับแต่งธีม, ที่อยู่เซิร์ฟเวอร์ Gateway URL และ API Keys",
            icon: Settings,
            color: "text-gray-400 bg-gray-500/10 border-gray-500/20",
          },
        ].map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="glass-card rounded-2xl p-4 group border border-surface-border/50 hover:border-delentia-500/25 transition duration-300 flex flex-col gap-2"
          >
            <div className="flex items-center gap-2">
              <span className={`w-7 h-7 rounded-lg ${card.color.split(" ")[1]} flex items-center justify-center`}>
                <card.icon className={`w-4 h-4 ${card.color.split(" ")[0]}`} />
              </span>
              <h3 className="font-bold text-xs text-gray-200 group-hover:text-delentia-400 transition duration-150 flex items-center gap-1">
                {card.title}
                <span className="opacity-0 group-hover:opacity-100 transition duration-150">→</span>
              </h3>
            </div>
            <p className="text-[10px] text-gray-400 leading-relaxed font-medium">{card.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
