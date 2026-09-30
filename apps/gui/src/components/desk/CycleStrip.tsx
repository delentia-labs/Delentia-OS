"use client";

import type { SessionSummary } from "@/lib/desk-api";

type StepState = "pass" | "stop" | "wait" | "skip" | "none";

const STYLE: Record<StepState, string> = {
  pass: "border-dl-fern bg-dl-pine/50 text-dl-text",
  stop: "border-dl-rust/70 bg-dl-rust/10 text-dl-rust",
  wait: "border-dl-amber/70 bg-dl-amber/10 text-dl-amber",
  skip: "border-dl-rule text-dl-muted",
  none: "border-dl-rule text-dl-muted/60",
};

/** One governed episode drawn as the eight steps of the Constitutional
 *  Cycle, each with what actually happened to it (from the audit trail). */
export function CycleStrip({ s, rct7Count }: { s: SessionSummary; rct7Count?: number }) {
  const guardStop = s.stopped_reason === "guard_blocked" || s.guard === "rejected";
  const blocked = s.stopped_reason === "fdia_blocked";
  const waiting = s.stopped_reason === "pending_approval";
  const running = s.stopped_reason === "running";
  const steps: { name: string; state: StepState; note: string }[] = [
    { name: "GUARD", state: guardStop ? "stop" : s.guard ? "pass" : "none", note: s.guard ? `CORD ${s.guard}` : "not recorded" },
    { name: "THINK", state: guardStop ? "skip" : "pass", note: rct7Count ? `RCT-7 ${rct7Count} steps` : "RCT-7 plan" },
    { name: "ROUTE", state: guardStop ? "skip" : s.route ? "pass" : "none", note: s.route ?? "-" },
    { name: "ACT", state: guardStop ? "skip" : blocked ? "stop" : waiting ? "wait" : "pass",
      note: blocked ? "FDIA blocked" : waiting ? "awaiting approval" : `${s.iterations ?? 0} steps` },
    { name: "COMPRESS", state: guardStop ? "skip" : "pass", note: "if output > 6k chars" },
    { name: "VERIFY", state: s.verified === null ? "skip" : s.verified ? "pass" : "stop",
      note: s.verified === null ? "not applicable" : `${s.verified ? "aligned" : "not aligned"} ${s.similarity ?? ""}` },
    { name: "RECORD", state: running ? "none" : s.jitna_verified ? "pass" : "none", note: s.jitna_verified ? "JITNA signed" : "-" },
    { name: "LEARN", state: s.skill_extracted ? "pass" : "skip", note: s.skill_extracted ? "skill kept" : "nothing learned" },
  ];
  return (
    <ol aria-label="Constitutional cycle" className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 xl:grid-cols-8">
      {steps.map((step) => (
        <li key={step.name} className={`rounded border px-2 py-1.5 ${STYLE[step.state]}`} title={step.note}>
          <p className="desk-mono text-[11px] tracking-wider">{step.name}</p>
          <p className="truncate text-[11px] opacity-80">{step.note}</p>
        </li>
      ))}
    </ol>
  );
}
