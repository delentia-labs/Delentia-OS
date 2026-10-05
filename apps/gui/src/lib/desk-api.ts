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
export interface JitnaPacketReport {
  packet_id: string; source: string; target: string; message_type: string; signature_valid: boolean; signer: string | null;
  language: Record<string, string> | null; problems: string[];
}
export interface JitnaReport {
  valid: boolean; trusted: boolean; sender_fingerprint: string; created: string | null; problems: string[]; untrusted_keys: string[];
  packets: JitnaPacketReport[];
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
  bundled?: boolean;
  imported?: boolean;
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
  required_signatures?: number; signatures_collected?: number; approver_roles?: string[] | null; policy_rule?: string | null;
}
export interface Health { status: string; version?: string }
export interface SubagentRun {
  id: string; created_at: string; agent_id: string; goal: string; success: boolean;
  stopped_reason: string | null; iterations: number | null; final_answer: string | null;
  jitna: { request_packet_id?: string; request_hash?: string; response_verified: boolean; reason: string | null } | null;
  timed_out: boolean; error: string | null;
}


// ---- governance view (governance_view.py, Round 56) --------------------------------
export interface GovControl { id: string; name: string; on: boolean; detail: string; how_to_change: string; always_on: boolean; applicable: boolean }
export interface GovGap { control: string; severity: "bad" | "warn" | "info"; text: string; fix: string }
export interface GovActivity {
  goals_blocked: number; goals_refused_by_jury: number; tool_calls_judged: number; tool_calls_blocked: number;
  tool_results_withheld: number; tool_results_warned: number; second_opinion_attacks: number; jury_agreed: number; jury_refused: number;
  approvals_by_status: Record<string, number>; policy_changes: number; model_calls_blocked: number; model_calls_redacted: number;
  model_calls_allowed: number; notary_gaps: number; episodes: number;
}
export interface GovOverview {
  controls: GovControl[]; on: number; total: number; gaps: GovGap[]; activity: GovActivity;
  last_policy_change: { at: string; by: string; changes: Record<string, unknown> } | null; generated_at: number; reading_this: string;
}
export type GovCategory = "attention" | "all" | "blocked" | "screening" | "gate" | "jury" | "approvals" | "policy" | "sovereignty" | "notary" | "identity" | "episodes" | "steps";
export interface GovEvent {
  id: number; category: string; entity_type: string; entity_id: string | null; action: string; actor: string | null; at: string;
  summary: string; chain_seq: number | null; row_hash: string | null; signed: boolean;
}
export interface GovEventDetail {
  id: number; entity_type: string; entity_id: string | null; action: string; actor: string | null; at: string; summary: string;
  changes: Record<string, unknown>;
  chain: { seq: number; prev_hash: string; row_hash: string; recomputed_matches: boolean; signed: boolean; signer_fingerprint: string | null; signature_hex: string | null } | null;
  related: { id: number; entity_type: string; action: string; at: string }[];
}
export interface GovSigner { name: string | null; role: string | null; key_fingerprint: string; at: number | null; signature_prefix: string; verifies_now: boolean; key_still_trusted: boolean; decision: string }
export interface GovApproval {
  approval_id: string; tool_name: string; goal: string; namespace: string; status: string; reason: string | null; created_at: number;
  decided_at: number | null; executed_at: number | null; action_sha256: string; policy_rule: string | null; required_signatures: number;
  signatures_collected: number; roles_required: string[]; roles_missing: string[]; signers: GovSigner[];
}
export interface GovApprover { name: string; role: string | null; public_key: string; fingerprint: string; approvals_signed: number; last_signed: number | null; rejections_signed: number }
export interface GovIdentity { name: string; disabled: boolean; created_at: number | null; disabled_at: number | null; role: string | null; role_is_default: boolean }
export interface GovDecision { id: string; type: string; description: string; at: string; before: Record<string, unknown>; after: Record<string, unknown> }
export interface GovVerify {
  chain: { ok: boolean; chained_rows: number; signed_rows: number; legacy_unchained_rows: number; head_seq: number | null; first_bad_seq: number | null; reason: string | null };
  signature_check: string;
  episodes: { checked: number; signature_ok: number; signature_bad: number; bad_audit_ids: number[]; unsigned: number; signed_with_a_persistent_key: number; note: string };
  notary: { receipts_in_local_trail: number; gaps: number };
}
export interface WitnessCheck { witness: string; key_id: string; ok: boolean; checked: number; problems: string[] }


