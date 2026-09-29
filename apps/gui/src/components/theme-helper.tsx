"use client";

import { useEffect } from "react";
import { useThemeStore } from "@/hooks/useTheme";

export function ThemeHelper() {
  const { theme, colorMode } = useThemeStore();

  useEffect(() => {
    const body = document.body;
    if (!body) return;

    // Remove all previous theme classes
    const classes = Array.from(body.classList);
    for (const c of classes) {
      if (c.startsWith("theme-")) {
        body.classList.remove(c);
      }
    }

    // Add current theme class
    body.classList.add(`theme-${theme}`);

    // Manage document light/dark class
    const html = document.documentElement;
    if (colorMode === "dark") {
      html.classList.add("dark");
      html.classList.remove("light");
      html.style.colorScheme = "dark";
    } else {
      html.classList.add("light");
      html.classList.remove("dark");
      html.style.colorScheme = "light";
    }
  }, [theme, colorMode]);

  return null;
}
