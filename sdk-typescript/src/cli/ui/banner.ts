import chalk from "chalk";
import { centerText } from "./align";

const LOGO_LINES = [
  "██████╗  ██████╗████████╗",
  "██╔══██╗██╔════╝╚══██╔══╝",
  "██████╔╝██║        ██║   ",
  "██╔══██╗██║        ██║   ",
  "██║  ██║╚██████╗   ██║   ",
  "╚═╝  ╚═╝ ╚═════╝   ╚═╝  ",
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
  const terminalWidth = process.stdout.columns || 80;
  console.log();
  
  // Format each line with color and center it
  LOGO_LINES.forEach((line, i) => {
    const colorFn = PALETTE[i] ?? chalk.magenta;
    const coloredLine = colorFn(line);
    console.log(centerText(coloredLine, terminalWidth));
  });

  const subtitle =
    chalk.cyan("Intent-Centric AI Operating System  ") +
    chalk.bold.white(`v${version}`);
  console.log(centerText(subtitle, terminalWidth) + "\n");
}
