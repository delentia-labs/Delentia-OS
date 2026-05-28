/**
 * RCT Platform REST Client
 *
 * Thin Axios wrapper for the delentia-os FastAPI endpoints.
 * Set BASE_URL to your running delentia-os instance.
 *
 * Reference: delentia-os/rct_control_plane/api.py
 */

import axios, { AxiosInstance, AxiosResponse } from "axios";
import type { JITNAPacket } from "./jitna";

export interface CompileResponse {
  intent_id: string;
  intent_type: string;
  risk_profile: string;
  success: boolean;
  errors: string[];
  warnings: string[];
  compilation_time_ms: number;
}

export interface PolicyEvalResponse {
  intent_id: string;
  decision: "approve" | "reject" | "require_approval" | "log" | "escalate";
  requires_approval: boolean;
  governance_score: number;
  triggered_rules: Array<{ name: string; priority: string; action: string }>;
  violations: string[];
  warnings: string[];
}

export interface MetricsResponse {
  total_intents: number;
  total_compilations: number;
  total_graphs: number;
  total_policy_evaluations: number;
  total_executions: number;
  total_failures: number;
  avg_compilation_latency_ms: number;
  approvals_required: number;
  approvals_granted: number;
  audit_trail_entries: number;
}

export interface RCTClientConfig {
  /** Base URL of the delentia-os API (default: http://localhost:8000) */
  baseURL?: string;
  /** Request timeout in ms (default: 10000) */
  timeoutMs?: number;
  /** Bearer token for authentication */
  apiKey?: string;
}

export class RCTClient {
  private readonly http: AxiosInstance;

  constructor(config: RCTClientConfig = {}) {
    const {
      baseURL = "http://localhost:8000",
      timeoutMs = 10_000,
      apiKey,
    } = config;

    this.http = axios.create({
      baseURL,
      timeout: timeoutMs,
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
    });
  }

  /**
   * Compile a natural-language intent into a structured IntentObject.
   *
   * POST /v1/compile
   */
  async compile(
    naturalLanguage: string,
    userId = "sdk-user",
    userTier = "PRO"
  ): Promise<CompileResponse> {
    const res: AxiosResponse<CompileResponse> = await this.http.post(
      "/v1/compile",
      { natural_language: naturalLanguage, user_id: userId, user_tier: userTier }
    );
    return res.data;
  }

  /**
   * Compile a JITNA packet (uses the .intent field as natural language).
   */
  async compileJITNA(
    packet: JITNAPacket,
    userId?: string
  ): Promise<CompileResponse> {
    return this.compile(
      packet.intent,
      userId ?? packet.meta?.user_id ?? "sdk-user",
      packet.meta?.user_tier ?? "PRO"
    );
  }

  /**
   * Evaluate policies for a compiled intent.
   *
   * POST /v1/evaluate
   */
  async evaluatePolicy(
    intentId: string,
    intentType?: string
  ): Promise<PolicyEvalResponse> {
    const res: AxiosResponse<PolicyEvalResponse> = await this.http.post(
      "/v1/evaluate",
      { intent_id: intentId, intent_type: intentType }
    );
    return res.data;
  }

  /**
   * Get aggregated metrics from the control plane.
   *
   * GET /v1/metrics
   */
  async getMetrics(): Promise<MetricsResponse> {
    const res: AxiosResponse<MetricsResponse> = await this.http.get("/v1/metrics");
    return res.data;
  }

  /**
   * Health check.
   *
   * GET /health
   */
  async health(): Promise<{ status: string; version: string }> {
    const res = await this.http.get("/health");
    return res.data;
  }
}
