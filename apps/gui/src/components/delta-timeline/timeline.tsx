"use client";

import { useState, useEffect } from "react";
import { getMemoryHistory, rollbackMemory } from "@/lib/delentia-client";
import type { MemoryDelta } from "@/lib/types";
import {
  Search,
  Filter,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Hash,
  Clock,
  Link2,
} from "lucide-react";

const OUTCOME_COLORS = {
  success: "bg-green-500/10 border-green-500/30 text-green-400",
  partial: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  blocked: "bg-red-500/10 border-red-500/30 text-red-400",
};

const OUTCOME_ICONS = {
  success: CheckCircle2,
  partial: AlertCircle,
  blocked: XCircle,
};

export function DeltaTimeline() {
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
      const data = await getMemoryHistory();
      setDeltas(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDeltas();
  }, []);

  const filtered = deltas.filter((d) => {
    if (filterAgentId && !d.agent_id.toLowerCase().includes(filterAgentId.toLowerCase())) return false;
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
      await rollbackMemory(ticks);
      setRollbackConfirm(false);
      setRollbackTarget(null);
      await fetchDeltas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    }
  };

  return (
    <div className="space-y-6">
      {/* Filters Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-surface-card border border-surface-border rounded-xl p-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="ค้นหาตามรหัสเอเจนต์ (Agent ID)..."
            value={filterAgentId}
            onChange={(e) => setFilterAgentId(e.target.value)}
            className="w-full bg-surface border border-surface-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 outline-none focus:border-delentia-500 transition"
          />
        </div>
        
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-gray-500" />
          <select
            value={filterOutcome}
            onChange={(e) => setFilterOutcome(e.target.value as typeof filterOutcome)}
            className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-xs text-gray-200 outline-none focus:border-delentia-500 transition"
          >
            <option value="">สถานะผลลัพธ์ทั้งหมด (All Outcomes)</option>
            <option value="success">Success</option>
            <option value="partial">Partial</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>

        <select
          value={filterViolation}
          onChange={(e) => setFilterViolation(e.target.value as typeof filterViolation)}
          className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-xs text-gray-200 outline-none focus:border-delentia-500 transition"
        >
          <option value="">นโยบายความปลอดภัยทั้งหมด</option>
          <option value="true">ตรวจพบนโยบายละเมิด (Violations)</option>
          <option value="false">ไม่ละเมิดนโยบาย (Clean only)</option>
        </select>

        <button
          onClick={fetchDeltas}
          disabled={loading}
          className="flex items-center gap-1.5 ml-auto text-xs font-semibold text-delentia-500 hover:text-delentia-400 bg-delentia-600/5 hover:bg-delentia-600/10 border border-delentia-500/20 rounded-lg px-3.5 py-1.5 transition disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          รีเฟรชข้อมูล
        </button>
      </div>

      {error && (
        <div className="bg-red-950/20 border border-red-800/40 rounded-xl p-3 flex items-center gap-2 text-xs text-red-400">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && deltas.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 space-y-3">
          <RefreshCw className="w-6 h-6 text-delentia-500 animate-spin" />
          <p className="text-xs text-gray-500">กำลังโหลดบันทึกการเปลี่ยนแปลงหน่วยความจำ...</p>
        </div>
      )}

      {/* Timeline Grid */}
      <div className="relative border-l border-surface-border ml-4 pl-6 space-y-4">
        {filtered.map((delta, i) => {
          const OutcomeIcon = OUTCOME_ICONS[delta.outcome] || AlertCircle;
          return (
            <div
              key={`${delta.agent_id}-${delta.tick}-${i}`}
              className="relative group flex flex-col md:flex-row md:items-start gap-4"
            >
              {/* Dot Indicator on the Timeline line */}
              <div className="absolute -left-[31px] top-1.5 flex items-center justify-center w-6 h-6 rounded-full bg-surface border border-surface-border shadow-md">
                <Clock className="w-3 h-3 text-gray-400" />
              </div>

              {/* Tick badge on the left side */}
              <div className="w-20 shrink-0 text-left font-mono text-xs text-gray-500 pt-1.5">
                Tick #{delta.tick}
              </div>

              {/* Glass Card Details Panel */}
              <div className="flex-1 glass-card rounded-xl p-5 border border-surface-border/50 hover:border-delentia-500/20 transition duration-300">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-surface-border/30">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-indigo-400 bg-indigo-950/20 border border-indigo-900/30 px-2 py-0.5 rounded">
                      {delta.agent_id}
                    </span>
                    <span
                      className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${OUTCOME_COLORS[delta.outcome]}`}
                    >
                      <OutcomeIcon className="w-3 h-3" />
                      {delta.outcome}
                    </span>
                    {delta.governance_violation && (
                      <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border bg-red-950/20 border-red-500/30 text-red-400 font-semibold animate-pulse">
                        <ShieldAlert className="w-3 h-3" />
                        ละเมิดนโยบายความปลอดภัย
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setRollbackTarget(delta.tick);
                      setRollbackConfirm(true);
                    }}
                    className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-[10px] text-orange-400 hover:text-orange-300 transition duration-200 border border-orange-500/20 rounded-md px-2.5 py-1 bg-orange-500/5 hover:bg-orange-500/10"
                  >
                    <RotateCcw className="w-3 h-3" />
                    ย้อนกลับมาที่ Tick นี้
                  </button>
                </div>

                <div className="space-y-2">
                  <p className="text-gray-200 font-medium text-xs">
                    {delta.intent_type} <span className="text-gray-500">→</span> {delta.action_type}
                  </p>
                  
                  {delta.changes && Object.keys(delta.changes).length > 0 && (
                    <div className="bg-surface/50 rounded-lg p-2.5 border border-surface-border/40 text-[11px] font-mono text-gray-400 space-y-1">
                      <p className="text-gray-500 text-[10px] font-sans">ผลการเปลี่ยนแปลงในระบบ (System Changes):</p>
                      {Object.entries(delta.changes).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span>{k}:</span>
                          <span className="text-gray-300">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {delta.sha256_hash && (
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-500 mt-2 truncate bg-surface/30 px-2.5 py-1 rounded border border-surface-border/50 max-w-full">
                      <Hash className="w-3 h-3 text-gray-600 shrink-0" />
                      <span className="text-gray-600 font-sans">SHA-256 Chain:</span>
                      <span className="truncate">{delta.sha256_hash}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && !loading && (
          <div className="text-center text-gray-500 text-xs py-12">
            ไม่พบประวัติข้อมูล Memory delta ตามตัวกรองปัจจุบัน
          </div>
        )}
      </div>

      {/* Rollback Confirmation Modal */}
      {rollbackConfirm && rollbackTarget !== null && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 animate-in fade-in duration-200">
          <div className="bg-surface-card border border-orange-500/40 rounded-xl p-6 max-w-md w-full mx-4 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-orange-400">
              <RotateCcw className="w-5 h-5" />
              <h2 className="font-semibold text-sm">ยืนยันการย้อนกลับสถานะหน่วยความจำ (Confirm Rollback)</h2>
            </div>
            <p className="text-xs text-gray-300 leading-relaxed">
              การดำเนินการนี้จะทำการย้อนกลับสถานะหน่วยความจำ (Memory State) ของระบบ Delentia OS กลับไปที่สถานะใน
              <strong className="font-mono text-orange-400 bg-surface px-1.5 py-0.5 rounded border border-surface-border mx-1">Tick #{rollbackTarget}</strong>.
              ข้อมูลการเปลี่ยนแปลงทั้งหมดหลังจากจุดนี้จะถูกลบและสูญหายทันที ไม่สามารถยกเลิกการกระทำนี้ภายหลังได้
            </p>
            <div className="flex gap-3 justify-end pt-2">
              <button
                onClick={() => { setRollbackConfirm(false); setRollbackTarget(null); }}
                className="text-xs border border-surface-border rounded-lg px-4 py-2 text-gray-400 hover:text-gray-200 hover:bg-white/5 transition"
              >
                ยกเลิก (Cancel)
              </button>
              <button
                onClick={handleRollback}
                className="text-xs bg-orange-600 hover:bg-orange-500 text-white rounded-lg px-4 py-2 font-semibold shadow-md transition"
              >
                ยืนยันย้อนกลับสถานะ (Rollback)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
