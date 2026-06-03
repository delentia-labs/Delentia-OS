"use client";

import { DeltaTimeline } from "@/components/delta-timeline/timeline";

export default function MemoryPage() {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-pink-600/80 to-purple-600/80 flex items-center justify-center text-base shadow-md shadow-purple-900/30">
              🧠
            </div>
            <h1 className="text-xl font-bold tracking-tight">Memory Timeline</h1>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-purple-900/40 text-purple-300 border border-purple-700/30 font-mono uppercase tracking-wider">
              Delta Engine
            </span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed max-w-xl">
            Full audit log of memory state-change events recorded by the{" "}
            <span className="text-purple-400 font-medium">Delta Engine</span>. Each delta is
            checkpointed every 50 ticks with{" "}
            <span className="text-indigo-400 font-medium">91.5% zstd compression</span> and
            cryptographically signed via SHA-256 audit chain.
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-3 bg-surface-card border border-surface-border rounded-xl px-4 py-2.5 text-[10px]">
          {[
            { color: "#10b981", label: "success" },
            { color: "#f59e0b", label: "partial" },
            { color: "#ef4444", label: "blocked" },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
              <span className="text-gray-500 capitalize">{label}</span>
            </div>
          ))}
          <div className="border-l border-white/5 pl-3 flex items-center gap-1.5">
            <span className="text-amber-400">⚠</span>
            <span className="text-gray-500">violation</span>
          </div>
        </div>
      </div>

      {/* ── Delta Timeline Component ── */}
      <DeltaTimeline apiKey={apiKey} gateway={gateway} />
    </div>
  );
}