// ---- persistent cron jobs (cron_jobs.py, Round 57) ----------------------------------
export interface CronJob {
  id: string; namespace: string; name: string; goal: string; schedule_text: string; schedule_meaning: string; enabled: boolean; deleted: boolean;
  deliver: { channel: string; to: string } | null; created_at: number; created_by: string | null; next_run_at: number | null; last_run_at: number | null;
  last_status: string | null; last_result: string | null; run_count: number; fail_streak: number; max_runs: number | null;
}
export interface CronJobs {
  jobs: CronJob[]; owner: string; delivery: Record<string, string[]>; timezone: string; forms: string[];
  limits: { max_jobs: number; min_interval_s: number; fails_before_off: number; hourly_cap_env: string };
}
export interface CronPreview { kind: string; meaning: string; timezone: string; upcoming: string[] }


// ---- checkpoints of files the agent wrote (checkpoints.py, Round 57) ----------------
export interface Checkpoint {
  id: number; project: string; rel_path: string; tool: string; existed_before: number; before_sha: string | null; after_sha: string | null;
  protected: number; note: string | null; created_at: number; rolled_back_at: number | null; rollback_of: number | null;
}
export interface CheckpointList { checkpoints: Checkpoint[]; status: { enabled: boolean; checkpoints: number; unprotected: number; stored_bytes: number; blob_dir: string } }


export interface WitnessStatus {
  configured: number; fresh_witnesses: number; independent_witnesses: number; head_seq: number; rows_not_yet_anchored: number; stale_after_s: number;
  tamper_evident_against_host_compromise: boolean; plain: string; problem: string;
  witnesses: { name: string; type: string; last_anchored_entries: number | null; last_anchored_age_s: number | null; fresh: boolean; last_attempt_ok: boolean | null; last_attempt_detail: string | null }[];
}
export interface WitnessesChecked { ok: boolean; witnesses: { witness: string; reachable: boolean; ok: boolean; checked: number; problems: string[] }[] }


export interface PairingView {
  enabled: boolean;
  pending: { code: string; channel: string; sender_id: string; asked_at: number }[];
  grants: { channel: string; sender_id: string; approval_id: string; granted_at: number; revoked_at: number | null }[];
  limits: { max_pending_per_channel: number; refusal_cooldown_s: number };
}


export interface EnvelopeStatus {
  paused: { by: string; reason: string; at: number | null } | null;
  limits: Record<string, number | null>;
  last_24h: { cost_usd?: number; tokens?: number; episodes?: number };
  last_hour: { cost_usd?: number; tokens?: number; episodes?: number };
  any_limit_set: boolean;
  resume_needs_signature: boolean;
  ledger_problem: string | null;
  owner_alerts: { configured: boolean; targets: { channel: string; to: string }[]; dropped: { channel: string; to: string; why: string }[]; per_hour: number };
}
export interface ResumeAnswer { resumed?: boolean; pending_signature?: boolean; approval_id?: string; how?: string }
export interface WebhooksView {
  routes: { name: string; verify: string; mode: string; events: string[]; open: boolean; secret_env: string; deliver: { channel: string; to: string } | null; max_per_minute: number }[];
  problems: string[]; recent: { route: string; action: string; at: string }[]; path: string;
}
export interface BoardTask { id: string; namespace: string; goal: string; status: string; tainted: boolean; taint_source: string | null; note: string | null; steps: { n: number; text: string; status: string; summary: string | null; approval_id: string | null }[] }
export interface TasksView { tasks: BoardTask[]; jobs: { id: string; namespace: string; status: string; stopped: string | null; steps: number; last_tool: string | null; created_at: number; finished_at: number | null; approval_id: string | null }[] }

