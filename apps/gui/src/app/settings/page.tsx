"use client";

import { useState, useEffect } from "react";
import { getHealthStatus } from "@/lib/delentia-client";
import { HEXACORE_REGISTRY } from "@/lib/types";
import type { HexaCoreRole } from "@/lib/types";
import { useThemeStore, type ThemeName, type ColorMode } from "@/hooks/useTheme";
import {
  Palette,
  Sun,
  Moon,
  Server,
  Key,
  Eye,
  EyeOff,
  Cpu,
  CheckCircle2,
  Save,
  Activity,
  Globe,
  DollarSign,
  AlertTriangle,
  RotateCcw,
  Settings,
} from "lucide-react";

const THEMES = [
  { value: "dark-modern-default", label: "Default Dark Modern (Space Deep)", mode: "dark" },
  { value: "abyss", label: "Abyss (Deep Oceanic)", mode: "dark" },
  { value: "dark-visual-studio", label: "Dark (Visual Studio)", mode: "dark" },
  { value: "dark-modern", label: "Dark Modern", mode: "dark" },
  { value: "default-dark-plus", label: "Dark+ (Default)", mode: "dark" },
  { value: "kimbie-dark", label: "Kimbie Dark (Warm Clay)", mode: "dark" },
  { value: "monokai", label: "Monokai", mode: "dark" },
  { value: "monokai-dimmed", label: "Monokai Dimmed", mode: "dark" },
  { value: "red", label: "Red (Ruby Deep)", mode: "dark" },
  { value: "solarized-dark", label: "Solarized Dark", mode: "dark" },
  { value: "synthwave-84", label: "Synthwave '84 (Cyberpunk)", mode: "dark" },
  { value: "tokyo-night", label: "Tokyo Night", mode: "dark" },
  { value: "tokyo-night-storm", label: "Tokyo Night Storm", mode: "dark" },
  { value: "tomorrow-night-blue", label: "Tomorrow Night Blue", mode: "dark" },
  { value: "dark-high-contrast", label: "Dark High Contrast", mode: "dark" },
  
  { value: "powershell-ise", label: "PowerShell ISE (White/Blue)", mode: "light" },
  { value: "quiet-light", label: "Quiet Light (Soft Cream)", mode: "light" },
  { value: "solarized-light", label: "Solarized Light", mode: "light" },
  { value: "tokyo-night-light", label: "Tokyo Night Light", mode: "light" },
  { value: "light-high-contrast", label: "Light High Contrast", mode: "light" },
];

