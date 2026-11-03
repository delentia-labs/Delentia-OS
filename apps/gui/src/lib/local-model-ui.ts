/**
 * The words and decisions of the local-model panel, with no React and no network, so plain node can test them (apps/gui/scripts/local-model-ui.test.mjs).
 * Every sentence here is about what Delentia knows: a fit is an ESTIMATE, "measured" means this project measured that model, and a local model is for trying Delentia, not for real work.
 */
import type { LocalModelRow, LocalModelsView } from "@/lib/desk-api";

export type Lang = "th" | "en";

export const TRY_ONLY = {
  en: "Every local model here is for trying Delentia on your own computer. Small models are slow and often choose the wrong tool; for real work an online model is usually needed.",
  th: "โมเดลในเครื่องทุกตัวในรายการนี้มีไว้ลองใช้ Delentia บนเครื่องของคุณเอง โมเดลเล็กช้าและมักเลือกเครื่องมือผิด งานจริงมักต้องใช้โมเดลออนไลน์",
};

export type StepAdvice = { title: string; text: string; action: "open_download" | "start" | "pick" | "none" };

/** What to tell the person, and which single button to offer first, for the state of Ollama on this computer. */
export function ollamaAdvice(state: LocalModelsView["ollama"]["state"] | undefined, hasModels: boolean, lang: Lang): StepAdvice {
  const th = lang === "th";
  if (state === "not_installed") {
    return { action: "open_download",
      title: th ? "ยังไม่พบ Ollama บนเครื่องนี้" : "Ollama was not found on this computer",
      text: th ? "Ollama คือโปรแกรมฟรีที่รันโมเดลบนเครื่องคุณ กดปุ่มเพื่อเปิดหน้าดาวน์โหลดทางการ ติดตั้งแล้วกลับมากด “ตรวจอีกครั้ง” (Delentia ไม่ดาวน์โหลดหรือรันตัวติดตั้งให้เอง)"
        : "Ollama is a free program that runs models on your computer. Press the button to open its official download page, install it, then come back and press “Check again”. (Delentia does not download or run an installer by itself.)" };
  }
  if (state === "installed_not_running") {
    return { action: "start", title: th ? "Ollama ติดตั้งแล้วแต่ยังไม่ทำงาน" : "Ollama is installed but not running",
      text: th ? "กดปุ่มเพื่อเริ่มโปรแกรม ใช้เวลาไม่กี่วินาที" : "Press the button to start it. It takes a few seconds." };
  }
  if (state === "running") {
    return hasModels
      ? { action: "pick", title: th ? "Ollama ทำงานอยู่ และมีโมเดลในเครื่อง" : "Ollama is running and has models", text: th ? "เลือกตัวที่ใช้ได้ด้านล่าง หรือดาวน์โหลดตัวอื่นเพิ่ม" : "Choose one below, or download another." }
      : { action: "pick", title: th ? "Ollama ทำงานอยู่ แต่ยังไม่มีโมเดล" : "Ollama is running but has no model yet", text: th ? "เลือกโมเดลด้านล่างแล้วกดดาวน์โหลด ไม่ต้องใช้เทอร์มินัล" : "Pick a model below and press download. No terminal needed." };
  }
  return { action: "none", title: th ? "กำลังตรวจ Ollama…" : "Checking Ollama…", text: "" };
}

export function formatGb(gb: number): string {
  return gb < 10 ? `${gb.toFixed(1)} GB` : `${Math.round(gb)} GB`;
}

/** Whether a model probably fits this computer, in words, always saying it is an estimate. */
export function fitText(row: LocalModelRow, ramGb: number | null, lang: Lang): { tone: "ok" | "warn" | "muted"; text: string } {
  const th = lang === "th";
  if (ramGb === null || row.fits === null) {
    return { tone: "muted", text: th ? "ไม่ทราบแรมของเครื่องนี้ จึงประเมินไม่ได้" : "This computer's memory is not known, so no estimate." };
  }
  return row.fits
    ? { tone: "ok", text: th ? `น่าจะพอดีกับแรม ${ramGb} GB (ประเมินว่าใช้ราว ${formatGb(row.estimated_memory_gb)}, ยังไม่ได้วัด)` : `Probably fits ${ramGb} GB of memory (estimated ${formatGb(row.estimated_memory_gb)}, not measured)` }
    : { tone: "warn", text: th ? `อาจไม่พอกับแรม ${ramGb} GB (ประเมินว่าต้องใช้ราว ${formatGb(row.estimated_memory_gb)}) เครื่องอาจช้ามากหรือค้าง` : `May not fit ${ramGb} GB of memory (estimated ${formatGb(row.estimated_memory_gb)}); the computer may become very slow or freeze.` };
}

export function evidenceText(row: LocalModelRow, lang: Lang): string {
  const th = lang === "th";
  if (row.measured_here) return th ? `วัดโดยโครงการนี้: ${row.measured_th}` : `Measured by this project: ${row.measured_en}`;
  return th ? "โครงการนี้ยังไม่ได้วัดโมเดลนี้" : "This project has not measured this model.";
}

export function pullText(p: { status: string; percent: number | null; message: string }, lang: Lang): string {
  const th = lang === "th";
  switch (p.status) {
    case "downloading": return p.percent === null ? (th ? "กำลังเตรียมดาวน์โหลด…" : "Preparing the download…") : (th ? `กำลังดาวน์โหลด ${p.percent.toFixed(0)}%` : `Downloading ${p.percent.toFixed(0)}%`);
    case "done": return th ? "ดาวน์โหลดเสร็จแล้ว" : "Download finished";
    case "cancelled": return th ? "ยกเลิกการดาวน์โหลดแล้ว" : "Download cancelled";
    case "failed": return (th ? "ดาวน์โหลดไม่สำเร็จ: " : "The download failed: ") + p.message;
    default: return "";
  }
}

/** The rows to show: those that probably fit first, then the rest, each group in the catalog's own order. Nothing is ordered by claimed quality. */
export function orderRows(rows: LocalModelRow[]): LocalModelRow[] {
  const rank = (r: LocalModelRow) => (r.fits === true ? 0 : r.fits === null ? 1 : 2);
  return rows.map((r, i) => ({ r, i })).sort((a, b) => rank(a.r) - rank(b.r) || a.i - b.i).map((x) => x.r);
}
