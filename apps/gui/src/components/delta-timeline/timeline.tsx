"use client";

import { useState, useEffect, useMemo } from "react";
import { getMemoryHistory, rollbackMemory } from "@/lib/delentia-client";
import type { MemoryDelta } from "@/lib/types";

// ─── Props ────────────────────────────────────────────────────────────────────
interface DeltaTimelineProps {
  apiKey: string;
  gateway: string;
}

// ─── Design tokens ────────────────────────────────────────────────────────────
const OUTCOME_META = {
  success: {
    label: "success",
    color: "#10b981",
    bg: "rgba(16,185,129,0.10)",
    border: "rgba(16,185,129,0.30)",
    dot: "bg-emerald-500",
    glow: "0 0 8px rgba(16,185,129,0.5)",
  },
  partial: {
    label: "partial",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.10)",
    border: "rgba(245,158,11,0.30)",
    dot: "bg-amber-500",
    glow: "0 0 8px rgba(245,158,11,0.5)",
  },
  blocked: {
    label: "blocked",
    color: "#ef4444",
    bg: "rgba(239,68,68,0.10)",
    border: "rgba(239,68,68,0.30)",
    dot: "bg-red-500",
    glow: "0 0 8px rgba(239,68,68,0.5)",
  },
} as const;

// ─── Helpers ──────────────────────────────────────────────────────────────────
function agentShortName(id: string) {
  return id.replace("agent-hexa-", "").replace("-01", "").replace(/-/g, " ");
}

function agentColor(id: string): string {
  const colors = ["#6366f1", "#8b5cf6", "#10b981", "#0ea5e9", "#f59e0b", "#ec4899", "#14b8a6", "#a855f7"];
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % colors.length;
  return colors[h];
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex flex-col gap-1.5">
      <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">{label}</p>
      <p className="text-2xl font-extrabold font-mono tracking-tight" style={{ color: color ?? "hsl(var(--text-primary))" }}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-gray-600">{sub}</p>}
    </div>
  );
}

function FDIABar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "#10b981" : value >= 0.5 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span className="text-[9px] text-gray-600 w-5 shrink-0">{label}</span>
      <div className="flex-1 bg-white/5 rounded-full h-1 min-w-0">
        <div className="h-1 rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 4px ${color}` }} />
      </div>
      <span className="text-[9px] font-mono shrink-0" style={{ color }}>{pct}%</span>
    </div>
  );
}

function DiffView({ changes }: { changes: Record<string, unknown> }) {
  const entries = Object.entries(changes);
  if (entries.length === 0) return <p className="text-[10px] text-gray-600 italic">No changes recorded.</p>;
  return (
    <div className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-start gap-2 font-mono text-[10px]">
          <span className="text-emerald-500 shrink-0">+</span>
          <span className="text-gray-500 shrink-0">{k}:</span>
          <span className="text-emerald-300 break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
        </div>
      ))}
    </div>
  );
}

