import { Command } from "commander";
import chalk from "chalk";
import { computeFDIA, meetsThreshold } from "../../fdia";
import { showBanner } from "../ui/banner";
import { riskBadge } from "../ui/badge";

export const fdiaCommand = new Command("fdia")
  .description(
    "Compute the FDIA constitutional score offline (no server required)",
  )
  .argument("<d>", "Delta — intent drift score (0–1)")
  .argument("<i>", "Identity confidence score (0–1)")
  .argument("<a>", "Approval multiplier (0 = blocked, 1 = approved)")
  .option("-g, --gate <value>", "Minimum FDIA threshold to pass", "0.75")
  .option("--no-banner", "Skip the banner")
  .action(
    async (dStr: string, iStr: string, aStr: string, opts: Record<string, unknown>) => {
      const { default: boxen } = await import("boxen");

      if (opts["banner"] !== false) showBanner();

      const d = parseFloat(dStr);
      const i = parseFloat(iStr);
      const a = parseFloat(aStr);
      const gate = parseFloat(opts["gate"] as string);

      if ([d, i, a, gate].some((n) => isNaN(n))) {
        console.error(chalk.red("  Error: All arguments must be numeric values.\n"));
        process.exit(1);
      }

      const result = computeFDIA(d, i, a);
      const passes = meetsThreshold(result, gate);

      const lines = [
        `${chalk.bold("Formula:")}     ${chalk.white("F = D")}${chalk.white("ᴵ")} ${chalk.white("× A")}`,
        `${chalk.bold("Inputs:")}      D = ${chalk.cyan(d.toFixed(4))}  I = ${chalk.cyan(i.toFixed(4))}  A = ${chalk.cyan(a.toFixed(4))}`,
        ``,
        `${chalk.bold("F Score:")}     ${result.isBlocked ? chalk.red("BLOCKED (A=0)") : chalk.magenta(result.f.toFixed(6))}`,
        `${chalk.bold("Risk Level:")}  ${riskBadge(result.riskLevel)}`,
        `${chalk.bold("Gate:")}        ${chalk.yellow(gate.toFixed(4))} — ${passes ? chalk.green("PASS \u2714") : chalk.red("FAIL \u2718")}`,
      ];

      const borderColor = passes ? "green" : "red";
      const title = passes ? "FDIA — Constitutional Gate PASSED" : "FDIA — Constitutional Gate FAILED";

      console.log(
        boxen(lines.join("\n"), {
          padding: { top: 1, bottom: 1, left: 2, right: 2 },
          margin: { top: 0, bottom: 1, left: 0, right: 0 },
          borderStyle: "round",
          borderColor,
          title,
          titleAlignment: "center",
        }),
      );
    },
  );
