"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  KeyboardEvent,
} from "react";
import { useStreamIntent } from "@/hooks/useIntent";
import { FDIABadge } from "@/components/fdia-visualizer/score-card";
import type { FDIAScore } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────
type Mode = "quick" | "standard" | "deep" | "mirror";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  fdia?: FDIAScore;
  hexa_role?: string;
  streaming?: boolean;
  timestamp: Date;
  mode?: Mode;
  copied?: boolean;
}

interface ChatWindowProps {
  apiKey: string;
  gateway: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────
const MODES: { value: Mode; label: string; icon: string; desc: string; color: string }[] = [
  { value: "quick",    label: "Quick",    icon: "⚡", desc: "Fast · LPU-optimized · Groq adapter",           color: "#f59e0b" },
  { value: "standard", label: "Standard", icon: "◎", desc: "Balanced · RCT v5 multi-tier routing",           color: "#6366f1" },
  { value: "deep",     label: "Deep",     icon: "🔬", desc: "Thorough · Supreme Architect · 1M ctx",          color: "#8b5cf6" },
  { value: "mirror",   label: "Mirror",   icon: "🔮", desc: "9-model consensus · Highest accuracy",           color: "#ec4899" },
];

const SLASH_COMMANDS = [
  { cmd: "/summarize",  desc: "Summarize a document or topic" },
  { cmd: "/translate",  desc: "Translate text to Thai / EN" },
  { cmd: "/analyze",    desc: "Deep analysis with FDIA scoring" },
  { cmd: "/pdpa",       desc: "PDPA compliance check (Thailand)" },
  { cmd: "/audit",      desc: "Run a full constitutional AI audit" },
  { cmd: "/explain",    desc: "Explain a concept step-by-step" },
  { cmd: "/compare",    desc: "Compare options with pros/cons" },
  { cmd: "/draft",      desc: "Draft a document or email" },
];

const WELCOME_SUGGESTIONS = [
  "ตรวจสอบความสอดคล้องกับ PDPA มาตรา 40 ของสัญญานี้",
  "Summarize the Delentia OS architecture for a non-technical audience",
  "Translate this legal clause to Thai and flag ambiguities",
  "Run a constitutional AI compliance audit on my intent pipeline",
  "Compare HexaCore model tiers by cost vs. accuracy",
];

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatTime(d: Date) {
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

function roleLabel(r?: string) {
  return r ? r.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "HexaCore";
}

// ─── Slash Command Palette ────────────────────────────────────────────────────
function SlashPalette({
  query,
  onSelect,
}: {
  query: string;
  onSelect: (cmd: string) => void;
}) {
  const filtered = SLASH_COMMANDS.filter((c) =>
    c.cmd.includes(query.toLowerCase())
  );
  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full mb-2 left-0 right-0 bg-surface-card border border-surface-border rounded-xl shadow-2xl shadow-black/50 overflow-hidden z-50">
      <div className="px-3 py-2 border-b border-surface-border">
        <p className="text-[9px] font-bold text-gray-600 uppercase tracking-wider">Slash Commands</p>
      </div>
      {filtered.map((c) => (
        <button
          key={c.cmd}
          onClick={() => onSelect(c.cmd + " ")}
          className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-white/5 transition text-left group"
        >
          <span className="text-xs font-mono font-semibold text-indigo-400 group-hover:text-indigo-300 w-24 shrink-0">
            {c.cmd}
          </span>
          <span className="text-[11px] text-gray-500 group-hover:text-gray-300">{c.desc}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Mode Pill ────────────────────────────────────────────────────────────────
function ModePill({
  mode,
  active,
  onClick,
}: {
  mode: typeof MODES[number];
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={mode.desc}
      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-150 ${
        active
          ? "text-white shadow-md"
          : "text-gray-500 hover:text-gray-300 hover:bg-white/5"
      }`}
      style={active ? { background: `${mode.color}20`, border: `1px solid ${mode.color}40`, color: mode.color } : {}}
    >
      <span>{mode.icon}</span>
      <span>{mode.label}</span>
    </button>
  );
}

// ─── Message Bubble ───────────────────────────────────────────────────────────
function MessageBubble({
  msg,
  onCopy,
  onRegenerate,
  isLast,
}: {
  msg: Message;
  onCopy: (id: string, text: string) => void;
  onRegenerate?: () => void;
  isLast: boolean;
}) {
  const isUser = msg.role === "user";
  const modeInfo = MODES.find((m) => m.value === msg.mode);

  return (
    <div className={`group flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} items-start`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-xl flex items-center justify-center text-sm shrink-0 mt-0.5 font-bold ${
          isUser
            ? "bg-indigo-600/30 border border-indigo-500/40 text-indigo-300"
            : "bg-gradient-to-br from-purple-600/30 to-indigo-600/30 border border-purple-500/30 text-purple-300"
        }`}
      >
        {isUser ? "U" : "D"}
      </div>

      {/* Bubble */}
      <div className={`flex flex-col gap-1.5 max-w-[78%] ${isUser ? "items-end" : "items-start"}`}>
        {/* Role label (assistant only) */}
        {!isUser && (
          <div className="flex items-center gap-2 px-0.5">
            <span className="text-[10px] font-semibold text-purple-400">Delentia AI</span>
            {msg.hexa_role && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-900/30 text-purple-400 border border-purple-700/30 font-mono">
                {roleLabel(msg.hexa_role)}
              </span>
            )}
            {modeInfo && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full font-mono" style={{ color: modeInfo.color, background: `${modeInfo.color}15` }}>
                {modeInfo.icon} {modeInfo.label}
              </span>
            )}
          </div>
        )}

        {/* Content */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed transition-all ${
            isUser
              ? "bg-indigo-600/20 border border-indigo-500/30 text-white rounded-tr-sm"
              : "bg-surface-card border border-surface-border text-gray-100 rounded-tl-sm"
          } ${msg.streaming ? "border-l-2 border-l-indigo-500" : ""}`}
        >
          <p className="whitespace-pre-wrap break-words">
            {msg.content}
            {msg.streaming && (
              <span className="inline-flex ml-1 gap-0.5 items-center">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
            )}
          </p>

          {/* FDIA Score */}
          {!msg.streaming && msg.fdia && (
            <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center gap-2 flex-wrap">
              <FDIABadge score={msg.fdia} />
              <div className="flex items-center gap-2 text-[9px] font-mono text-gray-600">
                <span>D:{msg.fdia.D.toFixed(2)}</span>
                <span>I:{msg.fdia.I.toFixed(2)}</span>
                <span>A:{msg.fdia.A.toFixed(2)}</span>
                {msg.fdia.signed && (
                  <span className="text-emerald-500 flex items-center gap-0.5">
                    <span>✔</span>
                    <span>SignedAI</span>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Timestamp + actions */}
        <div className={`flex items-center gap-2 px-0.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
          <span className="text-[9px] text-gray-700">{formatTime(msg.timestamp)}</span>

          {/* Hover actions (assistant only) */}
          {!isUser && !msg.streaming && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              <button
                onClick={() => onCopy(msg.id, msg.content)}
                title="Copy response"
                className="text-[10px] px-2 py-0.5 rounded-md text-gray-600 hover:text-gray-300 hover:bg-white/5 transition"
              >
                {msg.copied ? "✔ Copied" : "⎘ Copy"}
              </button>
              {isLast && onRegenerate && (
                <button
                  onClick={onRegenerate}
                  title="Regenerate response"
                  className="text-[10px] px-2 py-0.5 rounded-md text-gray-600 hover:text-gray-300 hover:bg-white/5 transition"
                >
                  ↻ Regen
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Welcome Screen ───────────────────────────────────────────────────────────
function WelcomeScreen({ onSuggestion }: { onSuggestion: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 px-4 py-12">
      {/* Logo */}
      <div className="flex flex-col items-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-700 flex items-center justify-center text-3xl shadow-2xl shadow-indigo-900/40">
          🧠
        </div>
        <div className="text-center">
          <h2 className="text-xl font-bold tracking-tight">Delentia Intent Chat</h2>
          <p className="text-xs text-gray-500 mt-1 max-w-xs">
            All messages are routed through{" "}
            <span className="text-indigo-400 font-medium">RCT v5 HexaCore</span> with FDIA scoring
            and SignedAI constitutional verification.
          </p>
        </div>
      </div>

      {/* Feature pills */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        {[
          { icon: "🛡️", label: "FDIA Scoring" },
          { icon: "✔", label: "SignedAI Verified" },
          { icon: "🌏", label: "Thai Language" },
          { icon: "⚡", label: "Streaming" },
          { icon: "🔒", label: "PDPA Compliant" },
          { icon: "9×", label: "HexaCore Models" },
        ].map((f) => (
          <span
            key={f.label}
            className="flex items-center gap-1.5 text-[10px] px-2.5 py-1.5 rounded-full bg-white/5 border border-white/8 text-gray-400"
          >
            <span>{f.icon}</span>
            <span>{f.label}</span>
          </span>
        ))}
      </div>

      {/* Suggestion chips */}
      <div className="w-full max-w-2xl space-y-2">
        <p className="text-[10px] text-gray-600 uppercase tracking-wider font-bold text-center">Suggested Intents</p>
        <div className="grid grid-cols-1 gap-2">
          {WELCOME_SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onSuggestion(s)}
              className="w-full text-left text-xs text-gray-400 hover:text-gray-200 border border-surface-border hover:border-indigo-500/40 rounded-xl px-4 py-3 transition hover:bg-indigo-500/5 group"
            >
              <span className="text-indigo-500 mr-2 group-hover:text-indigo-400">→</span>
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Thinking Indicator ───────────────────────────────────────────────────────
function ThinkingBubble({ mode }: { mode: Mode }) {
  const modeInfo = MODES.find((m) => m.value === mode);
  return (
    <div className="flex gap-3 items-start">
      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-600/30 to-indigo-600/30 border border-purple-500/30 flex items-center justify-center text-sm shrink-0 mt-0.5">
        D
      </div>
      <div className="bg-surface-card border border-surface-border rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-2.5">
        <div className="flex gap-1 items-center">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
        <span className="text-[11px] text-gray-500">
          {modeInfo?.icon} Routing through {modeInfo?.label ?? "HexaCore"}…
        </span>
      </div>
    </div>
  );
}

// ─── Main Chat Window ─────────────────────────────────────────────────────────
export function ChatWindow({ apiKey, gateway }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("standard");
  const [showSlash, setShowSlash] = useState(false);
  const [lastUserIntent, setLastUserIntent] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamingMsgId = useRef<string | null>(null);

  const { streamState, runStream, abortStream } = useStreamIntent({ apiKey, gateway, mode });

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Textarea auto-resize
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  // Stream token updates
  useEffect(() => {
    if (streamState.status === "streaming" && streamingMsgId.current) {
      const id = streamingMsgId.current;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, content: streamState.partial, streaming: true } : m
        )
      );
    }
    if ((streamState.status === "done" || streamState.status === "error") && streamingMsgId.current) {
      const id = streamingMsgId.current;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id
            ? {
                ...m,
                content:
                  streamState.status === "error"
                    ? `⚠ ${streamState.errorMessage ?? "Stream failed"}`
                    : streamState.partial || m.content,
                fdia: streamState.fdia ?? m.fdia,
                hexa_role: streamState.hexaRole ?? m.hexa_role,
                streaming: false,
              }
            : m
        )
      );
      streamingMsgId.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamState.status, streamState.partial]);

  // Slash command detection
  useEffect(() => {
    if (input.startsWith("/")) {
      setShowSlash(true);
    } else {
      setShowSlash(false);
    }
  }, [input]);

  const handleSend = useCallback(async (text?: string) => {
    const intentText = (text ?? input).trim();
    if (!intentText) return;

    setLastUserIntent(intentText);
    setInput("");
    setShowSlash(false);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: intentText,
      timestamp: new Date(),
      mode,
    };
    setMessages((prev) => [...prev, userMsg]);

    const assistantId = crypto.randomUUID();
    streamingMsgId.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", streaming: true, timestamp: new Date(), mode },
    ]);

    await runStream(intentText);
  }, [input, mode, runStream]);

  const handleRegenerate = useCallback(async () => {
    if (!lastUserIntent) return;
    // Remove last assistant message
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === "assistant");
      if (idx === -1) return prev;
      const realIdx = prev.length - 1 - idx;
      return prev.filter((_, i) => i !== realIdx);
    });
    const assistantId = crypto.randomUUID();
    streamingMsgId.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", streaming: true, timestamp: new Date(), mode },
    ]);
    await runStream(lastUserIntent);
  }, [lastUserIntent, mode, runStream]);

  const handleCopy = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, copied: true } : m))
    );
    setTimeout(() => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, copied: false } : m))
      );
    }, 2000);
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape") {
      setShowSlash(false);
    }
  };

  const isStreaming = streamState.status === "streaming";
  const isThinking = isStreaming && !streamState.partial;
  const lastAssistantIdx = [...messages].reverse().findIndex((m) => m.role === "assistant" && !m.streaming);
  const lastAssistantId = lastAssistantIdx !== -1 ? messages[messages.length - 1 - lastAssistantIdx]?.id : null;

  return (
    <div className="flex flex-col h-full bg-surface-card border border-surface-border rounded-2xl overflow-hidden">
      {/* ── Chat Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border glass-nav shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
            <span className="text-xs font-semibold text-gray-300">HexaCore Online</span>
          </div>
          <div className="h-4 w-px bg-white/8" />
          <span className="text-[10px] text-gray-600 font-mono">{messages.length} messages</span>
        </div>

        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="text-[10px] text-gray-600 hover:text-gray-400 px-2 py-1 rounded-md hover:bg-white/5 transition"
            >
              ✕ Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Mode Selector ── */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-surface-border bg-black/10 shrink-0 overflow-x-auto">
        <span className="text-[9px] text-gray-700 uppercase tracking-wider font-bold mr-1 shrink-0">Mode</span>
        {MODES.map((m) => (
          <ModePill key={m.value} mode={m} active={mode === m.value} onClick={() => setMode(m.value)} />
        ))}
        <div className="ml-auto shrink-0">
          <span className="text-[9px] text-gray-700 font-mono">
            {MODES.find(m => m.value === mode)?.desc}
          </span>
        </div>
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 min-h-0">
        {messages.length === 0 ? (
          <WelcomeScreen onSuggestion={(s) => handleSend(s)} />
        ) : (
          <>
            {messages.map((msg, idx) => {
              const isLast = idx === messages.length - 1;
              const isLastAssistant = msg.id === lastAssistantId;
              return (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  onCopy={handleCopy}
                  onRegenerate={isLastAssistant ? handleRegenerate : undefined}
                  isLast={isLast}
                />
              );
            })}
            {isThinking && <ThinkingBubble mode={mode} />}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input Bar ── */}
      <div className="border-t border-surface-border p-3 shrink-0">
        <div className="relative">
          {/* Slash command palette */}
          {showSlash && (
            <SlashPalette
              query={input}
              onSelect={(cmd) => {
                setInput(cmd);
                setShowSlash(false);
                inputRef.current?.focus();
              }}
            />
          )}

          {/* Input area */}
          <div
            className={`flex gap-2 items-end rounded-xl border bg-surface transition-all duration-200 ${
              isStreaming
                ? "border-indigo-500/40 shadow-[0_0_0_3px_rgba(99,102,241,0.08)]"
                : "border-surface-border hover:border-white/10 focus-within:border-indigo-500/50 focus-within:shadow-[0_0_0_3px_rgba(99,102,241,0.06)]"
            }`}
          >
            {/* Slash hint */}
            <div className="pl-3 pt-2.5 text-gray-700 text-sm shrink-0 self-start">
              {input.startsWith("/") ? (
                <span className="text-indigo-400">/</span>
              ) : (
                <span className="text-gray-700">›</span>
              )}
            </div>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              rows={1}
              placeholder={
                isStreaming
                  ? "Streaming response…"
                  : "Send an intent… (type / for commands, Enter to send, Shift+Enter for new line)"
              }
              className="flex-1 bg-transparent text-gray-100 placeholder-gray-700 py-2.5 pr-2 text-sm outline-none resize-none max-h-40 disabled:opacity-50 leading-relaxed"
              style={{ scrollbarWidth: "thin" }}
            />

            {/* Send / Stop */}
            <div className="p-2 shrink-0">
              {isStreaming ? (
                <button
                  onClick={abortStream}
                  className="flex items-center justify-center w-8 h-8 rounded-lg bg-red-600/20 border border-red-500/30 text-red-400 hover:bg-red-600/30 transition"
                  title="Stop streaming"
                >
                  <span className="w-3 h-3 rounded-sm bg-red-400" />
                </button>
              ) : (
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim()}
                  className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed text-white transition shadow-md shadow-indigo-900/30"
                  title="Send intent (Enter)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Footer hint */}
          <div className="flex items-center justify-between mt-1.5 px-1">
            <p className="text-[9px] text-gray-700">
              Type <kbd className="px-1 py-0.5 bg-white/5 rounded text-gray-600 border border-white/5">/</kbd> for commands ·{" "}
              <kbd className="px-1 py-0.5 bg-white/5 rounded text-gray-600 border border-white/5">Enter</kbd> to send ·{" "}
              <kbd className="px-1 py-0.5 bg-white/5 rounded text-gray-600 border border-white/5">Shift+Enter</kbd> for new line
            </p>
            <p className="text-[9px] text-gray-700 font-mono">
              FDIA · SignedAI · RCT v5
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