export default function SettingsPage() {
  const { theme: activeTheme, colorMode, setTheme, setColorMode } = useThemeStore();
  
  const [mounted, setMounted] = useState(false);
  const [gateway, setGateway] = useState("http://localhost:8000");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [defaultRole, setDefaultRole] = useState<HexaCoreRole>("SUPREME_ARCHITECT");
  
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (typeof window !== "undefined") {
      const savedGateway = window.localStorage.getItem("delentia_gateway");
      const savedApiKey = window.localStorage.getItem("delentia_api_key");
      const savedRole = window.localStorage.getItem("delentia_default_role");
      
      if (savedGateway) setGateway(savedGateway);
      else if (process.env.NEXT_PUBLIC_GATEWAY) setGateway(process.env.NEXT_PUBLIC_GATEWAY);

      if (savedApiKey) setApiKey(savedApiKey);
      else if (process.env.NEXT_PUBLIC_API_KEY) setApiKey(process.env.NEXT_PUBLIC_API_KEY);

      if (savedRole) setDefaultRole(savedRole as HexaCoreRole);
    }
  }, []);

  const saveSettings = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("delentia_gateway", gateway);
      window.localStorage.setItem("delentia_api_key", apiKey);
      window.localStorage.setItem("delentia_default_role", defaultRole);
      
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    }
  };

  const resetToDefaults = () => {
    const defaultGateway = process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000";
    const defaultApi = process.env.NEXT_PUBLIC_API_KEY ?? "";
    setGateway(defaultGateway);
    setApiKey(defaultApi);
    setDefaultRole("SUPREME_ARCHITECT");
    setTheme("dark-modern-default");
    
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("delentia_gateway");
      window.localStorage.removeItem("delentia_api_key");
      window.localStorage.removeItem("delentia_default_role");
    }

    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  const testConnection = async () => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const health = await getHealthStatus(gateway);
      setTestResult(
        `✅ เชื่อมต่อสำเร็จ — ${health.service} v${health.version} — สถานะ: ${health.status}`
      );
    } catch (err) {
      setTestResult(`❌ ล้มเหลว: ${err instanceof Error ? err.message : "ไม่สามารถเชื่อมต่อได้"}`);
    } finally {
      setTestLoading(false);
    }
  };

  const maskedKey = apiKey.length > 8
    ? `${apiKey.slice(0, 4)}${"•".repeat(apiKey.length - 8)}${apiKey.slice(-4)}`
    : "•".repeat(apiKey.length);

  if (!mounted) return null;

  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-6 min-h-0 flex-1">
      <div className="flex justify-between items-center border-b border-surface-border pb-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="w-6 h-6 text-delentia-500 animate-spin-slow" />
            การตั้งค่าระบบ (Settings)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            ปรับปรุงธีมสี เชื่อมต่อ API Gateway และจัดการคุณสมบัติการทดลองสำหรับ Delentia OS
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={resetToDefaults}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-surface-border text-xs text-gray-400 hover:text-gray-200 hover:bg-white/5 transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            รีเซ็ตเป็นค่าเริ่มต้น
          </button>
          <button
            onClick={saveSettings}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-delentia-600 hover:bg-delentia-500 text-white text-xs font-semibold shadow-md transition"
          >
            <Save className="w-3.5 h-3.5" />
            บันทึกการตั้งค่า
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="bg-green-950/40 border border-green-800/60 rounded-xl p-3 flex items-center gap-3 text-green-400 text-xs animate-in fade-in slide-in-from-top-2 duration-300">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>บันทึกการตั้งค่าลง Local Storage เรียบร้อยแล้ว ระบบจะอัปเดตการแสดงผลโดยทันที</span>
        </div>
      )}

      {/* 🚀 Appearance Section */}
      <section className="glass-card rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <Palette className="w-4 h-4 text-delentia-500" />
          การออกแบบและการแสดงผล (Appearance)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Color Mode Selection */}
          <div className="space-y-2">
            <label className="text-xs text-gray-400 block">โหมดแสดงผล (Color Mode)</label>
            <div className="flex bg-surface border border-surface-border rounded-lg p-1 gap-1">
              <button
                onClick={() => setColorMode("light")}
                className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-xs font-medium transition ${
                  colorMode === "light"
                    ? "bg-white text-gray-900 shadow"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                <Sun className="w-3.5 h-3.5" />
                โหมดสว่าง (Light)
              </button>
              <button
                onClick={() => setColorMode("dark")}
                className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-xs font-medium transition ${
                  colorMode === "dark"
                    ? "bg-white/10 text-white shadow"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                <Moon className="w-3.5 h-3.5" />
                โหมดมืด (Dark)
              </button>
            </div>
          </div>

          {/* Color Theme Dropdown */}
          <div className="space-y-2">
            <label className="text-xs text-gray-400 block">ชุดสีธีมของระบบ (Color Theme)</label>
            <select
              value={activeTheme}
              onChange={(e) => setTheme(e.target.value as ThemeName)}
              className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-xs text-gray-200 outline-none focus:border-delentia-500 transition"
            >
              <optgroup label="โหมดมืด (Dark Themes)">
                {THEMES.filter((t) => t.mode === "dark").map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="โหมดสว่าง (Light Themes)">
                {THEMES.filter((t) => t.mode === "light").map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
        </div>
      </section>

      {/* 🌐 API Gateway URL */}
      <section className="glass-card rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <Server className="w-4 h-4 text-delentia-500" />
          การเชื่อมต่อ API Gateway
        </h2>
        <p className="text-xs text-gray-400">
          ระบุที่อยู่ของเซิร์ฟเวอร์ Delentia OS API Server โดยปกติคือ{" "}
          <code className="bg-surface border border-surface-border px-1.5 py-0.5 rounded text-gray-300 font-mono">http://localhost:8000</code>.
        </p>
        <div className="flex gap-2">
          <input
            type="url"
            value={gateway}
            onChange={(e) => setGateway(e.target.value)}
            placeholder="http://localhost:8000"
            className="flex-1 bg-surface border border-surface-border rounded-lg px-3 py-2 text-xs text-gray-200 font-mono outline-none focus:border-delentia-500 transition"
          />
          <button
            onClick={testConnection}
            disabled={testLoading}
            className="bg-white/10 hover:bg-white/15 disabled:opacity-40 border border-surface-border text-gray-200 rounded-lg px-4 py-2 text-xs font-medium transition"
          >
            {testLoading ? "กำลังเชื่อมต่อ…" : "ทดสอบการเชื่อมต่อ"}
          </button>
        </div>
        {testResult && (
          <p
            className={`text-xs rounded-lg p-2.5 border ${
              testResult.includes("✅")
                ? "bg-green-950/20 border-green-800/40 text-green-400"
                : "bg-red-950/20 border-red-800/40 text-red-400"
            }`}
          >
            {testResult}
          </p>
        )}
      </section>

      {/* 🔑 API Authentication Key */}
      <section className="glass-card rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <Key className="w-4 h-4 text-delentia-500" />
          กุญแจตรวจสอบสิทธิ์ (API Authorization Key)
        </h2>
        <p className="text-xs text-gray-400">
          ใช้เพื่อเรียกใช้บริการ endpoints ภายใต้เส้นทาง <code className="text-gray-300 font-mono bg-surface px-1 py-0.5 rounded">/v1/*</code>. 
          สร้างกุญแจนี้โดยตรงผ่าน CLI ของ Delentia OS โดยใช้คำสั่ง <code className="text-gray-300 font-mono bg-surface px-1 py-0.5 rounded">rct init</code>.
        </p>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={showKey ? "text" : "password"}
              value={showKey ? apiKey : maskedKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-…"
              className="w-full bg-surface border border-surface-border rounded-lg pl-3 pr-10 py-2 text-xs font-mono text-gray-200 outline-none focus:border-delentia-500 transition"
            />
            <button
              onClick={() => setShowKey((v) => !v)}
              type="button"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 transition"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </section>

      {/* 🧠 Default HexaCore Role Configuration */}
      <section className="glass-card rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-delentia-500" />
          บทบาทของโมเดลผู้ให้ความเห็น (Default HexaCore Role)
        </h2>
        <p className="text-xs text-gray-400">
          เลือกบทบาทโมเดล AI ที่ต้องการทำงานเป็นอันดับแรกสำหรับผู้ใช้ทั่วไป 
          โดยในการประมวลผลจริง ระบบ RCT Compiler อาจปรับเปลี่ยนอัตโนมัติตามประเภทและระดับความยากของคำสั่ง
        </p>
        <select
          value={defaultRole}
          onChange={(e) => setDefaultRole(e.target.value as HexaCoreRole)}
          className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-xs text-gray-200 outline-none focus:border-delentia-500 transition"
        >
          {HEXACORE_REGISTRY.map((m) => (
            <option key={m.role} value={m.role}>
              {m.role} — {m.model_id} ({m.provider}){" "}
              {m.input_cost_per_1m === 0 ? "ฟรี (FREE)" : `$${m.input_cost_per_1m}/1M tokens`}
            </option>
          ))}
        </select>

        {/* Selected model details */}
        {(() => {
          const m = HEXACORE_REGISTRY.find((r) => r.role === defaultRole);
          if (!m) return null;
          return (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2">
              {[
                { label: "โมเดลฐาน (Model)", value: m.model_id, icon: Cpu },
                { label: "ผู้ให้บริการ (Provider)", value: m.provider, icon: Globe },
                { label: "พื้นที่โฮสต์ (Country)", value: m.country, icon: Globe },
                { label: "หน้าต่างความจำ (Context)", value: `${(m.context_window / 1000).toFixed(0)}k tokens`, icon: Activity },
                { label: "ราคาขาเข้า (Input Cost)", value: m.input_cost_per_1m === 0 ? "ฟรี" : `$${m.input_cost_per_1m} / 1M`, icon: DollarSign },
                { label: "ราคาขาออก (Output Cost)", value: m.output_cost_per_1m === 0 ? "ฟรี" : `$${m.output_cost_per_1m} / 1M`, icon: DollarSign },
              ].map(({ label, value, icon: Icon }) => (
                <div key={label} className="bg-surface border border-surface-border/50 rounded-lg p-3 space-y-1">
                  <span className="text-gray-400 text-[10px] flex items-center gap-1">
                    <Icon className="w-3 h-3 text-delentia-500" />
                    {label}
                  </span>
                  <p className="text-gray-200 font-mono text-xs truncate">{value}</p>
                </div>
              ))}
            </div>
          );
        })()}
      </section>

      {/* Version and Footer */}
      <div className="text-[10px] text-gray-500 text-center py-4 flex flex-col items-center gap-1">
        <span>Delentia Desk v1.0.4 — Apache 2.0 License</span>
        <span>ระบบความมั่นคงด้านปัญญาประดิษฐ์ (SignedAI Verified Engine)</span>
      </div>
    </div>
  );
}
