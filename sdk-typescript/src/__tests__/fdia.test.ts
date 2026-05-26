import { computeFDIA, meetsThreshold } from "../fdia";

describe("computeFDIA", () => {
  // ── Happy path ──────────────────────────────────────────────────────────

  test("LOW risk: F=0.7254 for d=0.7, i=0.9, a=1 (F = D^I × A)", () => {
    // F = 0.7^0.9 × 1 = 0.7254 (not 0.667 — readme example had rounding)
    const r = computeFDIA(0.7, 0.9, 1);
    expect(r.f).toBeCloseTo(0.725, 2);
    expect(r.riskLevel).toBe("LOW");
    expect(r.isBlocked).toBe(false);
    expect(r.d).toBe(0.7);
    expect(r.i).toBe(0.9);
    expect(r.a).toBe(1);
  });

  test("STRUCTURAL risk: F=0.5 for d=0.5, i=1.0, a=1.0", () => {
    const r = computeFDIA(0.5, 1.0, 1.0);
    expect(r.f).toBeCloseTo(0.5, 4);
    expect(r.riskLevel).toBe("STRUCTURAL");
    expect(r.isBlocked).toBe(false);
  });

  test("SYSTEMIC risk: F=0.3 for d=0.3, i=1.0, a=1.0", () => {
    const r = computeFDIA(0.3, 1.0, 1.0);
    expect(r.f).toBeCloseTo(0.3, 4);
    expect(r.riskLevel).toBe("SYSTEMIC");
    expect(r.isBlocked).toBe(false);
  });

  test("Blocked: A=0 always gives F=0 and isBlocked=true", () => {
    const r = computeFDIA(1.0, 1.0, 0);
    expect(r.f).toBe(0);
    expect(r.isBlocked).toBe(true);
    expect(r.riskLevel).toBe("SYSTEMIC");
    expect(r.explanation).toContain("blocked");
  });

  test("Partial gate: A=0.5 gives half freedom", () => {
    const r = computeFDIA(1.0, 1.0, 0.5);
    expect(r.f).toBeCloseTo(0.5, 4);
    expect(r.isBlocked).toBe(false);
  });

  test("HIGH confidence: d=1.0, i=1.0, a=1.0 => F=1.0 LOW", () => {
    const r = computeFDIA(1.0, 1.0, 1.0);
    expect(r.f).toBeCloseTo(1.0, 4);
    expect(r.riskLevel).toBe("LOW");
  });

  test("All zeros: d=0, i=0, a=0 => F=0", () => {
    // 0^0 = 1 mathematically, but a=0 gates to 0
    const r = computeFDIA(0, 0, 0);
    expect(r.f).toBe(0);
    expect(r.isBlocked).toBe(true);
  });

  test("explanation contains F= and Risk=", () => {
    const r = computeFDIA(0.6, 0.8, 1.0);
    expect(r.explanation).toContain("F=");
    expect(r.explanation).toContain("Risk=");
  });

  // ── Boundary thresholds ────────────────────────────────────────────────

  test("F=0.7 exact boundary is LOW", () => {
    // d=0.7, i=1.0, a=1.0 => F = 0.7
    const r = computeFDIA(0.7, 1.0, 1.0);
    expect(r.f).toBeCloseTo(0.7, 4);
    expect(r.riskLevel).toBe("LOW");
  });

  test("F=0.4 exact boundary is STRUCTURAL", () => {
    const r = computeFDIA(0.4, 1.0, 1.0);
    expect(r.f).toBeCloseTo(0.4, 4);
    expect(r.riskLevel).toBe("STRUCTURAL");
  });

  // ── Error cases ────────────────────────────────────────────────────────

  test("throws RangeError if d > 1", () => {
    expect(() => computeFDIA(1.1, 0.5, 1)).toThrow(RangeError);
    expect(() => computeFDIA(1.1, 0.5, 1)).toThrow(/d must be/);
  });

  test("throws RangeError if d < 0", () => {
    expect(() => computeFDIA(-0.1, 0.5, 1)).toThrow(RangeError);
  });

  test("throws RangeError if i > 1", () => {
    expect(() => computeFDIA(0.5, 1.5, 1)).toThrow(RangeError);
    expect(() => computeFDIA(0.5, 1.5, 1)).toThrow(/i must be/);
  });

  test("throws RangeError if i < 0", () => {
    expect(() => computeFDIA(0.5, -0.1, 1)).toThrow(RangeError);
  });

  test("throws RangeError if a > 1", () => {
    expect(() => computeFDIA(0.5, 0.5, 1.5)).toThrow(RangeError);
    expect(() => computeFDIA(0.5, 0.5, 1.5)).toThrow(/a must be/);
  });

  test("throws RangeError if a < 0", () => {
    expect(() => computeFDIA(0.5, 0.5, -0.1)).toThrow(RangeError);
  });
});

describe("meetsThreshold", () => {
  test("returns true when f >= threshold", () => {
    const r = computeFDIA(0.8, 0.9, 1.0);
    expect(meetsThreshold(r, 0.5)).toBe(true);
  });

  test("returns false when f < threshold", () => {
    const r = computeFDIA(0.3, 1.0, 1.0);
    expect(meetsThreshold(r, 0.5)).toBe(false);
  });

  test("exact boundary: f === threshold returns true", () => {
    const r = computeFDIA(0.5, 1.0, 1.0);
    expect(meetsThreshold(r, 0.5)).toBe(true);
  });

  test("blocked result never meets threshold > 0", () => {
    const r = computeFDIA(1.0, 1.0, 0);
    expect(meetsThreshold(r, 0.01)).toBe(false);
  });

  test("threshold=0: non-blocked result always passes", () => {
    // meetsThreshold returns !isBlocked && f >= minF
    // A blocked result (a=0) always returns false regardless of threshold
    const nonBlocked = computeFDIA(0.1, 0.1, 1.0); // a=1, not blocked
    expect(meetsThreshold(nonBlocked, 0)).toBe(true);
  });

  test("blocked result always fails meetsThreshold even at threshold=0", () => {
    const blocked = computeFDIA(1.0, 1.0, 0); // a=0, blocked
    expect(meetsThreshold(blocked, 0)).toBe(false); // isBlocked=true overrides
  });
});
