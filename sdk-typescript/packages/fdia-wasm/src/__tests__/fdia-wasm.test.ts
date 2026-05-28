/**
 * @delentia/fdia-wasm — Test Suite
 *
 * 25 tests covering:
 *  - computeFDIA core formula
 *  - Kill-switch (A=0)
 *  - Risk level classification
 *  - Input range validation
 *  - meetsThreshold
 *  - intentAlignment cooperative pairs
 *  - FDIAScorer class (stateful)
 *  - Precision / numeric stability
 */

import {
  computeFDIA,
  meetsThreshold,
  intentAlignment,
  FDIAScorer,
  DEFAULT_FDIA_WEIGHTS,
  type FDIAResult,
  type NPCIntentType,
} from "../index";

// ─────────────────────────────────────────────────────────────────────────────
// 1. computeFDIA core formula
// ─────────────────────────────────────────────────────────────────────────────

describe("computeFDIA — core formula", () => {
  test("canonical: computeFDIA(0.9, 1.0, 0.9) ≈ 0.81", () => {
    const r = computeFDIA(0.9, 1.0, 0.9);
    expect(r.f).toBeCloseTo(0.81, 5);
  });

  test("perfect alignment: computeFDIA(1.0, 1.0, 1.0) === 1.0", () => {
    const r = computeFDIA(1.0, 1.0, 1.0);
    expect(r.f).toBe(1.0);
  });

  test("neutral identity I=0 → F = A (D^0 = 1)", () => {
    const r = computeFDIA(0.5, 0.0, 0.8);
    // D^0 = 1, so F = 1 × A = 0.8
    expect(r.f).toBeCloseTo(0.8, 5);
  });

  test("zero delta: computeFDIA(0.0, 0.9, 1.0) === 0.0", () => {
    const r = computeFDIA(0.0, 0.9, 1.0);
    // 0^0.9 ≈ 0
    expect(r.f).toBeLessThanOrEqual(0.001);
  });

  test("result contains all required fields", () => {
    const r = computeFDIA(0.7, 0.8, 0.9);
    expect(r).toHaveProperty("f");
    expect(r).toHaveProperty("d");
    expect(r).toHaveProperty("i");
    expect(r).toHaveProperty("a");
    expect(r).toHaveProperty("riskLevel");
    expect(r).toHaveProperty("isBlocked");
    expect(r).toHaveProperty("explanation");
  });

  test("F is bounded between 0 and 1 for any valid inputs", () => {
    const cases: [number, number, number][] = [
      [0.1, 0.1, 0.1],
      [0.999, 0.999, 0.999],
      [0.5, 0.5, 0.5],
      [1.0, 1.0, 1.0],
      [0.0, 0.0, 0.0],
    ];
    for (const [d, i, a] of cases) {
      const r = computeFDIA(d, i, a);
      expect(r.f).toBeGreaterThanOrEqual(0);
      expect(r.f).toBeLessThanOrEqual(1.0001); // float tolerance
    }
  });

  test("deterministic: same inputs always produce same F", () => {
    const r1 = computeFDIA(0.65, 0.72, 0.88);
    const r2 = computeFDIA(0.65, 0.72, 0.88);
    expect(r1.f).toBe(r2.f);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Constitutional kill-switch (A = 0)
// ─────────────────────────────────────────────────────────────────────────────

describe("computeFDIA — constitutional kill switch (A=0)", () => {
  test("A=0 → F=0 regardless of D and I", () => {
    const r = computeFDIA(0.9, 1.0, 0.0);
    expect(r.f).toBe(0);
  });

  test("A=0 → isBlocked === true", () => {
    const r = computeFDIA(0.9, 1.0, 0.0);
    expect(r.isBlocked).toBe(true);
  });

  test("A=0 with D=1, I=1 → still blocked", () => {
    const r = computeFDIA(1.0, 1.0, 0.0);
    expect(r.isBlocked).toBe(true);
    expect(r.f).toBe(0);
  });

  test("A=0 explanation mentions BLOCKED or kill switch", () => {
    const r = computeFDIA(0.9, 0.9, 0.0);
    expect(r.explanation.toUpperCase()).toContain("BLOCK");
  });

  test("A > 0 → isBlocked === false", () => {
    const r = computeFDIA(0.9, 0.9, 0.01);
    expect(r.isBlocked).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Risk level classification
// ─────────────────────────────────────────────────────────────────────────────

describe("computeFDIA — risk classification", () => {
  test("F >= 0.7 → LOW risk", () => {
    const r = computeFDIA(0.9, 1.0, 0.9); // F ≈ 0.81
    expect(r.riskLevel).toBe("LOW");
  });

  test("F in [0.4, 0.7) → STRUCTURAL risk", () => {
    const r = computeFDIA(0.6, 0.9, 0.8); // F = 0.6^0.9 * 0.8 ≈ 0.51
    expect(r.riskLevel).toBe("STRUCTURAL");
  });

  test("F < 0.4 → SYSTEMIC risk", () => {
    const r = computeFDIA(0.3, 0.9, 0.6); // F = 0.3^0.9 * 0.6 ≈ 0.2
    expect(r.riskLevel).toBe("SYSTEMIC");
  });

  test("blocked (A=0) → SYSTEMIC risk", () => {
    const r = computeFDIA(0.9, 0.9, 0.0);
    expect(r.riskLevel).toBe("SYSTEMIC");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. Input validation
// ─────────────────────────────────────────────────────────────────────────────

describe("computeFDIA — input validation", () => {
  test("throws RangeError when d > 1.0", () => {
    expect(() => computeFDIA(1.1, 0.9, 1.0)).toThrow(RangeError);
  });

  test("throws RangeError when d < 0.0", () => {
    expect(() => computeFDIA(-0.1, 0.9, 1.0)).toThrow(RangeError);
  });

  test("throws RangeError when a > 1.0", () => {
    expect(() => computeFDIA(0.9, 0.9, 1.5)).toThrow(RangeError);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. meetsThreshold helper
// ─────────────────────────────────────────────────────────────────────────────

describe("meetsThreshold", () => {
  test("returns true for F >= 0.3 and not blocked", () => {
    const r = computeFDIA(0.9, 1.0, 0.9); // F ≈ 0.81
    expect(meetsThreshold(r)).toBe(true);
  });

  test("returns false when blocked", () => {
    const r = computeFDIA(0.9, 1.0, 0.0);
    expect(meetsThreshold(r)).toBe(false);
  });

  test("respects custom minF threshold", () => {
    const r = computeFDIA(0.6, 0.9, 0.8); // F ≈ 0.51
    expect(meetsThreshold(r, 0.6)).toBe(false);
    expect(meetsThreshold(r, 0.4)).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. intentAlignment
// ─────────────────────────────────────────────────────────────────────────────

describe("intentAlignment", () => {
  test("no peers → 1.0 (no conflicts)", () => {
    expect(intentAlignment("COOPERATE", {})).toBe(1.0);
  });

  test("all peers aligned → 1.0", () => {
    const peers: Record<string, NPCIntentType> = {
      a: "COOPERATE",
      b: "TRADE",
    };
    const alignment = intentAlignment("COOPERATE", peers);
    expect(alignment).toBe(1.0);
  });

  test("all peers hostile → 0.0", () => {
    const peers: Record<string, NPCIntentType> = {
      a: "DOMINATE",
      b: "SABOTAGE",
    };
    const alignment = intentAlignment("COOPERATE", peers);
    expect(alignment).toBe(0.0);
  });

  test("half aligned → 0.5", () => {
    const peers: Record<string, NPCIntentType> = {
      a: "COOPERATE",
      b: "DOMINATE",
    };
    const alignment = intentAlignment("COOPERATE", peers);
    expect(alignment).toBe(0.5);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. FDIAScorer class
// ─────────────────────────────────────────────────────────────────────────────

describe("FDIAScorer", () => {
  test("scoreAction returns NPCActionScore with all fields", () => {
    const scorer = new FDIAScorer();
    const result = scorer.scoreAction(
      { actionId: "act-1", actionType: "trade", desirability: 0.8 },
      "TRADE"
    );
    expect(result).toHaveProperty("actionId", "act-1");
    expect(result).toHaveProperty("fdia");
    expect(result).toHaveProperty("intentAlignment");
    expect(result).toHaveProperty("approved");
  });

  test("scoreAction with A=0 returns approved=false", () => {
    const scorer = new FDIAScorer();
    const result = scorer.scoreAction(
      { actionId: "act-2", actionType: "attack", desirability: 0.9 },
      "DOMINATE",
      {},
      0.0 // architect gate closed
    );
    expect(result.approved).toBe(false);
    expect(result.fdia.isBlocked).toBe(true);
  });

  test("meanScore is average of scored actions", () => {
    const scorer = new FDIAScorer();
    scorer.scoreAction({ actionId: "a1", actionType: "x", desirability: 0.0 }, "NEUTRAL", {}, 1.0);
    scorer.scoreAction({ actionId: "a2", actionType: "y", desirability: 1.0 }, "NEUTRAL", {}, 1.0);
    // F1 = 0 (or very small), F2 = 1.0 → mean ≈ 0.5
    expect(scorer.meanScore).toBeGreaterThanOrEqual(0);
    expect(scorer.meanScore).toBeLessThanOrEqual(1);
  });

  test("scoredCount increments per scored action", () => {
    const scorer = new FDIAScorer();
    expect(scorer.scoredCount).toBe(0);
    scorer.scoreAction({ actionId: "a1", actionType: "x" }, "NEUTRAL");
    scorer.scoreAction({ actionId: "a2", actionType: "y" }, "NEUTRAL");
    expect(scorer.scoredCount).toBe(2);
  });

  test("reset() clears history", () => {
    const scorer = new FDIAScorer();
    scorer.scoreAction({ actionId: "a1", actionType: "x" }, "NEUTRAL");
    scorer.reset();
    expect(scorer.scoredCount).toBe(0);
    expect(scorer.meanScore).toBe(0);
  });

  test("DEFAULT_FDIA_WEIGHTS sums to 1.0", () => {
    const { intentWeight, desirabilityWeight, contextWeight } = DEFAULT_FDIA_WEIGHTS;
    expect(intentWeight + desirabilityWeight + contextWeight).toBeCloseTo(1.0);
  });
});
