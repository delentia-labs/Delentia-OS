/**
 * rct memory — MEE v2 Growth State CLI
 *
 * Sub-commands:
 *   rct memory show               Display current MEE session from .rct.json
 *   rct memory improve [delta]    Record a MEE step with given delta (default 0.05)
 *   rct memory reset              Reset MEE session in .rct.json
 *
 * MEE v2 formula: G(t+1) = max(G_FLOOR, G(t) × (1 + M × Δ) × R_t)
 *   M = meta_rate = 0.10 (default)
 *   R_t = 1.0 - governance_violations × 0.02
 *   G_FLOOR = 0.10,  G_CAP = 1000.0
 */

import { Command } from "commander";
import chalk from "chalk";
import { existsSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import boxen from "boxen";
import { randomBytes } from "crypto";

// ─── MEE v2 constants ────────────────────────────────────────────────────────
const MEE_VERSION = "2.0";
const DEFAULT_META_RATE = 0.10;
const G_FLOOR = 0.10;
const G_CAP = 1000.0;
const RESILIENCE_PENALTY = 0.02;

// ─── Types ────────────────────────────────────────────────────────────────────
interface MEEState {
  version: string;
  session_id: string;
  g_initial: number;
  g_current: number;
  step_count: number;
  meta_rate: number;
  resilience: number;
  governance_violations: number;
  trend: "growing" | "stable" | "declining";
  total_growth_ratio: number;
  last_updated: string;
  history: MEEStep[];
}

interface MEEStep {
  step: number;
  g_before: number;
  g_after: number;
  delta: number;
  meta_rate: number;
  resilience: number;
  governance_violation: boolean;
  timestamp: string;
}

interface RCTConfig {
  baseURL?: string;
  userTier?: string;
  tier?: string;
  project_name?: string;
  region?: string;
  fdiaGate?: boolean;
  version?: string;
  createdAt?: string;
  mee_state?: MEEState;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const CONFIG_PATH = join(process.cwd(), ".rct.json");

function loadConfig(): RCTConfig {
  if (!existsSync(CONFIG_PATH)) return {};
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as RCTConfig;
  } catch {
    return {};
  }
}

function saveConfig(cfg: RCTConfig): void {
  writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), "utf-8");
}

function randomSessionId(): string {
  const bytes = randomBytes(3);
  return `mee-${Date.now().toString(36)}-${bytes.toString("hex")}`;
}

function initialMEEState(): MEEState {
  return {
    version: MEE_VERSION,
    session_id: randomSessionId(),
    g_initial: 1.0,
    g_current: 1.0,
    step_count: 0,
    meta_rate: DEFAULT_META_RATE,
    resilience: 1.0,
    governance_violations: 0,
    trend: "stable",
    total_growth_ratio: 1.0,
    last_updated: new Date().toISOString(),
    history: [],
  };
}

function computeTrend(history: MEEStep[]): "growing" | "stable" | "declining" {
  if (history.length < 3) return "stable";
  const recent = history.slice(-3);
  const deltas = recent.map((s) => s.g_after - s.g_before);
  const avg = deltas.reduce((a, b) => a + b, 0) / deltas.length;
  if (avg > 0.01) return "growing";
  if (avg < -0.01) return "declining";
  return "stable";
}

function applyMEEStep(
  state: MEEState,
  delta: number,
  governanceViolation = false
): MEEState {
  const gBefore = state.g_current;

  // Update resilience
  let newResilience = state.resilience;
  if (governanceViolation) {
    newResilience = Math.max(0.0, newResilience - RESILIENCE_PENALTY);
  } else {
    // Slight recovery when no violation (capped at 1.0)
    newResilience = Math.min(1.0, newResilience + 0.005);
  }

  const M = state.meta_rate;
  const gAfter = Math.min(
    G_CAP,
    Math.max(G_FLOOR, gBefore * (1 + M * delta) * newResilience)
  );

  const step: MEEStep = {
    step: state.step_count + 1,
    g_before: gBefore,
    g_after: gAfter,
    delta,
    meta_rate: M,
    resilience: newResilience,
    governance_violation: governanceViolation,
    timestamp: new Date().toISOString(),
  };

  const newHistory = [...state.history, step];
  const trend = computeTrend(newHistory);
  const newViolations = governanceViolation
    ? state.governance_violations + 1
    : state.governance_violations;

  return {
    ...state,
    g_current: gAfter,
    step_count: state.step_count + 1,
    resilience: newResilience,
    governance_violations: newViolations,
    trend,
    total_growth_ratio: gAfter / state.g_initial,
    last_updated: new Date().toISOString(),
    history: newHistory.slice(-50), // keep last 50 steps
  };
}

function trendColor(trend: string): string {
  switch (trend) {
    case "growing": return chalk.green(trend);
    case "declining": return chalk.red(trend);
    default: return chalk.yellow(trend);
  }
}

