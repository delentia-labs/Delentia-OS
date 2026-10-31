import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DeskShell } from "@/components/desk/Shell";
import "./fonts.css";

// Round 96: three roles, chosen by the Architect from the specimen page.
//   Prompt          Thai (and the Latin letters inside Thai text): the interface.
//   JetBrains Mono  English, numbers, code, terminal output, navigation, data.
//   Sarabun         documents the system writes for a person to read at length
//                   (answers, statute passages, reports): class "desk-doc".
// JetBrains Mono has no Thai letters, so Thai inside a mono block falls back to Prompt.
// The three families come from src/app/fonts.css (generated from the @fontsource packages, so the build needs no network); the variables are set in globals.css.

export const metadata: Metadata = {
  title: "Delentia Desk",
  description: "Delentia agent runtime: governed chat, sessions, approvals and audit",
  icons: { icon: "/delentia-mark.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th" suppressHydrationWarning>
      <body className="antialiased" style={{ background: "var(--dl-ink)" }}>
        <DeskShell>{children}</DeskShell>
        <CommandPalette />
      </body>
    </html>
  );
}
