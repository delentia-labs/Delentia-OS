import ora from "ora";
import type { Ora } from "ora";
import chalk from "chalk";

export function createSpinner(text: string): Ora {
  return ora({
    text: chalk.cyan(text),
    spinner: "dots",
    color: "cyan",
  });
}

export function succeed(spinner: Ora, text: string): void {
  spinner.succeed(chalk.green(text));
}

export function fail(spinner: Ora, text: string): void {
  spinner.fail(chalk.red(text));
}

export function warn(spinner: Ora, text: string): void {
  spinner.warn(chalk.yellow(text));
}
