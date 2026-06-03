"use client";

import { ChatWindow } from "@/components/intent-chat/chat-window";

export default function ChatPage() {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";

  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 7rem)" }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3 shrink-0">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600/80 to-purple-600/80 flex items-center justify-center text-base shadow-md shadow-indigo-900/30">
              💬
            </div>
            <h1 className="text-xl font-bold tracking-tight">Intent Chat</h1>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300 border border-indigo-700/30 font-mono uppercase tracking-wider">
              RCT v5
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            Constitutional AI chat · FDIA-scored · SignedAI-verified · HexaCore 9-tier routing
          </p>
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-2">
          {[
            { label: "FDIA Active",     color: "#10b981" },
            { label: "SignedAI On",     color: "#6366f1" },
            { label: "PDPA Compliant",  color: "#8b5cf6" },
          ].map(({ label, color }) => (
            <span
              key={label}
              className="flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-full border font-medium"
              style={{ color, borderColor: `${color}30`, background: `${color}10` }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: color, boxShadow: `0 0 6px ${color}` }}
              />
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Chat window — fills remaining height */}
      <div className="flex-1 min-h-0">
        <ChatWindow apiKey={apiKey} gateway={gateway} />
      </div>
    </div>
  );
}
