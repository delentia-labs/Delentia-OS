import { selectSignedAITier } from "../signedai";

describe("selectSignedAITier", () => {
  // ── FREE tier ────────────────────────────────────────────────────────────

  test("FREE tier LOW risk: 4 roles, maxParallelAgents=2", () => {
    const s = selectSignedAITier("FREE", "LOW");
    expect(s.tier).toBe("FREE");
    expect(s.riskProfile).toBe("LOW");
    expect(s.roles).toHaveLength(4);
    expect(s.maxParallelAgents).toBe(2);
    expect(s.roles).toContain("LEAD_BUILDER");
    expect(s.roles).toContain("JUNIOR_BUILDER");
    expect(s.roles).toContain("LIBRARIAN");
    expect(s.roles).toContain("HUMANIZER");
  });

  test("FREE tier STRUCTURAL risk: 4 base roles", () => {
    const s = selectSignedAITier("FREE", "STRUCTURAL");
    expect(s.tier).toBe("FREE");
    expect(s.roles).toHaveLength(4);
    expect(s.maxParallelAgents).toBe(2);
  });

  test("FREE tier SYSTEMIC risk: escalates to ENTERPRISE roles (8)", () => {
    const s = selectSignedAITier("FREE", "SYSTEMIC");
    expect(s.tier).toBe("FREE");
    expect(s.roles).toHaveLength(8);
    expect(s.roles).toContain("SUPREME_ARCHITECT");
    expect(s.roles).toContain("REGIONAL_THAI");
    expect(s.roles).toContain("REVIEWER");
  });

  // ── PRO tier ─────────────────────────────────────────────────────────────

  test("PRO tier LOW risk: 6 roles, maxParallelAgents=4", () => {
    const s = selectSignedAITier("PRO", "LOW");
    expect(s.tier).toBe("PRO");
    expect(s.roles).toHaveLength(6);
    expect(s.maxParallelAgents).toBe(4);
    expect(s.roles).toContain("SUPREME_ARCHITECT");
    expect(s.roles).toContain("SPECIALIST");
  });

  test("PRO tier STRUCTURAL risk: 6 roles", () => {
    const s = selectSignedAITier("PRO", "STRUCTURAL");
    expect(s.roles).toHaveLength(6);
    expect(s.maxParallelAgents).toBe(4);
  });

  test("PRO tier SYSTEMIC risk: escalates to all 8 ENTERPRISE roles", () => {
    const s = selectSignedAITier("PRO", "SYSTEMIC");
    expect(s.tier).toBe("PRO");
    expect(s.roles).toHaveLength(8);
    expect(s.roles).toContain("REGIONAL_THAI");
    expect(s.roles).toContain("REVIEWER");
  });

  // ── ENTERPRISE tier ──────────────────────────────────────────────────────

  test("ENTERPRISE tier LOW risk: 8 roles, maxParallelAgents=8", () => {
    const s = selectSignedAITier("ENTERPRISE", "LOW");
    expect(s.tier).toBe("ENTERPRISE");
    expect(s.roles).toHaveLength(8);
    expect(s.maxParallelAgents).toBe(8);
    const expected = [
      "SUPREME_ARCHITECT",
      "LEAD_BUILDER",
      "JUNIOR_BUILDER",
      "SPECIALIST",
      "LIBRARIAN",
      "HUMANIZER",
      "REGIONAL_THAI",
      "REVIEWER",
    ];
    for (const role of expected) {
      expect(s.roles).toContain(role);
    }
  });

  test("ENTERPRISE SYSTEMIC: still 8 roles (already max)", () => {
    const s = selectSignedAITier("ENTERPRISE", "SYSTEMIC");
    expect(s.roles).toHaveLength(8);
    expect(s.maxParallelAgents).toBe(8);
  });

  // ── Default parameter ────────────────────────────────────────────────────

  test("riskProfile defaults to LOW when omitted", () => {
    const s = selectSignedAITier("PRO");
    expect(s.riskProfile).toBe("LOW");
    expect(s.roles).toHaveLength(6);
  });

  // ── Result shape ─────────────────────────────────────────────────────────

  test("result has tier, riskProfile, roles, maxParallelAgents, description", () => {
    const s = selectSignedAITier("ENTERPRISE", "LOW");
    expect(s).toHaveProperty("tier");
    expect(s).toHaveProperty("riskProfile");
    expect(s).toHaveProperty("roles");
    expect(s).toHaveProperty("maxParallelAgents");
    expect(s).toHaveProperty("description");
    expect(typeof s.description).toBe("string");
  });

  test("description is non-empty string", () => {
    const s = selectSignedAITier("FREE", "LOW");
    expect(s.description.length).toBeGreaterThan(0);
  });

  // ── Idempotency ───────────────────────────────────────────────────────────

  test("same inputs always produce same outputs (idempotent)", () => {
    const s1 = selectSignedAITier("PRO", "STRUCTURAL");
    const s2 = selectSignedAITier("PRO", "STRUCTURAL");
    expect(s1.roles).toEqual(s2.roles);
    expect(s1.maxParallelAgents).toBe(s2.maxParallelAgents);
  });
});
