"use client";

import { DeltaTimeline } from "@/components/delta-timeline/timeline";

export default function MemoryPage() {
  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-4 min-h-0 flex-1">
      <div>
        <h1 className="text-xl font-bold">Memory Timeline</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Audit log of all memory delta events. Each tick represents a state change recorded by the
          Delta Engine (checkpointed every 50 ticks, 91.5% compression).
        </p>
      </div>
      <DeltaTimeline />
    </div>
  );
}
