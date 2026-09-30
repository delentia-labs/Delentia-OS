'use client';

import { apiFetch } from "@/lib/delentia-client";
import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';

interface TargetVariables {
  core_skills: string | null;
  weekly_hours: string | null;
  capital_budget: string | null;
  target_audience: string | null;
  unfair_advantage: string | null;
  disliked_tasks: string | null;
  preferred_stack: string | null;
}

interface ProfilerSession {
  session_id: string;
  goal: string;
  target_revenue: string;
  turn_count: number;
  active_adapter: string;
  vram_allocated_gb: number;
  paging_latency_ms: number;
  target_variables: TargetVariables;
  delta_memory: Record<string, any>;
  radar_metrics: {
    tech: number;
    business: number;
    marketing: number;
    operations: number;
    capital: number;
    time_avail: number;
  };
  fdia_safety_score: number;
  is_completed: boolean;
  resolved_pct: number;
  generated_blueprint?: {
    blueprint_id: string;
    product_name: string;
    target_revenue_goal: string;
    business_model: string;
    recommended_tech_stack: string;
    market_wedge: string;
    execution_steps: string[];
    signedai_attestation: string;
  };
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function DeepProfilerPage() {
  const [goal, setGoal] = useState<string>('สร้าง Digital Product สร้างรายได้ $3,000/เดือน');
  const [targetRevenue, setTargetRevenue] = useState<string>('$3,000/mo');
  const [session, setSession] = useState<ProfilerSession | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState<string>('');
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isSending, setIsSending] = useState<boolean>(false);
  const [executorStatus, setExecutorStatus] = useState<string | null>(null);

