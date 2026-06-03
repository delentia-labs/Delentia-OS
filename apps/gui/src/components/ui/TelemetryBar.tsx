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
    <div className="bg-surface-card border-t border-surface-border text-gray-500 text-[10px] h-9 px-6 flex items-center justify-between font-mono shrink-0 select-none">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1 text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 glow-ok animate-pulse" />
          Gateway Live
        </span>
        <span>·</span>
        <span className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-amber-500" />
          {tokensPerSec} t/s
        </span>
        <span className="hidden sm:inline">·</span>
        <span className="hidden sm:flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-blue-500" />
          CPU: {cpuUsage}%
        </span>
        <span className="hidden sm:inline">·</span>
        <span className="hidden sm:flex items-center gap-1.5">
          <HardDrive className="w-3.5 h-3.5 text-purple-500" />
          GPU RAM: {ramUsage} GB / 16.0 GB
        </span>
      </div>

      <div className="flex items-center gap-4">
        <span className="hidden md:inline text-gray-600">Delta Engine Cache: 91.5%</span>
        <span>·</span>
        <span className="flex items-center gap-1.5 text-indigo-400">
          <ShieldCheck className="w-3.5 h-3.5" />
          SignedAI TIER_4 Secure
        </span>
      </div>
    </div>
  );
}
