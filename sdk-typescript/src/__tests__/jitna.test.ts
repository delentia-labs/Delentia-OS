import { constructJITNA, serializeJITNA } from "../jitna";
import type { JITNAPacket } from "../jitna";

describe("constructJITNA", () => {
  // ── Minimal valid packet ───────────────────────────────────────────────

  test("constructs packet with required intent field", () => {
    const p = constructJITNA({ intent: "Refactor auth module" });
    expect(p.intent).toBe("Refactor auth module");
    expect(p.architect).toBe(1); // default approved
  });

  test("trims whitespace from intent", () => {
    const p = constructJITNA({ intent: "  fix database  " });
    expect(p.intent).toBe("fix database");
  });

  test("default architect=1 when not specified", () => {
    const p = constructJITNA({ intent: "test" });
    expect(p.architect).toBe(1);
  });

  test("explicit architect=0 (blocked) is preserved", () => {
    const p = constructJITNA({ intent: "test", architect: 0 });
    expect(p.architect).toBe(0);
  });

  test("explicit architect=1 is preserved", () => {
    const p = constructJITNA({ intent: "test", architect: 1 });
    expect(p.architect).toBe(1);
  });

  test("constructs full 6-field JITNA packet", () => {
    const p = constructJITNA({
      intent: "Optimize DB queries",
      data: "PostgreSQL production database",
      delta: "SELECT queries only, no schema changes",
      architect: 1,
      result: "Query latency < 100ms",
      meta: { priority: "HIGH", user_tier: "PRO" },
      scope: { type: "SERVICE", target: "db-service" },
      budget: { max_cost_usd: "1.00", max_time_seconds: 60 },
    });

    expect(p.intent).toBe("Optimize DB queries");
    expect(p.data).toBe("PostgreSQL production database");
    expect(p.delta).toBe("SELECT queries only, no schema changes");
    expect(p.architect).toBe(1);
    expect(p.result).toBe("Query latency < 100ms");
    expect(p.meta?.priority).toBe("HIGH");
    expect(p.meta?.user_tier).toBe("PRO");
    expect(p.scope?.type).toBe("SERVICE");
    expect(p.scope?.target).toBe("db-service");
    expect(p.budget?.max_cost_usd).toBe("1.00");
    expect(p.budget?.max_time_seconds).toBe(60);
  });

  test("scope types: all enum values accepted", () => {
    const types = ["FILE", "MODULE", "SERVICE", "SYSTEM", "ORGANIZATION"] as const;
    for (const type of types) {
      const p = constructJITNA({ intent: "test", scope: { type } });
      expect(p.scope?.type).toBe(type);
    }
  });

  test("meta with user_id and organization_id", () => {
    const p = constructJITNA({
      intent: "test",
      meta: { user_id: "user-123", organization_id: "org-456" },
    });
    expect(p.meta?.user_id).toBe("user-123");
    expect(p.meta?.organization_id).toBe("org-456");
  });

  test("meta with tags array", () => {
    const p = constructJITNA({
      intent: "test",
      meta: { tags: ["performance", "database", "v2"] },
    });
    expect(p.meta?.tags).toEqual(["performance", "database", "v2"]);
  });

  // ── Error cases ────────────────────────────────────────────────────────

  test("throws if intent is empty string", () => {
    expect(() => constructJITNA({ intent: "" })).toThrow(
      /requires a non-empty 'intent'/
    );
  });

  test("throws if intent is only whitespace", () => {
    expect(() => constructJITNA({ intent: "   " })).toThrow(
      /requires a non-empty 'intent'/
    );
  });

  test("throws if architect is not 0 or 1", () => {
    const badPacket = { intent: "test", architect: 0.5 } as unknown as JITNAPacket;
    expect(() => constructJITNA(badPacket)).toThrow(
      /architect.*must be 0 or 1/
    );
  });
});

describe("serializeJITNA", () => {
  test("returns valid JSON string", () => {
    const p = constructJITNA({ intent: "test serialization" });
    const json = serializeJITNA(p);
    expect(typeof json).toBe("string");
    expect(() => JSON.parse(json)).not.toThrow();
  });

  test("serialized JSON contains intent field", () => {
    const p = constructJITNA({ intent: "deploy to staging" });
    const json = serializeJITNA(p);
    const parsed = JSON.parse(json);
    expect(parsed.intent).toBe("deploy to staging");
  });

  test("serialized JSON has architect=1 by default", () => {
    const p = constructJITNA({ intent: "test" });
    const json = serializeJITNA(p);
    const parsed = JSON.parse(json);
    expect(parsed.architect).toBe(1);
  });

  test("round-trip: serialize then parse preserves all fields", () => {
    const original = constructJITNA({
      intent: "Analyze code quality",
      data: "src/",
      result: "quality report",
      meta: { priority: "MEDIUM", user_tier: "ENTERPRISE" },
      scope: { type: "MODULE", target: "core/" },
      budget: { max_time_seconds: 120 },
    });
    const json = serializeJITNA(original);
    const parsed = JSON.parse(json);
    expect(parsed.intent).toBe(original.intent);
    expect(parsed.data).toBe(original.data);
    expect(parsed.result).toBe(original.result);
    expect(parsed.meta.priority).toBe("MEDIUM");
    expect(parsed.scope.type).toBe("MODULE");
    expect(parsed.budget.max_time_seconds).toBe(120);
  });
});