// ---- calls --------------------------------------------------------------------

// ---- the owner's policy for A in F = D^I x A (fdia_policy.py) ----------------
export type FdiaActionType = "ALLOW" | "CONDITIONAL" | "REQUIRE_HUMAN_SIGNATURE";
export interface FdiaRule {
  rule_id: string; intent_patterns: string[]; action_type: FdiaActionType; description: string; assigned_A: number;
  require_human_confirmation: boolean; denied_paths: string[]; allowed_roles: string[]; human_approver_role: string[];
  required_signatures: number; jury_tier: string;
}
export interface FdiaPolicy {
  version: string; policy_id: string; policy_name: string; default_fallback_A: number; custom_safety_threshold: number;
  rules: FdiaRule[]; blocked_action_patterns: string[]; require_human_dual_signoff: string[];
  roles: { default_role: string; principals: Record<string, string> }; jury_by_risk: Record<string, string>;
}
export interface FdiaToolInfo { name: string; description: string; built_in: "always a signature" | "FDIA gate" | "open" }
export interface FdiaState {
  path: string; exists: boolean; error: string; policy: FdiaPolicy | null; digest: string | null;
  built_in: { threshold: number; rules: string[] }; tools: FdiaToolInfo[];
  approvers: { name: string; role: string | null; key_prefix: string }[]; jury: { configured: boolean; path: string };
  limits: { max_rules: number; action_types: FdiaActionType[]; jury_tiers: string[]; risk_levels: string[] };
}
export interface FdiaEvaluation {
  policy?: null; A: number; F: number; threshold: number; outcome: string; reason: string; rule_id?: string; action_type?: string;
  needs_signature?: boolean; required_signatures?: number; approver_roles?: string[]; jury_tier?: string; role?: string;
  matched_rules?: string[]; D?: number; I?: number;
}
export interface FdiaEvaluateInput {
  tool_name: string; tool_args: Record<string, unknown>; principal?: string; approved?: boolean; D: number; I: number; policy?: FdiaPolicy;
}

