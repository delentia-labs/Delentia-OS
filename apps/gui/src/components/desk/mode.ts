"use client";

import { useEffect, useState } from "react";
import { parseMode, type DeskMode } from "@/lib/nav-model";

export const MODE_KEY = "delentia_desk_mode";
export const MODE_EVENT = "delentia-desk-mode";

/** The Simple / Advanced choice the person made in the sidebar. Read after hydration (the first paint is Simple, the default), and kept in step when the sidebar changes it. */
export function useDeskMode(): DeskMode {
  const [mode, setMode] = useState<DeskMode>("simple");
  useEffect(() => {
    const read = () => {
      try { setMode(parseMode(window.localStorage.getItem(MODE_KEY))); } catch { setMode("simple"); }
    };
    read();
    window.addEventListener(MODE_EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(MODE_EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, []);
  return mode;
}
