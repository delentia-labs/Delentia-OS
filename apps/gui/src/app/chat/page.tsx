"use client";

import { ChatWindow } from "@/components/intent-chat/chat-window";

export default function ChatPage() {
  return (
    <div className="w-full h-full flex flex-col min-h-0 p-6 md:p-8">
      <div className="mb-4">
        <h1 className="text-xl font-bold">Intent Chat</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Chat modes are a conversation with a local model (no tools). Agent (governed) runs real tools: FDIA gate per action, signed human approval for risky ones, hash-chained audit.
        </p>
      </div>
      <div className="flex-1 min-h-0">
        <ChatWindow />
      </div>
    </div>
  );
}
