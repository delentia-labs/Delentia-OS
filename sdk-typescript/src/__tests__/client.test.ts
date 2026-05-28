import axios from "axios";
import { RCTClient } from "../client";
import type { JITNAPacket } from "../jitna";

jest.mock("axios");
const mockedAxios = axios as jest.Mocked<typeof axios>;

// Build a fake axios instance that we can spy on
const mockPost = jest.fn();
const mockGet = jest.fn();
const fakeAxiosInstance = { post: mockPost, get: mockGet } as unknown as ReturnType<typeof axios.create>;

beforeEach(() => {
  jest.clearAllMocks();
  mockedAxios.create.mockReturnValue(fakeAxiosInstance);
});

describe("RCTClient constructor", () => {
  test("creates instance with default config", () => {
    const client = new RCTClient();
    expect(client).toBeInstanceOf(RCTClient);
    expect(mockedAxios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: "http://localhost:8000",
        timeout: 10_000,
      })
    );
  });

  test("creates instance with custom baseURL and timeout", () => {
    const client = new RCTClient({ baseURL: "https://api.delentia.com", timeoutMs: 5000 });
    expect(client).toBeInstanceOf(RCTClient);
    expect(mockedAxios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: "https://api.delentia.com",
        timeout: 5000,
      })
    );
  });

  test("includes Authorization header when apiKey provided", () => {
    new RCTClient({ apiKey: "secret-key" });
    expect(mockedAxios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret-key",
        }),
      })
    );
  });

  test("no Authorization header when apiKey is omitted", () => {
    new RCTClient({});
    const createCall = mockedAxios.create.mock.calls[0][0] as Record<string, unknown>;
    const headers = createCall?.headers as Record<string, unknown>;
    expect(headers?.["Authorization"]).toBeUndefined();
  });
});

describe("RCTClient.compile", () => {
  const mockCompileResponse = {
    intent_id: "intent-123",
    intent_type: "CODE_REFACTOR",
    risk_profile: "LOW",
    success: true,
    errors: [],
    warnings: [],
    compilation_time_ms: 42,
  };

  test("POST /v1/compile with natural language text", async () => {
    mockPost.mockResolvedValue({ data: mockCompileResponse });
    const client = new RCTClient();
    const result = await client.compile("Refactor auth module");

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/compile",
      expect.objectContaining({ natural_language: "Refactor auth module" })
    );
    expect(result.intent_id).toBe("intent-123");
    expect(result.success).toBe(true);
  });

  test("passes userId and userTier to compile", async () => {
    mockPost.mockResolvedValue({ data: mockCompileResponse });
    const client = new RCTClient();
    await client.compile("test", "user-456", "ENTERPRISE");

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/compile",
      expect.objectContaining({
        user_id: "user-456",
        user_tier: "ENTERPRISE",
      })
    );
  });

  test("defaults userId=sdk-user and userTier=PRO", async () => {
    mockPost.mockResolvedValue({ data: mockCompileResponse });
    const client = new RCTClient();
    await client.compile("test");

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/compile",
      expect.objectContaining({
        user_id: "sdk-user",
        user_tier: "PRO",
      })
    );
  });
});

describe("RCTClient.compileJITNA", () => {
  const mockCompileResponse = {
    intent_id: "jitna-intent-001",
    intent_type: "JITNA",
    risk_profile: "STRUCTURAL",
    success: true,
    errors: [],
    warnings: [],
    compilation_time_ms: 55,
  };

  test("delegates to compile using packet.intent", async () => {
    mockPost.mockResolvedValue({ data: mockCompileResponse });
    const client = new RCTClient();
    const packet: JITNAPacket = {
      intent: "Optimize database queries",
      meta: { user_id: "pkt-user", user_tier: "PRO" },
    };
    const result = await client.compileJITNA(packet);

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/compile",
      expect.objectContaining({ natural_language: "Optimize database queries" })
    );
    expect(result.intent_id).toBe("jitna-intent-001");
  });

  test("uses packet.meta.user_id when no explicit userId", async () => {
    mockPost.mockResolvedValue({ data: mockCompileResponse });
    const client = new RCTClient();
    const packet: JITNAPacket = {
      intent: "test",
      meta: { user_id: "from-meta" },
    };
    await client.compileJITNA(packet);
    expect(mockPost).toHaveBeenCalledWith(
      "/v1/compile",
      expect.objectContaining({ user_id: "from-meta" })
    );
  });
});

describe("RCTClient.evaluatePolicy", () => {
  const mockEvalResponse = {
    intent_id: "intent-123",
    decision: "approve" as const,
    requires_approval: false,
    governance_score: 0.95,
    triggered_rules: [],
    violations: [],
    warnings: [],
  };

  test("POST /v1/evaluate with intent_id", async () => {
    mockPost.mockResolvedValue({ data: mockEvalResponse });
    const client = new RCTClient();
    const result = await client.evaluatePolicy("intent-123");

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/evaluate",
      expect.objectContaining({ intent_id: "intent-123" })
    );
    expect(result.decision).toBe("approve");
    expect(result.requires_approval).toBe(false);
  });

  test("passes intentType when provided", async () => {
    mockPost.mockResolvedValue({ data: mockEvalResponse });
    const client = new RCTClient();
    await client.evaluatePolicy("intent-123", "CODE_REFACTOR");

    expect(mockPost).toHaveBeenCalledWith(
      "/v1/evaluate",
      expect.objectContaining({
        intent_id: "intent-123",
        intent_type: "CODE_REFACTOR",
      })
    );
  });
});

describe("RCTClient.getMetrics", () => {
  const mockMetrics = {
    total_intents: 100,
    total_compilations: 95,
    total_graphs: 90,
    total_policy_evaluations: 88,
    total_executions: 70,
    total_failures: 5,
    avg_compilation_latency_ms: 120,
    approvals_required: 10,
    approvals_granted: 8,
    audit_trail_entries: 200,
  };

  test("GET /v1/metrics and returns metrics data", async () => {
    mockGet.mockResolvedValue({ data: mockMetrics });
    const client = new RCTClient();
    const result = await client.getMetrics();

    expect(mockGet).toHaveBeenCalledWith("/v1/metrics");
    expect(result.total_intents).toBe(100);
    expect(result.avg_compilation_latency_ms).toBe(120);
  });
});
