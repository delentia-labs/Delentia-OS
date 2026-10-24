import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DeskShell } from "@/components/desk/Shell";
import { JetBrains_Mono, Prompt, Sarabun } from "next/font/google";

// Round 96: three roles, chosen by the Architect from the specimen page.
//   Prompt          Thai (and the Latin letters inside Thai text): the interface.
//   JetBrains Mono  English, numbers, code, terminal output, navigation, data.
//   Sarabun         documents the system writes for a person to read at length
//                   (answers, statute passages, reports): class "desk-doc".
// JetBrains Mono has no Thai letters, so Thai inside a mono block falls back to Prompt.
const fontMono = JetBrains_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-mono-en",
  display: "swap",
});

const fontThai = Prompt({
  weight: ["300", "400", "500", "600"],
  subsets: ["thai", "latin"],
  variable: "--font-th",
  display: "swap",
});

const fontDoc = Sarabun({
  weight: ["400", "500", "600"],
  subsets: ["thai", "latin"],
  variable: "--font-doc",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Delentia Desk",
  description: "Delentia agent runtime: governed chat, sessions, approvals and audit",
  icons: { icon: "/delentia-mark.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th" suppressHydrationWarning>
      <body className={`${fontMono.variable} ${fontThai.variable} ${fontDoc.variable} antialiased`} style={{ background: "var(--dl-ink)" }}>
        <DeskShell>{children}</DeskShell>
        <CommandPalette />
      </body>
    </html>
  );
}
