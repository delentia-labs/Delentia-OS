"use client";

import { useState, useRef, useEffect } from "react";
import { useStreamIntent } from "@/hooks/useIntent";
import { FDIABadge } from "@/components/fdia-visualizer/score-card";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  fdia?: { D: number; I: number; A: number; F: number; signed: boolean; signature_hash: string };
  hexa_role?: string;
  streaming?: boolean;
  timestamp: Date;
}

interface ChatWindowProps {
  apiKey: string;
  gateway: string;
}

export function ChatWindow({ apiKey, gateway }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingMsgId = useRef<string | null>(null);

  const { streamState, runStream, abortStream } = useStreamIntent({ apiKey, gateway });

  // Scroll to bottom on new message or token
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Update in-progress streaming message as tokens arrive
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
                    ? `โ ๏ธ ${streamState.errorMessage}`
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

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;

    // Add user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    // Add placeholder assistant message (will update as tokens stream in)
    const assistantId = crypto.randomUUID();
    streamingMsgId.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", streaming: true, timestamp: new Date() },
    ]);

    await runStream(text);
  };

  const isStreaming = streamState.status === "streaming";

  return (
    <div className="flex flex-col h-full bg-surface rounded-xl border border-surface-border overflow-hidden">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-gray-500 text-sm mt-16">
            Send an intent to begin. All messages routed through RCT v5 HexaCore.
          </p>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm ${
                msg.role === "user"
                  ? "bg-delentia-600 text-white"
                  : "bg-surface-card text-gray-100"
              }`}
            >
              <p className="whitespace-pre-wrap">
                {msg.content}
                {msg.streaming && (
                  <span className="inline-block w-2 h-4 bg-delentia-400 ml-0.5 animate-pulse align-middle" />
                )}
              </p>
              {!msg.streaming && msg.fdia && (
                <div className="mt-2 flex items-center gap-2 text-xs opacity-80">
                  <FDIABadge score={msg.fdia} />
                  {msg.hexa_role && (
                    <span className="font-mono bg-black/20 px-1.5 py-0.5 rounded">
                      {msg.hexa_role}
                    </span>
                  )}
                </div>
              )}
              <p className="text-[10px] opacity-40 mt-1 text-right">
                {msg.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="p-3 border-t border-surface-border">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="Enter intent... (e.g. 'summarize latest legal updates in Thai')"
            disabled={isStreaming}
            className="flex-1 bg-surface-card text-gray-100 placeholder-gray-500 border border-surface-border rounded-lg px-3 py-2 text-sm outline-none focus:border-delentia-500 transition disabled:opacity-50"
          />
          {isStreaming ? (
            <button
              onClick={abortStream}
              className="bg-red-600 hover:bg-red-500 text-white rounded-lg px-4 py-2 text-sm font-medium transition"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-sm font-medium transition"
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
