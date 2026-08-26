'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';

interface TierInfo {
  monthly_price_thb: number;
  token_limit: number;
  tokens_used: number;
  features: string[];
}

export default function BillingPage() {
  const [currentTier, setCurrentTier] = useState<string>('PRO');
  const [tiers, setTiers] = useState<Record<string, TierInfo>>({
    FREE: {
      monthly_price_thb: 0,
      token_limit: 100000,
      tokens_used: 14250,
      features: ['1+4 Local SLM (Bonsai-27B)', 'Basic Creator Profiler', 'Community 2D Sandbox']
    },
    PRO: {
      monthly_price_thb: 590,
      token_limit: 2500000,
      tokens_used: 320000,
      features: [
        '1+N Unlimited LoRA Hot-Swapping (<12ms)',
        'RCT-7 Deep Profiler & Blueprint Synthesis',
        'Stardew Valley Full Living AI Mod & BDI Engine',
        'Auto Code Generation via LoRA-Executor'
      ]
    },
    ENTERPRISE: {
      monthly_price_thb: 2900,
      token_limit: 15000000,
      tokens_used: 1850000,
      features: [
        'Sovereign Air-Gapped Offline Vault',
        'Thai Legal PDPA 2562 Contract Auditor',
        'PromptPay Smart Billing & EMVCo CRC-16 Engine',
        'SignedAI ED25519 Cryptographic SLA'
      ]
    }
  });

  const [selectedTierForPayment, setSelectedTierForPayment] = useState<string | null>(null);
  const [customerEmail, setCustomerEmail] = useState<string>('whale@delentia.com');
  const [activeInvoice, setActiveInvoice] = useState<any | null>(null);
  const [isCreatingInvoice, setIsCreatingInvoice] = useState<boolean>(false);

  const handleOpenPaymentModal = async (tierName: string) => {
    setSelectedTierForPayment(tierName);
    setIsCreatingInvoice(true);
    try {
      const resp = await fetch('http://127.0.0.1:8000/v1/billing/create-invoice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier: tierName,
          customer_email: customerEmail,
          promptpay_id: '0812345678'
        })
      });
      const data = await resp.json();
      setActiveInvoice(data.invoice);
    } catch (e: any) {
      // Fallback
      setActiveInvoice({
        invoice_id: `INV-${Date.now()}`,
        tier: tierName,
        amount_thb: tiers[tierName]?.monthly_price_thb || 590,
        qr_payload: '00020101021229370016A000000677010111011300668123456785802TH53037645406590.006304E8A2',
        signedai_seal: 'ED25519-7d8a91c0e2b3c4d5'
      });
    } finally {
      setIsCreatingInvoice(false);
    }
  };

  const activeQuota = tiers[currentTier] || tiers.PRO;
  const pctUsed = Math.round((activeQuota.tokens_used / activeQuota.token_limit) * 100);

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 p-4 md:p-6 font-sans selection:bg-purple-500/30">
      {/* Top Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              MONETIZATION & BILLING HUB
            </span>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              PROMPTPAY & STRIPE GATEWAYS ACTIVE
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
            💳 Billing, Quotas & Sovereign Subscription Tiers
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            เลือกแพ็กเกจการใช้งานสำหรับบุคคล, ครีเอเตอร์, และองค์กร พร้อมระบบชำระเงินผ่าน PromptPay QR และบัตรเครดิตสากล
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/enterprise"
            className="px-3.5 py-2 rounded-lg bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 text-xs font-mono font-semibold transition"
          >
            🛡️ Enterprise Vault
          </Link>
          <Link
            href="/profiler"
            className="px-3.5 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 text-xs font-mono font-semibold transition"
          >
            🧠 Deep Profiler
          </Link>
        </div>
      </header>

      {/* Active Quota Usage Meter */}
      <div className="max-w-7xl mx-auto mt-6 p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
        <div className="flex justify-between items-center text-xs font-mono">
          <span className="font-bold text-slate-200 flex items-center gap-2">
            <span>⚡ โควต้าการประมวลผลประจำเดือน (Active Plan: <span className="text-emerald-400 font-bold">{currentTier}</span>)</span>
          </span>
          <span className="text-slate-400">
            {activeQuota.tokens_used.toLocaleString()} / {activeQuota.token_limit.toLocaleString()} Tokens ({pctUsed}%)
          </span>
        </div>

        {/* Progress Bar */}
        <div className="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 to-cyan-500 transition-all duration-500"
            style={{ width: `${pctUsed}%` }}
          />
        </div>
      </div>

      {/* 3 Pricing Tiers Cards */}
      <main className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
        {/* FREE TIER */}
        <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            <span className="px-2.5 py-1 rounded bg-slate-800 text-[11px] font-mono text-slate-300 font-bold">
              STARTER / COMMUNITY
            </span>
            <div className="text-3xl font-extrabold text-white">0 ฿ <span className="text-xs text-slate-400 font-normal">/ เดือน</span></div>
            <p className="text-xs text-slate-400 leading-relaxed">
              สำหรับผู้เริ่มต้นทดลองใช้สมองกล 1+4 Bonsai และฟาร์มเสมือนจริงเบื้องต้น
            </p>
            <ul className="space-y-2.5 text-xs font-mono text-slate-300 pt-2 border-t border-slate-800">
              {tiers.FREE.features.map((f, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-emerald-400">✓</span> {f}
                </li>
              ))}
            </ul>
          </div>
          <button
            disabled
            className="w-full py-3 rounded-xl bg-slate-800 text-slate-500 font-bold text-xs font-mono cursor-not-allowed"
          >
            แผนปัจจุบัน
          </button>
        </div>

        {/* PRO TIER (POPULAR) */}
        <div className="p-6 rounded-2xl bg-slate-900/90 border-2 border-emerald-500/50 shadow-2xl shadow-emerald-950/30 flex flex-col justify-between space-y-6 relative">
          <div className="absolute -top-3 right-6 px-3 py-0.5 rounded-full bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-[10px] font-bold font-mono uppercase tracking-wider">
            ⭐ ยอดนิยมสำหรับ Creator
          </div>
          <div className="space-y-4">
            <span className="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[11px] font-mono font-bold">
              CREATOR PRO TIER
            </span>
            <div className="text-3xl font-extrabold text-white">590 ฿ <span className="text-xs text-slate-400 font-normal">/ เดือน ($19)</span></div>
            <p className="text-xs text-slate-400 leading-relaxed">
              ปลดล็อก 1+N Dynamic LoRA Swapping, Stardew Valley Living AI Mod และ RCT-7 Deep Profiler เต็มรูปแบบ
            </p>
            <ul className="space-y-2.5 text-xs font-mono text-slate-200 pt-2 border-t border-slate-800">
              {tiers.PRO.features.map((f, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-emerald-400 font-bold">✓</span> {f}
                </li>
              ))}
            </ul>
          </div>
          <button
            onClick={() => handleOpenPaymentModal('PRO')}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-bold text-xs font-mono shadow-xl transition"
          >
            ⚡ ชำระเงินผ่าน PromptPay QR (590 บาท)
          </button>
        </div>

        {/* ENTERPRISE SOVEREIGN TIER */}
        <div className="p-6 rounded-2xl bg-slate-900/60 border border-amber-500/40 flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            <span className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[11px] font-mono font-bold">
              SOVEREIGN ENTERPRISE
            </span>
            <div className="text-3xl font-extrabold text-white">2,900 ฿ <span className="text-xs text-slate-400 font-normal">/ เดือน ($99)</span></div>
            <p className="text-xs text-slate-400 leading-relaxed">
              สำหรับธุรกิจ SME, สำนักงานกฎหมาย และผู้ที่ต้องการระบบความมั่นคงออฟไลน์แบบ Air-Gapped 100%
            </p>
            <ul className="space-y-2.5 text-xs font-mono text-slate-300 pt-2 border-t border-slate-800">
              {tiers.ENTERPRISE.features.map((f, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-amber-400">✓</span> {f}
                </li>
              ))}
            </ul>
          </div>
          <button
            onClick={() => handleOpenPaymentModal('ENTERPRISE')}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-600 to-yellow-600 hover:from-amber-500 hover:to-yellow-500 text-slate-950 font-bold text-xs font-mono shadow-xl transition"
          >
            🛡️ สมัครใช้งาน Enterprise (2,900 บาท)
          </button>
        </div>
      </main>

      {/* Payment Modal */}
      {selectedTierForPayment && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full p-6 rounded-2xl bg-slate-900 border border-emerald-500/50 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex justify-between items-center">
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>📱 ชำระเงินผ่าน PromptPay Dynamic QR</span>
              </h3>
              <button
                onClick={() => setSelectedTierForPayment(null)}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            {activeInvoice ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center space-y-3 font-mono text-xs">
                <div className="text-emerald-400 font-bold text-sm">
                  ยอดชำระ: {activeInvoice.amount_thb.toLocaleString()} บาท
                </div>
                <div className="text-[11px] text-slate-400">
                  แพ็กเกจ: <strong className="text-white">{activeInvoice.tier} Tier</strong> • รหัสบิล: {activeInvoice.invoice_id}
                </div>
                <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[10px] text-cyan-300 break-all">
                  EMVCo Payload: {activeInvoice.qr_payload}
                </div>
                <div className="text-slate-400 text-[10px]">
                  ✓ รองรับการสแกนผ่านแอปธนาคารไทยทุกแห่ง (KBANK, SCB, KTB, BBL)
                </div>
                <div className="pt-2 border-t border-slate-800 text-[10px] text-purple-300">
                  🔏 ตรารับรอง: {activeInvoice.signedai_seal}
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-400 text-xs font-mono animate-pulse">
                กำลังคำนวณ Checksum CRC-16 และสร้าง QR Code...
              </div>
            )}

            <button
              onClick={() => {
                alert('✓ ยืนยันการชำระเงินสำเร็จ! สิทธิ์การใช้งานของคุณได้รับการอัปเกรดเรียบร้อยแล้ว');
                setCurrentTier(selectedTierForPayment);
                setSelectedTierForPayment(null);
              }}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 font-bold text-xs font-mono shadow-xl transition"
            >
              ✓ จำลองการชำระเงินสำเร็จ (Confirm Payment)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
