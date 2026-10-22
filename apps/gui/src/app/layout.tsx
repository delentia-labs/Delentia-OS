import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DeskShell } from "@/components/desk/Shell";
// Installed font stacks keep production builds independent of Google Fonts.
// No font binary is downloaded or redistributed by this layout.

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
