/**
 * index.ts exports smoke test — verify all public symbols are exported correctly.
 */
import {
  computeFDIA,
  meetsThreshold,
  constructJITNA,
  serializeJITNA,
  selectSignedAITier,
  RCTClient,
} from "../index";

describe("package exports", () => {
  test("computeFDIA is a function", () => {
    expect(typeof computeFDIA).toBe("function");
  });

  test("meetsThreshold is a function", () => {
    expect(typeof meetsThreshold).toBe("function");
  });

  test("constructJITNA is a function", () => {
    expect(typeof constructJITNA).toBe("function");
  });

  test("serializeJITNA is a function", () => {
    expect(typeof serializeJITNA).toBe("function");
  });

  test("selectSignedAITier is a function", () => {
    expect(typeof selectSignedAITier).toBe("function");
  });

  test("RCTClient is a class constructor", () => {
    expect(typeof RCTClient).toBe("function");
    const client = new RCTClient();
    expect(client).toBeInstanceOf(RCTClient);
  });

  test("RCTClient instantiates with custom config", () => {
    const client = new RCTClient({
      baseURL: "https://example.com",
      timeoutMs: 5000,
      apiKey: "test-key",
    });
    expect(client).toBeInstanceOf(RCTClient);
  });

  test("RCTClient has compile, evaluatePolicy, getMetrics methods", () => {
    const client = new RCTClient();
    expect(typeof client.compile).toBe("function");
    expect(typeof client.evaluatePolicy).toBe("function");
    expect(typeof client.getMetrics).toBe("function");
  });

  // ── Integration: modules work together ────────────────────────────────

  test("computeFDIA result can be checked with meetsThreshold", () => {
    const r = computeFDIA(0.8, 0.9, 1.0);
    expect(meetsThreshold(r, 0.6)).toBe(true);
    expect(meetsThreshold(r, 0.9)).toBe(false);
  });

  test("constructJITNA result can be serialized with serializeJITNA", () => {
    const packet = constructJITNA({
      intent: "integration test packet",
      meta: { user_tier: "PRO" },
    });
    const json = serializeJITNA(packet);
    const parsed = JSON.parse(json);
    expect(parsed.intent).toBe("integration test packet");
  });

  test("JITNA user_tier matches selectSignedAITier", () => {
    const packet = constructJITNA({
      intent: "enterprise workflow",
      meta: { user_tier: "ENTERPRISE" },
    });
    const tier = packet.meta?.user_tier ?? "FREE";
    const selection = selectSignedAITier(tier as "FREE" | "PRO" | "ENTERPRISE");
    expect(selection.roles).toHaveLength(8);
    expect(selection.maxParallelAgents).toBe(8);
  });
});
