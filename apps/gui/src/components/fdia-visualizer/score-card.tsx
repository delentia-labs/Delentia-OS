"use client";

import { useMemo } from "react";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from "recharts";
import type { FDIAScore } from "@/lib/types";
import { fdiaLevel } from "@/lib/types";

const COLOR_MAP = {
  critical:   { text: "text-red-400",   bg: "bg-red-500/20",   border: "border-red-500" },
  low:        { text: "text-orange-400", bg: "bg-orange-500/20", border: "border-orange-500" },
  acceptable: { text: "text-amber-400",  bg: "bg-amber-500/20",  border: "border-amber-500" },
  high:       { text: "text-green-400",  bg: "bg-green-500/20",  border: "border-green-500" },
};

/** Compact inline badge for use in chat messages */
export function FDIABadge({ score }: { score: FDIAScore }) {
  const level = fdiaLevel(score.F);
  const c = COLOR_MAP[level];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono border ${c.bg} ${c.border} ${c.text}`}>
      FDIA {score.F.toFixed(2)}
      {score.signed && <span title="SignedAI verified">✓</span>}
    </span>
  );
}

interface FDIAScoreCardProps {
  score: FDIAScore;
  title?: string;
}

/**
 * Full FDIA visualizer card.
 * Shows D/I/A sliders, formula display, Recharts radar, and level badge.
 * Formula: F = D^I × A
 */
export function FDIAScoreCard({ score, title = "FDIA Score" }: FDIAScoreCardProps) {
  const level = fdiaLevel(score.F);
  const c = COLOR_MAP[level];

  const radarData = useMemo(() => [
    { axis: "Data Quality (D)", value: score.D },
    { axis: "Intent Clarity (I)", value: score.I },
    { axis: "Action Confidence (A)", value: score.A },
  ], [score.D, score.I, score.A]);

  return (
    <div className={`bg-surface-card border ${c.border} rounded-xl p-4 space-y-4`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        <div className={`flex items-center gap-1.5 text-xs font-mono ${c.text}`}>
          <span className={`w-2 h-2 rounded-full ${c.bg} border ${c.border}`} />
          F = {score.F.toFixed(3)}
          {score.signed && (
            <span
              title={`SignedAI verified — hash: ${score.signature_hash.slice(0, 8)}…`}
              className="ml-1 text-green-400"
            >
              ✓ Signed
            </span>
          )}
        </div>
      </div>

      {/* Formula */}
      <p className="text-xs font-mono text-gray-500 text-center">
        F = D<sup>{score.I.toFixed(2)}</sup> × A = {score.D.toFixed(2)}
        <sup>{score.I.toFixed(2)}</sup> × {score.A.toFixed(2)} ={" "}
        <strong className={c.text}>{score.F.toFixed(4)}</strong>
      </p>

      {/* Radar chart */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid stroke="#2a2d3e" />
            <PolarAngleAxis
              dataKey="axis"
              tick={{ fill: "#9ca3af", fontSize: 9 }}
            />
            <Radar
              name="FDIA"
              dataKey="value"
              stroke="#3b6fe8"
              fill="#3b6fe8"
              fillOpacity={0.25}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Dimension bars */}
      {(["D", "I", "A"] as const).map((dim) => (
        <div key={dim} className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400">
            <span>
              {dim === "D" ? "Data Quality" : dim === "I" ? "Intent Clarity" : "Action Confidence"}
            </span>
            <span className="font-mono">{score[dim].toFixed(3)}</span>
          </div>
          <div className="h-1.5 w-full bg-surface-border rounded-full overflow-hidden">
            <div
              className="h-full bg-delentia-500 rounded-full transition-all"
              style={{ width: `${score[dim] * 100}%` }}
            />
          </div>
        </div>
      ))}

      {/* Hash footer */}
      {score.signature_hash && (
        <p className="text-[9px] font-mono text-gray-600 truncate">
          SHA-256: {score.signature_hash}
        </p>
      )}
    </div>
  );
}
