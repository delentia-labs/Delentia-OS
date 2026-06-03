import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { ThemeHelper } from "@/components/theme-helper";

export const metadata: Metadata = {
  title: "Delentia Desk",
  description: "Desktop GUI for Delentia OS — Intent-Centric Constitutional AI",
};

const NAV_LINKS = [
  { href: "/",          label: "Dashboard",  icon: "⬛" },
  { href: "/chat",      label: "Intent Chat", icon: "💬" },
  { href: "/memory",    label: "Memory",      icon: "🧠" },
  { href: "/ecosystem", label: "Ecosystem",   icon: "⬡" },
  { href: "/models",    label: "Models",      icon: "🤖" },
  { href: "/workflow",  label: "Workflow",    icon: "⚡" },
  { href: "/monitor",   label: "Monitor",     icon: "📡" },
  { href: "/settings",  label: "Settings",    icon: "⚙️" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-surface text-gray-100 antialiased min-h-screen">
        <ThemeHelper />
        <nav className="glass-nav sticky top-0 z-50 h-14 flex items-center px-6 gap-6 justify-between">
          {/* Brand */}
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5 group shrink-0">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-indigo-900/30 group-hover:scale-105 transition duration-200">
                D
              </div>
              <span className="font-bold text-sm tracking-tight text-white group-hover:text-indigo-300 transition hidden sm:block">
                Delentia Desk
              </span>
            </Link>

            {/* Nav links */}
            <div className="hidden md:flex items-center gap-0.5">
              {NAV_LINKS.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  className="text-xs px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition duration-150 font-medium whitespace-nowrap"
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

          {/* Right: version badge */}
          <div className="flex items-center gap-3 shrink-0">
            <span className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono text-gray-500 bg-white/5 px-2.5 py-1 rounded-full border border-white/5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]" />
              v1.0.1
            </span>
          </div>
        </nav>

        <main className="p-5 md:p-8 max-w-7xl mx-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
