#!/usr/bin/env node
import { Command } from "commander";
import { showBanner } from "./ui/banner";
import { compileCommand } from "./commands/compile";
import { statusCommand } from "./commands/status";
import { initCommand } from "./commands/init";
import { fdiaCommand } from "./commands/fdia";
import { doctorCommand } from "./commands/doctor";
import { memoryCommand } from "./commands/memory";

const VERSION = "1.3.0";

const program = new Command()
  .name("rct")
  .description("RCT Platform — Intent-Centric AI Operating System CLI")
  .version(VERSION, "-v, --version", "Output the current version")
  .helpOption("-h, --help", "Display help for command");

program.addCommand(compileCommand);
program.addCommand(statusCommand);
program.addCommand(initCommand);
program.addCommand(fdiaCommand);
program.addCommand(doctorCommand);
program.addCommand(memoryCommand);

// Show banner when invoked with no subcommand
if (process.argv.length <= 2) {
  showBanner(VERSION);
  program.outputHelp();
  process.exit(0);
}

program.parse(process.argv);
