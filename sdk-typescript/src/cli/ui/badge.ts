import chalk from "chalk";

export const badge = {
  success: (t: string) => chalk.bgGreen.bold.black(` ${t} `),
  error: (t: string) => chalk.bgRed.bold.white(` ${t} `),
  warn: (t: string) => chalk.bgYellow.bold.black(` ${t} `),
  info: (t: string) => chalk.bgCyan.bold.black(` ${t} `),
  low: () => chalk.bgGreen.bold.black(" LOW "),
  structural: () => chalk.bgYellow.bold.black(" STRUCTURAL "),
  systemic: () => chalk.bgRed.bold.white(" SYSTEMIC "),
  approved: () => chalk.bgGreen.bold.black(" APPROVED "),
  rejected: () => chalk.bgRed.bold.white(" REJECTED "),
  pending: () => chalk.bgYellow.bold.black(" PENDING "),
};

export function riskBadge(risk: string): string {
  switch (risk?.toUpperCase()) {
    case "LOW":
      return badge.low();
    case "STRUCTURAL":
      return badge.structural();
    case "SYSTEMIC":
      return badge.systemic();
    default:
      return badge.info(risk ?? "UNKNOWN");
  }
}

export function decisionBadge(decision: string): string {
  switch (decision?.toLowerCase()) {
    case "approve":
      return badge.approved();
    case "reject":
      return badge.rejected();
    default:
      return badge.pending();
  }
}