// ─── Sub-command: show ────────────────────────────────────────────────────────
function showMemory(): void {
  const cfg = loadConfig();

  if (!cfg.mee_state) {
    console.log(
      chalk.yellow("\n  No MEE v2 state found in .rct.json\n") +
      chalk.gray("  Run: ") + chalk.cyan("rct memory improve") + chalk.gray(" to initialize\n")
    );
    return;
  }

  const m = cfg.mee_state;
  const trendStr = trendColor(m.trend);
  const ratioChange = ((m.total_growth_ratio - 1) * 100).toFixed(2);
  const sign = m.total_growth_ratio >= 1 ? "+" : "";

  const histPreview = m.history.slice(-5).map((s, i) =>
    `    Step ${s.step.toString().padStart(3)} | ` +
    `G: ${s.g_before.toFixed(4)} → ${s.g_after.toFixed(4)} | ` +
    `Δ=${s.delta > 0 ? "+" : ""}${s.delta.toFixed(3)} | ` +
    `R=${s.resilience.toFixed(3)}` +
    (s.governance_violation ? chalk.red(" [GOV-VIO]") : "")
  ).join("\n");

  const box = boxen(
    [
      chalk.bold(`MEE v2 — Session: ${m.session_id}`),
      "",
      `  ${chalk.bold("G (current):")}     ${chalk.cyan(m.g_current.toFixed(6))}`,
      `  ${chalk.bold("G (initial):")}     ${chalk.gray(m.g_initial.toFixed(6))}`,
      `  ${chalk.bold("Total growth:")}    ${sign}${ratioChange}% (${m.total_growth_ratio.toFixed(4)}×)`,
      `  ${chalk.bold("Steps:")}           ${m.step_count}`,
      `  ${chalk.bold("Trend:")}           ${trendStr}`,
      `  ${chalk.bold("Resilience:")}      ${m.resilience.toFixed(4)}`,
      `  ${chalk.bold("Gov. violations:")} ${m.governance_violations}`,
      `  ${chalk.bold("Meta-rate:")}       ${m.meta_rate}`,
      `  ${chalk.bold("Last updated:")}    ${m.last_updated}`,
      "",
      chalk.bold("  Recent Steps (last 5):"),
      histPreview || "    (no history yet)",
    ].join("\n"),
    {
      padding: { top: 1, bottom: 1, left: 2, right: 2 },
      margin: { top: 0, bottom: 1, left: 0, right: 0 },
      borderStyle: "round",
      borderColor: m.trend === "growing" ? "green" : m.trend === "declining" ? "red" : "yellow",
      title: "RCT MEE v2 Growth Engine",
      titleAlignment: "left",
    }
  );

  console.log(box);
}

// ─── Sub-command: improve ─────────────────────────────────────────────────────
function improveMemory(deltaArg: string | undefined, govViolation: boolean): void {
  const delta = deltaArg !== undefined ? parseFloat(deltaArg) : 0.05;

  if (isNaN(delta)) {
    console.log(chalk.red(`  Invalid delta: "${deltaArg}" — must be a number (e.g. 0.05)\n`));
    process.exitCode = 1;
    return;
  }

  if (delta < -1 || delta > 1) {
    console.log(chalk.yellow(`  Warning: delta ${delta} is outside typical range [-1.0, 1.0]\n`));
  }

  const cfg = loadConfig();
  const prevState: MEEState = cfg.mee_state ?? initialMEEState();
  const newState = applyMEEStep(prevState, delta, govViolation);

  cfg.mee_state = newState;
  saveConfig(cfg);

  const step = newState.history[newState.history.length - 1];
  const trendStr = trendColor(newState.trend);
  const arrow = step.g_after >= step.g_before ? chalk.green("▲") : chalk.red("▼");

  console.log(
    chalk.bold("\n  MEE v2 Step Recorded\n") +
    `  Step:       ${newState.step_count}\n` +
    `  G:          ${step.g_before.toFixed(6)} ${arrow} ${chalk.cyan(step.g_after.toFixed(6))}\n` +
    `  Δ:          ${delta > 0 ? "+" : ""}${delta.toFixed(3)}\n` +
    `  Resilience: ${step.resilience.toFixed(4)}\n` +
    `  Trend:      ${trendStr}\n` +
    `  Saved to .rct.json\n`
  );
}

// ─── Sub-command: reset ───────────────────────────────────────────────────────
function resetMemory(): void {
  const cfg = loadConfig();
  const fresh = initialMEEState();
  cfg.mee_state = fresh;
  saveConfig(cfg);

  console.log(
    chalk.bold("\n  MEE v2 Session Reset\n") +
    chalk.gray(`  Session ID: ${fresh.session_id}\n`) +
    chalk.gray(`  G = 1.0 (starting point)\n`) +
    chalk.gray(`  .rct.json updated\n`)
  );
}

// ─── Command definition ───────────────────────────────────────────────────────
export const memoryCommand = new Command("memory")
  .description("Manage MEE v2 growth engine state (G = G × (1 + M × Δ) × R_t)")
  .addCommand(
    new Command("show")
      .description("Display current MEE session state from .rct.json")
      .action(() => showMemory())
  )
  .addCommand(
    new Command("improve")
      .description("Record a MEE growth step (default delta = +0.05)")
      .argument("[delta]", "Growth delta in range [-1.0, 1.0] (default: 0.05)")
      .option("--gov-violation", "Mark step as a governance violation (R_t penalised)")
      .action((delta: string | undefined, opts: Record<string, unknown>) => {
        improveMemory(delta, opts["govViolation"] === true);
      })
  )
  .addCommand(
    new Command("reset")
      .description("Reset MEE session (G returns to 1.0, history cleared)")
      .action(() => resetMemory())
  );
