import { Command } from "commander";
import chalk from "chalk";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { showBanner } from "../ui/banner";

interface RCTConfig {
  baseURL?: string;
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

export const statusCommand = new Command("status")
  .description("Show RCT Platform server health and system metrics")
  .option("-u, --url <url>", "API endpoint URL")
  .option("--no-banner", "Skip the banner")
  .action(async (opts: Record<string, unknown>) => {
    // Lazy-load heavy packages
    const { RCTClient } = await import("../../client");
    const { createSpinner, succeed, fail } = await import("../ui/spinner");
    const { formatMetricsBox } = await import("../ui/output");

    if (opts["banner"] !== false) showBanner();

    const config = loadConfig();
    const baseURL =
      (opts["url"] as string | undefined) ??
      config.baseURL ??
      "http://localhost:8000";

    console.log(chalk.gray(`  Connecting to: ${baseURL}\n`));

    const spinner = createSpinner("Fetching system metrics...");
    spinner.start();

    try {
      const client = new RCTClient({ baseURL, timeoutMs: 5_000 });
      const metrics = await client.getMetrics();
      succeed(spinner, "Connected — server is healthy");
      console.log();
      console.log(formatMetricsBox(metrics));
    } catch (err: unknown) {
      fail(spinner, "Connection failed");
      const message = err instanceof Error ? err.message : String(err);
      console.log();
      console.log(chalk.red("  Cannot reach RCT Platform server."));
      console.log(chalk.gray("  Error: ") + chalk.yellow(message));
      console.log();
      console.log(chalk.bold("  To start the server:"));
      console.log(
        chalk.cyan("    pip install rct-platform") +
          chalk.gray("  # install the Python SDK"),
      );
      console.log(
        chalk.cyan("    rct serve") +
          chalk.gray("              # start the API server on :8000"),
      );
      console.log();
      process.exit(1);
    }
  });
