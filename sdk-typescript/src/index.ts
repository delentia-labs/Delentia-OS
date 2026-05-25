/**
 * @rctlabs/rct-platform — TypeScript SDK
 *
 * Exports:
 *   - FDIA constitutional formula (computeFDIA, meetsThreshold)
 *   - JITNA packet construction (constructJITNA, serializeJITNA)
 *   - SignedAI tier selection (selectSignedAITier)
 *   - RCT Platform REST client (RCTClient)
 */

export { computeFDIA, meetsThreshold } from "./fdia";
export type { FDIAScores, FDIAResult, RiskLevel } from "./fdia";

export { constructJITNA, serializeJITNA } from "./jitna";
export type { JITNAPacket, JITNAMeta, JITNAScope, JITNABudget } from "./jitna";

export { selectSignedAITier } from "./signedai";
export type {
  UserTier,
  RiskProfile,
  HexaCoreRole,
  TierSelection,
} from "./signedai";

export { RCTClient } from "./client";
export type {
  CompileResponse,
  PolicyEvalResponse,
  MetricsResponse,
  RCTClientConfig,
} from "./client";
