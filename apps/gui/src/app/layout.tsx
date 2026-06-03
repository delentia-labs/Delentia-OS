import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import ThemeProvider from "@/components/ThemeProvider";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { TelemetryBar } from "@/components/ui/TelemetryBar";
import {
  LayoutDashboard,
  MessageSquare,
  Brain,
  Package,
  Cpu,
  GitBranch,
  Activity,
  Settings,
  Compass,
} from "lucide-react";

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
      <body className="bg-surface text-gray-100 antialiased min-h-screen flex flex-col justify-between">
        <ThemeProvider>
          <div className="flex-1 flex flex-col min-h-0">
            <nav className="glass-nav sticky top-0 z-50 h-14 flex items-center px-6 gap-6 justify-between">
              <div className="flex items-center gap-6">
                <Link href="/" className="flex items-center gap-3 group">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-indigo-900/30 group-hover:scale-105 transition duration-200">
                    D
                  </div>
                  <span className="font-bold text-base tracking-tight text-white group-hover:text-indigo-400 transition">
                    Delentia Desk
                  </span>
                </Link>
                <div className="hidden xl:flex items-center gap-1 ml-4">
                  {[
                    { href: "/",          label: "Dashboard",   icon: LayoutDashboard },
                    { href: "/chat",      label: "Intent Chat", icon: MessageSquare },
                    { href: "/memory",    label: "Memory",      icon: Brain },
                    { href: "/ecosystem", label: "Ecosystem",   icon: Package },
                    { href: "/models",    label: "Models",      icon: Cpu },
                    { href: "/workflow",  label: "Workflow",    icon: GitBranch },
                    { href: "/monitor",   label: "Monitor",     icon: Activity },
                    { href: "/discovery", label: "Discovery",   icon: Compass },
                    { href: "/settings",  label: "Settings",    icon: Settings },
                  ].map(({ href, label, icon: IconComponent }) => (
                    <Link
                      key={href}
                      href={href}
                      className="text-xs px-3 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition duration-150 font-medium flex items-center gap-1.5"
                    >
                      <IconComponent size={14} strokeWidth={1.75} />
                      <span>{label}</span>
                    </Link>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="hidden sm:inline-block text-[9px] font-mono text-gray-500 bg-white/5 px-2 py-1 rounded border border-white/5">
                  Ctrl+K สั่งการด่วน
                </span>
                <span className="text-[10px] font-mono text-gray-500 bg-white/5 px-2.5 py-1 rounded-full border border-white/5 shadow-inner">
                  v1.0.1
                </span>
              </div>
            </nav>
            <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full">{children}</main>
          </div>
          <TelemetryBar />
          <CommandPalette />
        </ThemeProvider>
      </body>
    </html>
  );
}
