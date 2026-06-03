"use client";

import { useState, useEffect } from "react";
import { getMemoryHistory, rollbackMemory } from "@/lib/delentia-client";
import type { MemoryDelta } from "@/lib/types";

interface DeltaTimelineProps {
  apiKey: string;
  gateway: string;
}

const OUTCOME_COLORS = {
  success: "bg-green-500/20 border-green-500 text-green-400",
  partial: "bg-amber-500/20 border-amber-500 text-amber-400",
  blocked: "bg-red-500/20 border-red-500 text-red-400",
};

export function DeltaTimeline({ apiKey, gateway }: DeltaTimelineProps) {
  const [deltas, setDeltas] = useState<MemoryDelta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterAgentId, setFilterAgentId] = useState("");
  const [filterOutcome, setFilterOutcome] = useState<"" | "success" | "partial" | "blocked">("");
  const [filterViolation, setFilterViolation] = useState<"" | "true" | "false">("");
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);
  const [rollbackConfirm, setRollbackConfirm] = useState(false);

  const fetchDeltas = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryHistory({ apiKey, gateway });
      setDeltas(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiKey && gateway) fetchDeltas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, gateway]);

  const filtered = deltas.filter((d) => {
    if (filterAgentId && !d.agent_id.includes(filterAgentId)) return false;
    if (filterOutcome && d.outcome !== filterOutcome) return false;
    if (filterViolation === "true" && !d.governance_violation) return false;
    if (filterViolation === "false" && d.governance_violation) return false;
    return true;
  });

  const handleRollback = async () => {
    if (rollbackTarget === null) return;
    try {
      const latest = deltas[0]?.tick ?? 0;
      const ticks = Math.max(0, latest - rollbackTarget);
      await rollbackMemory(ticks, { apiKey, gateway });
      setRollbackConfirm(false);
      setRollbackTarget(null);
      await fetchDeltas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    }
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          placeholder="Filter by agent_id…"
          value={filterAgentId}
          onChange={(e) => setFilterAgentId(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 outline-none focus:border-delentia-500"
        />
        <select
          value={filterOutcome}
          onChange={(e) => setFilterOutcome(e.target.value as typeof filterOutcome)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-delentia-500"
        >
          <option value="">All outcomes</option>
          <option value="success">success</option>
          <option value="partial">partial</option>
          <option value="blocked">blocked</option>
        </select>
        <select
          value={filterViolation}
          onChange={(e) => setFilterViolation(e.target.value as typeof filterViolation)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-delentia-500"
        >
          <option value="">All governance</option>
          <option value="true">Violations only</option>
          <option value="false">Clean only</option>
        </select>
        <button
          onClick={fetchDeltas}
          className="ml-auto text-xs text-delentia-500 hover:text-delentia-400 border border-surface-border rounded-lg px-3 py-1.5"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading && (
        <p className="text-center text-gray-500 text-sm py-8">Loading memory history…</p>
      )}

      {/* Timeline */}
      <div className="space-y-2">
        {filtered.map((delta, i) => (
          <div
            key={`${delta.agent_id}-${delta.tick}-${i}`}
            className="flex gap-3 group"
          >
            {/* Tick indicator */}
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-white/5 border border-white/5 flex items-center justify-center text-[10px] font-mono text-gray-300 shadow-inner">
                {delta.tick}
              </div>
              <div className="flex-1 w-px bg-white/5 mt-1" />
            </div>

            {/* Content */}
            <div className="flex-1 glass-card rounded-xl p-4 text-sm mb-2">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-indigo-400">{delta.agent_id}</span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full border ${OUTCOME_COLORS[delta.outcome]}`}
                  >
                    {delta.outcome}
                  </span>
                  {delta.governance_violation && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full border bg-red-950/20 border-red-500/30 text-red-400 font-semibold glow-red">
                      ⚠ violation
                    </span>
                  )}
                </div>
                <button
                  onClick={() => {
                    setRollbackTarget(delta.tick);
                    setRollbackConfirm(true);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-[10px] text-orange-400 hover:text-orange-300 transition duration-150 border border-orange-500/20 rounded-md px-2.5 py-1 bg-orange-500/5 hover:bg-orange-500/10"
                >
                  Rollback to here
                </button>
              </div>
              <p className="text-gray-300 font-medium mt-1">
                {delta.intent_type} → {delta.action_type}
              </p>
              {delta.sha256_hash && (
                <p className="text-[9px] font-mono text-gray-600 mt-2 truncate max-w-lg bg-black/20 px-2 py-0.5 rounded border border-white/5">
                  SHA-256: {delta.sha256_hash}
                </p>
              )}
            </div>
          </div>
        ))}

        {filtered.length === 0 && !loading && (
          <p className="text-center text-gray-500 text-sm py-8">No memory deltas match the current filters.</p>
        )}
      </div>

      {/* Rollback confirm modal */}
      {rollbackConfirm && rollbackTarget !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-surface-card border border-orange-500 rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <h2 className="text-orange-400 font-semibold">Confirm Memory Rollback</h2>
            <p className="text-sm text-gray-300">
              This will roll back the Delentia OS memory state to tick{" "}
              <strong className="font-mono">{rollbackTarget}</strong>. All deltas
              after this point will be discarded. This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setRollbackConfirm(false); setRollbackTarget(null); }}
                className="text-sm border border-surface-border rounded-lg px-4 py-2 text-gray-400 hover:text-gray-200 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRollback}
                className="text-sm bg-orange-600 hover:bg-orange-500 text-white rounded-lg px-4 py-2 transition"
              >
                Rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
