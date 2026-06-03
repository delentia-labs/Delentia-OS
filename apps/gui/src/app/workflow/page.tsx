"use client";

import {
  GitBranch,
  Play,
  Shuffle,
  ShieldCheck,
  Cpu,
  HelpCircle,
  Database,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  Terminal,
  Layers,
} from "lucide-react";

// JITNA Visual Workflow Builder — Phase 2 Skeleton
// Phase 3 will implement full drag-and-drop with React Flow / XY Flow

const NODE_TYPES = [
  { type: "input", label: "Input Node", color: "bg-blue-500", border: "border-blue-500/30", text: "text-blue-400", desc: "จุดนำเข้าคำสั่งความต้องการของผู้ใช้ (User Intent Entry)", icon: Cpu },
  { type: "filter", label: "FDIA Filter Gate", color: "bg-purple-500", border: "border-purple-500/30", text: "text-purple-400", desc: "ด่านตรวจสอบความปลอดภัยคะแนนขั้นต่ำ 0.700", icon: ShieldCheck },
  { type: "transform", label: "Transform Parser", color: "bg-amber-500", border: "border-amber-500/30", text: "text-amber-400", desc: "ตัวแปลงรูปแบบข้อมูลและการจัดเรียงโครงสร้าง Intent", icon: Shuffle },
  { type: "adapter", label: "Ecosystem Adapter", color: "bg-emerald-500", border: "border-emerald-500/30", text: "text-emerald-400", desc: "ตัวเชื่อมต่อและยิงข้อมูลออกไปไมโครเซอร์วิสปลายทาง", icon: ExternalLink },
  { type: "output", label: "Output Node", color: "bg-gray-500", border: "border-gray-500/30", text: "text-gray-400", desc: "สรุปผลการจัดส่งผลลัพธ์สุดท้ายกลับหาไคลเอนต์", icon: Database },
] as const;

function PlaceholderNode({
  label,
  color,
  border,
  text,
  desc,
  icon: Icon,
  index,
}: {
  label: string;
  color: string;
  border: string;
  text: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
  index: number;
}) {
  return (
    <div className="flex flex-col items-center gap-1 w-full max-w-md">
      {index > 0 && (
        <div className="flex flex-col items-center text-gray-600 my-2">
          <div className="w-px h-6 bg-gradient-to-b from-gray-700 to-gray-500" />
          <ChevronRight className="w-4 h-4 rotate-90 text-gray-500" />
          <div className="w-px h-6 bg-gradient-to-t from-gray-700 to-gray-500" />
        </div>
      )}
      <div
        className={`w-full glass-card rounded-xl p-4 border flex items-center gap-4 hover:border-delentia-500/25 transition duration-300`}
      >
        <div className={`w-10 h-10 rounded-lg ${color}/10 border ${border} flex items-center justify-center shrink-0 ${text}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="text-left space-y-0.5">
          <p className="text-xs font-semibold text-gray-200 font-mono">
            {label}
          </p>
          <p className="text-[10px] text-gray-500 leading-relaxed font-medium">{desc}</p>
        </div>
      </div>
    </div>
  );
}

export default function WorkflowPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-surface-border pb-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-delentia-500" />
            ตัวสร้างชุดกระบวนงาน (JITNA Visual Workflow Builder)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            ออกแบบโครงสร้างสายการประมวลผลคำสั่ง Intent Workflows แบบทัศนภาพเชิงเวกเตอร์
          </p>
        </div>
        <span className="text-[10px] px-2.5 py-1 rounded-full bg-amber-950/20 text-amber-400 border border-amber-800/40 font-mono font-bold uppercase">
          Phase 2 Preview
        </span>
      </div>

      {/* Preview canvas */}
      <div className="glass-card rounded-xl p-6 border border-surface-border/60">
        <p className="text-xs text-gray-400 uppercase tracking-wider font-semibold mb-6 text-center flex items-center justify-center gap-1.5">
          <Terminal className="w-3.5 h-3.5 text-delentia-500" />
          ตัวอย่างขั้นตอนเวิร์กโฟลว์ — ตรวจสอบมาตรฐานกฎหมาย PDPA (Compliance Check)
        </p>
        <div className="flex flex-col items-center">
          {NODE_TYPES.map((node, i) => (
            <PlaceholderNode
              key={node.type}
              label={node.label}
              color={node.color}
              border={node.border}
              text={node.text}
              desc={node.desc}
              icon={node.icon}
              index={i}
            />
          ))}
        </div>
      </div>

      {/* Node palette */}
      <div className="glass-card rounded-xl p-5 border border-surface-border/60 space-y-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
          <Layers className="w-4 h-4 text-delentia-500" />
          คลังโหนดใช้งาน (Node Palette)
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {NODE_TYPES.map((node) => {
            const Icon = node.icon;
            return (
              <div
                key={node.type}
                className="border border-dashed border-surface-border/60 hover:border-surface-border rounded-xl p-4 text-center cursor-not-allowed opacity-50 hover:opacity-75 transition duration-200"
                title="ระบบลากวาง (Drag-and-drop) จะเปิดให้ใช้งานในระยะที่ 3"
              >
                <div className={`w-8 h-8 rounded-lg ${node.color}/10 border ${node.border} flex items-center justify-center mx-auto mb-2 ${node.text}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <p className="text-[10px] text-gray-400 font-mono font-semibold">{node.label}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Roadmap callout */}
      <div className="bg-delentia-500/5 border border-delentia-500/20 rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-delentia-400 flex items-center gap-1.5">
          <Play className="w-4 h-4 fill-delentia-400" />
          แผนการพัฒนาในระยะที่ 3 — Visual Builder เต็มรูปแบบ (Q4 2026)
        </h2>
        <ul className="space-y-2 text-xs text-gray-400 font-medium">
          <li className="flex gap-2">
            <span className="text-delentia-500 shrink-0">→</span>
            <span>หน้าผืนผ้าใบแบบลากวางโหนดได้ยืดหยุ่น โดยอาศัยเทคโนโลยี <span className="font-mono text-delentia-400 bg-surface px-1 py-0.5 rounded border border-surface-border">@xyflow/react</span></span>
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500 shrink-0">→</span>
            <span>จำลองการคำนวณและแสดงคะแนนเสถียรภาพความมั่นคง FDIA แบบเวลาจริงในทุกจุดเชื่อมโยงของโหนด</span>
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500 shrink-0">→</span>
            <span>การส่งออกโครงงานกระบวนการทำงานให้อยู่ในรูปไฟล์ JITNA DSL JSON เพื่อนำไปติดตั้งรันจริง</span>
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500 shrink-0">→</span>
            <span>นำเข้าโครงงานจากคลังประวัติไฟล์ JITNA Packets ย้อนหลังที่เคยประมวลผลสำเร็จ</span>
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500 shrink-0">→</span>
            <span>การปรับเชื่อมต่อโหนด Adapter ตรงเข้ากับแอปพลิเคชันหรือไมโครเซอร์วิสในทะเบียนภายนอก (Ecosystem Registry)</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
