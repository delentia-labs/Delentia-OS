"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Lang = "th" | "en";

// Navigation and shared wording. Page bodies keep the runtime's own terms
// (FDIA, RCT-7, JITNA) untranslated, the way the Architect writes them.
const DICT = {
  status: { en: "Status", th: "สถานะ" },
  chat: { en: "Chat", th: "แชท" },
  sessions: { en: "Sessions", th: "เซสชัน" },
  approvals: { en: "Approvals", th: "อนุมัติ" },
  audit: { en: "Audit", th: "Audit" },
  models: { en: "Models", th: "โมเดล" },
  skills: { en: "Skills", th: "สกิล" },
  tools: { en: "Tools", th: "เครื่องมือ" },
  cron: { en: "Cron", th: "งานตามเวลา" },
  channels: { en: "Channels", th: "ช่องทาง" },
  experiments: { en: "Experiments", th: "การทดลอง" },
  labs: { en: "Labs", th: "Labs" },
  settings: { en: "Settings", th: "ตั้งค่า" },
  system: { en: "System", th: "ระบบ" },
  api_up: { en: "API up", th: "API ทำงาน" },
  api_down: { en: "API unreachable", th: "ต่อ API ไม่ได้" },
  daemon: { en: "Daemon", th: "Daemon" },
  running: { en: "running", th: "ทำงาน" },
  stopped: { en: "stopped", th: "หยุด" },
  pending: { en: "pending", th: "รออนุมัติ" },
  chain: { en: "Audit chain", th: "Audit chain" },
  verified: { en: "verified", th: "ตรวจผ่าน" },
  broken: { en: "BROKEN", th: "เสียหาย" },
  not_checked: { en: "not checked yet", th: "ยังไม่ได้ตรวจ" },
  new_chat: { en: "New chat", th: "แชทใหม่" },
  loading: { en: "Loading", th: "กำลังโหลด" },
  retry: { en: "Retry", th: "ลองใหม่" },
} as const;

export type DictKey = keyof typeof DICT;

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: DictKey) => string };
const LangContext = createContext<Ctx>({ lang: "th", setLang: () => {}, t: (k) => DICT[k].th });

const STORAGE_KEY = "delentia-desk-lang";

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("th");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "en" || saved === "th") setLangState(saved);
    } catch {
      /* storage blocked: keep Thai */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* storage blocked */
    }
  }, []);

  const t = useCallback((k: DictKey) => DICT[k][lang], [lang]);
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export const useLang = () => useContext(LangContext);
