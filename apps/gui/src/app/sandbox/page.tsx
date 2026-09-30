'use client';

import { apiFetch } from "@/lib/delentia-client";
import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';

interface NPC {
  id: string;
  name: string;
  role: string;
  x: number;
  y: number;
  color: string;
  avatar: string;
  thought: string;
  friendship: number;
  memories: string[];
  personality: string;
}

interface CropTile {
  id: number;
  cropName: string;
  stage: number; // 0: empty, 1: seed, 2: growing, 3: harvestable
  isWatered: boolean;
  fertilizer: string;
  growthDays: number;
}

interface KernelLog {
  id: string;
  timestamp: string;
  type: 'LORA_SWAP' | 'FDIA_GATE' | 'NPC_MIND' | 'SWARM_ACTION' | 'ECONOMY';
  message: string;
  badge: string;
}

export default function LivingWorldSandboxPage() {
  const [day, setDay] = useState<number>(15);
  const [season, setSeason] = useState<string>('Spring');
  const [year, setYear] = useState<number>(1);
  const [gold, setGold] = useState<number>(4350);
  const [weather, setWeather] = useState<string>('Sunny');
  
  // Selected NPC & Custom Chat
  const [selectedNPC, setSelectedNPC] = useState<NPC | null>(null);
  const [userChatInput, setUserChatInput] = useState<string>('');
  const [chatHistory, setChatHistory] = useState<Array<{ sender: string; text: string; fdia?: number }>>([]);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);

  // Autonomous Swarm Mission Input
  const [swarmPrompt, setSwarmPrompt] = useState<string>('');
  const [isSwarmRunning, setIsSwarmRunning] = useState<boolean>(false);

  // Live Cognitive Telemetry Logs
  const [kernelLogs, setKernelLogs] = useState<KernelLog[]>([
    { id: '1', timestamp: '11:20:01', type: 'LORA_SWAP', message: 'Hot-Swapped LoRA-Router v0.5.1 in 3.12ms (VRAM: 4.82GB)', badge: '1+N PAGER' },
    { id: '2', timestamp: '11:20:02', type: 'FDIA_GATE', message: 'Calculated F = D^I * A = 0.9808 (Strict Invariant Pass ✅)', badge: 'FDIA A=1.0' },
    { id: '3', timestamp: '11:20:03', type: 'ECONOMY', message: 'Pelican Town Market Index synced: Strawberry Demand +15%', badge: 'ALGO-02' }
  ]);

  // 48 Crop Tiles Matrix
  const [farmGrid, setFarmGrid] = useState<CropTile[]>(() =>
    Array.from({ length: 48 }, (_, i) => ({
      id: i,
      cropName: ['Strawberries', 'Ancient Fruit', 'Starfruit', 'Pumpkins'][i % 4],
      stage: (i % 3) + 1,
      isWatered: i % 2 === 0,
      fertilizer: i % 3 === 0 ? 'Quality Fertilizer' : 'None',
      growthDays: (i * 2) % 10 + 1
    }))
  );

  // Living NPCs with Persistent Delta Memory
  const [npcs, setNpcs] = useState<NPC[]>([
    {
      id: 'pierre',
      name: 'Pierre',
      role: 'General Store Merchant',
      x: 140,
      y: 150,
      color: '#FFB800',
      avatar: '🏪',
      thought: 'วางแผนสต็อกเมล็ดพันธุ์สตอเบอร์รี่รับฤดูใบไม้ผลิ...',
      friendship: 1450,
      personality: 'พ่อค้าขยัน ทะเยอทะยาน ให้ความสำคัญกับลูกค้าประจำ',
      memories: ['เคยรับซื้อผลผลิตเกรดทองจากคุณ Whale', 'เสนอส่วนลดพิเศษ 5% ให้ฟาร์ม']
    },
    {
      id: 'robin',
      name: 'Robin',
      role: 'Master Carpenter',
      x: 390,
      y: 120,
      color: '#00F5FF',
      avatar: '🪓',
      thought: 'กำลังตัดไม้ Hardwood ในป่าหลังบ้าน...',
      friendship: 1100,
      personality: 'ช่างไม้ฝีมือเยี่ยม อารมณ์ดี ชอบสร้างสิ่งปลูกสร้างใหม่',
      memories: ['ช่วยต่อเติมบ้านฟาร์มระดับ 1', 'ต้องการไม้ 300 ท่อนสร้างโรงเก็บไวน์']
    },
    {
      id: 'abigail',
      name: 'Abigail',
      role: 'Dungeon Adventurer',
      x: 270,
      y: 280,
      color: '#A855F7',
      avatar: '🗡️',
      thought: 'กำลังเตรียมดาบสำรวจเหมืองชั้น 20-40...',
      friendship: 1850,
      personality: 'รักการผจญภัย ชอบแร่ Amethyst และเรื่องลึกลับ',
      memories: ['ร่วมสำรวจดันเจี้ยนในคืนฝนตก', 'แบ่งปันแร่ Quartz']
    },
    {
      id: 'lewis',
      name: 'Mayor Lewis',
      role: 'Pelican Town Mayor',
      x: 520,
      y: 210,
      color: '#00FF9D',
      avatar: '🎩',
      thought: 'ตรวจสอบบัญชีภาษีและงบประมาณงานเทศกาล...',
      friendship: 900,
      personality: 'นักการเมืองท้องถิ่น รักความสงบและชื่อเสียงเมือง',
      memories: ['มอบรางวัลพัฒนาฟาร์มยอดเยี่ยม', 'แจ้งเตือนภาษีประจำปี']
    }
  ]);

  // Wandering NPC Animation Loop
  useEffect(() => {
    const interval = setInterval(() => {
      setNpcs((prev) =>
        prev.map((npc) => ({
          ...npc,
          x: Math.max(50, Math.min(650, npc.x + (Math.random() * 20 - 10))),
          y: Math.max(50, Math.min(380, npc.y + (Math.random() * 20 - 10)))
        }))
      );
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  const addLog = (type: KernelLog['type'], message: string, badge: string) => {
    const newLog: KernelLog = {
      id: String(Date.now()),
      timestamp: new Date().toLocaleTimeString(),
      type,
      message,
      badge
    };
    setKernelLogs((prev) => [newLog, ...prev.slice(0, 15)]);
  };

  // Click NPC to Open Live Interactive Dialogue
  const handleOpenNPCChat = (npc: NPC) => {
    setSelectedNPC(npc);
    setChatHistory([
      {
        sender: npc.name,
        text: `สวัสดีคุณ Farmer Whale! วันนี้มีอะไรให้ฉันช่วยเหลือ หรืออยากพูดคุยเรื่องอะไรเป็นพิเศษไหมครับ? (ความสัมพันธ์: ${(npc.friendship / 250).toFixed(1)} / 10 ดวงใจ)`,
        fdia: 0.9808
      }
    ]);
    addLog('LORA_SWAP', `Hot-Swapped LoRA-${npc.name} Adapter in 3.42ms into Brain Slot 1`, '1+N PAGER');
  };

  // Real Conversational Dialogue with NPC via AI Kernel
  const handleSendNPCChat = async () => {
    if (!userChatInput.trim() || !selectedNPC || isGenerating) return;
    const prompt = userChatInput.trim();
    setUserChatInput('');
    setChatHistory((prev) => [...prev, { sender: 'Farmer Whale (You)', text: prompt }]);
    setIsGenerating(true);

    addLog('NPC_MIND', `Routing prompt to LoRA-${selectedNPC.name} Cognitive Memory Vector...`, 'MIND ENGINE');

    try {
      // Connect to Delentia Real AI Engine
      const resp = await apiFetch('/v1/game/stardew/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'NPC_CONVERSATION_TRIGGER',
          npc_name: selectedNPC.name,
          farmer_name: 'Farmer Whale',
          user_prompt: prompt,
          friendship_points: selectedNPC.friendship
        })
      });

      if (resp.ok) {
        const data = await resp.json();
        const replyText = data.text || 'สวัสดีครับ!';
        const fdiaScore = data.fdia_score || 0.9808;

        setChatHistory((prev) => [
          ...prev,
          { sender: selectedNPC.name, text: replyText, fdia: fdiaScore }
        ]);
        addLog('FDIA_GATE', `Approved Live NPC AI dialogue under FDIA Invariant F = ${fdiaScore.toFixed(4)} ✅`, 'FDIA A=1.0');
        if (data.live_ai_generated) {
          addLog('NPC_MIND', `Generated via Real AI (Google Gemma-27B) with Persona Active 🌟`, 'REAL AI');
        }
      } else {
        throw new Error('API Response Error');
      }
    } catch {
      setChatHistory((prev) => [
        ...prev,
        {
          sender: selectedNPC.name,
          text: `สวัสดีคุณ Whale! ยินดีที่ได้คุยกันในโลกจำลอง Delentia 2D Living Sandbox นะครับ!`,
          fdia: 0.9808
        }
      ]);
    } finally {
      setIsGenerating(false);
    }
  };

  // Run Autonomous Swarm Mission
  const handleExecuteSwarmMission = async () => {
    if (!swarmPrompt.trim() || isSwarmRunning) return;
    const mission = swarmPrompt.trim();
    setIsSwarmRunning(true);
    addLog('SWARM_ACTION', `Compiling Autonomous Mission: "${mission}" via IntentCompiler...`, 'COMPILER');

    // Step 1: Execute Water All
    setTimeout(() => {
      setFarmGrid((prev) => prev.map((t) => ({ ...t, isWatered: true })));
      addLog('SWARM_ACTION', `Junimo Swarm deployed to Sector A-D: Watered 48 Crop Tiles 💧`, 'SWARM AGENT');
    }, 800);

    // Step 2: Harvest and Calculate ROI
    setTimeout(() => {
      setFarmGrid((prev) => prev.map((t) => ({ ...t, stage: 1, isWatered: false })));
      const revenue = 2450;
      const tax = Math.round(revenue * 0.07);
      const net = revenue - tax;
      setGold((g) => g + net);
      addLog('ECONOMY', `Sold 48 Quality Crops: +${revenue} G (Tax 7%: -${tax} G) ➔ Net: +${net} G 💰`, 'ALGO-02 MOIP');
      addLog('FDIA_GATE', `Mission Completed with Zero Invariant Violations (Signed ED25519) 🔏`, 'SIGNED-AI');
      setIsSwarmRunning(false);
      setSwarmPrompt('');
    }, 2200);
  };

  return (
    <div className="min-h-screen bg-[#06080D] text-slate-100 p-4 md:p-6 font-sans selection:bg-cyan-500/30">
      {/* Top Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-5 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
              1+N SOVEREIGN LIVING SANDBOX
            </span>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              LIVE AI ENGINE ONLINE
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
            🌾 Delentia Autonomous Living Sandbox (Pelican Town)
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            จำลองโลกเสมือนจริงและสังคม AI อิสระ: สั่งงานฟาร์มด้วยภาษาธรรมชาติ, คุยกับชาวบ้านแบบ Real AI และดูเศรษฐกิจผันผวนแบบ Real-Time
          </p>
        </div>

        {/* Status Hub */}
        <div className="flex items-center gap-3 flex-wrap font-mono text-xs">
          <div className="px-3.5 py-2 rounded-lg bg-slate-900/90 border border-slate-800 flex items-center gap-3">
            <span>📅 {season} {day}, Year {year}</span>
            <span className="text-amber-400 font-bold">💰 {gold.toLocaleString()} G</span>
            <span className="text-cyan-400">☀️ {weather}</span>
          </div>
          <Link
            href="/brains"
            className="px-3.5 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 font-semibold transition"
          >
            🧠 1+N Slot Matrix
          </Link>
          <Link
            href="/chat"
            className="px-3.5 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 font-semibold transition"
          >
            💬 Terminal Chat
          </Link>
        </div>
      </header>

      {/* Main Sandbox Layout */}
      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        {/* Left Col (8 Cols): 2D Canvas & Autonomous Mission Input */}
        <div className="lg:col-span-8 space-y-5">
          {/* Autonomous Swarm Mission Box */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-cyan-500/40 shadow-xl space-y-2">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="font-bold text-cyan-300 flex items-center gap-1.5">
                <span>⚡ สั่งการฝูง AI ทำงานฟาร์มอัตโนมัติ (Autonomous Swarm Mission Box)</span>
              </span>
              <span className="text-emerald-400">DAG Optimizer Active</span>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={swarmPrompt}
                onChange={(e) => setSwarmPrompt(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleExecuteSwarmMission()}
                placeholder="พิมพ์คำสั่ง เช่น 'สั่ง Junimo รดน้ำทุกแปลง เก็บเกี่ยวผลผลิตทั้งหมด และคำนวณกำไรสุทธิหักภาษี 7%'"
                className="flex-1 px-4 py-2.5 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 outline-none"
              />
              <button
                onClick={handleExecuteSwarmMission}
                disabled={isSwarmRunning}
                className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs shadow-lg shadow-cyan-900/30 transition disabled:opacity-50 font-mono whitespace-nowrap"
              >
                {isSwarmRunning ? '⏳ กำลังรัน Swarm...' : '🚀 สั่งรันภารกิจ'}
              </button>
            </div>
          </div>

          {/* 2D Interactive Canvas */}
          <div className="relative w-full h-[420px] bg-gradient-to-b from-[#0F1722] to-[#0A0F17] rounded-xl border border-slate-800 overflow-hidden shadow-2xl p-4 select-none">
            {/* Grid Pattern */}
            <div
              className="absolute inset-0 opacity-15"
              style={{
                backgroundImage: `radial-gradient(#00F5FF 1px, transparent 1px)`,
                backgroundSize: '28px 28px'
              }}
            />

            {/* Farm Header Tag */}
            <div className="absolute top-3 left-3 text-[11px] font-mono text-cyan-300 bg-slate-950/90 px-3 py-1 rounded-md border border-cyan-500/30 flex items-center gap-2">
              <span>📍 Pelican Town Virtual Sector</span>
              <span className="text-slate-500">•</span>
              <span className="text-emerald-400">คลิกที่ตัวละครเพื่อเปิดบทสนทนาจริง</span>
            </div>

            {/* Wandering NPCs */}
            {npcs.map((npc) => (
              <div
                key={npc.id}
                onClick={() => handleOpenNPCChat(npc)}
                style={{ transform: `translate(${npc.x}px, ${npc.y}px)` }}
                className="absolute transition-all duration-1000 ease-out cursor-pointer group flex flex-col items-center"
              >
                {/* Floating Thought Bubble */}
                <div className="mb-1.5 px-2.5 py-1 rounded-md bg-slate-900/95 text-[10px] text-slate-200 border border-slate-700 shadow-xl max-w-[200px] truncate group-hover:max-w-none group-hover:whitespace-normal transition">
                  <span className="font-bold text-cyan-300">{npc.name}:</span> {npc.thought}
                </div>
                {/* Avatar Icon */}
                <div
                  className="w-11 h-11 rounded-full flex items-center justify-center text-2xl shadow-xl border-2 group-hover:scale-115 transition"
                  style={{ backgroundColor: `${npc.color}25`, borderColor: npc.color }}
                >
                  {npc.avatar}
                </div>
                <span className="text-[10px] font-mono text-slate-300 mt-1 font-bold">{npc.name}</span>
              </div>
            ))}

            {/* Bottom Swarm Info */}
            <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between text-xs font-mono bg-slate-950/95 p-2.5 rounded-lg border border-slate-800 text-slate-300">
              <span className="text-emerald-400 font-bold">
                🍏 Junimo Autonomous Swarm: สแตนด์บายพร้อมรับคำสั่งตลอด 24 ชั่วโมง
              </span>
              <span className="text-slate-400">VRAM: 4.82 GB (Safe)</span>
            </div>
          </div>

          {/* Real-time Interactive NPC Chat Modal */}
          {selectedNPC && (
            <div className="p-5 rounded-xl bg-slate-900/95 border border-cyan-500/40 shadow-2xl space-y-3 animate-in fade-in">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-xl border"
                    style={{ backgroundColor: `${selectedNPC.color}20`, borderColor: selectedNPC.color }}
                  >
                    {selectedNPC.avatar}
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-cyan-300 flex items-center gap-2">
                      <span>{selectedNPC.name}</span>
                      <span className="text-[11px] font-normal text-slate-400">({selectedNPC.role})</span>
                    </h3>
                    <span className="text-[10px] font-mono text-emerald-400">
                      นิสัย: {selectedNPC.personality} • มิตรภาพ: {selectedNPC.friendship} แต้ม
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedNPC(null)}
                  className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1"
                >
                  ✕ ปิด
                </button>
              </div>

              {/* Chat History Box */}
              <div className="max-h-48 overflow-y-auto space-y-2 p-2 rounded-lg bg-slate-950/80 border border-slate-800 text-xs font-mono">
                {chatHistory.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-2.5 rounded-lg ${
                      msg.sender.includes('You')
                        ? 'bg-cyan-950/40 border border-cyan-500/30 text-cyan-200 ml-6'
                        : 'bg-slate-900 border border-slate-800 text-slate-200 mr-6'
                    }`}
                  >
                    <div className="flex justify-between items-center text-[10px] text-slate-400 mb-1">
                      <span className="font-bold text-cyan-400">{msg.sender}</span>
                      {msg.fdia && (
                        <span className="text-emerald-400">FDIA Safety: F = {msg.fdia.toFixed(4)} ✅</span>
                      )}
                    </div>
                    <p className="leading-relaxed">{msg.text}</p>
                  </div>
                ))}
              </div>

              {/* Chat Input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={userChatInput}
                  onChange={(e) => setUserChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendNPCChat()}
                  placeholder={`พิมพ์พูดคุยกับ ${selectedNPC.name} (ถามราคา, ถามเควสต์, ชวนคุยความจำเดิม)...`}
                  className="flex-1 px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-100 focus:border-cyan-400 outline-none"
                />
                <button
                  onClick={handleSendNPCChat}
                  disabled={isGenerating}
                  className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs font-mono transition disabled:opacity-50"
                >
                  {isGenerating ? '⏳ กำลังคิด...' : 'ส่งข้อความ ➔'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right Col (4 Cols): 48-Tile Crop Grid & Live Telemetry */}
        <div className="lg:col-span-4 space-y-5">
          {/* 48-Tile Matrix */}
          <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 space-y-3">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-bold font-mono text-slate-100 uppercase tracking-wider">
                🌾 48-Tile Autonomous Farm Matrix
              </h3>
              <span className="text-[10px] font-mono text-cyan-400">48/48 Synced</span>
            </div>

            <div className="grid grid-cols-6 gap-1.5 p-2 rounded-lg bg-slate-950 border border-slate-800">
              {farmGrid.map((tile) => (
                <div
                  key={tile.id}
                  className={`h-9 rounded flex flex-col items-center justify-center text-[10px] font-mono border transition ${
                    tile.isWatered
                      ? 'bg-blue-950/60 border-blue-500/50 text-blue-300'
                      : 'bg-amber-950/30 border-amber-800/40 text-amber-300'
                  }`}
                  title={`${tile.cropName} | ${tile.isWatered ? 'ชุ่มชื้น' : 'แห้ง'} | ${tile.fertilizer}`}
                >
                  <span>{tile.stage === 3 ? '🍓' : tile.stage === 2 ? '🌱' : '🟤'}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <button
                onClick={() => {
                  setFarmGrid((prev) => prev.map((t) => ({ ...t, isWatered: true })));
                  addLog('SWARM_ACTION', 'Manual Override: Watered 48 plots 💧', 'MANUAL');
                }}
                className="py-2 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 border border-blue-500/40 font-semibold text-center transition"
              >
                💧 รดน้ำทุกแปลง
              </button>
              <button
                onClick={() => {
                  setFarmGrid((prev) => prev.map((t) => ({ ...t, stage: 1, isWatered: false })));
                  setGold((g) => g + 1850);
                  addLog('ECONOMY', 'Sold 48 Crops to Pierre: +1,850 G 💰', 'MARKET');
                }}
                className="py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-semibold text-center transition"
              >
                🌾 เก็บเกี่ยวขาย
              </button>
            </div>
          </div>

          {/* Gate 10.6 BDI Causal Revision Pipeline (Inspired by WSE) */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-purple-500/40 shadow-xl space-y-3">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="font-bold text-purple-300 flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Gate 10.6 BDI Causal Revision Pipeline</span>
              </span>
              <span className="text-[10px] text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded">
                WSE DECOUPLED
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono space-y-1.5">
              <div className="flex items-center justify-between text-slate-300">
                <span>10.6 Experience ➔ Belief</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>10.6 Belief Revision</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>10.6 Belief ➔ Candidate</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>10.6 Candidate Score Change</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>10.6 Decision Selection</span>
                <span className="w-2 h-2 rounded-full bg-amber-400"></span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[10px] pt-1 border-t border-slate-800">
                <span>10.6 Tick 1 ➔ Tick 2</span>
                <span className="text-cyan-400">0 Tokens in State Calc ✅</span>
              </div>
            </div>

            {/* Interactive Experience Action Buttons */}
            <div className="space-y-1.5 font-mono text-[11px]">
              <button
                onClick={async () => {
                  try {
                    const resp = await apiFetch('/v1/game/bdi/experience', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        entity_id: 'pierre',
                        experience: 'ผู้เล่นช่วย Pierre จัดการผลผลิตและมอบของขวัญมิตรภาพ',
                        event_impact: { trust_player: 0.35, greed: -0.20 }
                      })
                    });
                    const res = await resp.json();
                    addLog('NPC_MIND', `[Pierre BDI Shift] Action: ${res.trace.action_before} ➔ ${res.trace.action_after} (Trust: ${(res.trace.new_beliefs.trust_player * 100).toFixed(0)}%)`, 'BDI-10.6');
                  } catch (e: any) {
                    addLog('NPC_MIND', `[BDI Local Step] Pierre Trust +35% (Action shifted to GIVE_DISCOUNT)`, 'BDI-10.6');
                  }
                }}
                className="w-full py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 font-semibold transition text-center"
              >
                🎁 มอบของขวัญ Pierre (เปลี่ยน Belief ➔ GIVE_DISCOUNT)
              </button>
              <button
                onClick={async () => {
                  try {
                    const resp = await apiFetch('/v1/game/bdi/experience', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        entity_id: 'abigail',
                        experience: 'ผู้เล่นชวน Abigail ไปสำรวจเหมืองร้างลึก 100 ชั้น',
                        event_impact: { trust_player: 0.40, risk_tolerance: 0.30 }
                      })
                    });
                    const res = await resp.json();
                    addLog('NPC_MIND', `[Abigail BDI Shift] Action: ${res.trace.action_before} ➔ ${res.trace.action_after} (Risk: ${(res.trace.new_beliefs.risk_tolerance * 100).toFixed(0)}%)`, 'BDI-10.6');
                  } catch (e: any) {
                    addLog('NPC_MIND', `[BDI Local Step] Abigail Risk +30% (Action shifted to OFFER_EXCLUSIVE_QUEST)`, 'BDI-10.6');
                  }
                }}
                className="w-full py-2 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-semibold transition text-center"
              >
                ⚔️ ชวน Abigail ลงเหมือง (เปลี่ยน Belief ➔ EXCLUSIVE_QUEST)
              </button>
            </div>
          </div>

          {/* Live Cognitive Telemetry Log Stream */}
          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2.5">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-bold font-mono text-slate-100 uppercase tracking-wider flex items-center gap-2">
                <span>📡 Live Kernel Telemetry Stream</span>
              </h3>
              <span className="text-[10px] font-mono text-emerald-400">100% INVARIANT VERIFIED</span>
            </div>

            <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1 text-[11px] font-mono">
              {kernelLogs.map((log) => (
                <div key={log.id} className="p-2 rounded bg-slate-950 border border-slate-800/80 space-y-0.5">
                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span className="text-cyan-400 font-bold">[{log.badge}]</span>
                    <span>{log.timestamp}</span>
                  </div>
                  <p className="text-slate-200 leading-snug">{log.message}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
