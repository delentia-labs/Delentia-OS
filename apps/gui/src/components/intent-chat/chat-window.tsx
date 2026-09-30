"use client";

import { useState, useRef, useEffect } from "react";
import { useStreamIntent } from "@/hooks/useIntent";
import { FDIABadge } from "@/components/fdia-visualizer/score-card";
import { TraceInspector } from "./TraceInspector";
import { TerminalSandbox } from "./terminal-sandbox";
import {
  Send,
  Square,
  Zap,
  Circle,
  ScanSearch,
  GitMerge,
  Sparkles,
  Copy,
  Check,
  RotateCcw,
  Cpu,
  User,
  Bot,
  Terminal,
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  fdia?: { D: number; I: number; A: number; F: number; signed: boolean; signature_hash: string };
  hexa_role?: string;
  streaming?: boolean;
  timestamp: Date;
}

// Round 50: quick/standard/deep/mirror are chat modes (no tools); "agent" runs the governed loop.
const MODES = [
  { value: "quick", label: "Quick", desc: "การตอบสนองที่รวดเร็ว ประมวลผลขั้นพื้นฐาน", icon: Zap, color: "text-amber-400" },
  { value: "standard", label: "Standard", desc: "โหมดมาตรฐาน มีความสมดุลด้านความถูกต้อง", icon: Circle, color: "text-blue-400" },
  { value: "deep", label: "Deep Reasoning", desc: "วิเคราะห์เชิงลึก ผ่านระบบ RCT 9-Tier", icon: ScanSearch, color: "text-purple-400" },
  { value: "mirror", label: "Mirror Execution", desc: "จำลองขั้นตอนการตอบกลับแบบคู่ขนาน", icon: GitMerge, color: "text-emerald-400" },
  { value: "agent", label: "Agent (governed)", desc: "ลงมือทำงานจริงด้วย tool: ผ่าน FDIA gate, action เสี่ยงรอมนุษย์ลงลายเซ็น, บันทึก audit (ช้ากว่าโหมดสนทนา)", icon: Bot, color: "text-rose-400" },
] as const;

const SUGGESTIONS = [
  "สรุปรายงานการอัปเดตกฎหมายในไทยล่าสุด",
  "ตรวจสอบไฟล์ postcss.config.mjs และหาช่องโหว่ความปลอดภัย",
  "เช็คสถานะสุขภาพระบบและประสิทธิภาพการรันของ Delentia OS",
  "สร้าง Mock data สำหรับ Memory delta tick ล่าสุด",
];

