"use client";

import React, { useState } from "react";
import { Terminal as TerminalIcon, CheckCircle2, ShieldCheck, Play, FolderCode, FileText, ChevronRight } from "lucide-react";

interface TerminalSandboxProps {
  logs?: string[];
  activeTool?: string;
  createdFiles?: string[];
  isOpen?: boolean;
  onToggle?: () => void;
}

export function TerminalSandbox({
  logs = [
    "[MCP Gateway] Initializing Layer 5 Tool Protocol...",
    "[JITNA v3] Protocol Handshake ACK (latency: 1.2ms)",
    "[SignedAI] Keypair Verified: ED25519-SHA256 (Valid)",
    "[Sandbox] Ready to execute safe local actions."
  ],
  activeTool = "delentia_file_writer",
  createdFiles = ["workspace_output/task_result.txt"],
  isOpen = true,
  onToggle
}: TerminalSandboxProps) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="w-full bg-[#070b14] border border-cyan-500/30 rounded-xl overflow-hidden shadow-2xl shadow-cyan-950/20 my-3 transition-all duration-200">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#0d1527] border-b border-cyan-500/20">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5 mr-2">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>
          <TerminalIcon className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-mono font-semibold text-cyan-200 tracking-wider">
            DELENTIA OS // SANDBOX TERMINAL
          </span>
          <span className="px-2 py-0.5 text-[10px] font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 rounded-full flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            ZERO-TRUST ISOLATED
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] font-mono text-gray-400 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            FDIA Gate: A=1
          </span>
        </div>
      </div>

      {/* Terminal Content Body */}
      <div className="p-4 font-mono text-xs text-gray-300 space-y-2 bg-[#050811] max-h-60 overflow-y-auto">
        <div className="text-emerald-400/90 flex items-center gap-1">
          <ChevronRight className="w-3.5 h-3.5" />
          <span>Kernel PID: 8000 | Sovereign Multi-Model Execution</span>
        </div>

        {logs.map((log, index) => (
          <div key={index} className="text-gray-300/80 pl-4 border-l border-cyan-500/20">
            {log}
          </div>
        ))}

        {createdFiles.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-800">
            <div className="text-cyan-400 flex items-center gap-1 mb-1.5 font-semibold">
              <FolderCode className="w-3.5 h-3.5" />
              <span>Generated Artifacts & Output Files:</span>
            </div>
            {createdFiles.map((file, idx) => (
              <div key={idx} className="flex items-center justify-between bg-cyan-950/30 border border-cyan-500/20 px-3 py-1.5 rounded-lg text-gray-200 text-[11px] mb-1">
                <span className="flex items-center gap-1.5">
                  <FileText className="w-3 h-3 text-cyan-400" />
                  {file}
                </span>
                <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Signed & Verified
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
