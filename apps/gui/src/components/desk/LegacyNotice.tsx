"use client";

import { usePathname } from "next/navigation";
import { useLang } from "./i18n";

type Kind = "real" | "scripted" | "game" | "static" | "notbuilt";

// What each earlier page actually is, checked against its backend on 2026-09-30.
// These pages predate the Desk redesign and keep their old look until each one
// is rebuilt on real data.
const PAGES: Record<string, { kind: Kind; th: string; en: string }> = {
  "/memory": { kind: "real", en: "Real: shows the kernel's Delta memory ticks and can roll them back.", th: "ข้อมูลจริง: แสดง memory tick ของ Delta engine และย้อนกลับได้" },
  "/models": { kind: "real", en: "Real: talks to your local Ollama (list, pull, test). The Models page in the main menu chooses the agent's model.", th: "ข้อมูลจริง: คุยกับ Ollama บนเครื่องคุณ (ดูรายการ ดึงโมเดล ทดสอบ) ส่วนหน้า Models ในเมนูหลักใช้เลือกโมเดลของ agent" },
  "/monitor": { kind: "real", en: "Real health checks of the API and the reference services. FDIA history and drift appear only if the API reports them.", th: "เช็กสถานะจริงของ API และ service ตัวอย่าง ประวัติ FDIA และ drift จะแสดงต่อเมื่อ API รายงานมา" },
  "/profiler": { kind: "real", en: "Uses a real model to interview you and draft a product blueprint. Not part of the governed agent loop.", th: "ใช้โมเดลจริงสัมภาษณ์และร่าง blueprint ของผลิตภัณฑ์ ไม่อยู่ในวงจร agent ที่ถูกควบคุม" },
  "/billing": { kind: "real", en: "Generates a real PromptPay (EMVCo) QR payload. No payment is processed or verified.", th: "สร้าง QR PromptPay (EMVCo) จริง แต่ไม่ได้ประมวลผลหรือตรวจสอบการชำระเงิน" },
  "/workflow": { kind: "scripted", en: "Scripted demo: the team's outputs are fixed text, not model calls, and the \"seal\" is a hash, not a signature. Real subagents are not connected here yet.", th: "เดโมที่เขียนสคริปต์ไว้: ผลลัพธ์ของทีมเป็นข้อความตายตัว ไม่ได้เรียกโมเดล และ \"seal\" เป็นแค่ hash ไม่ใช่ลายเซ็น ยังไม่ได้ต่อกับ subagent จริง" },
  "/brains": { kind: "static", en: "Static placeholder: the adapter and VRAM figures are fixed values, not read from a GPU.", th: "ข้อมูลตายตัว: ตัวเลข adapter และ VRAM เป็นค่าคงที่ ไม่ได้อ่านจาก GPU" },
  "/brains/train": { kind: "scripted", en: "Simulation: the loss curve comes from a formula and no weights are trained.", th: "การจำลอง: กราฟ loss มาจากสูตร และไม่ได้ฝึกน้ำหนักโมเดลจริง" },
  "/ecosystem": { kind: "real", en: "Real only while an adapter registry runs on port 8090; otherwise it lists nothing.", th: "ใช้ได้จริงเมื่อมี adapter registry รันที่พอร์ต 8090 ถ้าไม่มีจะไม่แสดงรายการ" },
  "/discovery": { kind: "static", en: "A hand-picked reading list. Nothing here is fetched or scored.", th: "รายการอ่านที่คัดไว้เอง ไม่ได้ดึงหรือให้คะแนนจากที่ไหน" },
  "/sandbox": { kind: "game", en: "Game demo (Pelican Town NPC simulation). Not part of the agent runtime; VRAM and farm figures are simulated.", th: "เดโมเกม (จำลอง NPC ในเมือง Pelican) ไม่เกี่ยวกับ agent runtime ตัวเลข VRAM และฟาร์มเป็นค่าจำลอง" },
  "/enterprise": { kind: "notbuilt", en: "Not built. This page used to show a fixed compliance score and a made-up key; it no longer does.", th: "ยังไม่ได้สร้าง หน้านี้เคยแสดงคะแนน compliance ตายตัวและกุญแจที่แต่งขึ้น ตอนนี้เลิกแล้ว" },
};

const TONE: Record<Kind, string> = {
  real: "border-dl-fern/60 text-dl-muted",
  scripted: "border-dl-amber/60 text-dl-amber",
  game: "border-dl-amber/60 text-dl-amber",
  static: "border-dl-amber/60 text-dl-amber",
  notbuilt: "border-dl-rust/60 text-dl-rust",
};
const LABEL: Record<Kind, string> = {
  real: "Labs · earlier design", scripted: "Labs · simulated", game: "Labs · game demo",
  static: "Labs · static data", notbuilt: "Labs · not built",
};

/** One line above earlier pages saying what they really are. */
export function LegacyNotice() {
  const pathname = usePathname() || "";
  const { lang } = useLang();
  const info = PAGES[pathname];
  if (!info) return null;
  return (
    <div role="note" className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b bg-dl-panel px-6 py-2 text-[12px] leading-relaxed ${TONE[info.kind]}`}>
      <span className="desk-mono shrink-0">{LABEL[info.kind]}</span>
      <span className="min-w-0 max-w-[110ch]">{lang === "th" ? info.th : info.en}</span>
    </div>
  );
}
