import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" className="dark">
      <body className="bg-surface text-gray-100 font-sans antialiased min-h-screen">
        <nav className="h-12 border-b border-surface-border flex items-center px-4 gap-4">
          <a href="/" className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-delentia-600 flex items-center justify-center text-white text-xs font-bold">D</div>
            <span className="font-semibold text-sm text-gray-100">Delentia Desk</span>
          </a>
          <div className="flex-1 flex items-center gap-1 ml-4">
            {[
              { href: "/",          label: "Dashboard" },
              { href: "/chat",      label: "Intent Chat" },
              { href: "/memory",    label: "Memory" },
              { href: "/ecosystem", label: "Ecosystem" },
              { href: "/models",    label: "Models" },
              { href: "/workflow",  label: "Workflow" },
              { href: "/monitor",   label: "Monitor" },
              { href: "/settings",  label: "Settings" },
            ].map(({ href, label }) => (
              <a
                key={href}
                href={href}
                className="text-xs px-3 py-1.5 rounded-md text-gray-400 hover:text-gray-100 hover:bg-surface-card transition"
              >
                {label}
              </a>
            ))}
          </div>
          <span className="text-[10px] font-mono text-gray-600">v1.0.1</span>
        </nav>
        <main className="p-4 md:p-6">{children}</main>
      </body>
    </html>
  );
}
