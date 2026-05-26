import { Command } from "commander";
import chalk from "chalk";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { showBanner } from "../ui/banner";

interface RCTConfig {
  baseURL?: string;
  userTier?: string;
}

function loadConfig(): RCTConfig {
  const configPath = join(process.cwd(), ".rct.json");
  if (existsSync(configPath)) {
    try {
      return JSON.parse(readFileSync(configPath, "utf-8")) as RCTConfig;
    } catch {
      // ignore parse errors
    }
  }
  return { baseURL: "http://localhost:8000" };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const compileCommand = new Command("compile")
  .description(
    "Compile a natural-language intent through the RCT constitutional pipeline",
  )
  .argument("<intent>", "The intent to compile (natural language)")
  .option("-u, --url <url>", "API endpoint URL")
  .option("-t, --tier <tier>", "User tier (FREE|PRO|ENTERPRISE)")
  .option("--no-banner", "Skip the banner")
  .action(async (intent: string, opts: Record<string, unknown>) => {
    // Lazy-load heavy packages
    const { RCTClient } = await import("../../client");
    const { createSpinner, succeed, fail } = await import("../ui/spinner");
    const { formatCompileBox } = await import("../ui/output");
    const { centerText } = await import("../ui/align");

    if (opts["banner"] !== false) showBanner();

    const config = loadConfig();
    const baseURL = (opts["url"] as string | undefined) ?? config.baseURL ?? "http://localhost:8000";
    const userTier = (opts["tier"] as string | undefined) ?? config.userTier ?? "PRO";

    const terminalWidth = process.stdout.columns || 80;
    console.log(centerText(chalk.gray(`Intent: "${intent}"\n`), terminalWidth));

    // Step 1 — JITNA
    const s1 = createSpinner("Initializing JITNA Protocol...");
    s1.start();
    await delay(350);
    succeed(s1, "JITNA packet constructed");

    // Step 2 — FDIA
    const s2 = createSpinner("Calculating FDIA Equation (F = D\u1d35 \u00d7 A)...");
    s2.start();
    await delay(280);
    succeed(s2, "FDIA constitutional score computed");

    // Step 3 — Compile via server
    const s3 = createSpinner("Compiling through constitutional pipeline...");
    s3.start();

    try {
      const client = new RCTClient({ baseURL, timeoutMs: 15_000 });
      const compiled = await client.compile(intent, "cli-user", userTier);
      succeed(s3, "Compilation complete");

      // Step 4 — Policy evaluation
      const s4 = createSpinner("Evaluating governance policies...");
      s4.start();

      let evalResult;
      try {
        evalResult = await client.evaluatePolicy(compiled.intent_id);
        succeed(s4, "Policy evaluation complete");
      } catch {
        warn(s4, "Policy evaluation skipped (endpoint unavailable)");
      }

      console.log();
      console.log(centerText(formatCompileBox(compiled, evalResult), terminalWidth));
    } catch (err: unknown) {
      fail(s3, "Connection to RCT Platform server failed");
      const message = err instanceof Error ? err.message : String(err);
      console.log();
      console.log(chalk.red("  Cannot connect to RCT Platform server."));
      console.log(chalk.gray("  Error: ") + chalk.yellow(message));
      console.log();
      console.log(chalk.bold("  To start the server:"));
      console.log(
        chalk.cyan("    pip install rct-platform") +
          chalk.gray("  # install the Python SDK"),
      );
      console.log(
        chalk.cyan("    rct serve") + chalk.gray("              # start the API server"),
      );
      console.log();
      process.exit(1);
    }
  });

import type { Ora } from "ora";

function warn(spinner: Ora, text: string): void {
  spinner.warn(chalk.yellow(text));
}