// ---- Tool Forge (tool_forge.py) ---------------------------------------------
export interface ForgeApproval { approval_id: string; status: string; action_sha256: string; required_signatures: number; signatures_collected: number }
export interface ForgeProposal {
  id: string; name: string; spec: string; code_sha256: string; status: string; created_at: number; approval_id: string | null;
  verification: { passed?: boolean; stage?: string; problems?: string[]; code_source?: string; stdout?: string; stderr?: string };
  gap: { goals?: string[]; count?: number; gap_id?: string }; approval?: ForgeApproval | null; code?: string; smoke_test?: string;
}
export interface ForgeGap { gap_id: string; goals: string[]; count: number; users: number; keywords: string[]; first_seen: string; last_seen: string }
export interface ForgeTool { name: string; spec: string; active: boolean; activated_at: number; calls: number; code_sha256: string }
export interface ForgeState {
  gaps: ForgeGap[]; proposals: ForgeProposal[]; tools: ForgeTool[];
  limits: { allowed_imports: string[]; min_asserts: number; run_timeout_s: number; max_code_chars: number };
}
export interface PolicySavePending { pending_signature: true; approval_id: string; action_sha256: string; how: string }

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
  verifyJitna: (file: unknown, trustedKeys: string[]) =>
    call<JitnaReport>("/v1/jitna/verify", { method: "POST", body: JSON.stringify({ file, trusted_keys: trustedKeys }) }),
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
  governance: () => call<GovOverview>("/v1/desk/governance"),
  govEvents: (category: GovCategory, query: string, beforeId?: number, limit = 40) => {
    const q = new URLSearchParams({ category, limit: String(limit) });
    if (query.trim()) q.set("q", query.trim());
    if (beforeId) q.set("before_id", String(beforeId));
    return call<{ category: string; events: GovEvent[]; next_before_id: number | null }>(`/v1/desk/governance/events?${q}`);
  },
  govEvent: (id: number) => call<GovEventDetail>(`/v1/desk/governance/events/${id}`),
  govSignatures: (status?: string) => call<{ approvals: GovApproval[]; all_signatures_verify: boolean }>(`/v1/desk/governance/signatures${status ? `?status=${status}` : ""}`),
  govApprovers: () => call<{ file: string; problem: string; keys: GovApprover[]; roles_held: string[] }>("/v1/desk/governance/approvers"),
  govIdentities: () => call<{ mode: string; file: string; shared_token_set: boolean; users: GovIdentity[]; problem: string; default_role: string | null; note: string }>("/v1/desk/governance/identities"),
  govDecisions: () => call<{ decisions: GovDecision[] }>("/v1/desk/governance/decisions"),
  govVerify: () => call<GovVerify>("/v1/desk/governance/audit/verify"),
  govWitnesses: () => call<WitnessStatus>("/v1/desk/governance/audit/witnesses"),
  govCheckWitnesses: () => call<WitnessesChecked>("/v1/desk/governance/audit/check-witnesses", { method: "POST", body: "{}" }),
  govCheckWitness: () => call<WitnessCheck>("/v1/desk/governance/audit/check-witness", { method: "POST", body: "{}" }),
  experiments: () => call<{ experiments: Experiment[] }>("/v1/desk/experiments"),
  experiment: (id: string) => call<{ runs: ExperimentRun[]; compare: Record<string, unknown> | null }>(`/v1/desk/experiments/${encodeURIComponent(id)}`),
  channels: () => call<{ channels: Channel[] }>("/v1/desk/channels"),
  envelope: () => call<EnvelopeStatus>("/v1/desk/envelope"),
  envelopePause: (reason: string) => call<{ paused: unknown }>("/v1/desk/envelope/pause", { method: "POST", body: JSON.stringify({ reason }) }),
  envelopeResume: async (approval_id?: string): Promise<ResumeAnswer> => {
    const gateway = getGateway();
    const key = getApiKey();
    const res = await fetch(`${gateway}/v1/desk/envelope/resume`, { method: "POST", headers: { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) }, body: JSON.stringify(approval_id ? { approval_id } : {}) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new DeskError(`${res.status}: ${typeof body?.detail === "string" ? body.detail : res.statusText}`, res.status);
    return body as ResumeAnswer;
  },
  webhooks: () => call<WebhooksView>("/v1/desk/webhooks"),
  tasks: () => call<TasksView>("/v1/desk/tasks"),
  taskCancel: (id: string) => call<BoardTask>(`/v1/desk/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST", body: "{}" }),
  taskStart: (id: string) => call<BoardTask>(`/v1/desk/tasks/${encodeURIComponent(id)}/start`, { method: "POST", body: "{}" }),
  taskPlan: (id: string, steps: string[]) => call<BoardTask>(`/v1/desk/tasks/${encodeURIComponent(id)}/plan`, { method: "PUT", body: JSON.stringify({ steps }) }),
  taskReplan: (id: string) => call<BoardTask>(`/v1/desk/tasks/${encodeURIComponent(id)}/replan`, { method: "POST", body: "{}" }),
  pairing: () => call<PairingView>("/v1/desk/pairing"),
  pairingRevoke: (channel: string, sender_id: string) => call<{ revoked: boolean }>("/v1/desk/pairing/revoke", { method: "POST", body: JSON.stringify({ channel, sender_id }) }),
  daemon: () => call<DaemonStatus>("/v1/daemon/status"),
  cronJobs: () => call<CronJobs>("/v1/desk/cron/jobs"),
  cronPreview: (text: string) => call<CronPreview>("/v1/desk/cron/parse", { method: "POST", body: JSON.stringify({ text }) }),
  cronCreate: (body: { goal: string; schedule: string; name?: string; deliver?: { channel: string; to: string } | null; max_runs?: number }) =>
    call<{ job: CronJob }>("/v1/desk/cron/jobs", { method: "POST", body: JSON.stringify(body) }),
  cronAction: (id: string, action: "enable" | "pause" | "run") => call<{ job: CronJob }>(`/v1/desk/cron/jobs/${encodeURIComponent(id)}/${action}`, { method: "POST", body: "{}" }),
  cronDelete: (id: string) => call<{ job: CronJob }>(`/v1/desk/cron/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  checkpoints: () => call<CheckpointList>("/v1/desk/checkpoints"),
  checkpointDiff: (id: number) => call<{ diff: string }>(`/v1/desk/checkpoints/${id}/diff`),
  checkpointRollback: (id: number, force = false) => call<{ path: string; result: string; undo_checkpoint: number | null }>(`/v1/desk/checkpoints/${id}/rollback`, { method: "POST", body: JSON.stringify({ force }) }),
  skillImportPreview: (text: string, source: string) =>
    call<{ needs_review: true; preview: { name: string; description: string; version: string; tags: string[]; instructions: string; source: string; screen_findings: string[] } }>(
      "/v1/desk/skills/import", { method: "POST", body: JSON.stringify({ text, source }) }),
  skillImport: (text: string, source: string) =>
    call<{ skill_id: string; status: string; name: string }>("/v1/desk/skills/import", { method: "POST", body: JSON.stringify({ text, source, reviewed: true }) }),
  skillExport: (id: string) => call<{ skill_id: string; skill_md: string }>(`/v1/desk/skills/${encodeURIComponent(id)}/export`),
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
  fdia: () => call<FdiaState>("/v1/desk/fdia"),
  fdiaTemplate: (name: "balanced" | "strict") => call<{ policy: FdiaPolicy }>(`/v1/desk/fdia/template/${name}`),
  fdiaValidate: (policy: FdiaPolicy) =>
    call<{ valid: boolean; errors: string[]; digest: string | null }>("/v1/desk/fdia/validate", { method: "POST", body: JSON.stringify({ policy }) }),
  fdiaEvaluate: (body: FdiaEvaluateInput) =>
    call<FdiaEvaluation>("/v1/desk/fdia/evaluate", { method: "POST", body: JSON.stringify(body) }),
  fdiaSave: (policy: FdiaPolicy, approvalId?: string) =>
    call<{ saved: string; digest: string; rules: number } | PolicySavePending>("/v1/desk/fdia/policy", { method: "PUT", body: JSON.stringify({ policy, ...(approvalId ? { approval_id: approvalId } : {}) }) }),
  fdiaDisable: (approvalId?: string) =>
    call<{ archived_as: string } | PolicySavePending>("/v1/desk/fdia/policy/disable", { method: "POST", body: JSON.stringify(approvalId ? { approval_id: approvalId } : {}) }),
  forge: () => call<ForgeState>("/v1/desk/forge"),
  forgeProposal: (id: string) => call<ForgeProposal>(`/v1/desk/forge/proposals/${encodeURIComponent(id)}`),
  forgePropose: (body: { name: string; spec: string; smoke_test: string; code?: string; gap?: unknown }) =>
    call<ForgeProposal>("/v1/desk/forge/propose", { method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(300000) }),
  forgeRequest: (id: string) => call<{ approval_id: string; action_sha256: string; how: string }>(`/v1/desk/forge/proposals/${encodeURIComponent(id)}/request`, { method: "POST" }),
  forgeActivate: (approvalId: string) => call<{ name: string; file: string }>("/v1/desk/forge/activate", { method: "POST", body: JSON.stringify({ approval_id: approvalId }) }),
  forgeOff: (name: string) => call<{ turned_off: string }>(`/v1/desk/forge/tools/${encodeURIComponent(name)}/off`, { method: "POST" }),
  forgeRun: (name: string, args: Record<string, unknown>) =>
    call<{ ok: boolean; result?: unknown; error?: string }>(`/v1/desk/forge/tools/${encodeURIComponent(name)}/run`, { method: "POST", body: JSON.stringify({ args }) }),
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