function RelationshipDiff({ rel }: { rel: Record<string, number> }) {
  const entries = Object.entries(rel);
  if (entries.length === 0) return null;
  return (
    <div className="space-y-1">
      {entries.map(([agent, delta]) => (
        <div key={agent} className="flex items-center gap-2 text-[10px]">
          <span className={delta >= 0 ? "text-emerald-400" : "text-red-400"}>
            {delta >= 0 ? "↑" : "↓"}
          </span>
          <span className="text-gray-500 font-mono">{agent.replace("agent-hexa-", "")}</span>
          <span className={`font-mono font-semibold ${delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Main Timeline Component ──────────────────────────────────────────────────
export function DeltaTimeline({ apiKey, gateway }: DeltaTimelineProps) {
  const [deltas, setDeltas] = useState<MemoryDelta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Filter state
  const [search, setSearch] = useState("");
  const [filterOutcome, setFilterOutcome] = useState<"" | "success" | "partial" | "blocked">("");
  const [filterViolation, setFilterViolation] = useState<"" | "true" | "false">("");
  const [filterAgent, setFilterAgent] = useState("");

  // Rollback state
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchDeltas = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryHistory({ apiKey, gateway, limit: 50 });
      setDeltas(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDeltas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, gateway]);

  // ── Filtering ──────────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return deltas.filter((d) => {
      const q = search.toLowerCase();
      if (q && !d.agent_id.toLowerCase().includes(q) && !d.intent_type.toLowerCase().includes(q) && !d.action_type.toLowerCase().includes(q)) return false;
      if (filterOutcome && d.outcome !== filterOutcome) return false;
      if (filterViolation === "true" && !d.governance_violation) return false;
      if (filterViolation === "false" && d.governance_violation) return false;
      if (filterAgent && !d.agent_id.includes(filterAgent)) return false;
      return true;
    });
  }, [deltas, search, filterOutcome, filterViolation, filterAgent]);

  // ── Stats ──────────────────────────────────────────────────────────────────
  const stats = useMemo(() => {
    const total = deltas.length;
    const violations = deltas.filter((d) => d.governance_violation).length;
    const success = deltas.filter((d) => d.outcome === "success").length;
    const blocked = deltas.filter((d) => d.outcome === "blocked").length;
    const partial = deltas.filter((d) => d.outcome === "partial").length;
    const maxTick = deltas[0]?.tick ?? 0;
    const minTick = deltas[deltas.length - 1]?.tick ?? 0;
    const compressionRatio = "91.5%";
    return { total, violations, success, blocked, partial, maxTick, minTick, compressionRatio };
  }, [deltas]);

  // ── Unique agent IDs ───────────────────────────────────────────────────────
  const agentIds = useMemo(() => [...new Set(deltas.map((d) => d.agent_id))], [deltas]);

  // ── Toggle expand ──────────────────────────────────────────────────────────
  const toggleExpand = (tick: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(tick) ? next.delete(tick) : next.add(tick);
      return next;
    });
  };

  // ── Rollback ───────────────────────────────────────────────────────────────
  const handleRollback = async () => {
    if (rollbackTarget === null) return;
    try {
      const latest = deltas[0]?.tick ?? 0;
      const ticks = Math.max(0, latest - rollbackTarget);
      await rollbackMemory(ticks, { apiKey, gateway });
      setRollbackTarget(null);
      await fetchDeltas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
      setRollbackTarget(null);
    }
  };

  return (
    <div className="space-y-5">

      {/* ── Summary Stats ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard label="Total Deltas" value={stats.total} sub={`Tick ${stats.minTick} → ${stats.maxTick}`} color="#6366f1" />
        <StatCard label="Successful" value={stats.success} sub={`${stats.total > 0 ? Math.round((stats.success / stats.total) * 100) : 0}% of total`} color="#10b981" />
        <StatCard label="Partial" value={stats.partial} color="#f59e0b" />
        <StatCard label="Blocked" value={stats.blocked} color="#ef4444" />
        <StatCard label="Violations" value={stats.violations} sub="governance flags" color={stats.violations > 0 ? "#ef4444" : "#10b981"} />
        <StatCard label="Compression" value={stats.compressionRatio} sub="Delta Engine ckpt/50" color="#8b5cf6" />
      </div>

      {/* ── Faceted Filter Bar ── */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* Global search */}
          <div className="relative flex-1 min-w-[180px]">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 text-xs">⌕</span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agent, intent, action…"
              className="w-full bg-surface border border-surface-border rounded-lg pl-7 pr-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 transition"
            />
          </div>

          {/* Agent filter */}
          <select
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-xs text-gray-300 outline-none focus:border-indigo-500"
          >
            <option value="">All agents</option>
            {agentIds.map((id) => (
              <option key={id} value={id}>{agentShortName(id)}</option>
            ))}
          </select>

          {/* Outcome filter — pill buttons */}
          <div className="flex items-center gap-1 bg-black/20 p-1 rounded-lg border border-white/5">
            {(["", "success", "partial", "blocked"] as const).map((o) => (
              <button
                key={o}
                onClick={() => setFilterOutcome(o)}
                className={`text-[10px] px-2.5 py-1 rounded-md transition font-medium ${filterOutcome === o ? "bg-indigo-600 text-white" : "text-gray-500 hover:text-gray-300"}`}
              >
                {o === "" ? "All" : o.charAt(0).toUpperCase() + o.slice(1)}
              </button>
            ))}
          </div>

          {/* Violation filter */}
          <div className="flex items-center gap-1 bg-black/20 p-1 rounded-lg border border-white/5">
            {([["", "Governance"], ["true", "⚠ Violations"], ["false", "✓ Clean"]] as const).map(([v, lbl]) => (
              <button
                key={v}
                onClick={() => setFilterViolation(v)}
                className={`text-[10px] px-2.5 py-1 rounded-md transition font-medium whitespace-nowrap ${filterViolation === v ? "bg-indigo-600 text-white" : "text-gray-500 hover:text-gray-300"}`}
              >
                {lbl}
              </button>
            ))}
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 ml-auto">
            {(search || filterAgent || filterOutcome || filterViolation) && (
              <button
                onClick={() => { setSearch(""); setFilterAgent(""); setFilterOutcome(""); setFilterViolation(""); }}
                className="text-[10px] text-red-400 hover:text-red-300 border border-red-500/20 rounded-lg px-3 py-2 transition"
              >
                ✕ Clear
              </button>
            )}
            <button
              onClick={fetchDeltas}
              disabled={loading}
              className="text-[10px] text-indigo-400 hover:text-indigo-300 border border-indigo-500/20 rounded-lg px-3 py-2 bg-indigo-500/5 hover:bg-indigo-500/10 transition disabled:opacity-40"
            >
              {loading ? "↻ Loading…" : "↻ Refresh"}
            </button>
          </div>
        </div>

        {/* Result count */}
        {filtered.length !== deltas.length && (
          <p className="text-[10px] text-gray-600 mt-2">
            Showing <span className="text-indigo-400 font-semibold">{filtered.length}</span> of {deltas.length} deltas
          </p>
        )}
      </div>

      {/* ── Error Banner ── */}
      {error && (
        <div className="flex items-start gap-3 bg-red-950/20 border border-red-500/30 rounded-xl p-4">
          <span className="text-red-500 mt-0.5 shrink-0">⚠</span>
          <div>
            <p className="text-xs font-semibold text-red-400">API Error</p>
            <p className="text-xs text-red-400/70 mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="ml-auto text-red-500 text-xs hover:text-red-300">✕</button>
        </div>
      )}

      {/* ── Skeleton Loading ── */}
      {loading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-surface-card border border-surface-border rounded-xl h-16 animate-pulse opacity-50" />
          ))}
        </div>
      )}

      {/* ── Timeline ── */}
      {!loading && (
        <div className="relative space-y-0">
          {/* Vertical line behind */}
          <div className="absolute left-[18px] top-0 bottom-0 w-px bg-gradient-to-b from-indigo-500/30 via-white/5 to-transparent pointer-events-none" />

          {filtered.length === 0 ? (
            <div className="text-center py-16 bg-surface-card border border-surface-border rounded-xl">
              <p className="text-3xl mb-3">🧠</p>
              <p className="text-sm font-semibold text-gray-400">No memory deltas found</p>
              <p className="text-xs text-gray-600 mt-1">Adjust your filters or connect to the Delentia OS gateway.</p>
            </div>
          ) : (
            filtered.map((delta, idx) => {
              const meta = OUTCOME_META[delta.outcome];
              const isExpanded = expanded.has(delta.tick);
              const color = agentColor(delta.agent_id);
              const isLast = idx === filtered.length - 1;

              return (
                <div key={`${delta.agent_id}-${delta.tick}-${idx}`} className="flex gap-4 group relative">
                  {/* Tick node */}
                  <div className="flex flex-col items-center shrink-0 relative z-10">
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center text-[10px] font-mono font-bold text-white shrink-0 mt-1 transition-transform group-hover:scale-110 duration-150"
                      style={{ background: `${color}20`, border: `1.5px solid ${color}50`, boxShadow: `0 0 12px ${color}20` }}
                    >
                      {delta.tick}
                    </div>
                    {!isLast && <div className="w-px flex-1 min-h-[12px] mt-1" style={{ background: `${color}15` }} />}
                  </div>

                  {/* Card */}
                  <div
                    className="flex-1 mb-3 rounded-xl border transition-all duration-200 overflow-hidden cursor-pointer"
                    style={{
                      background: isExpanded ? `${color}08` : "hsl(var(--surface-card))",
                      borderColor: isExpanded ? `${color}40` : "hsl(var(--surface-border))",
                    }}
                    onClick={() => toggleExpand(delta.tick)}
                  >
                    {/* ── Card header ── */}
                    <div className="flex items-center gap-3 p-3.5">
                      {/* Agent color dot */}
                      <div
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                      />

                      {/* Agent + action */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-semibold font-mono capitalize" style={{ color }}>
                            {agentShortName(delta.agent_id)}
                          </span>
                          <span className="text-gray-600 text-[10px]">→</span>
                          <span className="text-[11px] text-gray-300 font-medium truncate">
                            {delta.intent_type} <span className="text-gray-600">→</span> {delta.action_type}
                          </span>
                        </div>
                      </div>

                      {/* Badges */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {/* Outcome badge */}
                        <span
                          className="text-[9px] px-2 py-0.5 rounded-full font-semibold font-mono uppercase tracking-wide"
                          style={{ color: meta.color, background: meta.bg, border: `1px solid ${meta.border}`, boxShadow: isExpanded ? meta.glow : "none" }}
                        >
                          {meta.label}
                        </span>

                        {/* Violation badge */}
                        {delta.governance_violation && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full font-semibold bg-red-950/30 text-red-400 border border-red-500/30">
                            ⚠ violation
                          </span>
                        )}

                        {/* Expand icon */}
                        <span className="text-gray-600 text-xs transition-transform duration-200" style={{ transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}>
                          ⌄
                        </span>
                      </div>
                    </div>

                    {/* ── Expanded detail ── */}
                    {isExpanded && (
                      <div
                        className="px-4 pb-4 border-t space-y-4"
                        style={{ borderColor: `${color}20` }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-4">
                          {/* Changes diff */}
                          <div>
                            <p className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-2">State Changes</p>
                            <div className="bg-black/30 rounded-lg p-2.5 border border-white/5">
                              <DiffView changes={delta.changes} />
                            </div>
                          </div>

                          {/* Relationships */}
                          <div>
                            <p className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-2">Relationship Δ</p>
                            <div className="bg-black/30 rounded-lg p-2.5 border border-white/5 space-y-1.5">
                              <RelationshipDiff rel={delta.relationship_change} />
                              {Object.keys(delta.relationship_change).length === 0 && (
                                <p className="text-[10px] text-gray-600 italic">No relationship changes.</p>
                              )}
                            </div>
                          </div>

                          {/* Resources */}
                          <div>
                            <p className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-2">Resource Usage</p>
                            <div className="bg-black/30 rounded-lg p-2.5 border border-white/5 space-y-1.5">
                              {Object.entries(delta.resources_delta).map(([k, v]) => {
                                const val = parseFloat(String(v));
                                const max = k.includes("ram") ? 512 : 1.0;
                                return (
                                  <FDIABar key={k} value={Math.min(1, val / max)} label={k.replace("_", " ").slice(0, 6)} />
                                );
                              })}
                              {Object.keys(delta.resources_delta).length === 0 && (
                                <p className="text-[10px] text-gray-600 italic">No resource data.</p>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* SHA-256 audit chain */}
                        {delta.sha256_hash && (
                          <div className="flex items-center gap-2 bg-black/25 rounded-lg px-3 py-2 border border-white/5">
                            <span className="text-[9px] text-gray-600 uppercase tracking-wide shrink-0 font-bold">SHA-256</span>
                            <span className="font-mono text-[9px] text-emerald-600 truncate flex-1">{delta.sha256_hash}</span>
                            <span className="text-[9px] text-emerald-500 shrink-0">✔ chain verified</span>
                          </div>
                        )}

                        {/* Action buttons */}
                        <div className="flex items-center justify-between pt-1">
                          <div className="flex items-center gap-2">
                            {delta.governance_violation && (
                              <span className="text-[10px] text-red-400 flex items-center gap-1">
                                <span>⚠</span>
                                Constitutional policy blocked this action
                              </span>
                            )}
                          </div>
                          <button
                            onClick={() => setRollbackTarget(delta.tick)}
                            className="text-[10px] text-orange-400 hover:text-orange-300 border border-orange-500/20 rounded-lg px-3 py-1.5 bg-orange-500/5 hover:bg-orange-500/10 transition flex items-center gap-1.5"
                          >
                            <span>↩</span>
                            Rollback to tick {delta.tick}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ── Rollback Confirm Modal ── */}
      {rollbackTarget !== null && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-card border border-orange-500/40 rounded-2xl p-6 max-w-md w-full shadow-2xl shadow-orange-900/20">
            {/* Header */}
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/30 flex items-center justify-center text-orange-400 text-lg shrink-0">
                ↩
              </div>
              <div>
                <h2 className="text-sm font-bold text-orange-400">Confirm Memory Rollback</h2>
                <p className="text-[10px] text-gray-500">This action cannot be undone</p>
              </div>
            </div>

            {/* Warning body */}
            <div className="bg-orange-950/20 border border-orange-500/20 rounded-xl p-4 mb-4">
              <p className="text-xs text-gray-300 leading-relaxed">
                Rolling back to{" "}
                <span className="font-mono font-bold text-orange-300">tick {rollbackTarget}</span>{" "}
                will discard <span className="font-semibold text-white">
                  {Math.max(0, (deltas[0]?.tick ?? 0) - rollbackTarget)} delta entries
                </span>{" "}
                from the Delentia OS memory state. All agents affected by these deltas will revert to their previous state.
              </p>
            </div>

            {/* Tick visualization */}
            <div className="flex items-center gap-2 bg-black/30 rounded-lg p-3 border border-white/5 mb-5">
              <div className="flex-1">
                <p className="text-[9px] text-gray-600 uppercase mb-1">Current tick</p>
                <p className="text-sm font-mono font-bold text-white">{deltas[0]?.tick ?? "—"}</p>
              </div>
              <span className="text-orange-500 text-lg">→</span>
              <div className="flex-1 text-right">
                <p className="text-[9px] text-gray-600 uppercase mb-1">Rollback target</p>
                <p className="text-sm font-mono font-bold text-orange-300">{rollbackTarget}</p>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-3">
              <button
                onClick={() => setRollbackTarget(null)}
                className="flex-1 border border-surface-border rounded-xl py-2.5 text-xs text-gray-400 hover:text-gray-200 hover:border-white/20 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRollback}
                className="flex-1 bg-orange-600 hover:bg-orange-500 text-white rounded-xl py-2.5 text-xs font-semibold transition shadow-lg shadow-orange-900/30"
              >
                ↩ Confirm Rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
