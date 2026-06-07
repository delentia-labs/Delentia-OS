/**
 * SignedAI tier selection — TypeScript helper
 *
 * Maps user tier + risk profile → HexaCore role assignments
 *
 * Tier tiers:
 *   FREE       → 4 roles (basic)
 *   PRO        → 6 roles (standard)
 *   ENTERPRISE → 8 roles (full HexaCore)
 *
 * Reference: delentia-os/signedai/hexacore_registry.py
 */

export type UserTier = "FREE" | "PRO" | "ENTERPRISE";
export type RiskProfile = "LOW" | "STRUCTURAL" | "SYSTEMIC";

export type HexaCoreRole =
  | "SUPREME_ARCHITECT"
  | "LEAD_BUILDER"
  | "JUNIOR_BUILDER"
  | "SPECIALIST"
  | "LIBRARIAN"
  | "HUMANIZER"
  | "REGIONAL_THAI"
  | "REGIONAL_CORE"
  | "REVIEWER";

export interface TierSelection {
  tier: UserTier;
  riskProfile: RiskProfile;
  roles: HexaCoreRole[];
  maxParallelAgents: number;
  description: string;
}

const TIER_ROLE_MAP: Record<UserTier, HexaCoreRole[]> = {
  FREE: ["LEAD_BUILDER", "JUNIOR_BUILDER", "LIBRARIAN", "HUMANIZER"],
  PRO: [
    "SUPREME_ARCHITECT",
    "LEAD_BUILDER",
    "JUNIOR_BUILDER",
    "SPECIALIST",
    "LIBRARIAN",
    "HUMANIZER",
  ],
  ENTERPRISE: [
    "SUPREME_ARCHITECT",
    "LEAD_BUILDER",
    "JUNIOR_BUILDER",
    "SPECIALIST",
    "LIBRARIAN",
    "HUMANIZER",
    "REGIONAL_THAI",
    "REGIONAL_CORE",
    "REVIEWER",
  ],
};

/**
 * Select SignedAI HexaCore roles based on user tier and risk profile.
 *
 * @param userTier    FREE | PRO | ENTERPRISE
 * @param riskProfile LOW | STRUCTURAL | SYSTEMIC
 *
 * @example
 * const selection = selectSignedAITier("PRO", "STRUCTURAL");
 * // { tier: "PRO", roles: [...6 roles...], maxParallelAgents: 3, ... }
 */
export function selectSignedAITier(
  userTier: UserTier,
  riskProfile: RiskProfile = "LOW"
): TierSelection {
  const roles = TIER_ROLE_MAP[userTier];
  // For SYSTEMIC risk, always escalate to ENTERPRISE roles
  const effectiveRoles =
    riskProfile === "SYSTEMIC" ? TIER_ROLE_MAP["ENTERPRISE"] : roles;

  const maxParallelAgents =
    userTier === "FREE" ? 2 : userTier === "PRO" ? 4 : 8;

  return {
    tier: userTier,
    riskProfile,
    roles: effectiveRoles,
    maxParallelAgents,
    description: `${userTier} tier (${effectiveRoles.length} roles, ${maxParallelAgents} parallel) — Risk: ${riskProfile}`,
  };
}
