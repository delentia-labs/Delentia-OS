/**
 * Delentia Ecosystem — Shared TypeScript Types
 *
 * Import in adapters:
 *   import type { JITNAIntent, AdapterConfig, ExecuteResult } from "../../sdk/types";
 */

// ── JITNA Intent ──────────────────────────────────────────────────────────────

/**
 * A JITNA v3 intent packet — the universal input format for Delentia OS.
 *
 * F = D^I × A
 *   F = Final FDIA score
 *   D = Data quality (0–1)
 *   I = Intent clarity (0–1)
 *   A = Authorization level (0–1)
 */
export interface JITNAIntent {
  /** Unique user identifier on the originating channel */
  user_id: string;

  /** Session identifier — used for memory continuity. Defaults to user_id if omitted */
  session_id: string;

  /** Raw intent text from the user */
  intent_text: string;

  /** Channel identifier matching the adapter's `jitna_channel` in manifest.json */
  channel: string;

  /** Optional language hint — ISO 639-1 code, e.g. "en", "th" */
  language?: string;

  /** Intent action code (optional — inferred by JITNA engine if omitted) */
  action?: string;

  /** Additional platform-specific metadata */
  metadata?: Record<string, unknown>;
}

// ── Execute Result ────────────────────────────────────────────────────────────

/** FDIA scoring breakdown */
export interface FDIAScore {
  /** Overall FDIA score: F = D^I × A */
  score: number;

  /** Data quality dimension (0–1) */
  data_quality: number;

  /** Intent clarity dimension (0–1) */
  intent_clarity: number;

  /** Authorization level (0–1) */
  authorization: number;

  /** Scoring rationale */
  rationale?: string;
}

/** HexaCore role that processed this intent */
export type HexaCoreRole =
  | "SOVEREIGN"
  | "ARCHITECT"
  | "SENTINEL"
  | "ANALYST"
  | "HERALD"
  | "ORACLE"
  | "GUARDIAN"
  | "AUDITOR"
  | "CATALYST";

/** Result returned by `executeIntent()` */
export interface ExecuteResult {
  /** Whether the intent was executed successfully */
  success: boolean;

  /** Natural language response to send to the user */
  response: string;

  /** FDIA score for this execution */
  fdia: FDIAScore;

  /** HexaCore role that handled the intent */
  handled_by?: HexaCoreRole;

  /** Structured data payload (domain-specific) */
  data?: Record<string, unknown>;

  /** Error message if `success` is false */
  error?: string;

  /** Intent was blocked (FDIA score below threshold) */
  blocked?: boolean;

  /** ISO timestamp of execution */
  executed_at?: string;
}

// ── Adapter Config ────────────────────────────────────────────────────────────

/** Runtime configuration passed to the webhook handler */
export interface AdapterConfig {
  /** Delentia OS gateway URL, e.g. http://localhost:8000 */
  gateway: string;

  /** Delentia OS API key */
  apiKey: string;

  /** Platform webhook secret — used to verify incoming requests */
  webhookSecret: string;

  /** Platform API token — used to send responses */
  platformToken?: string;

  /** Optional: override FDIA threshold (default 0.7) */
  fdiaThreshold?: number;

  /** Optional: preferred response language */
  language?: "en" | "th";
}

// ── Manifest ──────────────────────────────────────────────────────────────────

/** JSON Schema for manifest.json validation */
export interface AdapterManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  license: string;
  jitna_channel: string;
  regional_support: string[];
  security_scan_passed: boolean;
  permissions: AdapterPermission[];
  env_required: string[];
  tags?: string[];
  homepage?: string;
  repository?: string;
}

export type AdapterPermission =
  | "intent:read"
  | "intent:execute"
  | "data:read"
  | "data:write"
  | "media:read"
  | "media:write"
  | "admin:read";

/** JSON Schema for skills manifest.json */
export interface SkillManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  license: string;
  jitna_channel: string;
  capabilities: string[];
  security_scan_passed: boolean;
  tags?: string[];
  dependencies?: string[];
  env_required?: string[];
}
