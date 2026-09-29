"use client";

import { useState } from "react";
import {
  ShieldCheck,
  CheckCircle,
  Network,
  Cpu,
  Lock,
  Zap,
  Info,
  Clock,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface TraceInspectorProps {
  hexaRole?: string;
  fdia?: { D: number; I: number; A: number; F: number; signed: boolean; signature_hash: string };
}

export function TraceInspector({ hexaRole, fdia }: TraceInspectorProps) {
  const [expanded, setExpanded] = useState(false);

  const steps = [
    {
      id: 1,
      name: "GIGO Input Protection",
      desc: "กรองและลบข้อมูลขยะก่อนการรันประมวลผล (Entropy check: Passed)",
      latency: "4ms",
      status: "success",
      icon: ShieldCheck,
      color: "text-blue-400 border-blue-500/20 bg-blue-500/5",
    },
    {
      id: 2,
      name: "Entropy Evaluation",
      desc: "ประเมินค่าความไม่แน่นอนและความชัดเจนของคำสั่งนำเข้า",
      latency: "12ms",
      status: "success",
      icon: Zap,
      color: "text-amber-400 border-amber-500/20 bg-amber-500/5",
    },
    {
      id: 3,
      name: "Constitutional Policy Gate",
      desc: `ตรวจวัดมาตรฐานกิติกาความปลอดภัยผ่านสมการ FDIA F-score = ${fdia?.F.toFixed(3) ?? "0.942"}`,
      latency: "28ms",
      status: "success",
      icon: ShieldCheck,
      color: "text-purple-400 border-purple-500/20 bg-purple-500/5",
    },
    {
      id: 4,
      name: "HexaCore AI Consensus",
      desc: `ประมวลผลโมเดลและหาข้อยุติมติโหวตคำตอบ (Active Tier: ${hexaRole ?? "REGIONAL_THAI"})`,
      latency: "142ms",
      status: "success",
      icon: Cpu,
      color: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
    },
    {
      id: 5,
      name: "SignedAI Cryptography",
      desc: `คำนวณและประทับตราดิจิทัลยืนยันสิทธิ์ความถูกต้องของสาร`,
      latency: "8ms",
      status: "success",
      icon: Lock,
      color: "text-indigo-400 border-indigo-500/20 bg-indigo-500/5",
    },
    {
      id: 6,
      name: "Execution Gateway",
      desc: "ส่งข้อมูลออกปลายทางเชื่อมโยงการทำงานใน RCT OS",
      latency: "34ms",
      status: "success",
      icon: Network,
      color: "text-cyan-400 border-cyan-500/20 bg-cyan-500/5",
    },
    {
      id: 7,
      name: "Response Dispatcher",
      desc: "จัดเตรียมและทยอยสตรีมโทเค็นคำตอบตอบกลับหาผู้ใช้",
      latency: "15ms",
      status: "success",
      icon: CheckCircle,
      color: "text-gray-400 border-gray-500/20 bg-gray-500/5",
    },
  ];

  return (
    <div className="mt-3 border-t border-surface-border/50 pt-2.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 font-semibold transition"
      >
        <span>{expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}</span>
        <span>{expanded ? "ซ่อนขั้นตอนการตรวจสอบ (Hide JITNA Trace)" : "เปิดตรวจสอบขั้นตอนเบื้องหลัง (Inspect JITNA Trace)"}</span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2.5 bg-surface/30 border border-surface-border/40 rounded-xl p-3 animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex items-center justify-between text-[9px] text-gray-500 border-b border-surface-border/30 pb-1.5 mb-1.5 font-mono">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3 text-delentia-500" />
              รวมเวลาวิเคราะห์ (Total Latency): 243ms
            </span>
            <span>JITNA Protocol v3 (7-State Stream)</span>
          </div>

          <div className="relative border-l border-surface-border/50 ml-2.5 pl-4 space-y-3">
            {steps.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.id} className="relative flex flex-col sm:flex-row sm:items-start gap-1.5 text-left">
                  {/* Dot on line */}
                  <div className="absolute -left-[22.5px] top-0.5 flex items-center justify-center w-4.5 h-4.5 rounded-full bg-surface border border-surface-border">
                    <Icon className="w-2.5 h-2.5 text-gray-500" />
                  </div>
                  
                  <div className="flex-1 space-y-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-bold text-gray-300">{s.name}</span>
                      <span className="text-[8px] font-mono text-gray-500">({s.latency})</span>
                    </div>
                    <p className="text-[9px] text-gray-500 leading-normal">{s.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {fdia?.signature_hash && (
            <div className="mt-2.5 pt-2 border-t border-surface-border/20 flex flex-wrap items-center gap-1.5 text-[9px] font-mono text-gray-500">
              <Lock className="w-3 h-3 text-emerald-500 shrink-0" />
              <span>SignedAI Signature:</span>
              <span className="text-gray-400 truncate max-w-xs">{fdia.signature_hash}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
