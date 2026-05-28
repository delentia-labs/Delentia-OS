/**
 * @delentia/fdia-wasm — Constitutional FDIA Scoring Engine
 *
 * Edge-ready TypeScript implementation of the RCT Platform FDIA formula:
 *   F = D^I × A
 *
 * Where:
 *   F = Freedom to act (0.0 – 1.0) — computed result
 *   D = Delta (change vector magnitude, 0.0 – 1.0)
 *   I = Identity (role confidence, 0.0 – 1.0)
 *   A = Architect gate (0 = blocked, 1 = approved, float = partial)
 *
 * Design principles:
 *   - Zero external dependencies — pure TypeScript math
 *   - Runs in browser, Cloudflare Workers, Deno, Bun, and Node.js
 *   - Deterministic: same inputs always produce same output
 *   - Constitutional kill switch: A=0 → F=0 regardless of D and I
 *   - Bundle target: <15KB gzip
 *
 * Matches Python reference: delentia-os/core/fdia/fdia.py
 *
 * Apache 2.0 — Delentia Labs (https://delentia.com)
 */

// ─────────────────────────────────────────────────────────────────────────────
// Types & Interfaces
// ─────────────────────────────────────────────────────────────────────────────

/** Risk classification based on computed F score. */
export type RiskLevel = "LOW" | "STRUCTURAL" | "SYSTEMIC";

/** NPC intent type — mirrors Python NPCIntentType enum. */
export type NPCIntentType =
  | "SURVIVE"
  | "DISCOVER"
  | "DOMINATE"
  | "COOPERATE"
  | "PROTECT"
  | "TRADE"
  | "SABOTAGE"
  | "NEUTRAL";

/** Configurable weights for FDIA scoring. Mirrors Python FDIAWeights. */
export interface FDIAWeights {
  /** Weight for intent alignment contribution (default: 0.4) */
  intentWeight: number;
  /** Weight for desirability contribution (default: 0.4) */
  desirabilityWeight: number;
  /** Weight for context match contribution (default: 0.2) */
  contextWeight: number;
}

/** Default FDIA weights matching Python implementation. */
export const DEFAULT_FDIA_WEIGHTS: FDIAWeights = {
  intentWeight: 0.4,
  desirabilityWeight: 0.4,
  contextWeight: 0.2,
};

/** Raw D, I, A component inputs. */
export interface FDIAInputs {
  /** Delta — change magnitude (0.0 to 1.0) */
  d: number;
  /** Identity — role confidence (0.0 to 1.0) */
  i: number;
  /** Architect gate (0 = blocked, 1 = approved, float = partial) */
  a: number;
}

/** Full FDIA computation result. */
export interface FDIAResult extends FDIAInputs {
  /** Computed freedom-to-act score: F = D^I × A */
  f: number;
  /** Risk classification: LOW ≥0.7, STRUCTURAL ≥0.4, SYSTEMIC <0.4 */
  riskLevel: RiskLevel;
  /** True when A=0 (architect gate closed — constitutional kill switch) */
  isBlocked: boolean;
  /** Human-readable explanation of the computation */
  explanation: string;
}

