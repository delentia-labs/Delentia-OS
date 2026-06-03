"use client";

import { useState } from "react";
import { getHealthStatus } from "@/lib/delentia-client";
import { HEXACORE_REGISTRY } from "@/lib/types";
import type { HexaCoreRole } from "@/lib/types";
import { useThemeStore } from "@/hooks/useTheme";
import type { ThemeName } from "@/hooks/useTheme";

export default function SettingsPage() {
  const { theme, setTheme, colorMode, setColorMode } = useThemeStore();
  const [gateway, setGateway] = useState(
    process.env.NEXT_PUBLIC_GATEWAY ?? "http://localhost:8000"
  );
  const [apiKey, setApiKey] = useState(process.env.NEXT_PUBLIC_API_KEY ?? "");
  const [showKey, setShowKey] = useState(false);
  const [defaultRole, setDefaultRole] = useState<HexaCoreRole>("SUPREME_ARCHITECT");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);

  const testConnection = async () => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const health = await getHealthStatus(gateway);
      setTestResult(
        `✅ Connected — ${health.service} v${health.version} — Status: ${health.status}`
      );
    } catch (err) {
      setTestResult(`❌ ${err instanceof Error ? err.message : "Connection failed"}`);
    } finally {
      setTestLoading(false);
    }
  };

  const maskedKey = apiKey.length > 8
    ? `${apiKey.slice(0, 4)}${"•".repeat(apiKey.length - 8)}${apiKey.slice(-4)}`
    : "•".repeat(apiKey.length);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Configure the connection to your Delentia OS gateway.
        </p>
      </div>

      {/* Gateway URL */}
      <section className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-200">Gateway URL</h2>
        <p className="text-xs text-gray-500">
          The base URL of the Delentia OS API server. Default is{" "}
          <code className="bg-surface px-1 py-0.5 rounded text-gray-400">http://localhost:8000</code>.
        </p>
        <div className="flex gap-2">
          <input
            type="url"
            value={gateway}
            onChange={(e) => setGateway(e.target.value)}
            placeholder="http://localhost:8000"
            className="flex-1 bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-100 outline-none focus:border-delentia-500"
          />
          <button
            onClick={testConnection}
            disabled={testLoading}
            className="bg-delentia-600 hover:bg-delentia-500 disabled:opacity-40 text-white rounded-lg px-4 py-2 text-sm transition"
          >
            {testLoading ? "Testing…" : "Test"}
          </button>
        </div>
        {testResult && (
          <p className={`text-xs rounded-lg p-2 ${testResult.startsWith("✅") ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>
            {testResult}
          </p>
        )}
      </section>

      {/* API Key */}
      <section className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-200">API Key</h2>
        <p className="text-xs text-gray-500">
          Bearer token for authenticated /v1/* endpoints. Obtain via{" "}
          <code className="bg-surface px-1 py-0.5 rounded text-gray-400">rct init</code>.
          Never share this key.
        </p>
        <div className="flex gap-2">
          <input
            type={showKey ? "text" : "password"}
            value={showKey ? apiKey : maskedKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-sksk…"
            className="flex-1 bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm font-mono text-gray-100 outline-none focus:border-delentia-500"
          />
          <button
            onClick={() => setShowKey((v) => !v)}
            className="border border-surface-border rounded-lg px-3 py-2 text-xs text-gray-400 hover:text-gray-200 transition"
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
      </section>

      {/* Color Theme */}
      <section className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-200">Color Theme Settings</h2>
          <div className="flex items-center gap-1 bg-black/20 p-1 rounded-lg border border-white/5">
            <button
              onClick={() => setColorMode("light")}
              className={`text-xs px-2.5 py-1 rounded-md transition ${colorMode === "light" ? "bg-white/10 text-white font-medium" : "text-gray-400 hover:text-white"}`}
            >
              Light
            </button>
            <button
              onClick={() => setColorMode("dark")}
              className={`text-xs px-2.5 py-1 rounded-md transition ${colorMode === "dark" ? "bg-white/10 text-white font-medium" : "text-gray-400 hover:text-white"}`}
            >
              Dark
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-500">
          Select a custom color theme. Changing themes will automatically adjust light or dark system modes.
        </p>
        <div className="space-y-2">
          <label className="text-[10px] uppercase font-bold text-gray-400">Select Color Theme</label>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value as ThemeName)}
            className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500"
          >
            <optgroup label="Light Themes">
              <option value="powershell-ise">PowerShell ISE</option>
              <option value="quiet-light">Quiet Light</option>
              <option value="solarized-light">Solarized Light</option>
              <option value="tokyo-night-light">Tokyo Night Light</option>
            </optgroup>
            <optgroup label="Dark Themes">
              <option value="dark-modern-default">Default Dark Modern</option>
              <option value="abyss">Abyss</option>
              <option value="dark-visual-studio">Dark (Visual Studio)</option>
              <option value="dark-modern">Dark Modern</option>
              <option value="default-dark-plus">Dark+ (Default Dark+)</option>
              <option value="kimbie-dark">Kimbie Dark</option>
              <option value="monokai">Monokai</option>
              <option value="monokai-dimmed">Monokai Dimmed</option>
              <option value="red">Red</option>
              <option value="solarized-dark">Solarized Dark</option>
              <option value="synthwave-84">{"SynthWave '84"}</option>
              <option value="tokyo-night">Tokyo Night</option>
              <option value="tokyo-night-storm">Tokyo Night Storm</option>
              <option value="tomorrow-night-blue">Tomorrow Night Blue</option>
            </optgroup>
            <optgroup label="High Contrast Themes">
              <option value="dark-high-contrast">Dark High Contrast</option>
              <option value="light-high-contrast">Light High Contrast</option>
            </optgroup>
          </select>
        </div>
      </section>

      {/* Default HexaCore Role */}
      <section className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-200">Default HexaCore Role</h2>
        <p className="text-xs text-gray-500">
          Preferred model tier for intents sent from this desktop. The RCT architecture may override
          this based on task classification.
        </p>
        <select
          value={defaultRole}
          onChange={(e) => setDefaultRole(e.target.value as HexaCoreRole)}
          className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-100 outline-none focus:border-delentia-500"
        >
          {HEXACORE_REGISTRY.map((m) => (
            <option key={m.role} value={m.role}>
              {m.role} — {m.model_id} ({m.provider}){" "}
              {m.input_cost_per_1m === 0 ? "FREE" : `$${m.input_cost_per_1m}/1M in`}
            </option>
          ))}
        </select>

        {/* Selected model details */}
        {(() => {
          const m = HEXACORE_REGISTRY.find((r) => r.role === defaultRole);
          if (!m) return null;
          return (
            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                ["Model", m.model_id],
                ["Provider", m.provider],
                ["Country", m.country],
                ["Context", `${(m.context_window / 1000).toFixed(0)}k tokens`],
                ["Input cost", m.input_cost_per_1m === 0 ? "FREE" : `$${m.input_cost_per_1m}/1M`],
                ["Output cost", m.output_cost_per_1m === 0 ? "FREE" : `$${m.output_cost_per_1m}/1M`],
              ].map(([k, v]) => (
                <div key={k} className="bg-surface rounded p-2">
                  <p className="text-gray-500 text-[10px]">{k}</p>
                  <p className="text-gray-200 font-mono text-xs">{v}</p>
                </div>
              ))}
            </div>
          );
        })()}
      </section>

      {/* Version info */}
      <div className="text-xs text-gray-600 text-center">
        Delentia Desk v0.1.0 — Apache 2.0 — delentia-labs/delentia-gui
      </div>
    </div>
  );
}
