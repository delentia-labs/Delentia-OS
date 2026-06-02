"use client";

import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  digest: string;
  details?: {
    family: string;
    parameter_size: string;
    quantization_level: string;
  };
}

interface OllamaTagsResponse {
  models: OllamaModel[];
}

interface PullStatus {
  status: string;
  completed?: number;
  total?: number;
  error?: string;
}

// ── Model Card ────────────────────────────────────────────────────────────────

function ModelCard({
  model,
  onTest,
}: {
  model: OllamaModel;
  onTest: (name: string) => void;
}) {
  const sizeGb = (model.size / 1e9).toFixed(2);
  const isDelentia = model.name.includes("delentia") || model.name.includes("jitna");

  return (
    <div
      className={`bg-surface-card border rounded-xl p-4 flex flex-col gap-2 ${
        isDelentia
          ? "border-delentia-600/60"
          : "border-surface-border"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm text-gray-100 font-mono">
            {model.name}
            {isDelentia && (
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-delentia-800/60 text-delentia-300 border border-delentia-700/40 font-sans">
                Delentia
              </span>
            )}
          </p>
          <p className="text-[10px] text-gray-500 mt-0.5">
            {model.details?.parameter_size ?? "unknown"} ·{" "}
            {model.details?.quantization_level ?? "unknown"} · {sizeGb} GB
          </p>
        </div>
      </div>
      {model.details?.family && (
        <p className="text-xs text-gray-500">Family: {model.details.family}</p>
      )}
      <div className="mt-auto pt-2 border-t border-surface-border">
        <button
          onClick={() => onTest(model.name)}
          className="text-xs px-3 py-1.5 bg-delentia-600/20 hover:bg-delentia-600/40 border border-delentia-600/40 text-delentia-300 rounded-lg transition w-full"
        >
          Test inference →
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ModelsPage() {
  const ollamaUrl = process.env.NEXT_PUBLIC_OLLAMA_URL ?? "http://localhost:11434";
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [status, setStatus] = useState<"checking" | "running" | "offline">("checking");
  const [pullModel, setPullModel] = useState("delentia-labs/jitna-v0.1");
  const [pullStatus, setPullStatus] = useState<PullStatus | null>(null);
  const [pulling, setPulling] = useState(false);
  const [testModel, setTestModel] = useState<string | null>(null);
  const [testPrompt, setTestPrompt] = useState("สร้าง JITNA packet สำหรับ summarize_quarterly_report");
  const [testOutput, setTestOutput] = useState<string>("");
  const [testing, setTesting] = useState(false);

  const fetchModels = async () => {
    try {
      const res = await fetch(`${ollamaUrl}/api/tags`);
      if (!res.ok) throw new Error("Offline");
      const data: OllamaTagsResponse = await res.json();
      setModels(data.models ?? []);
      setStatus("running");
    } catch {
      setStatus("offline");
      setModels([]);
    }
  };

  useEffect(() => {
    fetchModels();
    const interval = setInterval(fetchModels, 10000);
    return () => clearInterval(interval);
  }, [ollamaUrl]);

  const handlePull = async () => {
    if (!pullModel.trim()) return;
    setPulling(true);
    setPullStatus({ status: "Starting pull…" });

    try {
      const res = await fetch(`${ollamaUrl}/api/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: pullModel, stream: false }),
      });
      if (!res.ok) {
        const err = await res.text();
        setPullStatus({ status: "error", error: err });
        return;
      }
      const data = await res.json();
      setPullStatus({ status: data.status ?? "done" });
      await fetchModels();
    } catch (err) {
      setPullStatus({ status: "error", error: String(err) });
    } finally {
      setPulling(false);
    }
  };

  const handleTest = async (modelName: string) => {
    setTestModel(modelName);
    setTestOutput("");
    setTesting(true);
    try {
      const res = await fetch(`${ollamaUrl}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: modelName,
          prompt: testPrompt,
          stream: false,
        }),
      });
      if (!res.ok) throw new Error(`Generate API returned ${res.status}`);
      const data = await res.json();
      setTestOutput(data.response ?? "(empty response)");
    } catch (err) {
      setTestOutput(`Error: ${String(err)}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      {/* Header + Status */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Local SLM Manager</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Manage Ollama models locally at {ollamaUrl}
          </p>
        </div>
        <span
          className={`flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border ${
            status === "running"
              ? "bg-green-900/30 text-green-400 border-green-700/40"
              : status === "offline"
              ? "bg-red-900/30 text-red-400 border-red-700/40"
              : "bg-gray-900/30 text-gray-400 border-gray-700/40"
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              status === "running"
                ? "bg-green-400"
                : status === "offline"
                ? "bg-red-400"
                : "bg-gray-400 animate-pulse"
            }`}
          />
          Ollama {status}
        </span>
      </div>

      {/* Offline banner */}
      {status === "offline" && (
        <div className="bg-red-900/20 border border-red-700/40 rounded-lg px-4 py-3 text-xs text-red-300 space-y-1">
          <p className="font-semibold">Ollama not detected at {ollamaUrl}</p>
          <p>
            Install Ollama from{" "}
            <a
              href="https://ollama.com/download"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-red-100"
            >
              ollama.com/download
            </a>
            , then run: <code className="font-mono bg-red-950/50 px-1 rounded">ollama serve</code>
          </p>
        </div>
      )}

      {/* Pull model */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Pull Model
        </h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={pullModel}
            onChange={(e) => setPullModel(e.target.value)}
            placeholder="model name (e.g. delentia-labs/jitna-v0.1)"
            className="flex-1 bg-surface text-gray-100 placeholder-gray-600 border border-surface-border rounded-lg px-3 py-2 text-sm outline-none focus:border-delentia-500 transition"
          />
          <button
            onClick={handlePull}
            disabled={pulling || status === "offline"}
            className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-sm font-medium transition"
          >
            {pulling ? "Pulling…" : "Pull"}
          </button>
        </div>
        {pullStatus && (
          <p
            className={`text-xs font-mono ${
              pullStatus.error ? "text-red-400" : "text-green-400"
            }`}
          >
            {pullStatus.error ?? pullStatus.status}
          </p>
        )}
      </div>

      {/* Installed models */}
      <div>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Installed Models ({models.length})
        </h2>
        {models.length === 0 && status === "running" && (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-center text-sm text-gray-500">
            No models installed. Pull{" "}
            <code className="font-mono text-delentia-400">delentia-labs/jitna-v0.1</code>{" "}
            to get started.
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {models.map((m) => (
            <ModelCard key={m.name} model={m} onTest={handleTest} />
          ))}
        </div>
      </div>

      {/* Test inference panel */}
      {testModel && (
        <div className="bg-surface-card border border-delentia-600/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Test: <span className="text-delentia-300 font-mono normal-case">{testModel}</span>
            </h2>
            <button
              onClick={() => setTestModel(null)}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              ✕ close
            </button>
          </div>
          <textarea
            value={testPrompt}
            onChange={(e) => setTestPrompt(e.target.value)}
            rows={2}
            className="w-full bg-surface text-gray-100 border border-surface-border rounded-lg px-3 py-2 text-sm outline-none focus:border-delentia-500 transition resize-none"
          />
          <button
            onClick={() => handleTest(testModel)}
            disabled={testing}
            className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-sm font-medium transition"
          >
            {testing ? "Running…" : "Run Inference"}
          </button>
          {testOutput && (
            <pre className="text-xs text-gray-300 bg-surface rounded-lg p-3 border border-surface-border overflow-auto max-h-60 whitespace-pre-wrap">
              {testOutput}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
