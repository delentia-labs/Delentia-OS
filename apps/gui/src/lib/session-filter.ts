/**
 * Sessions that never reached a model (Round 112B, criteria R11).
 *
 * Every episode is recorded, as it should be: the record is the product. But a computer with no model yet fills the list with attempts that say nothing about what the agent did, and the Architect's first
 * install showed it. These are hidden by default behind a visible count and a switch. Nothing is deleted, changed or left out of the audit record: this only chooses what the list shows first.
 * Pure (no React, no network) so a plain node test checks it.
 */
export const NO_MODEL_REASONS: readonly string[] = ["model_not_running", "llm_error"];

export interface SessionLike { id: number; stopped_reason?: string | null }

export function isNoModelAttempt(reason: string | null | undefined): boolean {
  return NO_MODEL_REASONS.includes(String(reason ?? ""));
}

/** `selectedId` stays visible even when hidden, so a link to one session never shows an empty list. */
export function splitSessions<T extends SessionLike>(sessions: readonly T[], showAll: boolean, selectedId: number | null = null): { visible: T[]; hiddenCount: number } {
  if (showAll) return { visible: [...sessions], hiddenCount: 0 };
  const visible = sessions.filter((s) => !isNoModelAttempt(s.stopped_reason) || s.id === selectedId);
  return { visible, hiddenCount: sessions.length - visible.length };
}

export function hiddenLabel(count: number, showAll: boolean, lang: "th" | "en"): string {
  const th = lang === "th";
  if (showAll) return th ? "ซ่อนรอบที่เรียกโมเดลไม่ได้" : "Hide attempts where no model could be reached";
  return th ? `แสดงอีก ${count} รอบที่เรียกโมเดลไม่ได้` : `Show ${count} more attempt${count === 1 ? "" : "s"} where no model could be reached`;
}
