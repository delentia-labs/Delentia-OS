import boxen from "boxen";
import chalk from "chalk";
import type {
  CompileResponse,
  PolicyEvalResponse,
  MetricsResponse,
} from "../../client";
import { riskBadge, decisionBadge } from "./badge";

export function formatCompileBox(
  compile: CompileResponse,
  evalResult?: PolicyEvalResponse,
): string {
  const lines: string[] = [
    `${chalk.bold("Intent ID:")}   ${chalk.cyan(compile.intent_id)}`,
    `${chalk.bold("Risk Level:")}  ${riskBadge(compile.risk_profile)}`,
    `${chalk.bold("Decision:")}    ${evalResult ? decisionBadge(evalResult.decision) : chalk.gray("—")}`,
    `${chalk.bold("Latency:")}     ${chalk.yellow(compile.compilation_time_ms + "ms")}`,
  ];

  if (evalResult?.governance_score !== undefined) {
    lines.push(
      `${chalk.bold("Gov Score:")}   ${chalk.magenta((evalResult.governance_score * 100).toFixed(1) + "%")}`,
    );
  }

  if (compile.warnings.length > 0) {
    lines.push("");
    compile.warnings.forEach((w) => lines.push(chalk.yellow(`  ⚠  ${w}`)));
  }

  if (compile.errors.length > 0) {
    lines.push("");
    compile.errors.forEach((e) => lines.push(chalk.red(`  ✘  ${e}`)));
  }

  return boxen(lines.join("\n"), {
    padding: { top: 1, bottom: 1, left: 2, right: 2 },
    margin: { top: 0, bottom: 1, left: 0, right: 0 },
    borderStyle: "round",
    borderColor: compile.success ? "green" : "red",
    title: compile.success ? "Compiled Successfully" : "Compilation Failed",
    titleAlignment: "left",
  });
}

export function formatMetricsBox(m: MetricsResponse): string {
  const failColor = m.total_failures > 0 ? chalk.red : chalk.green;
  const lines = [
    `${chalk.bold("Total Intents:")}          ${chalk.cyan(m.total_intents)}`,
    `${chalk.bold("Compilations:")}           ${chalk.cyan(m.total_compilations)}`,
    `${chalk.bold("Policy Evaluations:")}     ${chalk.cyan(m.total_policy_evaluations)}`,
    `${chalk.bold("Executions:")}             ${chalk.cyan(m.total_executions)}`,
    `${chalk.bold("Failures:")}               ${failColor(m.total_failures)}`,
    ``,
    `${chalk.bold("Avg Compile Latency:")}    ${chalk.yellow(m.avg_compilation_latency_ms.toFixed(1) + "ms")}`,
    `${chalk.bold("Approvals Required:")}     ${chalk.yellow(m.approvals_required)}`,
    `${chalk.bold("Approvals Granted:")}      ${chalk.green(m.approvals_granted)}`,
    `${chalk.bold("Audit Trail Entries:")}    ${chalk.cyan(m.audit_trail_entries)}`,
  ];

  return boxen(lines.join("\n"), {
    padding: { top: 1, bottom: 1, left: 2, right: 2 },
    margin: { top: 0, bottom: 1, left: 0, right: 0 },
    borderStyle: "round",
    borderColor: "cyan",
    title: "RCT Platform — System Metrics",
    titleAlignment: "center",
  });
}