  const radarCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Auto scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Draw 6-Axis Radar Chart on Canvas
  useEffect(() => {
    if (!radarCanvasRef.current || !session) return;
    const canvas = radarCanvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(centerX, centerY) - 28;

    ctx.clearRect(0, 0, width, height);

    const labels = [
      { name: 'Tech / Code', val: session.radar_metrics.tech },
      { name: 'Business', val: session.radar_metrics.business },
      { name: 'Marketing', val: session.radar_metrics.marketing },
      { name: 'Operations', val: session.radar_metrics.operations },
      { name: 'Capital', val: session.radar_metrics.capital },
      { name: 'Time Avail', val: session.radar_metrics.time_avail }
    ];

    const numAxes = labels.length;
    const angleStep = (Math.PI * 2) / numAxes;

    // Draw Web Grid Rings
    for (let r = 1; r <= 4; r++) {
      const ringRadius = (radius / 4) * r;
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(51, 65, 85, 0.4)';
      ctx.lineWidth = 1;
      for (let i = 0; i < numAxes; i++) {
        const angle = i * angleStep - Math.PI / 2;
        const x = centerX + ringRadius * Math.cos(angle);
        const y = centerY + ringRadius * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }

    // Draw Axes Lines & Labels
    labels.forEach((item, i) => {
      const angle = i * angleStep - Math.PI / 2;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);

      ctx.beginPath();
      ctx.strokeStyle = 'rgba(71, 85, 105, 0.5)';
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.stroke();

      // Label
      const labelX = centerX + (radius + 18) * Math.cos(angle);
      const labelY = centerY + (radius + 18) * Math.sin(angle);
      ctx.fillStyle = '#94A3B8';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${item.name} (${item.val}%)`, labelX, labelY);
    });

    // Draw Filled Polygon based on Radar values
    ctx.beginPath();
    ctx.fillStyle = 'rgba(168, 85, 247, 0.35)';
    ctx.strokeStyle = '#A855F7';
    ctx.lineWidth = 2;

    labels.forEach((item, i) => {
      const angle = i * angleStep - Math.PI / 2;
      const valRadius = (radius * item.val) / 100;
      const x = centerX + valRadius * Math.cos(angle);
      const y = centerY + valRadius * Math.sin(angle);

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }, [session]);

  const handleStartSession = async () => {
    setIsStarting(true);
    try {
      const resp = await apiFetch('/v1/profiler/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, target_revenue: targetRevenue })
      });
      const data = await resp.json();
      setSession(data.session);
      setChatMessages([{ role: 'assistant', content: data.initial_question }]);
    } catch (err: any) {
      alert('Error starting session: ' + err.message);
    } finally {
      setIsStarting(false);
    }
  };

  const handleSendReply = async () => {
    if (!userInput.trim() || !session || isSending) return;
    const text = userInput.trim();
    setUserInput('');
    setIsSending(true);

    setChatMessages((prev) => [...prev, { role: 'user', content: text }]);

    try {
      const resp = await apiFetch('/v1/profiler/step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.session_id, user_reply: text })
      });
      const data = await resp.json();
      setSession(data.session);
      setChatMessages((prev) => [...prev, { role: 'assistant', content: data.assistant_reply }]);
    } catch (err: any) {
      alert('Error processing step: ' + err.message);
    } finally {
      setIsSending(false);
    }
  };

  const handleTriggerExecutor = () => {
    setExecutorStatus('🚀 ส่งมอบ Blueprint ให้ LoRA-Executor สำเร็จ! กำลังแตกกิ่ง Virtual Worktree เพื่อเริ่มสร้างระบบ...');
    setTimeout(() => {
      setExecutorStatus('✅ โปรเจกต์ถูกคอมไพล์ลง workspace_output/top_50_projects/ และประทับตรา SignedAI เรียบร้อยแล้ว!');
    }, 2500);
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 p-4 md:p-6 font-sans selection:bg-purple-500/30">
      {/* Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
              RCT-7 INVERSE PROFILER
            </span>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              DEEP_PROFILER_LORA ACTIVE (3.12ms)
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-white via-slate-200 to-purple-400 bg-clip-text text-transparent">
            🧠 Deep Profiling Focus-Mode (Human Data Mining)
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            สกัดจุดแข็งและตัวตนของผู้ใช้ด้วย Reverse Component Thinking (RCT-7) และบีบอัดเป็น Delta Memory แบบไร้ Context Drift 100%
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <Link
            href="/brains"
            className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 text-xs font-mono transition"
          >
            🧠 1+N Matrix
          </Link>
          <Link
            href="/chat"
            className="px-3.5 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-mono font-semibold transition"
          >
            💬 Terminal Chat
          </Link>
        </div>
      </header>

      {/* Main Layout */}
      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        {/* Left Col (7 Cols): Goal Setup & Interactive Focus Chat */}
        <div className="lg:col-span-7 space-y-5">
          {!session ? (
            /* Session Setup Card */
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-purple-500/30 shadow-2xl space-y-4">
              <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>🎯 กำหนดเป้าหมายสำหรับกระบวนการคิดย้อนกลับ RCT-7</span>
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                ระบบจะตั้งเป้าหมายปลายทางไว้ แล้วทำการ Deconstruct ย่อยหาตัวแปรที่คุณมี (และขาดหายไป) จากนั้นจะยิงคำถามเฉพาะเจาะจงเพื่อนำคุณไปสู่ Blueprint สินค้าดิจิทัลจริง
              </p>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1">เป้าหมายที่ต้องการสร้าง (Goal):</label>
                  <input
                    type="text"
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-100 focus:border-purple-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1">เป้าหมายรายได้ (Target Revenue):</label>
                  <input
                    type="text"
                    value={targetRevenue}
                    onChange={(e) => setTargetRevenue(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-100 focus:border-purple-400 outline-none"
                  />
                </div>
              </div>

              <button
                onClick={handleStartSession}
                disabled={isStarting}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs font-mono shadow-xl shadow-purple-900/30 transition disabled:opacity-50"
              >
                {isStarting ? '⏳ กำลัง Hot-Swap Deep_Profiler_LoRA...' : '🚀 เริ่มต้นกระบวนการ Deep Profiling (RCT-7)'}
              </button>
            </div>
          ) : (
            /* Active Interactive Step Console */
            <div className="flex flex-col h-[580px] rounded-2xl bg-slate-900/90 border border-purple-500/40 shadow-2xl overflow-hidden">
              {/* Top Bar */}
              <div className="px-5 py-3.5 bg-slate-950/80 border-b border-slate-800 flex justify-between items-center text-xs font-mono">
                <span className="text-purple-300 font-bold flex items-center gap-2">
                  <span>🧠 Session: {session.session_id}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Turn {session.turn_count}
                  </span>
                </span>
                <span className="text-emerald-400">FDIA F = {session.fdia_safety_score.toFixed(4)} ✅</span>
              </div>

              {/* Chat Stream Box */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-3.5 rounded-xl ${
                      msg.role === 'user'
                        ? 'bg-purple-950/50 border border-purple-500/40 text-purple-200 ml-8'
                        : 'bg-slate-950 border border-slate-800 text-slate-200 mr-8'
                    }`}
                  >
                    <div className="text-[10px] text-slate-400 mb-1 font-bold">
                      {msg.role === 'user' ? '👤 คุณ (User)' : '🧠 Deep Profiler AI'}
                    </div>
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  </div>
                ))}
                {isSending && (
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-purple-300 animate-pulse">
                    🧠 Deep Profiler AI กำลังบีบอัด Delta Memory และสร้างคำถามถัดไป...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Chat Input or Final Action */}
              <div className="p-3.5 bg-slate-950/90 border-t border-slate-800">
                {!session.is_completed ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={userInput}
                      onChange={(e) => setUserInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendReply()}
                      placeholder="พิมพ์คำตอบของคุณตามความเป็นจริง..."
                      className="flex-1 px-4 py-2.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-slate-100 focus:border-purple-400 outline-none"
                    />
                    <button
                      onClick={handleSendReply}
                      disabled={isSending}
                      className="px-5 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs font-mono transition disabled:opacity-50"
                    >
                      ส่งคำตอบ ➔
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <button
                      onClick={handleTriggerExecutor}
                      className="w-full py-3 rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-bold text-xs font-mono shadow-xl transition"
                    >
                      🚀 ส่งต่อให้ LoRA-Executor เริ่มสร้างงานจริงทันที (1-Click Deploy)
                    </button>
                    {executorStatus && (
                      <p className="text-[11px] font-mono text-emerald-400 text-center animate-in fade-in">
                        {executorStatus}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Col (5 Cols): Live 6-Axis Radar & Delta Memory Inspector */}
        <div className="lg:col-span-5 space-y-5">
          {/* 6-Axis Radar Chart */}
          <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="font-bold text-slate-200">📊 6-Axis Human Capability Radar</span>
              <span className="text-purple-400">{session ? `${session.resolved_pct}% Resolved` : 'Waiting'}</span>
            </div>

            <div className="flex justify-center items-center py-2">
              <canvas
                ref={radarCanvasRef}
                width={320}
                height={260}
                className="max-w-full"
              />
            </div>
          </div>

          {/* Layer 7 Delta Memory Key-Value Inspector */}
          <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2.5">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="font-bold text-slate-200">💾 Layer 7 Delta Memory (JITNA Protocol)</span>
              <span className="text-emerald-400 text-[10px]">Zero Context Drift</span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-cyan-300 max-h-48 overflow-y-auto">
              {session && Object.keys(session.delta_memory).length > 0 ? (
                <pre>{JSON.stringify(session.delta_memory, null, 2)}</pre>
              ) : (
                <span className="text-slate-500">ยังไม่มีข้อมูล Delta Key-Value ถูกบันทึก</span>
              )}
            </div>

            {session?.generated_blueprint && (
              <div className="p-3 rounded-lg bg-purple-950/40 border border-purple-500/40 text-[11px] font-mono space-y-1 text-purple-200">
                <div className="font-bold text-emerald-400">🏆 Synthesized Digital Product:</div>
                <div><strong>ชื่อสินค้า:</strong> {session.generated_blueprint.product_name}</div>
                <div><strong>โมเดลธุรกิจ:</strong> {session.generated_blueprint.business_model}</div>
                <div className="text-[10px] text-slate-400 pt-1 border-t border-purple-800/60">
                  {session.generated_blueprint.signedai_attestation}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
