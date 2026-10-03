/**
 * F = D^I x A, the way the runtime computes it (governed_autonomous_loop.fdia_score), so the explainer on the
 * FDIA page shows the same numbers the gate would. D <= 0 or I <= 0 gives 0: no data, or no intent, is no future.
 */
export function fdiaScore(D: number, I: number, A: number): number {
  if (!(D > 0) || !(I > 0)) return 0;
  const d = Math.max(0.01, Math.min(100, D));
  const i = Math.max(0.01, Math.min(10, I));
  const a = Math.max(0, Math.min(1, A));
  if (i * Math.log(d) > 700) return a;
  return Math.round(d ** i * a * 10000) / 10000;
}

/** The built-in floor: a risky action needs F at or above this. The owner's policy can raise it, never lower it. */
export const BUILT_IN_THRESHOLD = 0.5;

export type Outcome = "allowed" | "blocked" | "waits";

export function outcomeOf(F: number, threshold: number, needsSignature: boolean, A: number): Outcome {
  if (!needsSignature && A <= 0) return "blocked";
  if (F < threshold) return "blocked";
  return needsSignature ? "waits" : "allowed";
}
