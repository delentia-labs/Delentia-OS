/**
 * Helper utilities for terminal text alignment and visual spacing.
 */

/**
 * Strips all ANSI escape sequences from a string to compute its visual length accurately.
 */
export function stripAnsi(text: string): string {
  return text.replace(
    /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g,
    ""
  );
}

/**
 * Perfectly centers a multi-line string block within the terminal viewport width.
 */
export function centerText(text: string, width = process.stdout.columns || 80): string {
  return text
    .split("\n")
    .map((line) => {
      const cleanLine = stripAnsi(line);
      const paddingLength = Math.max(0, Math.floor((width - cleanLine.length) / 2));
      return " ".repeat(paddingLength) + line;
    })
    .join("\n");
}
