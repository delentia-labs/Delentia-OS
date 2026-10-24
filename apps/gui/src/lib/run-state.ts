/**
 * What the Execution Inspector shows, derived ONLY from the events the runtime actually sent.
 * A pure function (no React, no network): nothing here is written by the interface after the fact, and anything the events do not say stays "unknown".
 */
export type RunStep = {
  iteration: number; kind: "tool" | "finish" | "blocked" | "pending" | "notary_down" | "unknown_tool";
  tool: string | null; thinking: string; result: string | null; F?: number; reason?: string;
};
export type RunSummary = {
  stopped_reason: string; iterations: number;
  route?: { path?: string; reason?: string };
  verification?: { applicable?: boolean; aligned_with_intent?: boolean; similarity_score?: number };
  guard?: { cord_verdict?: string; cord_findings?: { pattern_id: string }[] };
  notary?: { enabled?: boolean; receipts?: number };
  approval_id?: string | null; rct7_steps?: string[];
  /** Set when the episode stopped to ask the person (RCT-7 R5/R7). */
  clarification_id?: string | null; clarification_question?: string | null;
  usage?: { prompt_tokens?: number; completion_tokens?: number; cost_usd?: number | null; cost_known?: boolean };
};
export type RunFdia = { D: number | null; I: number | null; A: number; F: number | null; signed: boolean; signature_hash: string };
export type RunPlan = { steps: string[]; route?: { path?: string; reason?: string } };
export type RunEntry =
  | { kind: "user"; text: string }
  | { kind: "plan"; plan: RunPlan }
  | { kind: "step"; step: RunStep }
  | { kind: "answer"; text: string }
  | { kind: "summary"; summary: RunSummary; fdia?: RunFdia; seconds: number }
  | { kind: "error"; text: string };

export type Mood = "idle" | "thinking" | "acting" | "waiting" | "blocked" | "done";
export type CycleStatus = "done" | "active" | "blocked" | "unknown";
export const CYCLE = ["GUARD", "THINK", "ROUTE", "ACT", "COMPRESS", "VERIFY", "RECORD", "LEARN"] as const;

export type GateRow = { tool: string; verdict: "ran" | "blocked" | "waiting" | "not_run" | "unknown_tool"; F?: number; reason?: string };
export type RunState = {
  intent: string | null;
  mood: Mood;
  cycle: { name: (typeof CYCLE)[number]; status: CycleStatus; note: string }[];
  gates: GateRow[];
  /** The RCT-7 plan that arrived before the first tool (R6), or null when none was sent. */
  plan: string[] | null;
  approvalId: string | null;
  verification: { state: "aligned" | "not_aligned" | "not_applicable" | "unknown"; score?: number };
  evidence: { signed: boolean; signatureHash: string | null; notaryReceipts: number | null; stoppedReason: string | null; seconds: number | null };
  finished: boolean;
};

