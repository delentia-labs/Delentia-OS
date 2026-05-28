/**
 * JITNA — Just-In-Time Navigable Architecture packet
 *
 * 6-field schema: I / D / Δ / A / R / M
 *   I = Intent        — what the agent should do
 *   D = Data          — input data source description
 *   Δ = Delta         — change constraint (what may be modified)
 *   A = Architect     — approval gate (0 = blocked, 1 = approved)
 *   R = Result        — expected output specification
 *   M = Meta          — structured metadata
 *
 * Reference: delentia-os docs + cli.py _parse_intent_yaml()
 */

export interface JITNAMeta {
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  user_id?: string;
  user_tier?: "FREE" | "PRO" | "ENTERPRISE";
  organization_id?: string;
  source?: string;
  tags?: string[];
  [key: string]: unknown;
}

export interface JITNAScope {
  type: "FILE" | "MODULE" | "SERVICE" | "SYSTEM" | "ORGANIZATION";
  target?: string;
}

export interface JITNABudget {
  max_cost_usd?: string | number;
  max_time_seconds?: number;
}

/**
 * JITNA 6-field intent packet.
 * Serializes to YAML/JSON for rct apply -f pipeline.yaml
 */
export interface JITNAPacket {
  /** I — Intent instruction (natural language) */
  intent: string;
  /** D — Data source (where the agent reads from) */
  data?: string;
  /** Δ — Delta / change constraint */
  delta?: string;
  /** A — Architect gate (0=blocked, 1=approved) */
  architect?: 0 | 1;
  /** R — Expected result description */
  result?: string;
  /** M — Metadata */
  meta?: JITNAMeta;

  // Extended fields for RCT Platform API
  scope?: JITNAScope;
  budget?: JITNABudget;
}

/**
 * Construct a JITNA packet with validated fields.
 *
 * @example
 * const packet = constructJITNA({
 *   intent: "refactor authentication module",
 *   architect: 1,
 *   scope: { type: "MODULE", target: "src/auth" },
 *   budget: { max_cost_usd: "2.50" },
 * });
 */
export function constructJITNA(fields: JITNAPacket): JITNAPacket {
  if (!fields.intent || fields.intent.trim().length === 0) {
    throw new Error("JITNA packet requires a non-empty 'intent' field (I)");
  }
  if (fields.architect !== undefined && fields.architect !== 0 && fields.architect !== 1) {
    throw new Error("JITNA 'architect' field (A) must be 0 or 1");
  }
  return {
    architect: 1, // default: approved
    ...fields,
    intent: fields.intent.trim(),
  };
}

/**
 * Serialize a JITNA packet to a JSON string (for rct apply -f -)
 */
export function serializeJITNA(packet: JITNAPacket): string {
  return JSON.stringify(packet, null, 2);
}
