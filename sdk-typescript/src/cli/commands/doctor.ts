import { Command } from "commander";
import chalk from "chalk";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { showBanner } from "../ui/banner";

interface RCTConfig {
  baseURL?: string;
  userTier?: string;
  region?: string;
}

export const doctorCommand = new Command("doctor")
  .description("Run E2E preflight diagnostics on RCT Platform and developer environment")
  .option("--no-banner", "Skip the banner")
  .action(async (opts: Record<string, unknown>) => {
    // Dynamic imports for heavy packages to ensure ultra-fast cold starts
    const { default: boxen } = await import("boxen");
    const { default: ora } = await import("ora");
    const { RCTClient } = await import("../../client");

    if (opts["banner"] !== false) showBanner();

    console.log(chalk.bold.cyan("  Running RCT preflight diagnostics...\n"));

    const spinner = ora("Initiating system diagnostics...").start();

    // 1. Check Node.js version
    spinner.text = "Checking Node.js version...";
    const nodeVer = process.version;
    const major = parseInt(nodeVer.replace("v", "").split(".")[0], 10);
    const nodeStatus = major >= 16 ? chalk.green("✔ PASS") : chalk.red("✘ FAIL (Node >= 16 required)");

    // 2. Check local config file .rct.json
    spinner.text = "Validating .rct.json configuration...";
    const configPath = join(process.cwd(), ".rct.json");
    let configExists = false;
    let configValid = false;
    let configObj: RCTConfig = {};

    if (existsSync(configPath)) {
      configExists = true;
      try {
        configObj = JSON.parse(readFileSync(configPath, "utf-8")) as RCTConfig;
        configValid =
          configObj.baseURL !== undefined &&
          configObj.userTier !== undefined &&
          configObj.region !== undefined;
      } catch {
        configValid = false;
      }
    }

    const configStatus = !configExists
      ? chalk.yellow("⚠ WARNING (Missing .rct.json - run 'rct init')")
      : configValid
        ? chalk.green("✔ PASS")
        : chalk.red("✘ FAIL (Invalid config format)");

    // 3. Check local database read/write access
    spinner.text = "Checking database cache write permissions...";
    const dbPath = join(process.cwd(), "rct_control_plane.db");
    let dbStatus = chalk.green("✔ PASS");
    try {
      // Just check if we can check write access in the current working directory
      const testPath = join(process.cwd(), ".rct_write_test");
      const { writeFileSync, unlinkSync } = await import("fs");
      writeFileSync(testPath, "test");
      unlinkSync(testPath);
    } catch {
      dbStatus = chalk.red("✘ FAIL (No write access to workspace)");
    }

    // 4. Check REST API Connectivity & Latency
    spinner.text = "Pinging RCT Platform API server...";
    const baseURL = configObj.baseURL ?? "http://localhost:8000";
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
      serverStatus = chalk.red("✘ FAIL (Server unreachable)");
    }

    spinner.stop();

    // Compile diagnostics grid
    const lines = [
      `${chalk.bold("RCT CLI Engine:")}          v1.2.0`,
      `${chalk.bold("Node.js Environment:")}     ${nodeVer} — ${nodeStatus}`,
      `${chalk.bold("Config Validity:")}        ${configStatus}`,
      `${chalk.bold("Workspace Cache:")}        ${dbStatus}`,
      `${chalk.bold("FastAPI Backend Connection:")}  ${serverStatus}`,
      "",
    ];

    const isHealthy = major >= 16 && (configValid || !configExists) && serverStatus.includes("✔ PASS");

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

    console.log(
      boxen(lines.join("\n"), {
        padding: { top: 1, bottom: 1, left: 2, right: 2 },
        margin: { top: 0, bottom: 1, left: 0, right: 0 },
        borderStyle: "round",
        borderColor: isHealthy ? "green" : "red",
        title: "RCT Platform — Diagnostic Preflight Report",
        titleAlignment: "left",
      })
    );

    if (!isHealthy) {
      process.exit(1);
    }
  });
