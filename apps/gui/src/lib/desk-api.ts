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
export interface EndpointDecl { base_url: string; kind: "local" | "in_region" | "cross_border"; region: string; operator: string; credential_env?: string }
export interface PolicyVerdict { enforced: boolean; allowed: boolean | null; reason: string }
export interface ProviderPreset {
  id: string; name: string; country: string; base_url: string; credential_env: string; models: string[]; docs: string; note: string;
  suggested_data_location: "local" | "cross_border"; needs_key: boolean; company_country: string | null;
}
export interface ModelSetup {
  selection: ModelSelection; config_path: string; endpoint: EndpointDecl | null; credential_env: string | null; credential_present: boolean;
  openrouter_key_present: boolean; profiles: Record<string, { provider: string; model: string }>; endpoint_verdict: PolicyVerdict | null;
  presets: { countries: { code: string; name: string }[]; providers: ProviderPreset[]; notice: string };
  saved?: string; key_kept_in_memory?: boolean; key_note?: string | null;
}
export interface ProbeResult {
  contacted: boolean; reachable: boolean; status?: number; models: string[]; error: string | null; key_sent?: boolean; verdict: PolicyVerdict | null;
}
export interface SovereigntyPolicyInput {
  home_region: string; allowed_regions: string[]; allow_cross_border: boolean; pii_policy: "block" | "redact" | "allow"; legal_basis: string;
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
export interface DataEvidence {
  D: number;
  parts: { clarity: number; grounding: number; memory: number; skills: number; record: number };
  missing: string[];
  detail?: Record<string, unknown>;
}
export interface Pillars {
  gatekeeper: { guard: string | null; D: number | null; I: number | null; missing_data: string[] | null; stopped_here: boolean };
  memory: { memories_recalled: number; skills_injected: number; retrieval_algorithms_ok: number; warm_recall: boolean; tool_outputs_compressed: number };
  executor: { route: string | null; iterations: number | null; tool_calls: number; algorithms_ok: number; cost_usd: number | null; model_calls: number | null };
  verifier: { intent_aligned: boolean | null; similarity: number | null; belief_confidence: number | null; hallucination_probability: number | null; multi_model_consensus: string };
  committer: { growth_delta: number | null; G: number | null; verified: boolean; skill_extracted: boolean | null; experiment_run: string | null; audit_algorithms_recorded: number | null };
}
export interface SessionDetail extends SessionSummary {
  data_evidence: DataEvidence | null;
  pillars: Pillars | null;
  growth: { delta: number | null; G: number | null } | null;
  warm_recall: { hit: boolean; reason?: string } | null;
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
  uses: number; successes: number; failures: number; reinforced: number; archived: boolean; reliability: number;
}
export interface GrowthLedger {
  namespace: string; G: number | null; resilience: number | null; growth_ratio: number | null;
  episodes: number; verified_episodes: number; updated_at: string;
}
export interface GrowthRun {
  run_id: string; experiment_id: string; at: string; namespace: string | null; D: number | null; growth_delta: number | null;
  G: number | null; iterations: number | null; finished: number | null; aligned: number | null; skills_injected: number | null;
  cost_usd: number | null; duration_s: number | null;
}
export interface EvolutionSnapshot { steps: number | null; seconds: number | null; cost_usd: number | null; D: number | null; skills_injected: number | null; warm: boolean }
export interface Evolution {
  namespace: string; goals_repeated: number; note: string;
  clusters: { goal: string; verified_runs: number; first: EvolutionSnapshot; last: EvolutionSnapshot;
              fewer_steps: boolean | null; faster: boolean | null; cheaper: boolean | null; better_informed: boolean }[];
  summary: { fewer_steps: number; faster: number; cheaper: number; better_informed: number; median_D_change: number | null };
}
export interface IntentProfile {
  namespace: string; episodes: number;
  kinds: { type: string; episodes: number; verified: number; blocked: number; risk: Record<string, number>; avg_D: number | null; avg_steps: number | null }[];
  recurring: { goal: string; runs: number; verified: number }[];
}
export interface Growth {
  ledgers: GrowthLedger[]; recent: GrowthRun[]; evolution: Evolution[]; profiles: IntentProfile[];
  skills: { total: number; archived: number; reused: number; merged_repeats: number;
            most_reliable: { id: string; problem_statement: string; uses: number; successes: number; failures: number; reinforced: number; reliability: number }[] };
}
export interface PipelineAdapter { algo_id: string; name: string; stage: string; phase: string; needs_llm: boolean; needs_network: boolean; writes_files: boolean }
export interface PipelineAggregate { algo_id: string; stage: string; ok: number; not_triggered: number; error: number; mean_ms: number | null; effect?: string }
export interface Pipeline {
  enabled: boolean; algorithms: number; adapters: PipelineAdapter[]; by_algorithm: PipelineAggregate[];
  runs: { id: number; namespace: string; at: string; algorithms: number; ok: number; not_triggered: number; errors: number; total_ms: number; advice_lines: number }[];
}
export interface SovereigntyInfo {
  enforced: boolean;
  policy: { tenant_id: string; home_region: string; allowed_regions: string[]; allow_cross_border: boolean; pii_policy: string; legal_basis: string } | null;
  model: string;
  hosting: { kind: string; region: string; operator: string; note: string };
  config_path: string; pii_policies: string[]; warning?: string; would_be_allowed: boolean | null; reason?: string;
  decisions: { id: number; namespace: string; action: string; at: string; reason: string | null; hosting: { kind: string; region: string; operator?: string } | null; pii: Record<string, number> | null; cross_border: boolean | null; text_chars: number | null }[];
  counts: { allow: number; redact: number; block: number };
}
export interface MemoryItem { id: string; namespace: string; memory_type: string; content: string; importance: number; created_at: string; accessed_count: number }
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
  modelSetup: () => call<ModelSetup>("/v1/desk/models/setup"),
  testEndpoint: (endpoint: EndpointDecl, apiKey?: string) =>
    call<ProbeResult>("/v1/desk/models/test", { method: "POST", body: JSON.stringify({ endpoint, api_key: apiKey || undefined }) }),
  saveModel: (body: { provider: string; model: string; endpoint?: EndpointDecl; profile?: string; api_key?: string }) =>
    call<ModelSetup>("/v1/desk/models", { method: "POST", body: JSON.stringify(body) }),
  setSovereignty: (policy: SovereigntyPolicyInput) =>
    call<{ saved: string; enforced: boolean }>("/v1/desk/sovereignty", { method: "POST", body: JSON.stringify(policy) }),
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
  sovereignty: () => call<SovereigntyInfo>("/v1/desk/sovereignty"),
  growth: () => call<Growth>("/v1/desk/growth"),
  pipeline: () => call<Pipeline>("/v1/desk/pipeline"),
  memories: (namespace?: string) =>
    call<{ memories: MemoryItem[]; namespaces: { namespace: string; n: number }[] }>(`/v1/desk/memories${namespace ? `?namespace=${encodeURIComponent(namespace)}` : ""}`),
  remember: (content: string, memoryType = "fact", namespace?: string) =>
    call<{ memory_id: string; namespace: string }>("/v1/desk/memories", { method: "POST", body: JSON.stringify({ content, memory_type: memoryType, namespace }) }),
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
