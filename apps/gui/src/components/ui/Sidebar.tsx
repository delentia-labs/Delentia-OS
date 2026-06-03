"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  Brain,
  Package,
  Cpu,
  GitBranch,
  Activity,
  Compass,
  Settings,
  Menu,
  X,
  Search,
  ChevronDown,
  Sparkles,
  Bookmark,
  Blocks,
  FileCode,
  ShieldCheck,
  LogOut,
  Mail,
  User,
} from "lucide-react";

export function Sidebar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  // Close mobile drawer and dropdowns on page transition
  useEffect(() => {
    setMenuOpen(false);
    setProfileDropdownOpen(false);
  }, [pathname]);

  const triggerSearch = () => {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  };

  const navGroups = [
    {
      title: "CORE ROUTINES",
      links: [
        { href: "/",          label: "Dashboard",   icon: LayoutDashboard },
        { href: "/chat",      label: "Intent Chat", icon: MessageSquare },
        { href: "/memory",    label: "Memory",      icon: Brain },
      ],
    },
    {
      title: "EXPLORE SYSTEM",
      links: [
        { href: "/ecosystem", label: "Ecosystem Registry", icon: Package },
        { href: "/models",    label: "Local SLM Models",    icon: Cpu },
        { href: "/workflow",  label: "JITNA Workflows",    icon: GitBranch },
        { href: "/monitor",   label: "System Monitor",     icon: Activity },
        { href: "/discovery", label: "Research Discovery",   icon: Compass },
      ],
    },
  ];

  const actionTriggers = [
    {
      label: "Create agent with AI",
      onClick: () => {
        router.push("/chat?trigger=create-agent");
      },
    },
    {
      label: "Start from a template",
      onClick: () => {
        router.push("/workflow?tab=templates");
      },
    },
    {
      label: "Create agent manually",
      onClick: () => {
        router.push("/ecosystem?action=create");
      },
    },
  ];

  return (
    <>
      {/* Mobile Top Bar (Only visible on screens < lg) */}
      <div className="lg:hidden w-full h-14 bg-surface-card border-b border-surface-border sticky top-0 z-40 flex items-center px-4 justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition"
            aria-label="Toggle Navigation Drawer"
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className="font-bold text-sm tracking-tight text-white">Delentia Desk</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={triggerSearch}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition"
          >
            <Search size={18} />
          </button>
          <span className="text-[10px] font-mono text-gray-400 bg-white/5 px-2 py-0.5 rounded-full border border-white/5 shadow-inner flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
            v1.0.1
          </span>
        </div>
      </div>

      {/* Main Sidebar (Desktop fixed left, Mobile drawer overlay) */}
      <aside
        className={`w-64 h-screen sticky top-0 bg-surface-card border-r border-surface-border flex flex-col justify-between shrink-0 z-50 transition-transform duration-300 lg:translate-x-0 ${
          menuOpen ? "translate-x-0 fixed inset-y-0 left-0 shadow-2xl" : "-translate-x-full fixed inset-y-0 left-0 lg:flex"
        }`}
      >
        {/* Top Section */}
        <div className="flex flex-col p-4 gap-4 overflow-y-auto flex-1 min-h-0">
          {/* Logo & Dropdown header */}
          <div className="flex items-center justify-between pb-2 border-b border-surface-border/30">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="w-7.5 h-7.5 rounded-md bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white text-xs font-bold shadow-md shadow-indigo-900/30 group-hover:scale-105 transition duration-200">
                D
              </div>
              <span className="font-bold text-[13px] tracking-tight text-white group-hover:text-indigo-400 transition flex items-center gap-1.5 select-none">
                Delentia Desk
                <span className="text-[9px] font-mono font-medium text-gray-500 bg-white/5 px-1.5 py-0.5 rounded border border-white/5 flex items-center gap-1">
                  <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
                  v1.0.1
                </span>
              </span>
            </Link>
          </div>

          {/* Search container */}
          <button
            onClick={triggerSearch}
            className="w-full flex items-center justify-between px-3 py-2 bg-surface hover:bg-white/5 border border-surface-border/80 hover:border-surface-border rounded-lg text-left text-gray-500 hover:text-gray-300 transition duration-150 group"
          >
            <div className="flex items-center gap-2">
              <Search className="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-400 transition" />
              <span className="text-[11px] font-medium font-sans">ค้นหาคำสั่งด่วน...</span>
            </div>
            <span className="text-[8px] font-mono text-gray-600 bg-surface border border-surface-border px-1.5 py-0.5 rounded">
              Ctrl K
            </span>
          </button>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-5.5 mt-2">
            {navGroups.map((group) => (
              <div key={group.title} className="flex flex-col gap-1">
                <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest pl-3 select-none">
                  {group.title}
                </span>
                <div className="flex flex-col gap-0.5">
                  {group.links.map(({ href, label, icon: IconComponent }) => {
                    const active = pathname === href;
                    return (
                      <Link
                        key={href}
                        href={href}
                        className={`text-xs px-3 py-2 rounded-lg font-medium flex items-center gap-2.5 transition-all duration-150 ${
                          active
                            ? "text-white bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                            : "text-gray-400 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <IconComponent size={14} strokeWidth={active ? 2.25 : 1.75} className={active ? "text-indigo-400" : "text-gray-500"} />
                        <span className="font-sans font-medium text-[12px]">{label}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}

            {/* Get Started Action buttons */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest pl-3 select-none">
                GET STARTED
              </span>
              <div className="flex flex-col gap-1 px-1">
                {actionTriggers.map((act) => (
                  <button
                    key={act.label}
                    onClick={act.onClick}
                    className="w-full text-left px-3 py-1.5 rounded-md bg-white/3 hover:bg-white/7 border border-white/5 hover:border-white/10 text-gray-400 hover:text-white transition text-[11px] font-sans font-medium"
                  >
                    {act.label}
                  </button>
                ))}
              </div>
            </div>
          </nav>
        </div>

        {/* Bottom Section: User Profile & Utility links */}
        <div className="p-4 flex flex-col gap-3.5 border-t border-surface-border/30 relative shrink-0">
          {/* Quick utility list */}
          <div className="flex flex-col gap-0.5">
            <Link
              href="/settings"
              className="text-xs px-3 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition flex items-center gap-2 font-medium"
            >
              <Settings size={13} className="text-gray-500" />
              <span className="font-sans font-medium text-[12px]">Settings</span>
            </Link>
          </div>

          {/* User profile dropdown triggers */}
          <div className="relative">
            <button
              onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              className="w-full flex items-center justify-between p-2 rounded-lg bg-surface/50 hover:bg-white/5 border border-surface-border/50 hover:border-surface-border transition duration-150 text-left"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-7 h-7 rounded-full bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-300 text-xs font-bold font-mono">
                  W
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-gray-200 font-sans leading-tight">Personal</p>
                  <p className="text-[9px] text-gray-500 truncate max-w-[120px] font-mono mt-0.5">whale@delentia.labs</p>
                </div>
              </div>
              <ChevronDown size={14} className="text-gray-500 shrink-0 ml-1" />
            </button>

            {/* Profile Dropdown Context Menu */}
            {profileDropdownOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-2 bg-surface-card border border-surface-border rounded-xl shadow-xl overflow-hidden py-1 z-50 animate-in slide-in-from-bottom duration-150">
                <button
                  onClick={() => {
                    setProfileDropdownOpen(false);
                    triggerSearch();
                  }}
                  className="w-full px-3.5 py-2.5 text-left text-[11px] font-medium text-gray-400 hover:text-white hover:bg-white/5 transition flex items-center gap-2"
                >
                  <Sparkles size={13} className="text-indigo-400" />
                  สลับชุดสีธีมระบบ
                </button>
                <Link
                  href="/settings"
                  className="px-3.5 py-2.5 text-[11px] font-medium text-gray-400 hover:text-white hover:bg-white/5 transition flex items-center gap-2"
                >
                  <User size={13} className="text-gray-500" />
                  โปรไฟล์การใช้งาน
                </Link>
                <div className="h-px bg-surface-border/50 my-1" />
                <button
                  onClick={() => {
                    setProfileDropdownOpen(false);
                    alert("Logged out of simulated workspace.");
                  }}
                  className="w-full px-3.5 py-2.5 text-left text-[11px] font-medium text-red-400 hover:bg-red-500/5 transition flex items-center gap-2"
                >
                  <LogOut size={13} />
                  ออกจากระบบ
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Backdrop blur click receiver on mobile */}
      {menuOpen && (
        <div
          onClick={() => setMenuOpen(false)}
          className="lg:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-40 animate-in fade-in duration-200"
        />
      )}
    </>
  );
}
