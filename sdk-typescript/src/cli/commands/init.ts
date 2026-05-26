import { Command } from "commander";
import chalk from "chalk";
import { writeFileSync, existsSync } from "fs";
import { join } from "path";
import { showBanner } from "../ui/banner";

const CLI_VERSION = "1.2.0";

interface RCTConfig {
  baseURL: string;
  userTier: string;
  region: string;
  fdiaGate: boolean;
  version: string;
  createdAt: string;
}

export const initCommand = new Command("init")
  .description("Initialize RCT Platform configuration interactively")
  .option("-f, --force", "Overwrite existing .rct.json")
  .action(async (opts: Record<string, unknown>) => {
    const { default: boxen } = await import("boxen");
    const { centerText } = await import("../ui/align");

    showBanner(CLI_VERSION);

    const configPath = join(process.cwd(), ".rct.json");

    if (existsSync(configPath) && !opts["force"]) {
      console.log(
        chalk.yellow("  .rct.json already exists. Use --force to overwrite.\n"),
      );
    }

    let config: RCTConfig;

    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { prompt } = require("enquirer") as {
        prompt: (
          questions: unknown[],
        ) => Promise<Record<string, string | boolean>>;
      };

      const answers = await prompt([
        {
          type: "select",
          name: "userTier",
          message: "Select your tier:",
          choices: [
            { name: "FREE", hint: "2 parallel agents · 4 HexaCore roles" },
            { name: "PRO", hint: "4 parallel agents · 6 HexaCore roles" },
            {
              name: "ENTERPRISE",
              hint: "8 parallel agents · full HexaCore · SYSTEMIC escalation",
            },
          ],
        },
        {
          type: "select",
          name: "region",
          message: "Select primary region:",
          choices: ["ASEAN", "GLOBAL", "US", "EU", "JP"],
        },
        {
          type: "confirm",
          name: "fdiaGate",
          message: "Enable FDIA Constitutional Gate?",
          initial: true,
        },
        {
          type: "input",
          name: "baseURL",
          message: "RCT Platform API endpoint:",
          initial: "http://localhost:8000",
        },
      ]);

      config = {
        baseURL: String(answers["baseURL"] ?? "http://localhost:8000"),
        userTier: String(answers["userTier"] ?? "FREE"),
        region: String(answers["region"] ?? "GLOBAL"),
        fdiaGate: Boolean(answers["fdiaGate"] ?? true),
        version: CLI_VERSION,
        createdAt: new Date().toISOString(),
      };
    } catch {
      // enquirer not installed or user cancelled (Ctrl+C)
      console.log(chalk.yellow("\n  Using default configuration...\n"));
      config = {
        baseURL: "http://localhost:8000",
        userTier: "FREE",
        region: "GLOBAL",
        fdiaGate: true,
        version: CLI_VERSION,
        createdAt: new Date().toISOString(),
      };
    }

    writeFileSync(configPath, JSON.stringify(config, null, 2), "utf-8");

    const lines = [
      chalk.bold("Configuration saved!"),
      "",
      `${chalk.bold("Tier:")}        ${chalk.cyan(config.userTier)}`,
      `${chalk.bold("Region:")}      ${chalk.cyan(config.region)}`,
      `${chalk.bold("API:")}         ${chalk.cyan(config.baseURL)}`,
      `${chalk.bold("FDIA Gate:")}   ${config.fdiaGate ? chalk.green("Enabled") : chalk.yellow("Disabled")}`,
      "",
      chalk.gray(`Saved to: ${configPath}`),
      "",
      chalk.bold("Next steps:"),
      `  ${chalk.cyan("rct status")}${chalk.gray("             — check server connection")}`,
      `  ${chalk.cyan('rct compile "your intent"')}${chalk.gray("  — compile an intent")}`,
    ];

    const outputBox = boxen(lines.join("\n"), {
      padding: { top: 1, bottom: 1, left: 2, right: 2 },
      margin: { top: 0, bottom: 1, left: 0, right: 0 },
      borderStyle: "round",
      borderColor: "green",
      title: "RCT Platform Initialized",
      titleAlignment: "left",
    });

    const terminalWidth = process.stdout.columns || 80;
    console.log(centerText(outputBox, terminalWidth));
  });
