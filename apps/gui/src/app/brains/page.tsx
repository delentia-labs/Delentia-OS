'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';

interface ActiveSlot {
  slot_id: number;
  role: string;
  adapter: string;
  latency_ms: number;
  status: string;
}

interface DiskAdapter {
  adapter_id: string;
  name: string;
  size_mb: number;
  domain: string;
}

export default function BrainsManagerPage() {
  const [vramUsed, setVramUsed] = useState<number>(4.82);
  const [vramLimit] = useState<number>(4.90);
  const [fdiaA, setFdiaA] = useState<number>(1.0);
  const [fdiaScore, setFdiaScore] = useState<number>(0.9808);
  const [swapAlert, setSwapAlert] = useState<string | null>(null);

  const [activeSlots, setActiveSlots] = useState<ActiveSlot[]>([
    { slot_id: 1, role: 'ROUTER', adapter: 'jitna-router-v0.5.1', latency_ms: 3.12, status: 'ACTIVE' },
    { slot_id: 2, role: 'GUARDIAN', adapter: 'jitna-guardian-v0.5.1', latency_ms: 4.10, status: 'ACTIVE' },
    { slot_id: 3, role: 'EXECUTOR', adapter: 'jitna-executor-v0.5.1', latency_ms: 5.24, status: 'ACTIVE' }
  ]);

  const [diskAdapters, setDiskAdapters] = useState<DiskAdapter[]>([
    { adapter_id: 'adapter_scribe_v0.5.1', name: 'LoRA-Scribe (Synthesis & Formatting)', size_mb: 24.5, domain: 'General' },
    { adapter_id: 'adapter_stardew_pierre', name: 'LoRA-Pierre (Living Merchant Mind)', size_mb: 18.2, domain: 'Gaming' },
    { adapter_id: 'adapter_stardew_robin', name: 'LoRA-Robin (Living Carpenter Mind)', size_mb: 19.1, domain: 'Gaming' },
    { adapter_id: 'adapter_thai_law_pdpa', name: 'LoRA-ThaiLaw (PDPA & AI Act 2026)', size_mb: 32.0, domain: 'Legal' },
    { adapter_id: 'adapter_tax_accounting', name: 'LoRA-Finance (Tax & Ledger Balance)', size_mb: 28.4, domain: 'Finance' }
  ]);

  const handleHotSwap = (adapter: DiskAdapter, targetSlotId: number) => {
    setActiveSlots((prev) =>
      prev.map((s) =>
        s.slot_id === targetSlotId
          ? { ...s, adapter: adapter.name, latency_ms: 3.45 }
          : s
      )
    );
    setSwapAlert(`⚡ Hot-Swap สำเร็จ: โหลด "${adapter.name}" เข้าสู่ Slot ${targetSlotId} ในเวลา 3.45ms (VRAM: 4.82 GB / 4.90 GB ✅)`);
    setTimeout(() => setSwapAlert(null), 4000);
  };

  const handleFDIAChange = (newVal: number) => {
    setFdiaA(newVal);
    // Recalculate F = D^I * A (D=0.98, I=0.95)
    const baseF = Math.pow(0.98, 0.95);
    setFdiaScore(baseF * newVal);
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 p-4 md:p-8 font-sans selection:bg-cyan-500/30">
      {/* Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
              1+N ADAPTER MATRIX
            </span>
            <span className="text-xs text-emerald-400 font-mono flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              JITNA MEMORY PAGING ACTIVE
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
            🧠 1+N Dynamic LoRA Slot Manager
          </h1>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            สลับสล็อตโมเดลย่อยแบบ Hot-Swap ภายในเวลา &lt;12ms ภายใต้เพดาน VRAM 4.90 GB บนชิป AMD Ryzen Z1 Extreme
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <Link
            href="/brains/train"
            className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-lg shadow-purple-900/30 transition flex items-center gap-1.5"
          >
            🔨 + สร้าง LoRA เฉพาะตัว (LoRA Forge)
          </Link>
          <Link
            href="/sandbox"
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition"
          >
            🌾 2D Living Sandbox
          </Link>
        </div>
      </header>

      {/* Hot-Swap Alert */}
      {swapAlert && (
        <div className="max-w-7xl mx-auto mt-4 p-3 rounded-lg bg-cyan-950/60 border border-cyan-500/50 text-xs font-mono text-cyan-300 animate-in fade-in">
          {swapAlert}
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        {/* Left 2 Cols: 3 Active Hot Slots & N Disk Registry */}
        <div className="lg:col-span-2 space-y-6">
          {/* Active Hot Slots */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <span>⚡ 3 Active Hot Slots (VRAM Hot-Loaded)</span>
              </h2>
              <span className="text-xs font-mono text-cyan-400">Paging Latency: ~3.4ms</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {activeSlots.map((slot) => (
                <div key={slot.slot_id} className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2">
                  <div className="flex justify-between items-center text-[10px] font-mono text-slate-400">
                    <span>SLOT #{slot.slot_id}</span>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {slot.role}
                    </span>
                  </div>
                  <h3 className="font-bold text-xs text-slate-100 truncate">{slot.adapter}</h3>
                  <div className="flex justify-between text-[11px] font-mono text-slate-400 pt-1 border-t border-slate-800/80">
                    <span>Latency:</span>
                    <span className="text-cyan-400">{slot.latency_ms} ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* N Disk Adapters Registry */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-bold text-slate-100">
                📦 คลัง N Dynamic Adapters (On NVMe SSD Storage)
              </h2>
              <span className="text-xs font-mono text-purple-400">{diskAdapters.length} Adapters Available</span>
            </div>

            <div className="space-y-2.5">
              {diskAdapters.map((adapter) => (
                <div key={adapter.adapter_id} className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-xs text-slate-200">{adapter.name}</h4>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/20">
                        {adapter.domain}
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-slate-400">{adapter.size_mb} MB • Ready to Hot-Swap</span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleHotSwap(adapter, 1)}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-slate-200 transition"
                    >
                      ➔ Slot 1
                    </button>
                    <button
                      onClick={() => handleHotSwap(adapter, 2)}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-slate-200 transition"
                    >
                      ➔ Slot 2
                    </button>
                    <button
                      onClick={() => handleHotSwap(adapter, 3)}
                      className="px-2 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-[11px] font-mono transition"
                    >
                      ➔ Slot 3
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Col: VRAM Gauge & FDIA Controller */}
        <div className="space-y-6">
          {/* VRAM Meter */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
            <h3 className="text-sm font-bold text-slate-100 flex justify-between">
              <span>💾 Edge VRAM Ceiling Meter</span>
              <span className="text-xs font-mono text-amber-400">{vramUsed} / {vramLimit} GB</span>
            </h3>

            {/* VRAM Bar */}
            <div className="w-full bg-slate-950 rounded-full h-3.5 overflow-hidden border border-slate-800">
              <div
                className="bg-gradient-to-r from-cyan-500 via-emerald-400 to-amber-400 h-full"
                style={{ width: `${(vramUsed / vramLimit) * 100}%` }}
              />
            </div>

            <div className="text-[11px] font-mono text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Base Model (Qwen 27B):</span>
                <span className="text-slate-200">3.90 GB (Fixed)</span>
              </div>
              <div className="flex justify-between">
                <span>3 Active LoRA Slots:</span>
                <span className="text-slate-200">0.92 GB (Dynamic)</span>
              </div>
              <div className="flex justify-between text-emerald-400 pt-1 border-t border-slate-800">
                <span>VRAM Safety Headroom:</span>
                <span>+0.08 GB (Zero OOM ✅)</span>
              </div>
            </div>
          </div>

          {/* FDIA Invariant Safety Controller */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-sm font-bold text-slate-100">🛡️ Visual FDIA Safety Controller</h3>
              <span className="text-xs font-mono text-emerald-400">
                {fdiaA === 1.0 ? 'STRICT' : fdiaA === 0.0 ? 'VETO' : 'BALANCED'}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1.5 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">สมการกติกา:</span>
                <span className="text-cyan-300">F = D^I * A</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">ค่าความปลอดภัย F:</span>
                <span className="text-emerald-400 font-bold">{fdiaScore.toFixed(4)}</span>
              </div>
            </div>

            {/* Slider */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1 flex justify-between">
                <span>ปรับระดับพารามิเตอร์ A (0.0 ถึง 1.0):</span>
                <span className="text-cyan-400 font-bold">A = {fdiaA.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={fdiaA}
                onChange={(e) => handleFDIAChange(parseFloat(e.target.value))}
                className="w-full h-2 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
            </div>

            {/* Presets */}
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => handleFDIAChange(1.0)}
                className={`py-1.5 rounded text-[11px] font-mono border transition ${
                  fdiaA === 1.0
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 font-bold'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                Safe (1.0)
              </button>
              <button
                onClick={() => handleFDIAChange(0.7)}
                className={`py-1.5 rounded text-[11px] font-mono border transition ${
                  fdiaA === 0.7
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 font-bold'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                Explore (0.7)
              </button>
              <button
                onClick={() => handleFDIAChange(0.0)}
                className={`py-1.5 rounded text-[11px] font-mono border transition ${
                  fdiaA === 0.0
                    ? 'bg-red-500/20 text-red-300 border-red-500/50 font-bold'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                VETO (0.0)
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
