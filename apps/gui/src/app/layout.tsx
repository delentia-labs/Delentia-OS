import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DeskShell } from "@/components/desk/Shell";
import { IBM_Plex_Mono, IBM_Plex_Sans_Thai } from "next/font/google";

// Round 50 redesign: one family, two cuts. Plex Mono carries the terminal,
// navigation and data; Plex Sans Thai carries explanations in Thai and English.
const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-mono",
  display: "swap",
});

const plexThai = IBM_Plex_Sans_Thai({
  weight: ["400", "500", "600"],
  subsets: ["thai", "latin"],
  variable: "--font-plex-thai",
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
      <body className={`${plexMono.variable} ${plexThai.variable} antialiased`} style={{ background: "var(--dl-ink)" }}>
        <DeskShell>{children}</DeskShell>
        <CommandPalette />
      </body>
    </html>
  );
}
