"use client";

// JITNA Visual Workflow Builder — Phase 2 Skeleton
// Phase 3 will implement full drag-and-drop with React Flow / XY Flow

const NODE_TYPES = [
  { type: "input", label: "Input", color: "bg-blue-600", desc: "User intent entry point" },
  { type: "filter", label: "FDIA Filter", color: "bg-purple-600", desc: "Score gate (threshold: 0.7)" },
  { type: "transform", label: "Transform", color: "bg-amber-600", desc: "Intent format converter" },
  { type: "adapter", label: "Adapter", color: "bg-green-600", desc: "Ecosystem channel output" },
  { type: "output", label: "Output", color: "bg-gray-600", desc: "Final result node" },
] as const;

function PlaceholderNode({
  label,
  color,
  desc,
  index,
}: {
  label: string;
  color: string;
  desc: string;
  index: number;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      {index > 0 && (
        <div className="flex flex-col items-center gap-0.5 text-gray-600 mb-1">
          <div className="w-px h-4 bg-gray-700" />
          <span className="text-[10px] font-mono">→</span>
          <div className="w-px h-4 bg-gray-700" />
        </div>
      )}
      <div
        className={`${color}/20 border-2 rounded-xl px-5 py-3 text-center min-w-[140px]`}
        style={{ borderColor: `var(--${color.replace("bg-", "").replace("/20", "")})` }}
      >
        <p className={`text-sm font-bold ${color.replace("/20", "").replace("bg-", "text-")} mb-0.5`}>
          {label}
        </p>
        <p className="text-[10px] text-gray-500">{desc}</p>
      </div>
    </div>
  );
}

export default function WorkflowPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-xl font-bold">JITNA Visual Workflow Builder</h1>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-700/40 font-mono">
            Phase 2 Preview
          </span>
        </div>
        <p className="text-sm text-gray-500">
          Design JITNA intent workflows visually. Drag-and-drop builder coming in Phase 3 (Q4 2026).
        </p>
      </div>

      {/* Preview canvas */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-6">
        <p className="text-xs text-gray-500 uppercase tracking-wide font-semibold mb-6 text-center">
          Sample Workflow — PDPA Compliance Check
        </p>
        <div className="flex flex-col items-center">
          {NODE_TYPES.map((node, i) => (
            <PlaceholderNode key={node.type} label={node.label} color={node.color} desc={node.desc} index={i} />
          ))}
        </div>
      </div>

      {/* Node palette */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Node Palette
        </h2>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
          {NODE_TYPES.map((node) => (
            <div
              key={node.type}
              className="border border-dashed border-surface-border rounded-lg p-3 text-center cursor-not-allowed opacity-60 hover:opacity-80 transition"
              title="Drag-and-drop available in Phase 3"
            >
              <div className={`w-6 h-6 rounded ${node.color} mx-auto mb-1`} />
              <p className="text-[10px] text-gray-400">{node.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Roadmap callout */}
      <div className="bg-delentia-900/20 border border-delentia-700/40 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-delentia-300 mb-2">
          Phase 3 Roadmap — Full Visual Builder (Q4 2026)
        </h2>
        <ul className="space-y-1.5 text-xs text-gray-400">
          <li className="flex gap-2">
            <span className="text-delentia-500">→</span>
            Drag-and-drop node canvas using <span className="font-mono text-delentia-400">@xyflow/react</span>
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500">→</span>
            Real-time FDIA score simulation per node
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500">→</span>
            Export workflow as JITNA DSL JSON
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500">→</span>
            Import from existing JITNA packet history
          </li>
          <li className="flex gap-2">
            <span className="text-delentia-500">→</span>
            Adapter node connecting directly to ecosystem registry
          </li>
        </ul>
      </div>
    </div>
  );
}