export function deriveRun(allEntries: RunEntry[], running: boolean): RunState {
  // A chat can hold several goals one after another; the Inspector is about the CURRENT run, which starts at the last thing the person typed.
  const lastUser = allEntries.map((e) => e.kind).lastIndexOf("user");
  const entries = lastUser >= 0 ? allEntries.slice(lastUser) : allEntries;
  const intent = (entries.find((e) => e.kind === "user") as { text: string } | undefined)?.text ?? null;
  const planEntry = entries.find((e): e is Extract<RunEntry, { kind: "plan" }> => e.kind === "plan");
  const plan = planEntry ? planEntry.plan.steps : null;
  const steps = entries.filter((e): e is { kind: "step"; step: RunStep } => e.kind === "step").map((e) => e.step);
  const summaryEntry = [...entries].reverse().find((e): e is Extract<RunEntry, { kind: "summary" }> => e.kind === "summary");
  const summary = summaryEntry?.summary;
  const fdia = summaryEntry?.fdia;
  const errored = entries.some((e) => e.kind === "error");
  const finished = !!summary || errored;
  const cordStopped = summary?.guard?.cord_verdict === "rejected";

  const gates: GateRow[] = steps
    .filter((s) => s.kind !== "finish")
    .map((s) => {
      const tool = s.tool ?? "?";
      if (s.kind === "tool") return { tool, verdict: "ran" as const };
      if (s.kind === "blocked") return { tool, verdict: "blocked" as const, F: s.F, reason: s.reason };
      if (s.kind === "pending") return { tool, verdict: "waiting" as const };
      if (s.kind === "notary_down") return { tool, verdict: "not_run" as const, reason: "the audit notary could not record it" };
      return { tool, verdict: "unknown_tool" as const };
    });

  const started = entries.length > 0;
  const anyThinking = steps.some((s) => !!s.thinking);
  const cycle: RunState["cycle"] = [
    { name: "GUARD", status: !started ? "unknown" : cordStopped ? "blocked" : "done", note: cordStopped ? `CORD: ${(summary?.guard?.cord_findings ?? []).map((f) => f.pattern_id).join(", ")}` : started ? "the request was screened before the model saw it" : "" },
    { name: "THINK", status: cordStopped ? "unknown" : plan || summary?.rct7_steps?.length || anyThinking ? "done" : running && started ? "active" : "unknown", note: plan ? `RCT-7 plan, ${plan.length} steps, shown before the first tool` : summary?.rct7_steps?.length ? `RCT-7 plan, ${summary.rct7_steps.length} steps (shown at the end)` : "" },
    { name: "ROUTE", status: summary?.route?.path ? "done" : "unknown", note: summary?.route?.path ? `${summary.route.path}${summary.route.reason ? `: ${summary.route.reason}` : ""}` : "" },
    { name: "ACT", status: gates.some((g) => g.verdict === "blocked") ? "blocked" : gates.some((g) => g.verdict === "waiting") ? "active" : gates.length ? (running ? "active" : "done") : "unknown", note: gates.length ? `${gates.length} tool call${gates.length === 1 ? "" : "s"}` : "" },
    { name: "COMPRESS", status: "unknown", note: "the stream does not report it" },
    { name: "VERIFY", status: summary?.verification?.applicable ? "done" : "unknown", note: summary?.verification?.applicable ? (summary.verification.aligned_with_intent ? "answer matches the intent" : "answer does NOT match the intent") : "" },
    { name: "RECORD", status: summary?.notary?.enabled || fdia?.signed ? "done" : finished ? "unknown" : "unknown", note: summary?.notary?.enabled ? `notary receipts: ${summary.notary.receipts ?? 0}` : fdia?.signed ? "episode signed" : "" },
    { name: "LEARN", status: "unknown", note: "the stream does not report it" },
  ];

  const v = summary?.verification;
  const verification: RunState["verification"] = !summary ? { state: "unknown" } : !v?.applicable ? { state: "not_applicable" } : { state: v.aligned_with_intent ? "aligned" : "not_aligned", score: v.similarity_score };

  const last = steps[steps.length - 1];
  let mood: Mood = "idle";
  if (errored || cordStopped || gates.some((g) => g.verdict === "blocked" && !running)) mood = "blocked";
  else if (finished && !running) mood = summary?.approval_id || summary?.clarification_id || gates.some((g) => g.verdict === "waiting") ? "waiting" : "done";
  else if (running) mood = last?.kind === "pending" ? "waiting" : last?.kind === "blocked" ? "blocked" : last && last.kind === "tool" ? "acting" : "thinking";

  return {
    intent, mood, cycle, gates, plan,
    approvalId: summary?.approval_id ?? null,
    verification,
    evidence: {
      signed: !!fdia?.signed, signatureHash: fdia?.signature_hash ?? null,
      notaryReceipts: summary?.notary?.enabled ? summary.notary.receipts ?? 0 : null,
      stoppedReason: summary?.stopped_reason ?? null, seconds: summaryEntry?.seconds ?? null,
    },
    finished,
  };
}
