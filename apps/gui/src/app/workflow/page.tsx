"use client";

import { useState, useCallback, useRef } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────
type NodeType =
  | "trigger"
  | "filter"
  | "transform"
  | "llm"
  | "adapter"
  | "output"
  | "condition"
  | "memory"
  | "webhook";

interface WorkflowNode {
  id: string;
  type: NodeType;
  label: string;
  x: number;
  y: number;
  status: "idle" | "running" | "success" | "error";
  config: Record<string, string>;
}

interface WorkflowEdge {
  id: string;
  from: string;
  to: string;
}

interface LogEntry {
  ts: number;
  level: "info" | "warn" | "error" | "success";
  msg: string;
  nodeId?: string;
}

// ─── Node Metadata ────────────────────────────────────────────────────────────
const NODE_META: Record<NodeType, { label: string; color: string; bg: string; icon: string; desc: string; category: string }> = {
  trigger:   { label: "Trigger",      color: "#6366f1", bg: "rgba(99,102,241,0.12)",   icon: "⚡", desc: "Start workflow on event or schedule", category: "Entry" },
  webhook:   { label: "Webhook",      color: "#8b5cf6", bg: "rgba(139,92,246,0.12)",   icon: "🔗", desc: "HTTP webhook entry point", category: "Entry" },
  filter:    { label: "FDIA Filter",  color: "#a855f7", bg: "rgba(168,85,247,0.12)",   icon: "🛡️", desc: "Constitutional score gate (≥ 0.7)", category: "Guard" },
  condition: { label: "Condition",    color: "#f59e0b", bg: "rgba(245,158,11,0.12)",   icon: "◇", desc: "Branch on expression", category: "Logic" },
  llm:       { label: "LLM Node",     color: "#10b981", bg: "rgba(16,185,129,0.12)",   icon: "🤖", desc: "HexaCore AI inference step", category: "AI" },
  transform: { label: "Transform",    color: "#0ea5e9", bg: "rgba(14,165,233,0.12)",   icon: "⇄", desc: "Map / reshape data payload", category: "Data" },
  memory:    { label: "Memory",       color: "#ec4899", bg: "rgba(236,72,153,0.12)",   icon: "🧠", desc: "Read / write delta state", category: "Data" },
  adapter:   { label: "Adapter",      color: "#14b8a6", bg: "rgba(20,184,166,0.12)",   icon: "⬡", desc: "Ecosystem channel output", category: "Output" },
  output:    { label: "Output",       color: "#64748b", bg: "rgba(100,116,139,0.12)",  icon: "▣", desc: "Final result sink", category: "Output" },
};

// ─── Initial demo workflow ────────────────────────────────────────────────────
const INITIAL_NODES: WorkflowNode[] = [
  { id: "n1", type: "trigger",   label: "PDPA Request Trigger", x: 60,  y: 160, status: "idle", config: { schedule: "on-demand" } },
  { id: "n2", type: "filter",    label: "FDIA Filter",          x: 280, y: 160, status: "idle", config: { threshold: "0.7" } },
  { id: "n3", type: "condition", label: "Compliance Branch",    x: 500, y: 100, status: "idle", config: { expr: "score >= 0.9" } },
  { id: "n4", type: "llm",       label: "HexaCore Inference",   x: 720, y: 60,  status: "idle", config: { model: "SUPREME_ARCHITECT" } },
  { id: "n5", type: "memory",    label: "Write Delta State",    x: 720, y: 200, status: "idle", config: { key: "pdpa_audit" } },
  { id: "n6", type: "adapter",   label: "Ecosystem Adapter",    x: 940, y: 130, status: "idle", config: { channel: "rctlabs_api_L3" } },
  { id: "n7", type: "output",    label: "Audit Result",         x: 1140, y: 130, status: "idle", config: {} },
];

const INITIAL_EDGES: WorkflowEdge[] = [
  { id: "e1", from: "n1", to: "n2" },
  { id: "e2", from: "n2", to: "n3" },
  { id: "e3", from: "n3", to: "n4" },
  { id: "e4", from: "n3", to: "n5" },
  { id: "e5", from: "n4", to: "n6" },
  { id: "e6", from: "n5", to: "n6" },
  { id: "e7", from: "n6", to: "n7" },
];

