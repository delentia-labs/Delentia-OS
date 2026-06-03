"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  Cpu,
  Download,
  Terminal,
  Activity,
  Play,
  X,
  RefreshCw,
  HardDrive,
  Tag,
  AlertTriangle,
  Info,
  Server,
} from "lucide-react";

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
  const isDelentia = model.name.toLowerCase().includes("delentia") || model.name.toLowerCase().includes("jitna");

  return (
    <div
      className={`glass-card rounded-xl p-5 flex flex-col gap-3 border transition duration-300 ${
        isDelentia
          ? "border-delentia-500/40 hover:border-delentia-500/70"
          : "border-surface-border/60 hover:border-surface-border/90"
      }`}
    >
      <div className="flex justify-between items-start">
        <div className="space-y-1">
          <p className="font-semibold text-xs text-gray-200 font-mono flex items-center gap-1.5 flex-wrap">
            <Brain className={`w-3.5 h-3.5 ${isDelentia ? "text-delentia-400" : "text-gray-400"}`} />
            {model.name}
          </p>
          {isDelentia && (
            <span className="inline-block text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-delentia-500/10 border border-delentia-500/30 text-delentia-400">
              Delentia OS Core
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] text-gray-500 bg-surface/40 p-2.5 rounded-lg border border-surface-border/30">
        <div className="space-y-0.5">
          <span className="block text-gray-600">พารามิเตอร์</span>
          <span className="font-mono text-gray-300 font-semibold">{model.details?.parameter_size ?? "Unknown"}</span>
        </div>
        <div className="space-y-0.5">
          <span className="block text-gray-600">ขนาดไฟล์</span>
          <span className="font-mono text-gray-300 font-semibold">{sizeGb} GB</span>
        </div>
        <div className="space-y-0.5 col-span-2 border-t border-surface-border/20 pt-1.5 mt-0.5">
          <span className="block text-gray-600">รูปแบบการบีบอัด (Quantization)</span>
          <span className="font-mono text-gray-300 font-semibold">{model.details?.quantization_level ?? "Unknown"}</span>
        </div>
      </div>

      {model.details?.family && (
        <div className="flex items-center gap-1 text-[10px] text-gray-500 font-mono">
          <Tag className="w-3 h-3 text-gray-600" />
          <span>ตระกูล: {model.details.family}</span>
        </div>
      )}

      <button
        onClick={() => onTest(model.name)}
        className="mt-auto flex items-center justify-center gap-1.5 text-xs font-semibold py-2 bg-delentia-600/10 hover:bg-delentia-600/20 border border-delentia-500/20 hover:border-delentia-500/40 text-delentia-400 rounded-lg transition duration-200"
      >
        <Play className="w-3 h-3 fill-delentia-400" />
        ทดสอบอนุมาน (Test Inference)
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ModelsPage() {
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [status, setStatus] = useState<"checking" | "running" | "offline">("checking");
  const [pullModel, setPullModel] = useState("delentia-labs/jitna-v0.1");
  const [pullStatus, setPullStatus] = useState<PullStatus | null>(null);
  const [pulling, setPulling] = useState(false);
  const [testModel, setTestModel] = useState<string | null>(null);
  const [testPrompt, setTestPrompt] = useState("สร้าง JITNA packet สำหรับ summarize_quarterly_report ในภาษาไทย");
  const [testOutput, setTestOutput] = useState<string>("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem("delentia_ollama_url");
      if (saved) setOllamaUrl(saved);
      else if (process.env.NEXT_PUBLIC_OLLAMA_URL) setOllamaUrl(process.env.NEXT_PUBLIC_OLLAMA_URL);
    }
  }, []);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ollamaUrl]);

  const handlePull = async () => {
    if (!pullModel.trim()) return;
    setPulling(true);
    setPullStatus({ status: "กำลังเริ่มต้นดาวน์โหลดโมเดล..." });

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
      setPullStatus({ status: data.status ?? "ดาวน์โหลดเสร็จสิ้น" });
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
      setTestOutput(data.response ?? "(ไม่มีการตอบสนอง)");
    } catch (err) {
      setTestOutput(`ข้อผิดพลาด: ${String(err)}`);
    } finally {
      setTesting(false);
    }
  };

  const glowClass = {
    checking: "glow-simulator animate-pulse",
    running: "glow-ok",
    offline: "glow-offline",
  }[status];

  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-6 min-h-0 flex-1">
      {/* Header + Status */}
      <div className="flex justify-between items-center border-b border-surface-border pb-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Cpu className="w-5 h-5 text-delentia-500" />
            จัดการโมเดลขนาดเล็กภายในเครื่อง (Local SLM Manager)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            ดาวน์โหลด จัดระเบียบ และทดสอบโมเดลภาษาขนาดเล็ก (Small Language Models - SLM) ของคุณผ่าน Ollama
          </p>
        </div>
        
        <span
          className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider px-3.5 py-1.5 rounded-full border ${
            status === "running"
              ? "bg-green-950/20 border-green-800/40 text-green-400"
              : status === "offline"
              ? "bg-red-950/20 border-red-800/40 text-red-400"
              : "bg-purple-950/20 border-purple-800/40 text-purple-400"
          }`}
        >
          <span className={`w-2 h-2 rounded-full shrink-0 ${glowClass}`} />
          Ollama: {status}
        </span>
      </div>

      {/* Offline banner */}
      {status === "offline" && (
        <div className="bg-red-950/25 border border-red-800/40 rounded-xl p-4 flex gap-3 text-xs text-red-400 leading-relaxed">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <div className="space-y-1.5">
            <p className="font-semibold">ตรวจไม่พบเซิร์ฟเวอร์ Ollama ในที่อยู่ {ollamaUrl}</p>
            <p className="text-gray-400">
              กรุณาเปิดโปรแกรม Ollama หรือดาวน์โหลดได้ที่{" "}
              <a
                href="https://ollama.com/download"
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-red-300 hover:text-red-200 font-semibold"
              >
                ollama.com/download
              </a>
              {" "}จากนั้นรันคำสั่งบนเทอร์มินัลของคุณ: <code className="font-mono bg-red-950/50 px-2 py-0.5 rounded border border-red-800/30 text-red-300">ollama serve</code>
            </p>
          </div>
        </div>
      )}

      {/* Pull model */}
      <div className="glass-card rounded-xl p-5 space-y-4 border border-surface-border/60">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
          <Download className="w-4 h-4 text-delentia-500" />
          ดาวน์โหลดโมเดลเพิ่ม (Pull Model)
        </h2>
        <p className="text-xs text-gray-400">
          ระบุชื่อโมเดลที่ต้องการดาวน์โหลดจากคลังของ Ollama Registry (เช่น <code className="text-gray-300 font-mono bg-surface px-1 py-0.5 rounded">phi3</code>, <code className="text-gray-300 font-mono bg-surface px-1 py-0.5 rounded">llama3</code>) หรือคลังของ Delentia
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={pullModel}
            onChange={(e) => setPullModel(e.target.value)}
            placeholder="ชื่อโมเดล (เช่น delentia-labs/jitna-v0.1)"
            className="flex-1 bg-surface text-gray-200 placeholder-gray-600 border border-surface-border rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-delentia-500 transition"
          />
          <button
            onClick={handlePull}
            disabled={pulling || status === "offline"}
            className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-xs font-semibold shadow-md transition"
          >
            {pulling ? "กำลังดาวน์โหลด…" : "ดาวน์โหลด"}
          </button>
        </div>
        {pullStatus && (
          <div className="bg-surface/50 border border-surface-border/40 rounded-lg p-2.5 flex items-center gap-2 text-xs">
            <Info className="w-3.5 h-3.5 text-delentia-500" />
            <p className={`font-mono ${pullStatus.error ? "text-red-400" : "text-green-400"}`}>
              {pullStatus.error ? `ข้อผิดพลาด: ${pullStatus.error}` : pullStatus.status}
            </p>
          </div>
        )}
      </div>

      {/* Installed models */}
      <div>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <HardDrive className="w-4 h-4 text-delentia-500" />
          โมเดลที่ติดตั้งแล้ว ({models.length})
        </h2>
        {models.length === 0 && status === "running" && (
          <div className="glass-card rounded-xl p-8 text-center text-xs text-gray-500 border border-surface-border/50">
            ไม่มีโมเดลติดตั้งอยู่ในขณะนี้ แนะนำให้ดาวน์โหลด{" "}
            <code className="font-mono text-delentia-400">delentia-labs/jitna-v0.1</code> เพื่อเริ่มต้นการทดสอบ
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {models.map((m) => (
            <ModelCard key={m.name} model={m} onTest={handleTest} />
          ))}
        </div>
      </div>

      {/* Test inference panel */}
      {testModel && (
        <div className="glass-card rounded-xl p-5 border border-delentia-500/30 space-y-4 animate-in fade-in duration-200">
          <div className="flex items-center justify-between border-b border-surface-border/40 pb-2">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
              <Terminal className="w-4 h-4 text-delentia-500" />
              ทดสอบระบบอนุมาน: <span className="text-delentia-400 font-mono normal-case ml-1">{testModel}</span>
            </h2>
            <button
              onClick={() => setTestModel(null)}
              className="text-gray-500 hover:text-gray-300 hover:bg-white/5 rounded-full p-1 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] text-gray-500">ป้อนข้อความคำสั่งที่ส่งทดสอบ (Prompt)</label>
            <textarea
              value={testPrompt}
              onChange={(e) => setTestPrompt(e.target.value)}
              rows={2}
              className="w-full bg-surface text-gray-200 border border-surface-border rounded-lg px-3.5 py-2.5 text-xs outline-none focus:border-delentia-500 focus:ring-1 focus:ring-delentia-500/20 transition resize-none"
            />
          </div>
          <button
            onClick={() => handleTest(testModel)}
            disabled={testing}
            className="flex items-center gap-1.5 bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-xs font-semibold shadow-md transition"
          >
            {testing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-white" />}
            {testing ? "กำลังประมวลผล..." : "รันการประมวลผล (Run Inference)"}
          </button>
          {testOutput && (
            <div className="space-y-1.5 pt-2">
              <label className="text-[10px] text-gray-500">คำตอบจากโมเดล (Model Response)</label>
              <pre className="text-xs text-gray-300 bg-surface rounded-lg p-3 border border-surface-border/50 overflow-auto max-h-60 whitespace-pre-wrap font-mono leading-relaxed">
                {testOutput}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
