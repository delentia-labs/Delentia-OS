/**
 * FDIA — Constitutional Formula: F = D^I × A
 *
 * F = Freedom to act (0.0 – 1.0)
 * D = Delta (change vector magnitude, 0.0 – 1.0)
 * I = Identity (role confidence, 0.0 – 1.0)
 * A = Architect gate (0 = blocked, 1 = approved, float for partial)
 *
 * Reference: rct-platform/core/fdia/
 */

export type RiskLevel = "LOW" | "STRUCTURAL" | "SYSTEMIC";

export interface FDIAScores {
  /** Freedom to act — computed result of F = D^I × A */
  f: number;
  /** Delta — change magnitude (0.0–1.0) */
  d: number;
  /** Identity — role confidence (0.0–1.0) */
  i: number;
  /** Architect gate (0 = blocked, 1 = approved) */
  a: number;
}

export interface FDIAResult extends FDIAScores {
  riskLevel: RiskLevel;
  isBlocked: boolean;
  explanation: string;
}

/**
 * Compute FDIA score using constitutional formula F = D^I × A
 *
 * @param d  Delta — change magnitude (0.0 to 1.0)
 * @param i  Identity — role confidence (0.0 to 1.0)
 * @param a  Architect gate (0 = fully blocked, 1 = approved, float = partial)
 * @returns  FDIAResult with computed F score and risk classification
 *
 * @example
 * const result = computeFDIA(0.7, 0.9, 1);
 * // { f: 0.667, d: 0.7, i: 0.9, a: 1, riskLevel: "LOW", isBlocked: false }
 */
export function computeFDIA(d: number, i: number, a: number): FDIAResult {
  if (d < 0 || d > 1) throw new RangeError(`d must be 0.0–1.0, got ${d}`);
  if (i < 0 || i > 1) throw new RangeError(`i must be 0.0–1.0, got ${i}`);
  if (a < 0 || a > 1) throw new RangeError(`a must be 0.0–1.0, got ${a}`);

  // F = D^I × A  (D raised to power I, then multiplied by A gate)
  const dPowI = Math.pow(d, i);
  const f = dPowI * a;

  const isBlocked = a === 0;
  const riskLevel: RiskLevel =
    f >= 0.7 ? "LOW" : f >= 0.4 ? "STRUCTURAL" : "SYSTEMIC";

  const explanation = isBlocked
    ? `Execution blocked: A=0 (architect gate closed). F=${f.toFixed(3)}`
    : `F=${f.toFixed(3)} = D^I × A = ${d.toFixed(2)}^${i.toFixed(2)} × ${a.toFixed(2)} → Risk=${riskLevel}`;

  return { f, d, i, a, riskLevel, isBlocked, explanation };
}

/**
 * Check if an FDIA score meets a minimum threshold for execution.
 *
 * @param result   FDIAResult from computeFDIA()
 * @param minF     Minimum F score required (default: 0.3)
 */
export function meetsThreshold(result: FDIAResult, minF = 0.3): boolean {
  return !result.isBlocked && result.f >= minF;
}