// ─── Node Component ───────────────────────────────────────────────────────────
function WFNode({
  node,
  selected,
  onClick,
}: {
  node: WorkflowNode;
  selected: boolean;
  onClick: () => void;
}) {
  const meta = NODE_META[node.type];
  const statusRing =
    node.status === "running" ? "#6366f1"
    : node.status === "success" ? "#10b981"
    : node.status === "error"   ? "#ef4444"
    : "transparent";

  return (
    <g
      transform={`translate(${node.x}, ${node.y})`}
      onClick={onClick}
      style={{ cursor: "pointer" }}
    >
      {/* Shadow */}
      <rect x={-2} y={4} width={176} height={64} rx={12} fill="rgba(0,0,0,0.35)" />
      {/* Card */}
      <rect
        x={0} y={0} width={174} height={62} rx={11}
        fill={meta.bg}
        stroke={selected ? meta.color : statusRing !== "transparent" ? statusRing : "rgba(255,255,255,0.08)"}
        strokeWidth={selected ? 2 : 1.5}
      />
      {/* Running pulse */}
      {node.status === "running" && (
        <rect x={0} y={0} width={174} height={62} rx={11}
          fill="none"
          stroke={meta.color}
          strokeWidth={2}
          opacity={0.5}
        >
          <animate attributeName="opacity" values="0.5;0;0.5" dur="1.2s" repeatCount="indefinite" />
        </rect>
      )}
      {/* Icon bg pill */}
      <rect x={10} y={10} width={36} height={36} rx={8} fill={meta.color} opacity={0.2} />
      <text x={28} y={32} textAnchor="middle" dominantBaseline="middle" fontSize={18}>{meta.icon}</text>
      {/* Label */}
      <text x={56} y={22} fill="rgba(255,255,255,0.95)" fontSize={11} fontWeight="600" fontFamily="Outfit,sans-serif">{node.label}</text>
      <text x={56} y={38} fill="rgba(255,255,255,0.45)" fontSize={9} fontFamily="Plus Jakarta Sans,sans-serif">{node.type.toUpperCase()}</text>
      {/* Status dot */}
      {node.status !== "idle" && (
        <circle cx={158} cy={10} r={5} fill={statusRing}>
          {node.status === "running" && (
            <animate attributeName="opacity" values="1;0.3;1" dur="0.9s" repeatCount="indefinite" />
          )}
        </circle>
      )}
      {/* Port dots */}
      <circle cx={0}   cy={31} r={5} fill={meta.color} opacity={0.8} />
      <circle cx={174} cy={31} r={5} fill={meta.color} opacity={0.8} />
    </g>
  );
}

// ─── Edge Component ───────────────────────────────────────────────────────────
function WFEdge({ edge, nodes, animated }: { edge: WorkflowEdge; nodes: WorkflowNode[]; animated: boolean }) {
  const from = nodes.find((n) => n.id === edge.from);
  const to   = nodes.find((n) => n.id === edge.to);
  if (!from || !to) return null;

  const x1 = from.x + 174;
  const y1 = from.y + 31;
  const x2 = to.x;
  const y2 = to.y + 31;
  const mx = (x1 + x2) / 2;
  const d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;

  return (
    <g>
      <path d={d} stroke="rgba(255,255,255,0.07)" strokeWidth={8} fill="none" />
      <path d={d} stroke="rgba(99,102,241,0.3)" strokeWidth={2} fill="none" strokeDasharray={animated ? "6 4" : "none"}>
        {animated && <animate attributeName="strokeDashoffset" from="20" to="0" dur="0.8s" repeatCount="indefinite" />}
      </path>
    </g>
  );
}

