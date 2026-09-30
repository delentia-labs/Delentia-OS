/**
 * Client for the Delentia Desk endpoints (rct_control_plane/desk_api.py) and
 * the existing agent/daemon endpoints the redesigned Desk uses. Every call
 * either returns what the runtime reported or throws a DeskError that says
 * what failed; nothing is simulated.
 */
import { getApiKey, getGateway } from "./delentia-client";

export class DeskError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const gateway = getGateway();
  const key = getApiKey();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  if (key) headers.Authorization = `Bearer ${key}`;
  if (init.body) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${gateway}${path}`, { ...init, headers, signal: init.signal ?? AbortSignal.timeout(20000) });
  } catch {
    throw new DeskError(`The Delentia API at ${gateway} is not reachable. Start it with \`delentia serve\`.`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail : res.statusText;
    throw new DeskError(`${res.status}: ${detail}`, res.status);
  }
  return res.json() as Promise<T>;
}

// ---- types (mirror desk_api.py) ---------------------------------------------

export interface ModelSelection { provider: string; model: string; provider_source: string; model_source: string }
export interface ModelInfo {
  id: string; context_length: number | null; prompt_price_per_mtok: number | null;
  completion_price_per_mtok: number | null; supports_json_mode: boolean; supports_tools: boolean;
}
export interface Overview {
  model: ModelSelection;
  daemon: { running: boolean; tasks: number };
  audit_verify: { status: string; output: string | null } | null;
  sessions_total: number;
  approvals_pending: number;
  skills: number;
}
export interface SessionSummary {
  id: number; namespace: string; goal: string | null; started_at: string; ended_at: string | null;
  D: number | null; I: number | null; goal_F: number | null; route: string | null; guard: string | null;
  jitna_verified: boolean | null; stopped_reason: string; iterations: number | null; duration_s: number | null;
  verified: boolean | null; similarity: number | null; approval_id: string | null; skill_extracted: boolean | null;
}
export interface SessionEvent { id: number; type: string; action: string; at: string; data: Record<string, unknown> }
export interface SessionDetail extends SessionSummary {
  rct7_steps: string[];
  route_detail: Record<string, unknown>;
  guard_detail: { cord_verdict?: string; cord_findings?: { check: string; severity: string; pattern_id: string }[] };
  jitna: { packet_id: string | null; content_hash: string | null; public_key: string | null; key_persistent: boolean | null };
  verification: { applicable?: boolean; similarity_score?: number; threshold?: number; aligned_with_intent?: boolean; reason?: string } | null;
  events: SessionEvent[];
}
export interface Tool { name: string; description: string; gate: "approval" | "fdia" | "open" }
export interface Skill {
  id: string; problem_statement: string; solution: unknown; growth_ratio: number; delta: number;
  g_before: number; g_after: number; governance_violation: boolean; session_id: string | null; created_at: string;
}
export interface ChainReport {
  ok: boolean; chained_rows: number; signed_rows: number; legacy_unchained_rows: number;
  head_seq: number | null; head_hash: string | null; first_bad_seq: number | null; reason: string | null;
}
export interface AuditView {
  chain: ChainReport; head: { seq: number; row_hash: string } | null; signing_key_configured: boolean;
  notary: { configured: boolean; url: string | null };
  anchor: { configured: boolean; url: string | null; key_id: string | null };
  recent: { id: number; entity_type: string; action: string; actor: string; created_at: string }[];
}
export interface Experiment {
  id: string; name: string; created_at: string; runs: number; last_run: string | null;
  compare: Record<string, unknown> | null;
}
export interface ExperimentRun { id: string; timestamp: string; algorithm_id: string; metrics: Record<string, unknown> }
export interface Channel {
  channel: string; token_present: boolean; running: boolean; allowlist_env: string;
  allowlist: "everyone" | "nobody" | "listed"; allowlist_count: number | null;
}
export interface DaemonTask {
  task_id: string; name: string; description: string; interval_seconds: number; is_enabled: boolean;
  last_run_at: string | null; run_count: number; last_status: string; last_output: string | null;
}
export interface DaemonStatus { running: boolean; uptime_seconds: number | null; tasks: DaemonTask[] }
export interface PendingAction {
  approval_id: string; namespace: string; goal: string; tool_name: string; tool_args: Record<string, unknown>;
  action_sha256: string; reason: string; status: string; created_at: string; decided_at: string | null;
  approver_public_key: string | null; executed_at: string | null;
}
export interface Health { status: string; version?: string }
export interface SubagentRun {
  id: string; created_at: string; agent_id: string; goal: string; success: boolean;
  stopped_reason: string | null; iterations: number | null; final_answer: string | null;
  jitna: { request_packet_id?: string; request_hash?: string; response_verified: boolean; reason: string | null } | null;
  timed_out: boolean; error: string | null;
}

