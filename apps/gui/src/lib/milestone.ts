// The stage label that sits beside the version (docs/release/VERSIONING_POLICY.md): "Public Technical Preview 0.1" / "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1".
// It is a label for what has been opened to whom, never a version number. The server (GET /health) reports it only after the owner has declared it, so before that this code shows nothing.

export interface Milestone {
  id: string;
  number: string;
  release_level: string;
  name_en: string;
  name_th: string;
}

export type Lang = "th" | "en";

export interface MilestoneLine {
  /** the label in the language of the interface */
  primary: string;
  /** the same label in the other language (shown as a tooltip and as a second line where there is room) */
  secondary: string;
  /** both languages in one line, English first */
  both: string;
  /** the release level, e.g. L1 */
  level: string;
}

function validText(v: unknown): v is string {
  return typeof v === "string" && v.trim().length > 0;
}

/** Null when the server reports no milestone, or an incomplete one: a half-filled label is not shown. */
export function milestoneLine(m: Partial<Milestone> | null | undefined, lang: Lang): MilestoneLine | null {
  if (!m || !validText(m.name_en) || !validText(m.name_th) || !validText(m.number)) return null;
  const en = `${m.name_en.trim()} ${m.number.trim()}`;
  const th = `${m.name_th.trim()} ${m.number.trim()}`;
  return { primary: lang === "th" ? th : en, secondary: lang === "th" ? en : th, both: `${en} / ${th}`, level: validText(m.release_level) ? m.release_level.trim() : "" };
}
