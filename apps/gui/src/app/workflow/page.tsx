'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';

interface Subagent {
  agent_id: string;
  role_title: string;
  lora_slot: string;
  system_prompt: string;
  capabilities: string[];
  status: string;
}

interface TeamData {
  team_id: string;
  team_name: string;
  objective: string;
  subagents: Subagent[];
  shared_delta_memory: Record<string, any>;
  pending_approvals: any[];
}

export default function WorkflowPage() {
  const [activeTab, setActiveTab] = useState<'HR_BUILDER' | 'TEMPLATES' | 'SWARM_MONITOR'>('HR_BUILDER');
  const [briefInput, setBriefInput] = useState<string>('เปิดร้านขายเสื้อผ้าแฟชั่นออนไลน์ อยากได้ทีมช่วยตอบแชทลูกค้า เขียนแคปชั่น TikTok และสรุปยอดเงินโอนพร้อมเพย์');
  const [isProvisioning, setIsProvisioning] = useState<boolean>(false);
  const [activeTeam, setActiveTeam] = useState<TeamData | null>(null);

  // Execution & Review Queue State
  const [taskPrompt, setTaskPrompt] = useState<string>('ลูกค้ารายใหม่สนใจสั่งซื้อชุดเดรสสีชมพู 2 ชุด ยอดรวม 1,180 บาท');
  const [isRunningTask, setIsRunningTask] = useState<boolean>(false);
  const [lastStepOutput, setLastStepOutput] = useState<any | null>(null);
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);

  // Fetch initial Golden SME Template
  const handleSelectTemplate = async (templateKey: string) => {
    setIsProvisioning(true);
    try {
      const resp = await fetch('http://127.0.0.1:8000/v1/swarm/templates');
      const data = await resp.json();
      if (data.templates && data.templates[templateKey]) {
        setActiveTeam(data.templates[templateKey]);
        setActiveTab('SWARM_MONITOR');
      }
    } catch (e: any) {
      alert('Error fetching template: ' + e.message);
    } finally {
      setIsProvisioning(false);
    }
  };

  const handleConversationalProvision = async () => {
    setIsProvisioning(true);
    try {
      const resp = await fetch('http://127.0.0.1:8000/v1/swarm/provision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief: briefInput })
      });
      const data = await resp.json();
      setActiveTeam(data.team);
      setActiveTab('SWARM_MONITOR');
    } catch (e: any) {
      alert('Provisioning failed: ' + e.message);
    } finally {
      setIsProvisioning(false);
    }
  };

  const handleRunSwarmTask = async () => {
    if (!activeTeam) return;
    setIsRunningTask(true);
    try {
      const resp = await fetch('http://127.0.0.1:8000/v1/swarm/run-team', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_id: activeTeam.team_id,
          task: taskPrompt
        })
      });
      const data = await resp.json();
      setLastStepOutput(data.data.outputs);
      setPendingApproval(data.data.pending_approval);
    } catch (e: any) {
      alert('Task execution error: ' + e.message);
    } finally {
      setIsRunningTask(false);
    }
  };

  const handleApproveAction = async () => {
    if (!activeTeam || !pendingApproval) return;
    try {
      const resp = await fetch('http://127.0.0.1:8000/v1/swarm/approve-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_id: activeTeam.team_id,
          approval_id: pendingApproval.approval_id
        })
      });
      const data = await resp.json();
      alert(`✓ อนุมัติสำเร็จ! ${data.data.message}\nSeal: ${data.data.signedai_seal}`);
      setPendingApproval((prev: any) => ({ ...prev, status: 'APPROVED (A = 1.0)' }));
    } catch (e: any) {
      alert('Approval failed: ' + e.message);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 p-4 md:p-6 font-sans selection:bg-purple-500/30">
      {/* Top Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
              AUTONOMOUS SWARM HR BUILDER
            </span>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              MULTI-LORA HOT-SWAPPING (0 TOKEN RAM)
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-white via-slate-200 to-indigo-400 bg-clip-text text-transparent">
            👔 Swarm HR Team Provisioner & Review Queue
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            สร้างทีม AI Agent เฉพาะทางใน 3 นาทีด้วยภาษาคน พร้อมระบบกระจายงานคู่ขนาน และคิวอนุมัติความปลอดภัย FDIA A=1.0
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/profiler"
            className="px-3.5 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 text-xs font-mono font-semibold transition"
          >
            🧠 Deep Profiler
          </Link>
          <Link
            href="/enterprise"
            className="px-3.5 py-2 rounded-lg bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 text-xs font-mono font-semibold transition"
          >
            🛡️ Enterprise Vault
          </Link>
        </div>
      </header>

      {/* Tabs Navigation */}
      <div className="max-w-7xl mx-auto flex gap-2 border-b border-slate-800 mt-6 pb-2 font-mono text-xs">
        <button
          onClick={() => setActiveTab('HR_BUILDER')}
          className={`px-4 py-2 rounded-lg transition font-semibold ${
            activeTab === 'HR_BUILDER' ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          🗣️ คุยกับ HR สร้างทีม (Conversational HR)
        </button>
        <button
          onClick={() => setActiveTab('TEMPLATES')}
          className={`px-4 py-2 rounded-lg transition font-semibold ${
            activeTab === 'TEMPLATES' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          📦 3 Golden SME Templates (1-Click Launch)
        </button>
        <button
          onClick={() => setActiveTab('SWARM_MONITOR')}
          className={`px-4 py-2 rounded-lg transition font-semibold ${
            activeTab === 'SWARM_MONITOR' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          ⚡ สั่งรันงานคู่ขนาน & Review Queue {activeTeam ? `(${activeTeam.subagents.length} Bots)` : ''}
        </button>
      </div>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto mt-6">
        {activeTab === 'HR_BUILDER' && (
          <div className="max-w-3xl mx-auto p-6 rounded-2xl bg-slate-900/80 border border-indigo-500/30 shadow-2xl space-y-4">
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <span>👔 หัวหน้า HR: &quot;บอกความต้องการของคุณมาได้เลยครับ เดี๋ยวผมจัดทีมให้ใน 3 นาที&quot;</span>
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed font-mono">
              พิมพ์บรีฟธุรกิจของคุณด้วยภาษาคน เช่น รูปแบบร้านค้า, งานที่อยากให้ช่วยแบ่งเบา (ตอบแชท, เขียนคอนเทนต์, สรุปยอดเงิน, ตรวจสัญญา)
            </p>

            <textarea
              value={briefInput}
              onChange={(e) => setBriefInput(e.target.value)}
              rows={4}
              className="w-full p-4 rounded-xl bg-slate-950 border border-slate-700 text-slate-100 text-xs font-mono leading-relaxed focus:border-indigo-400 outline-none"
            />

            <button
              onClick={handleConversationalProvision}
              disabled={isProvisioning}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs font-mono shadow-xl transition disabled:opacity-50"
            >
              {isProvisioning ? '⏳ กำลังวิเคราะห์และจัดสรรทีม Swarm...' : '🚀 สั่งหัวหน้า HR สร้างทีม AI Agent เดี๋ยวนี้ (3 นาที)'}
            </button>
          </div>
        )}

        {activeTab === 'TEMPLATES' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* E-Commerce Template */}
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-cyan-500/40 flex flex-col justify-between space-y-4 hover:border-cyan-400 transition">
              <div className="space-y-3">
                <span className="px-2.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[10px] font-mono font-bold">
                  RETAIL & E-COMMERCE
                </span>
                <h3 className="text-base font-bold text-white">🛍️ ทีม E-Commerce Solo</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  สำหรับพ่อค้าแม่ค้าออนไลน์คนเดียว: ตอบแชทลูกค้าตลอด 24 ชม., เขียนแคปชั่น TikTok/Shopee และออกบิลพร้อมเพย์ CRC-16
                </p>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300 space-y-1">
                  <div>🤖 Bot 1: ตอบแชท & สต็อก (Scribe LoRA)</div>
                  <div>✍️ Bot 2: เขียนแคปชั่นขายดี (Router LoRA)</div>
                  <div>💳 Bot 3: สรุปยอด PromptPay (Executor LoRA)</div>
                </div>
              </div>
              <button
                onClick={() => handleSelectTemplate('ECOMMERCE_SOLO')}
                className="w-full py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs font-mono transition"
              >
                ⚡ เลือกทีมนี้ (1-Click Launch)
              </button>
            </div>

            {/* Legal & Tax Template */}
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-amber-500/40 flex flex-col justify-between space-y-4 hover:border-amber-400 transition">
              <div className="space-y-3">
                <span className="px-2.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-mono font-bold">
                  SME COMPLIANCE & FINANCE
                </span>
                <h3 className="text-base font-bold text-white">⚖️ ทีม Legal & Tax SME</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  สำหรับธุรกิจ SME: ตรวจจับความเสี่ยงสัญญา PDPA 2562, คำนวณภาษีหัก ณ ที่จ่าย 3% และประทับตราดิจิทัล SignedAI
                </p>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300 space-y-1">
                  <div>📜 Bot 1: ตรวจสัญญา PDPA (Guardian LoRA)</div>
                  <div>📊 Bot 2: คำนวณภาษี WHT 3% (Executor LoRA)</div>
                  <div>🔏 Bot 3: ประทับตรา Notary (Guardian LoRA)</div>
                </div>
              </div>
              <button
                onClick={() => handleSelectTemplate('LEGAL_TAX_SME')}
                className="w-full py-3 rounded-xl bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs font-mono transition"
              >
                🛡️ เลือกทีมนี้ (1-Click Launch)
              </button>
            </div>

            {/* Creator Template */}
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-purple-500/40 flex flex-col justify-between space-y-4 hover:border-purple-400 transition">
              <div className="space-y-3">
                <span className="px-2.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-mono font-bold">
                  GAMING & CREATOR
                </span>
                <h3 className="text-base font-bold text-white">🎮 ทีม Creator & Game Modder</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  สำหรับนักสร้างเกม & คอนเทนต์: เขียนบทสนทนา NPC สไตล์ BDI Gate 10.6, ออกแบบเควสต์พิเศษ และวิเคราะห์ฟีดแบ็กผู้เล่น
                </p>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300 space-y-1">
                  <div>🌾 Bot 1: เขียนจิตวิทยา NPC (Scribe LoRA)</div>
                  <div>⚔️ Bot 2: วางโครงสร้างเควสต์ (Router LoRA)</div>
                  <div>📈 Bot 3: วิเคราะห์คอมเมนต์ (Executor LoRA)</div>
                </div>
              </div>
              <button
                onClick={() => handleSelectTemplate('CREATOR_MODDER')}
                className="w-full py-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs font-mono transition"
              >
                🎮 เลือกทีมนี้ (1-Click Launch)
              </button>
            </div>
          </div>
        )}

        {activeTab === 'SWARM_MONITOR' && activeTeam && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Active Swarm Team Card */}
            <div className="lg:col-span-5 p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
              <div>
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-mono font-bold">
                  ACTIVE SWARM TEAM
                </span>
                <h2 className="text-base font-bold text-white mt-1">{activeTeam.team_name}</h2>
                <p className="text-xs text-slate-400 font-mono mt-0.5">{activeTeam.objective}</p>
              </div>

              {/* Subagents List */}
              <div className="space-y-2.5 font-mono text-xs">
                {activeTeam.subagents.map((sa) => (
                  <div key={sa.agent_id} className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-indigo-300">{sa.role_title}</span>
                      <span className="px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 text-[10px] border border-indigo-800/40 uppercase">
                        {sa.lora_slot} LoRA
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-snug">{sa.system_prompt}</p>
                    <div className="flex gap-1.5 flex-wrap pt-1">
                      {sa.capabilities.map((c, i) => (
                        <span key={i} className="px-2 py-0.5 rounded bg-slate-900 text-slate-400 text-[9px] border border-slate-800">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* Task Dispatcher */}
              <div className="pt-3 border-t border-slate-800 space-y-2 font-mono text-xs">
                <label className="block text-slate-300 font-bold">🎯 ส่งงานให้ทีมประมวลผลคู่ขนาน:</label>
                <input
                  type="text"
                  value={taskPrompt}
                  onChange={(e) => setTaskPrompt(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-100 text-xs outline-none focus:border-emerald-400"
                />
                <button
                  onClick={handleRunSwarmTask}
                  disabled={isRunningTask}
                  className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs transition disabled:opacity-50"
                >
                  {isRunningTask ? '⏳ กำลังประมวลผลคู่ขนาน...' : '⚡ สั่งรันงาน Swarm ทันที'}
                </button>
              </div>
            </div>

            {/* Right: Parallel Execution Outputs & Review Queue */}
            <div className="lg:col-span-7 space-y-4">
              {/* Output Results */}
              <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <h3 className="font-bold text-slate-200">📡 ผลการทำงานคู่ขนานของ Subagents</h3>
                  <span className="text-[10px] text-emerald-400">FDIA INVARIANT VERIFIED</span>
                </div>

                {lastStepOutput ? (
                  <div className="space-y-3">
                    {Object.entries(lastStepOutput).map(([botId, botData]: [string, any]) => (
                      <div key={botId} className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                        <div className="font-bold text-cyan-300">[{botData.role}]</div>
                        <p className="text-slate-300 leading-relaxed text-[11px]">{botData.result}</p>
                        {botData.qr_payload && (
                          <div className="p-2 rounded bg-slate-900 text-[10px] text-amber-300 break-all border border-slate-800">
                            QR Payload: {botData.qr_payload}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-8 text-center text-slate-500">
                    กดปุ่ม &apos;สั่งรันงาน Swarm ทันที&apos; ด้านซ้ายเพื่อดูผลลัพธ์ของแต่ละ Subagent
                  </div>
                )}
              </div>

              {/* Human-in-the-Loop Smart Review Queue */}
              {pendingApproval && (
                <div className="p-5 rounded-2xl bg-slate-900 border-2 border-amber-500/50 shadow-2xl space-y-3 font-mono text-xs animate-in fade-in">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-amber-400 flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse"></span>
                      <span>🛡️ Human-in-the-Loop Approval Queue (A = 1.0)</span>
                    </span>
                    <span className="text-[10px] text-slate-400">{pendingApproval.approval_id}</span>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1 text-[11px]">
                    <div className="text-slate-300">
                      <strong>ภารกิจ:</strong> {pendingApproval.task_summary}
                    </div>
                    <div className="text-slate-400">
                      <strong>สถานะ:</strong> <span className="text-amber-300 font-bold">{pendingApproval.status}</span>
                    </div>
                    <div className="text-purple-300 text-[10px]">
                      <strong>ตราดิจิทัล:</strong> {pendingApproval.signedai_seal}
                    </div>
                  </div>

                  {pendingApproval.status.includes('PENDING') && (
                    <button
                      onClick={handleApproveAction}
                      className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-500 text-slate-950 font-bold text-xs shadow-lg hover:from-amber-400 hover:to-yellow-400 transition"
                    >
                      ✓ กดอนุมัติ (Human Sign A = 1.0) พร้อมประทับตรา ED25519
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
