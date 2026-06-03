"use client";

import { ChatWindow } from "@/components/intent-chat/chat-window";

export default function ChatPage() {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-5rem)] flex flex-col">
      <div className="mb-4">
        <h1 className="text-xl font-bold">Intent Chat</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          All messages are routed through RCT v5 HexaCore with FDIA scoring and SignedAI verification.
        </p>
      </div>
      <div className="flex-1 min-h-0">
        <ChatWindow apiKey={apiKey} gateway={gateway} />
      </div>
    </div>
  );
}
