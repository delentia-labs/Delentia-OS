"use client";

import { useEffect, useState } from "react";
import { useThemeStore } from "@/hooks/useTheme";
import { usePathname } from "next/navigation";

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { theme, colorMode } = useThemeStore();
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const html = document.documentElement;

    // Filter out previous theme classes and color modes
    const themeClasses = Array.from(html.classList).filter(
      (c) => c.startsWith("theme-") || c === "light" || c === "dark"
    );
    themeClasses.forEach((c) => html.classList.remove(c));

    // Add current classes
    html.classList.add(`theme-${theme}`);
    html.classList.add(colorMode);

    // Also update body color-scheme
    html.style.colorScheme = colorMode;
  }, [theme, colorMode, mounted, pathname]);

  // Prevent flash during loading by wrapping children
  return <>{children}</>;
}
