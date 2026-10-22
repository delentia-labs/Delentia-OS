/** Pure policy gate used by the action and tested without network or credentials. */
export function gateFailure(
  decision: string, score: number, minimum: number, failOnReject: boolean
): string | null {
  if (!Number.isFinite(minimum) || minimum < 0 || minimum > 1) {
    return "Minimum governance score must be a finite number in [0, 1].";
  }
  if (!Number.isFinite(score) || score < 0 || score > 1) {
    return "API governance score must be a finite number in [0, 1].";
  }
  if (failOnReject && decision === "reject") return "Policy decision is REJECT.";
  if (score < minimum) return `Governance score ${score.toFixed(3)} < minimum ${minimum}.`;
  return null;
}