// ---- calls --------------------------------------------------------------------

export const desk = {
  health: () => call<Health>("/health"),
  overview: () => call<Overview>("/v1/desk/overview"),
  sessions: (limit = 60) => call<{ sessions: SessionSummary[] }>(`/v1/desk/sessions?limit=${limit}`),
  session: (id: number) => call<SessionDetail>(`/v1/desk/sessions/${id}`),
  tools: () => call<{ tools: Tool[]; count: number }>("/v1/desk/tools"),
  skills: () => call<{ count: number; skills: Skill[] }>("/v1/desk/skills"),
  models: (catalog?: "openrouter" | "ollama", free = false) =>
    call<{ selection: ModelSelection; config_path: string; openrouter_key_present: boolean; catalog?: ModelInfo[] }>(
      `/v1/desk/models${catalog ? `?catalog=${catalog}${free ? "&free=true" : ""}` : ""}`),
  setModel: (provider: string, model: string) =>
    call<{ saved: string; selection: ModelSelection }>("/v1/desk/models", { method: "POST", body: JSON.stringify({ provider, model }) }),
  audit: () => call<AuditView>("/v1/desk/audit"),
  experiments: () => call<{ experiments: Experiment[] }>("/v1/desk/experiments"),
  experiment: (id: string) => call<{ runs: ExperimentRun[]; compare: Record<string, unknown> | null }>(`/v1/desk/experiments/${encodeURIComponent(id)}`),
  channels: () => call<{ channels: Channel[] }>("/v1/desk/channels"),
  daemon: () => call<DaemonStatus>("/v1/daemon/status"),
  runTask: (taskId: string) => call<{ status: string; output?: string; error?: string }>(`/v1/desk/cron/${encodeURIComponent(taskId)}/run`, { method: "POST" }),
  subagents: (limit = 50) => call<{ runs: SubagentRun[] }>(`/v1/desk/subagents?limit=${limit}`),
  runSubagents: (goals: string[], timeoutSeconds = 240) =>
    call<{ runs: SubagentRun[] }>("/v1/desk/subagents/run", { method: "POST", body: JSON.stringify({ goals, timeout_seconds: timeoutSeconds }), signal: AbortSignal.timeout((timeoutSeconds + 60) * 1000) }),
  approvals: (status = "PENDING") => call<PendingAction[]>(`/v1/agent/approvals?status=${status}`),
  decide: (approvalId: string, body: { decision: string; public_key_hex: string; signature_hex: string }) =>
    call<Record<string, unknown>>(`/v1/agent/approvals/${encodeURIComponent(approvalId)}/decision`, { method: "POST", body: JSON.stringify(body) }),
  resume: (approvalId: string) =>
    call<Record<string, unknown>>(`/v1/agent/approvals/${encodeURIComponent(approvalId)}/resume`, { method: "POST", body: JSON.stringify({}) }),
};

/** WebSocket URL for the chat stream (the token rides in the query string
 *  because browsers cannot set headers on WebSocket connections). */
export function streamUrl(): string {
  const key = getApiKey();
  return `${getGateway().replace(/^http/, "ws")}/v1/kernel/stream${key ? `?token=${encodeURIComponent(key)}` : ""}`;
}