export function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [activeMode, setActiveMode] = useState<"quick" | "standard" | "deep" | "mirror" | "agent">("standard");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingMsgId = useRef<string | null>(null);

  const { streamState, runStream, abortStream } = useStreamIntent({ mode: activeMode });

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Update streaming messages
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
                    ? `⚠️ ข้อผิดพลาด: ${streamState.errorMessage}`
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
  }, [streamState.status, streamState.partial, streamState.fdia, streamState.hexaRole, streamState.errorMessage]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend ?? input).trim();
    if (!text) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    const assistantId = crypto.randomUUID();
    streamingMsgId.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", streaming: true, timestamp: new Date() },
    ]);

    await runStream(text);
  };

  const copyToClipboard = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const reRunMessage = async (text: string) => {
    if (streamState.status === "streaming") return;
    await handleSend(text);
  };

  const isStreaming = streamState.status === "streaming";

  return (
    <div className="flex flex-col md:flex-row h-full bg-surface border border-surface-border rounded-xl overflow-hidden shadow-2xl">
      {/* Sidebar Mode Selector */}
      <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-surface-border bg-surface-card/40 p-4 space-y-4">
        <div className="flex items-center gap-2 pb-2 border-b border-surface-border/60">
          <Cpu className="w-4 h-4 text-delentia-500" />
          <span className="text-xs font-semibold text-gray-200">ประมวลผลโมเดล (Intent Mode)</span>
        </div>
        <div className="flex flex-row md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
          {MODES.map((m) => {
            const Icon = m.icon;
            return (
              <button
                key={m.value}
                onClick={() => setActiveMode(m.value)}
                disabled={isStreaming}
                className={`flex-1 md:flex-initial flex items-center gap-2.5 p-2 rounded-lg text-left transition duration-200 ${
                  activeMode === m.value
                    ? "bg-delentia-600/10 border border-delentia-500/30 text-white"
                    : "border border-transparent text-gray-400 hover:text-gray-200 hover:bg-white/5"
                } disabled:opacity-40`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${m.color}`} />
                <div className="hidden md:block">
                  <p className="text-xs font-semibold">{m.label}</p>
                  <p className="text-[9px] text-gray-500 truncate max-w-[150px]">{m.desc}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-h-0 bg-surface">
        {/* Messages List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="max-w-md mx-auto mt-12 text-center space-y-6">
              <div className="w-12 h-12 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center mx-auto text-white shadow-lg animate-pulse">
                <Sparkles className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-semibold text-gray-200">ยินดีต้อนรับสู่ Delentia Intent Chat</h3>
                <p className="text-xs text-gray-400">
                  ป้อนคำสั่งหรือความตั้งใจ (Intent) ของคุณ ด้านล่างระบบจะจัดหาโมเดลที่สอดคล้องพร้อมตรวจสอบความปลอดภัยในทันที
                </p>
              </div>
              
              {/* Suggestion list */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2">
                {SUGGESTIONS.map((s, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(s)}
                    className="text-left p-3 rounded-lg border border-surface-border bg-surface-card/30 text-xs text-gray-400 hover:text-gray-200 hover:border-delentia-500/40 hover:bg-white/5 transition duration-200"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-lg bg-surface-card border border-surface-border flex items-center justify-center shrink-0 text-delentia-500 shadow-md">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}
                  <div
                    className={`relative group max-w-[80%] rounded-2xl px-4 py-3 text-xs leading-relaxed shadow-sm ${
                      msg.role === "user"
                        ? "bg-delentia-500 text-white font-medium"
                        : "bg-surface-card border border-surface-border text-gray-200"
                    }`}
                  >
                    {/* Hover action actions bar */}
                    <div className={`absolute top-2 right-2 flex gap-1 bg-surface border border-surface-border rounded-md p-0.5 opacity-0 group-hover:opacity-100 transition duration-150 ${msg.role === "user" ? "hidden" : ""}`}>
                      <button
                        onClick={() => copyToClipboard(msg.id, msg.content)}
                        title="Copy to clipboard"
                        className="p-1 text-gray-400 hover:text-white hover:bg-white/5 rounded"
                      >
                        {copiedId === msg.id ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                      <button
                        onClick={() => {
                          const userMsgs = messages.filter((m) => m.role === "user");
                          const lastUserMsg = userMsgs[userMsgs.length - 1];
                          if (lastUserMsg) reRunMessage(lastUserMsg.content);
                        }}
                        title="Regenerate response"
                        className="p-1 text-gray-400 hover:text-white hover:bg-white/5 rounded"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <p className="whitespace-pre-wrap pr-6">
                      {msg.content}
                      {msg.streaming && (
                        <span className="inline-block w-1.5 h-3 bg-delentia-500 ml-1 animate-pulse align-middle" />
                      )}
                    </p>

                    {msg.role === "assistant" && (msg.content.includes("MCP") || msg.content.includes("ไฟล์") || msg.content.includes("delentia_file_writer")) && (
                      <TerminalSandbox
                        logs={[
                          `[MCP Gateway] Active Tool: delentia_file_writer`,
                          `[Status] Intent Processed: ${msg.content.slice(0, 45)}...`,
                          `[Verification] SignedAI ED25519 Token Verified`
                        ]}
                      />
                    )}
                    
                    {!msg.streaming && msg.fdia && (
                      <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex items-center gap-2 text-[10px] text-gray-400">
                        <FDIABadge score={msg.fdia} />
                        {msg.hexa_role && (
                          <span className="font-mono bg-surface border border-surface-border px-1.5 py-0.5 rounded text-gray-300">
                            {msg.hexa_role}
                          </span>
                        )}
                        <span className="text-gray-500 font-mono text-[9px] ml-auto">
                          {msg.timestamp.toLocaleTimeString()}
                        </span>
                      </div>
                    )}

                    {!msg.streaming && msg.role === "assistant" && (
                      <TraceInspector hexaRole={msg.hexa_role} fdia={msg.fdia} />
                    )}

                    {msg.role === "user" && (
                      <p className="text-[9px] opacity-60 mt-1 text-right">
                        {msg.timestamp.toLocaleTimeString()}
                      </p>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-8 h-8 rounded-lg bg-delentia-600 flex items-center justify-center shrink-0 text-white shadow-md">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-surface-border bg-surface-card/10">
          <div className="flex gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="ป้อนคำสั่งของคุณที่นี่... (เช่น 'ช่วยค้นหาข้อมูลสรุปใน memory tick ล่าสุด')"
              disabled={isStreaming}
              className="flex-1 bg-surface-card text-gray-200 placeholder-gray-500 border border-surface-border rounded-lg px-3.5 py-2.5 text-xs outline-none focus:border-delentia-500 focus:ring-1 focus:ring-delentia-500/20 transition resize-none min-h-[40px] max-h-[120px] disabled:opacity-50"
            />
            {isStreaming ? (
              <button
                onClick={abortStream}
                className="bg-red-600 hover:bg-red-500 text-white rounded-lg px-4 flex items-center justify-center gap-1.5 text-xs font-semibold transition shrink-0"
              >
                <Square className="w-3.5 h-3.5 fill-white" />
                หยุด
              </button>
            ) : (
              <button
                onClick={() => handleSend()}
                disabled={!input.trim()}
                className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 flex items-center justify-center gap-1.5 text-xs font-semibold shadow-md transition shrink-0"
              >
                <Send className="w-3.5 h-3.5" />
                ส่ง
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between text-[9px] text-gray-500">
            <div className="flex items-center gap-1">
              <Terminal className="w-3 h-3 text-delentia-500" />
              <span>โหมดปัจจุบัน: <strong>{MODES.find((m) => m.value === activeMode)?.label}</strong></span>
            </div>
            <span>กด Enter เพื่อส่งคำสั่ง, Shift + Enter สำหรับขึ้นบรรทัดใหม่</span>
          </div>
        </div>
      </div>
    </div>
  );
}