// ─── Log Row ──────────────────────────────────────────────────────────────────
function LogRow({ entry }: { entry: LogEntry }) {
  const colors = {
    info:    "text-blue-400",
    warn:    "text-amber-400",
    error:   "text-red-400",
    success: "text-emerald-400",
  };
  const ts = new Date(entry.ts).toLocaleTimeString();
  return (
    <div className={`font-mono text-[11px] flex gap-2 py-0.5 border-b border-white/3`}>
      <span className="text-gray-600 shrink-0">{ts}</span>
      <span className={`shrink-0 ${colors[entry.level]}`}>[{entry.level.toUpperCase()}]</span>
      {entry.nodeId && <span className="text-indigo-400 shrink-0">[{entry.nodeId}]</span>}
      <span className="text-gray-300">{entry.msg}</span>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function WorkflowPage() {
  const [nodes, setNodes] = useState<WorkflowNode[]>(INITIAL_NODES);
  const [edges] = useState<WorkflowEdge[]>(INITIAL_EDGES);
  const [selected, setSelected] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([
    { ts: Date.now() - 12000, level: "info",    msg: "Workflow engine ready." },
    { ts: Date.now() - 8000,  level: "info",    msg: "Loaded workflow: PDPA Compliance Check" },
    { ts: Date.now() - 5000,  level: "success", msg: "Canvas loaded — 7 nodes, 7 edges." },
  ]);
  const [activeTab, setActiveTab] = useState<"logs" | "config" | "templates">("logs");
  const logRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((level: LogEntry["level"], msg: string, nodeId?: string) => {
    setLogs((prev) => [...prev.slice(-199), { ts: Date.now(), level, msg, nodeId }]);
    setTimeout(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, 50);
  }, []);

  const runWorkflow = useCallback(async () => {
    if (running) return;
    setRunning(true);
    addLog("info", "▶ Starting JITNA workflow execution…");

    const sequence = ["n1", "n2", "n3", "n4", "n5", "n6", "n7"];

    for (const nid of sequence) {
      setNodes((prev) =>
        prev.map((n) => (n.id === nid ? { ...n, status: "running" } : n))
      );
      const meta = NODE_META[nodes.find((n) => n.id === nid)!.type];
      addLog("info", `Executing node: ${meta.label}`, nid);

      await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));

      const success = Math.random() > 0.1;
      setNodes((prev) =>
        prev.map((n) => (n.id === nid ? { ...n, status: success ? "success" : "error" } : n))
      );
      if (!success) {
        addLog("error", `Node execution failed: ${meta.label}`, nid);
        setRunning(false);
        return;
      }
      addLog("success", `✓ ${meta.label} completed`, nid);
    }

    addLog("success", "✅ Workflow completed successfully — 7/7 nodes passed.");
    setRunning(false);
  }, [running, nodes, addLog]);

  const resetWorkflow = useCallback(() => {
    setNodes((prev) => prev.map((n) => ({ ...n, status: "idle" })));
    addLog("info", "Workflow reset to idle state.");
  }, [addLog]);

  const selectedNode = nodes.find((n) => n.id === selected);

  const CANVAS_W = 1380;
  const CANVAS_H = 320;

  const TEMPLATES = [
    { name: "PDPA Compliance Check",   nodes: 7, desc: "Full PDPA audit pipeline with FDIA gate and delta state write" },
    { name: "Intent → LLM → Adapter",  nodes: 4, desc: "Simple pass-through: Trigger → Filter → HexaCore → Output" },
    { name: "Webhook Responder",        nodes: 5, desc: "HTTP webhook → transform → memory store → response" },
    { name: "Batch Memory Audit",       nodes: 6, desc: "Scheduled delta-state audit across all agents" },
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* ── Header ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight">JITNA Visual Workflow Builder</h1>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-900/50 text-indigo-300 border border-indigo-700/40 font-mono uppercase tracking-wider">
              Alpha
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            Build, inspect, and execute constitutional AI pipelines visually.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={resetWorkflow}
            disabled={running}
            className="border border-white/10 text-gray-400 hover:text-white hover:border-white/20 disabled:opacity-30 rounded-lg px-3.5 py-2 text-xs transition font-medium"
          >
            ↺ Reset
          </button>
          <button
            onClick={runWorkflow}
            disabled={running}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-xs font-semibold transition shadow-lg shadow-indigo-900/30"
          >
            <span>{running ? "●" : "▶"}</span>
            {running ? "Running…" : "Run Workflow"}
          </button>
        </div>
      </div>

      {/* ── Main Canvas + Right Panel ── */}
      <div className="flex gap-4 min-h-[480px]">
        {/* Canvas */}
        <div className="flex-1 bg-surface-card border border-surface-border rounded-xl overflow-hidden relative">
          {/* Canvas header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-border">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]" />
              <span className="text-xs text-gray-400 font-mono">PDPA Compliance Check</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-gray-600">{nodes.length} nodes · {edges.length} edges</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                running
                  ? "bg-indigo-900/40 text-indigo-300 border border-indigo-700/30"
                  : nodes.some((n) => n.status === "error")
                    ? "bg-red-900/30 text-red-400 border border-red-700/30"
                    : nodes.every((n) => n.status === "success")
                      ? "bg-emerald-900/30 text-emerald-400 border border-emerald-700/30"
                      : "bg-white/5 text-gray-500 border border-white/5"
              }`}>
                {running ? "RUNNING" : nodes.some((n) => n.status === "error") ? "ERROR" : nodes.every((n) => n.status === "success") ? "COMPLETE" : "IDLE"}
              </span>
            </div>
          </div>

          {/* SVG Canvas */}
          <div className="overflow-x-auto">
            <svg
              width={CANVAS_W}
              height={CANVAS_H}
              style={{
                background: "radial-gradient(ellipse at 30% 50%, rgba(99,102,241,0.04) 0%, transparent 70%), radial-gradient(ellipse at 70% 30%, rgba(168,85,247,0.03) 0%, transparent 60%)",
              }}
            >
              {/* Grid dots */}
              <defs>
                <pattern id="wf-grid" x="0" y="0" width="28" height="28" patternUnits="userSpaceOnUse">
                  <circle cx="14" cy="14" r="0.8" fill="rgba(255,255,255,0.06)" />
                </pattern>
              </defs>
              <rect width={CANVAS_W} height={CANVAS_H} fill="url(#wf-grid)" />

              {/* Edges */}
              {edges.map((edge) => (
                <WFEdge key={edge.id} edge={edge} nodes={nodes} animated={running} />
              ))}

              {/* Nodes */}
              {nodes.map((node) => (
                <WFNode
                  key={node.id}
                  node={node}
                  selected={selected === node.id}
                  onClick={() => setSelected(selected === node.id ? null : node.id)}
                />
              ))}
            </svg>
          </div>
        </div>

        {/* Right panel */}
        <div className="w-72 bg-surface-card border border-surface-border rounded-xl flex flex-col shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-surface-border">
            {(["logs", "config", "templates"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 py-2.5 text-[10px] font-semibold uppercase tracking-wider transition ${
                  activeTab === tab
                    ? "text-indigo-400 border-b-2 border-indigo-500"
                    : "text-gray-600 hover:text-gray-400"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-3 min-h-0">
            {/* Logs tab */}
            {activeTab === "logs" && (
              <div ref={logRef} className="space-y-0.5">
                {logs.map((entry, i) => (
                  <LogRow key={i} entry={entry} />
                ))}
              </div>
            )}

            {/* Config tab */}
            {activeTab === "config" && (
              <div>
                {selectedNode ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 pb-2 border-b border-surface-border">
                      <span className="text-lg">{NODE_META[selectedNode.type].icon}</span>
                      <div>
                        <p className="text-xs font-semibold text-white">{selectedNode.label}</p>
                        <p className="text-[9px] text-gray-500 uppercase">{selectedNode.type}</p>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {Object.entries(selectedNode.config).map(([k, v]) => (
                        <div key={k}>
                          <label className="text-[9px] text-gray-500 uppercase tracking-wider block mb-1">{k}</label>
                          <input
                            defaultValue={v}
                            className="w-full bg-surface border border-surface-border rounded-lg px-2.5 py-1.5 text-xs text-gray-200 font-mono outline-none focus:border-indigo-500"
                          />
                        </div>
                      ))}
                    </div>
                    <div className="pt-2 border-t border-surface-border">
                      <p className="text-[9px] text-gray-500">{NODE_META[selectedNode.type].desc}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-gray-600 text-center py-8">
                    Click a node on the canvas to inspect & edit its config.
                  </p>
                )}
              </div>
            )}

            {/* Templates tab */}
            {activeTab === "templates" && (
              <div className="space-y-2">
                {TEMPLATES.map((tpl) => (
                  <div
                    key={tpl.name}
                    className="border border-surface-border rounded-lg p-3 hover:border-indigo-500/40 hover:bg-indigo-500/5 transition cursor-pointer group"
                  >
                    <p className="text-xs font-semibold text-gray-300 group-hover:text-indigo-300 transition">{tpl.name}</p>
                    <p className="text-[10px] text-gray-600 mt-0.5">{tpl.desc}</p>
                    <p className="text-[9px] text-gray-600 mt-1">{tpl.nodes} nodes</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Node Palette ── */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Node Palette</h2>
          <span className="text-[10px] text-gray-600">Drag-and-drop coming in v1.1</span>
        </div>

        <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-2">
          {(Object.entries(NODE_META) as [NodeType, typeof NODE_META[NodeType]][]).map(([type, meta]) => (
            <div
              key={type}
              className="flex flex-col items-center gap-1.5 p-2.5 rounded-xl border border-dashed cursor-default transition"
              style={{
                borderColor: `${meta.color}30`,
                background: meta.bg,
              }}
              title={meta.desc}
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-base"
                style={{ background: `${meta.color}20`, border: `1px solid ${meta.color}40` }}
              >
                {meta.icon}
              </div>
              <p className="text-[9px] text-gray-400 text-center leading-tight font-medium">{meta.label}</p>
              <span
                className="text-[8px] px-1.5 py-0.5 rounded-full font-mono"
                style={{ color: meta.color, background: `${meta.color}15` }}
              >
                {meta.category}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Integration Capabilities ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            title: "n8n-style Branching",
            icon: "◇",
            color: "#f59e0b",
            desc: "Condition nodes with expression-based branching let you build complex decision trees across your JITNA pipeline.",
            tags: ["Branching", "Expression", "Multi-path"],
          },
          {
            title: "LangChain-style Chains",
            icon: "🔗",
            color: "#10b981",
            desc: "Chain LLM nodes with memory, tools, and adapters. Each step is FDIA-scored and cryptographically signed.",
            tags: ["LLM", "Memory", "SignedAI"],
          },
          {
            title: "Windmill-style Execution",
            icon: "⚙️",
            color: "#6366f1",
            desc: "Reliable, type-safe execution logs. Every node run is audited and visible in real-time in the execution log.",
            tags: ["Audit", "Type-safe", "Real-time"],
          },
        ].map((card) => (
          <div
            key={card.title}
            className="bg-surface-card border border-surface-border rounded-xl p-4 hover:border-white/10 transition"
          >
            <div className="flex items-center gap-2.5 mb-3">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-base shrink-0"
                style={{ background: `${card.color}18`, border: `1px solid ${card.color}30` }}
              >
                {card.icon}
              </div>
              <h3 className="text-sm font-semibold text-gray-200">{card.title}</h3>
            </div>
            <p className="text-xs text-gray-500 leading-relaxed">{card.desc}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {card.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[9px] px-2 py-0.5 rounded-full font-mono"
                  style={{ color: card.color, background: `${card.color}12`, border: `1px solid ${card.color}25` }}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ── Roadmap ── */}
      <div className="bg-indigo-950/20 border border-indigo-800/30 rounded-xl p-4">
        <h2 className="text-xs font-semibold text-indigo-300 mb-3 uppercase tracking-wider">
          ⚡ Roadmap — Full Visual Builder v1.1 (Q4 2026)
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {[
            "Real drag-and-drop canvas using @xyflow/react",
            "Live FDIA score simulation per node execution",
            "Export workflow as JITNA DSL JSON / YAML",
            "Import from existing JITNA packet history",
            "Conditional branching with visual edge routing",
            "Adapter node connecting to ecosystem registry",
            "Parallel execution & fan-out / fan-in patterns",
            "Version control & rollback for workflow snapshots",
          ].map((item) => (
            <div key={item} className="flex items-start gap-2 text-[11px] text-gray-400">
              <span className="text-indigo-500 mt-0.5 shrink-0">→</span>
              <span>{item}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
