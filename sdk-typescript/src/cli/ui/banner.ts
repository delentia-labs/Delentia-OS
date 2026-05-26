import chalk from "chalk";

const LOGO_LINES = [
  "  ██████╗  ██████╗████████╗",
  "  ██╔══██╗██╔════╝╚══██╔══╝",
  "  ██████╔╝██║        ██║   ",
  "  ██╔══██╗██║        ██║   ",
  "  ██║  ██║╚██████╗   ██║   ",
  "  ╚═╝  ╚═╝ ╚═════╝   ╚═╝  ",
];

const PALETTE = [
  chalk.cyan,
  chalk.blue,
  chalk.blue,
  chalk.magenta,
  chalk.magenta,
  chalk.hex("#7b2ff7"),
];

export function showBanner(version = "1.2.0"): void {
  console.log();
  LOGO_LINES.forEach((line, i) => {
    const colorFn = PALETTE[i] ?? chalk.magenta;
    process.stdout.write(colorFn(line) + "\n");
  });
  console.log(
    chalk.cyan("  Intent-Centric AI Operating System  ") +
      chalk.bold.white(`v${version}`) +
      "\n",
  );
}
