/**
 * RCT Policy Gate — GitHub Action entry point
 *
 * Evaluates a PR's AI intent against RCT Platform constitutional policies.
 * Fails the job if policy decision is REJECT or governance score is below threshold.
 *
 * Inputs  → See action.yml
 * Outputs → decision, governance_score, risk_profile, triggered_rules
 */

import * as core from "@actions/core";
import axios from "axios";

interface CompileResponse {
  intent_id: string;
  intent_type: string;
  risk_profile: string;
  success: boolean;
  errors: string[];
  compilation_time_ms: number;
}

interface PolicyEvalResponse {
  decision: string;
  requires_approval: boolean;
  governance_score: number;
  triggered_rules: Array<{ name: string; priority: string; action: string }>;
  violations: string[];
  warnings: string[];
}

async function run(): Promise<void> {
  try {
    const intent = core.getInput("intent", { required: true });
    const rctApiUrl = core.getInput("rct_api_url") || "http://localhost:8000";
    const userTier = core.getInput("user_tier") || "PRO";
    const minScore = parseFloat(core.getInput("min_governance_score") || "0.6");
    const failOnReject = core.getInput("fail_on_reject") !== "false";
    const apiKey = core.getInput("rct_api_key");

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    };

    core.info(`RCT Policy Gate: evaluating intent "${intent.slice(0, 80)}..."`);
    core.info(`API: ${rctApiUrl}  Tier: ${userTier}  Min score: ${minScore}`);

    // Step 1: Compile intent
    const compileRes = await axios.post<CompileResponse>(
      `${rctApiUrl}/v1/compile`,
      {
        natural_language: intent,
        user_id: "github-action",
        user_tier: userTier,
      },
      { headers, timeout: 30_000 }
    );

    if (!compileRes.data.success) {
      const errors = compileRes.data.errors?.join(", ") ?? "compilation failed";
      core.setFailed(`RCT compile failed: ${errors}`);
      return;
    }

    const { intent_id, intent_type, risk_profile } = compileRes.data;
    core.info(`Compiled: intent_id=${intent_id}  type=${intent_type}  risk=${risk_profile}`);

    // Step 2: Evaluate policies
    const evalRes = await axios.post<PolicyEvalResponse>(
      `${rctApiUrl}/v1/evaluate`,
      { intent_id, intent_type },
      { headers, timeout: 30_000 }
    );

    const {
      decision,
      requires_approval,
      governance_score,
      triggered_rules,
      violations,
      warnings,
    } = evalRes.data;

    // Set outputs
    core.setOutput("decision", decision);
    core.setOutput("governance_score", governance_score.toString());
    core.setOutput("risk_profile", risk_profile);
    core.setOutput(
      "triggered_rules",
      triggered_rules.map((r) => r.name).join(",")
    );
    core.setOutput("requires_approval", requires_approval.toString());

    // Log summary
    core.info(`Decision: ${decision.toUpperCase()}`);
    core.info(`Governance score: ${governance_score.toFixed(3)}`);
    core.info(`Risk profile: ${risk_profile}`);
    if (triggered_rules.length > 0) {
      core.info(`Triggered rules: ${triggered_rules.map((r) => r.name).join(", ")}`);
    }
    if (warnings.length > 0) {
      for (const w of warnings) core.warning(w);
    }
    if (violations.length > 0) {
      for (const v of violations) core.error(v);
    }

    // Gate logic
    if (failOnReject && decision === "reject") {
      core.setFailed(
        `RCT Policy Gate: REJECTED — ${violations[0] ?? "policy violation"}`
      );
      return;
    }

    if (governance_score < minScore) {
      core.setFailed(
        `RCT Policy Gate: governance score ${governance_score.toFixed(3)} < minimum ${minScore}. ` +
          `Triggered rules: ${triggered_rules.map((r) => r.name).join(", ")}`
      );
      return;
    }

    if (requires_approval) {
      core.warning(
        `Human approval required. Run: rct approve --pending  (A-gate is open but requires human sign-off)`
      );
    }

    core.info(`RCT Policy Gate: PASSED — score=${governance_score.toFixed(3)} decision=${decision}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      core.setFailed(
        `RCT API error: ${error.response?.status ?? "network"} — ${
          error.message
        }. Is rct-platform running at the configured URL?`
      );
    } else if (error instanceof Error) {
      core.setFailed(error.message);
    } else {
      core.setFailed("Unknown error in RCT Policy Gate action");
    }
  }
}

run();