/** Result from scoring an NPC action. */
export interface NPCActionScore {
  /** Action identifier */
  actionId: string;
  /** Computed FDIA result */
  fdia: FDIAResult;
  /** Intent alignment score (0.0 – 1.0) */
  intentAlignment: number;
  /** Whether the action passes the minimum threshold */
  approved: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Core Formula
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Compute FDIA score using constitutional formula: F = D^I × A
 *
 * @param d  Delta — change magnitude (0.0 to 1.0)
 * @param i  Identity — role confidence (0.0 to 1.0)
 * @param a  Architect gate (0 = fully blocked, 1 = approved, float = partial)
 * @returns  FDIAResult with computed F and risk classification
 *
 * @example
 * computeFDIA(0.9, 1.0, 0.9)  // { f: 0.81, riskLevel: "LOW", ... }
 * computeFDIA(0.9, 1.0, 0.0)  // { f: 0.0, isBlocked: true, ... }  ← kill switch
 */
export function computeFDIA(d: number, i: number, a: number): FDIAResult {
  if (d < 0 || d > 1) throw new RangeError(`d must be 0.0–1.0, got ${d}`);
  if (i < 0 || i > 1) throw new RangeError(`i must be 0.0–1.0, got ${i}`);
  if (a < 0 || a > 1) throw new RangeError(`a must be 0.0–1.0, got ${a}`);

  // Constitutional formula: F = D^I × A
  const f = Math.pow(d, i) * a;

  const isBlocked = a === 0;
  const riskLevel: RiskLevel =
    f >= 0.7 ? "LOW" : f >= 0.4 ? "STRUCTURAL" : "SYSTEMIC";

  const explanation = isBlocked
    ? `BLOCKED: A=0 (architect gate closed). F=${f.toFixed(3)} — constitutional kill switch engaged.`
    : `F=${f.toFixed(3)} = D^I × A = ${d.toFixed(3)}^${i.toFixed(3)} × ${a.toFixed(3)} → Risk=${riskLevel}`;

  return { f, d, i, a, riskLevel, isBlocked, explanation };
}

/**
 * Compute intent alignment score between agent and peers.
 * Mirrors Python intent_alignment() in core/fdia/fdia.py.
 *
 * @param agentIntent       The agent's current intent type
 * @param otherIntents      Map of peer_id → their intent type
 * @returns alignment score 0.0 – 1.0
 */
export function intentAlignment(
  agentIntent: NPCIntentType,
  otherIntents: Record<string, NPCIntentType>
): number {
  const peers = Object.values(otherIntents);
  if (peers.length === 0) return 1.0;
  const aligned = peers.filter((p) => _intentsAligned(agentIntent, p)).length;
  return aligned / peers.length;
}

/** Cooperative intent pairs. */
const _COOPERATIVE_PAIRS: Array<[NPCIntentType, NPCIntentType]> = [
  ["COOPERATE", "COOPERATE"],
  ["TRADE", "TRADE"],
  ["TRADE", "COOPERATE"],
  ["COOPERATE", "TRADE"],
  ["PROTECT", "PROTECT"],
  ["PROTECT", "SURVIVE"],
  ["SURVIVE", "PROTECT"],
  ["DISCOVER", "DISCOVER"],
  ["SURVIVE", "SURVIVE"],
];

function _intentsAligned(a: NPCIntentType, b: NPCIntentType): boolean {
  if (a === b) return true;
  return _COOPERATIVE_PAIRS.some(([x, y]) => x === a && y === b);
}

/**
 * Check if a result meets the minimum F threshold for execution.
 *
 * @param result  FDIAResult from computeFDIA()
 * @param minF    Minimum F score (default 0.3)
 */
export function meetsThreshold(result: FDIAResult, minF = 0.3): boolean {
  return !result.isBlocked && result.f >= minF;
}

// ─────────────────────────────────────────────────────────────────────────────
// FDIAScorer — Stateful scorer matching Python FDIAScorer
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Stateful FDIA scorer with configurable weights.
 * Mirrors Python FDIAScorer class in core/fdia/fdia.py.
 *
 * @example
 * const scorer = new FDIAScorer();
 * const score = scorer.scoreAction(
 *   { actionId: "act-1", actionType: "trade", desirability: 0.8 },
 *   "TRADE",
 *   { peer_1: "COOPERATE" }
 * );
 */
export class FDIAScorer {
  private readonly weights: FDIAWeights;
  private _scoreHistory: number[] = [];

  constructor(weights: Partial<FDIAWeights> = {}) {
    this.weights = { ...DEFAULT_FDIA_WEIGHTS, ...weights };
  }

  /**
   * Score an agent action against the FDIA formula.
   *
   * @param action        Action descriptor with actionId, actionType, desirability
   * @param agentIntent   Agent's current intent type
   * @param otherIntents  Peer agents' intent types (optional)
   * @param architectGate Architect approval gate 0.0–1.0 (default 1.0)
   */
  scoreAction(
    action: { actionId: string; actionType: string; desirability?: number },
    agentIntent: NPCIntentType,
    otherIntents: Record<string, NPCIntentType> = {},
    architectGate = 1.0
  ): NPCActionScore {
    // D = desirability of the action (how much agent wants this)
    const d = action.desirability ?? 0.8;

    // I = intent alignment with peers
    const alignment = intentAlignment(agentIntent, otherIntents);

    // A = architect gate
    const a = Math.max(0, Math.min(1, architectGate));

    const fdia = computeFDIA(d, alignment, a);
    this._scoreHistory.push(fdia.f);

    return {
      actionId: action.actionId,
      fdia,
      intentAlignment: alignment,
      approved: meetsThreshold(fdia),
    };
  }

  /** Mean F score across all scored actions. */
  get meanScore(): number {
    if (this._scoreHistory.length === 0) return 0;
    return (
      this._scoreHistory.reduce((s, v) => s + v, 0) /
      this._scoreHistory.length
    );
  }

  /** Total number of actions scored. */
  get scoredCount(): number {
    return this._scoreHistory.length;
  }

  /** Reset score history. */
  reset(): void {
    this._scoreHistory = [];
  }
}
