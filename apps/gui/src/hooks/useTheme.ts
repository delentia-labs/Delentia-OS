"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeName =
  | "delentia-brand"
  | "dark-modern-default"
  | "powershell-ise"
  | "quiet-light"
  | "solarized-light"
  | "tokyo-night-light"
  | "abyss"
  | "dark-visual-studio"
  | "dark-modern"
  | "default-dark-plus"
  | "kimbie-dark"
  | "monokai"
  | "monokai-dimmed"
  | "red"
  | "solarized-dark"
  | "synthwave-84"
  | "tokyo-night"
  | "tokyo-night-storm"
  | "tomorrow-night-blue"
  | "dark-high-contrast"
  | "light-high-contrast";

export type ColorMode = "light" | "dark";

interface ThemeState {
  theme: ThemeName;
  colorMode: ColorMode;
  setTheme: (theme: ThemeName) => void;
  setColorMode: (mode: ColorMode) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "delentia-brand",
      colorMode: "dark",
      setTheme: (theme) => {
        // Automatically determine default mode based on the theme selection
        const lightThemes: ThemeName[] = [
          "powershell-ise",
          "quiet-light",
          "solarized-light",
          "tokyo-night-light",
          "light-high-contrast",
        ];
        const colorMode = lightThemes.includes(theme) ? "light" : "dark";
        set({ theme, colorMode });
      },
      setColorMode: (colorMode) => set({ colorMode }),
    }),
    {
      name: "delentia-theme-storage",
    }
  )
);
