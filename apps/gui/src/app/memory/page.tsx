"use client";

import { DeltaTimeline } from "@/components/delta-timeline/timeline";

export default function MemoryPage() {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const gateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-bold">Memory Timeline</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Audit log of all memory delta events. Each tick represents a state change recorded by the
          Delta Engine (checkpointed every 50 ticks, 91.5% compression).
        </p>
      </div>
      <DeltaTimeline apiKey={apiKey} gateway={gateway} />
    </div>
  );
}
