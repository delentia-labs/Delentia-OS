import type { Metadata } from "next";
import "./globals.css";
import ThemeProvider from "@/components/ThemeProvider";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { TelemetryBar } from "@/components/ui/TelemetryBar";
import { Sidebar } from "@/components/ui/Sidebar";
import { Space_Grotesk, Kanit } from "next/font/google";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const kanit = Kanit({
  weight: ["300", "400", "500", "600", "700"],
  subsets: ["thai", "latin"],
  variable: "--font-kanit",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Delentia Desk",
  description: "Desktop GUI for Delentia OS — Intent-Centric Constitutional AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${spaceGrotesk.variable} ${kanit.variable} bg-surface text-gray-100 antialiased min-h-screen flex flex-col justify-between`}>
        <ThemeProvider>
          <div className="flex flex-row h-screen w-screen overflow-hidden bg-surface">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0 h-full relative">
              <main className="flex-1 w-full min-w-0 relative flex flex-col min-h-0">
                {children}
              </main>
              <TelemetryBar />
            </div>
          </div>
          <CommandPalette />
        </ThemeProvider>
      </body>
    </html>
  );
}
