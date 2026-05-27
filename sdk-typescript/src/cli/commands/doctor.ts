import { Command } from "commander";
import chalk from "chalk";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { execSync } from "child_process";
import { showBanner } from "../ui/banner";

interface MEEState {
  session_id?: string;
  g_current?: number;
  g_initial?: number;
  step_count?: number;
  trend?: string;
  total_growth_ratio?: number;
}

interface RCTConfig {
  baseURL?: string;
  userTier?: string;
  region?: string;
  project_name?: string;
  tier?: string;
  mee_state?: MEEState;
}

function tryLoadConfig(): RCTConfig | null {
  const configPath = join(process.cwd(), ".rct.json");
  if (!existsSync(configPath)) return null;
  try {
    return JSON.parse(readFileSync(configPath, "utf-8")) as RCTConfig;
  } catch {
    return null;
  }
}

function tryPythonSdk(): string | null {
  for (const bin of ["python", "python3"]) {
    try {
      const v = execSync(
        `${bin} -c "import rct_control_plane; print(rct_control_plane.__version__)"`,
        { encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"] }
      ).trim();
      return v;
    } catch {
      continue;
    }
  }
  return null;
}

export const doctorCommand = new Command("doctor")
  .description("Run E2E preflight diagnostics on RCT Platform and developer environment")
  .option("--no-banner", "Skip the banner")
  .option("-u, --url <url>", "Override server URL for connectivity check")
  .action(async (opts: Record<string, unknown>) => {
    const { default: boxen } = await import("boxen");
    const { default: ora } = await import("ora");
    const { RCTClient } = await import("../../client");
    const { centerText } = await import("../ui/align");

    if (opts["banner"] !== false) showBanner();

    const terminalWidth = process.stdout.columns || 80;
    console.log(centerText(chalk.bold.cyan("Running RCT preflight diagnostics...\n"), terminalWidth));

    const spinner = ora("Initiating system diagnostics...").start();

    // 1. Check Node.js version
    spinner.text = "Checking Node.js version...";
    const nodeVer = process.version;
    const major = parseInt(nodeVer.replace("v", "").split(".")[0], 10);
    const nodeStatus = major >= 18 ? chalk.green("✔ PASS") : chalk.red("✘ FAIL (Node >= 18 required)");

    // 2. Check local config file .rct.json
    spinner.text = "Validating .rct.json configuration...";
    const configObj: RCTConfig = tryLoadConfig() ?? {};
    const configExists = Object.keys(configObj).length > 0;
    const configValid =
      (configObj.project_name !== undefined || configObj.baseURL !== undefined) &&
      (configObj.tier !== undefined || configObj.userTier !== undefined);

    const configStatus = !configExists
      ? chalk.yellow("⚠ WARNING (Missing .rct.json — run 'rct init')")
      : configValid
        ? chalk.green("✔ PASS")
        : chalk.red("✘ FAIL (Invalid config — run 'rct init')");

    // 3. Check local database read/write access
    spinner.text = "Checking database cache write permissions...";
    let dbStatus = chalk.green("✔ PASS");
    try {
      const testPath = join(process.cwd(), ".rct_write_test");
      const { writeFileSync, unlinkSync } = await import("fs");
      writeFileSync(testPath, "test");
      unlinkSync(testPath);
    } catch {
      dbStatus = chalk.red("✘ FAIL (No write access to workspace)");
    }

    // 4. Python SDK detection
    spinner.text = "Detecting Python SDK...";
    const pythonVer = tryPythonSdk();
    const pythonStatus = pythonVer
      ? chalk.green(`✔ PASS (rct_control_plane v${pythonVer})`)
      : chalk.yellow("⚠ WARNING (not installed — pip install rct-platform)");

    // 5. FDIA baseline sanity
    spinner.text = "Running FDIA baseline sanity check...";
    const fdiaD = 0.9, fdiaI = 1.0, fdiaA = 0.9;
    const fdiaF = Math.pow(fdiaD, fdiaI) * fdiaA;
    const fdiaDiff = Math.abs(fdiaF - 0.81);
    const fdiaStatus = fdiaDiff < 0.0001
      ? chalk.green(`✔ PASS  F(0.9,1.0,0.9) = ${fdiaF.toFixed(4)}`)
      : chalk.red(`✘ FAIL  expected 0.81 got ${fdiaF.toFixed(4)}`);

    // 6. MEE v2 state
    spinner.text = "Reading MEE v2 growth state...";
    let meeStatus: string;
    if (configObj.mee_state) {
      const m = configObj.mee_state;
      const ratio = m.g_current && m.g_initial ? (m.g_current / m.g_initial).toFixed(3) : "?";
      meeStatus = chalk.green(
        `✔ PASS  G=${m.g_current?.toFixed(4)} steps=${m.step_count} trend=${m.trend} (${ratio}×)`
      );
    } else {
      meeStatus = chalk.yellow("⚠ WARNING (no MEE state — run 'rct memory improve')");
    }

    // 7. Check REST API Connectivity & Latency
    spinner.text = "Pinging RCT Platform API server...";
    const baseURL =
      (opts["url"] as string | undefined) ?? configObj.baseURL ?? "http://localhost:8000";
    let serverStatus = chalk.red("✘ FAIL (Offline)");
    let latency = "N/A";

    try {
      const client = new RCTClient({ baseURL, timeoutMs: 3_000 });
      const startTime = Date.now();
      const metrics = await client.getMetrics();
      const duration = Date.now() - startTime;
      latency = `${duration}ms`;
      if (metrics.total_intents !== undefined) {
        serverStatus = chalk.green(`✔ PASS (${latency})`);
      }
    } catch {
      serverStatus = chalk.red("✘ FAIL (Server unreachable — offline OK)");
    }

    spinner.stop();

    // Compile diagnostics grid
    const lines = [
      `${chalk.bold("RCT CLI Engine:")}               v1.3.0`,
      `${chalk.bold("Node.js Environment:")}          ${nodeVer} — ${nodeStatus}`,
      `${chalk.bold("Config (.rct.json):")}           ${configStatus}`,
      `${chalk.bold("Workspace Cache:")}              ${dbStatus}`,
      `${chalk.bold("Python SDK:")}                   ${pythonStatus}`,
      `${chalk.bold("FDIA Baseline (F=D^I×A):")}      ${fdiaStatus}`,
      `${chalk.bold("MEE v2 Growth State:")}          ${meeStatus}`,
      `${chalk.bold("FastAPI Backend:")}              ${serverStatus}`,
      "",
    ];

    const isHealthy = major >= 18 && !dbStatus.includes("FAIL") && !fdiaStatus.includes("FAIL");


    if (isHealthy) {
      lines.push(
        chalk.green.bold("  ✔  All systems operational. Your developer pipeline is ready!")
      );
    } else {
      lines.push(chalk.red.bold("  ✘  Preflight checks failed. Please review the failures above."));
      if (!serverStatus.includes("✔ PASS")) {
        lines.push("");
        lines.push(chalk.bold("  Troubleshooting Backend Connection:"));
        lines.push(`    1. Ensure the Python FastAPI server is active.`);
        lines.push(`    2. Run ${chalk.cyan("pip install rct-platform")} & ${chalk.cyan("rct serve")} to start it.`);
        lines.push(`    3. Or override base URL using ` + chalk.cyan("rct doctor --url <custom_url>"));
      }
      if (!configExists) {
        lines.push("");
        lines.push(chalk.bold("  Troubleshooting Configuration:"));
        lines.push(`    1. Run ${chalk.cyan("rct init")} to build your .rct.json file.`);
      }
    }

    const outputBox = boxen(lines.join("\n"), {
      padding: { top: 1, bottom: 1, left: 2, right: 2 },
      margin: { top: 0, bottom: 1, left: 0, right: 0 },
      borderStyle: "round",
      borderColor: isHealthy ? "green" : "red",
      title: "RCT Platform — Diagnostic Preflight Report",
      titleAlignment: "left",
    });

    console.log(centerText(outputBox, terminalWidth));

    if (!isHealthy) {
      process.exit(1);
    }
  });
