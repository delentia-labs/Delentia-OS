"use client";

import { useEffect, useState } from "react";
import { Cpu, HardDrive, ShieldCheck, Zap } from "lucide-react";

export function TelemetryBar() {
  const [tokensPerSec, setTokensPerSec] = useState(142.5);
  const [cpuUsage, setCpuUsage] = useState(14);
  const [ramUsage, setRamUsage] = useState(12.4);

  // Small telemetry animation loop
  useEffect(() => {
    const interval = setInterval(() => {
      setTokensPerSec((prev) => +(prev + (Math.random() * 2 - 1)).toFixed(1));
      setCpuUsage((prev) => Math.max(8, Math.min(25, prev + Math.floor(Math.random() * 5 - 2))));
      setRamUsage((prev) => +(prev + (Math.random() * 0.2 - 0.1)).toFixed(1));
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-surface-card/65 backdrop-blur-md border-t border-surface-border/50 text-gray-500 text-[10px] h-10 px-6 flex items-center justify-between font-mono shrink-0 select-none shadow-[0_-4px_24px_rgba(0,0,0,0.45)]">
      <div className="flex items-center gap-2.5">
        <div className="bg-emerald-950/20 border border-emerald-800/30 px-2.5 py-0.5 rounded-lg flex items-center gap-1.5 text-emerald-400 font-semibold shadow-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 glow-ok animate-pulse" />
          Gateway Live
        </div>
        
        <div className="bg-surface/30 border border-surface-border/40 px-2.5 py-0.5 rounded-lg flex items-center gap-1.5 hover:border-surface-border/80 hover:bg-surface/40 transition duration-150 shadow-sm text-gray-300">
          <Zap className="w-3 h-3 text-amber-500" />
          <span>{tokensPerSec} t/s</span>
        </div>

        <div className="hidden sm:flex bg-surface/30 border border-surface-border/40 px-2.5 py-0.5 rounded-lg items-center gap-1.5 hover:border-surface-border/80 hover:bg-surface/40 transition duration-150 shadow-sm text-gray-300">
          <Cpu className="w-3 h-3 text-blue-500" />
          <span>CPU: {cpuUsage}%</span>
        </div>

        <div className="hidden sm:flex bg-surface/30 border border-surface-border/40 px-2.5 py-0.5 rounded-lg items-center gap-1.5 hover:border-surface-border/80 hover:bg-surface/40 transition duration-150 shadow-sm text-gray-300">
          <HardDrive className="w-3 h-3 text-purple-500" />
          <span>GPU RAM: {ramUsage} GB / 16.0 GB</span>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <div className="hidden md:flex bg-surface/30 border border-surface-border/40 px-2.5 py-0.5 rounded-lg items-center gap-1.5 hover:border-surface-border/80 hover:bg-surface/40 transition duration-150 shadow-sm text-gray-400">
          <span>Delta Engine Cache: 91.5%</span>
        </div>
        
        <div className="bg-indigo-950/20 border border-indigo-900/30 px-2.5 py-0.5 rounded-lg flex items-center gap-1.5 text-indigo-400 font-semibold shadow-sm hover:border-indigo-700/50 transition duration-150">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>SignedAI TIER_4 Secure</span>
        </div>
      </div>
    </div>
  );
}

