"use client";

import { useEffect, useState } from "react";
import { Activity, Clock, ShieldCheck, Anchor } from "lucide-react";
import { fetchRuntimeStatus, type RuntimeStatus } from "@/lib/delentia-client";

// Round 50: every value here comes from the API (/health, /v1/daemon/status).
// The earlier bar animated invented tokens/s, CPU and GPU RAM figures and
// showed a fixed "Delta Engine Cache 91.5%" and "SignedAI TIER_4 Secure".

function formatUptime(seconds?: number): string {
  if (seconds === undefined) return "-";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const chip = "bg-surface/30 border border-surface-border/40 px-2.5 py-0.5 rounded-lg flex items-center gap-1.5 shadow-sm";

export function TelemetryBar() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await fetchRuntimeStatus();
      if (alive) setStatus(next);
    };
    load();
    const interval = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, []);

  const verify = status?.tasks.find((t) => t.name === "audit_chain_verify");
  const anchor = status?.tasks.find((t) => t.name === "audit_chain_anchor");
  const apiUp = status?.apiUp ?? false;

  return (
    <div className="bg-surface-card/65 backdrop-blur-md border-t border-surface-border/50 text-gray-500 text-[10px] h-10 px-6 flex items-center justify-between font-mono shrink-0 select-none shadow-[0_-4px_24px_rgba(0,0,0,0.45)]">
      <div className="flex items-center gap-2.5">
        <div
          className={`px-2.5 py-0.5 rounded-lg flex items-center gap-1.5 font-semibold shadow-sm border ${
            status === null
              ? "border-surface-border/40 text-gray-400"
              : apiUp
                ? "bg-emerald-950/20 border-emerald-800/30 text-emerald-400"
                : "bg-red-950/20 border-red-800/30 text-red-400"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${apiUp ? "bg-green-500" : "bg-red-500"}`} />
          {status === null ? "Checking API..." : apiUp ? `API up · v${status.version ?? "?"}` : "API unreachable"}
        </div>

        <div className={`hidden sm:flex ${chip} text-gray-300`} title="Background scheduler (delentia serve)">
          <Activity className="w-3 h-3 text-blue-500" />
          <span>Daemon: {status?.daemonRunning === undefined ? "-" : status.daemonRunning ? "running" : "stopped"}</span>
        </div>

        <div className={`hidden sm:flex ${chip} text-gray-300`}>
          <Clock className="w-3 h-3 text-purple-500" />
          <span>Uptime: {formatUptime(status?.uptimeSeconds)}</span>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <div className={`hidden md:flex ${chip} text-gray-400`} title={verify?.last_output ?? "not run yet"}>
          <ShieldCheck className={`w-3.5 h-3.5 ${verify?.last_status === "FAILED" ? "text-red-400" : "text-indigo-400"}`} />
          <span>Audit chain: {verify ? (verify.last_status === "PENDING" ? "not checked yet" : verify.last_status === "SUCCESS" ? "verified" : "BROKEN") : "-"}</span>
        </div>
        <div className={`hidden md:flex ${chip} text-gray-400`} title={anchor?.last_output ?? "set DELENTIA_AUDIT_ANCHOR_URL on the host"}>
          <Anchor className="w-3.5 h-3.5 text-amber-500" />
          <span>A3 anchor: {anchor ? (anchor.is_enabled ? anchor.last_status.toLowerCase() : "off") : "-"}</span>
        </div>
      </div>
    </div>
  );
}
