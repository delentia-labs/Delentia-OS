"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useThemeStore, type ThemeName } from "@/hooks/useTheme";
import { Terminal, Search, HelpCircle, Sparkles, Sliders } from "lucide-react";

interface CommandItem {
  id: string;
  category: string;
  name: string;
  desc: string;
  action: (arg?: string) => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { setTheme } = useThemeStore();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const commands: CommandItem[] = [
    { id: "go-dashboard", category: "นำทาง (Navigation)", name: "ไปที่ หน้าหลัก Dashboard", desc: "เปลี่ยนหน้าไปยังหน้าสรุปสถิติหลัก", action: () => { router.push("/"); setOpen(false); } },
    { id: "go-chat", category: "นำทาง (Navigation)", name: "ไปที่ Intent Chat", desc: "หน้าสนทนาวิเคราะห์ความตั้งใจ AI", action: () => { router.push("/chat"); setOpen(false); } },
    { id: "go-memory", category: "นำทาง (Navigation)", name: "ไปที่ Memory Timeline", desc: "หน้าส่องบันทึกประวัติการตัดสินใจ", action: () => { router.push("/memory"); setOpen(false); } },
    { id: "go-ecosystem", category: "นำทาง (Navigation)", name: "ไปที่ Ecosystem Registry", desc: "หน้าจัดการไมโครเซอร์วิสและเอเจนต์", action: () => { router.push("/ecosystem"); setOpen(false); } },
    { id: "go-models", category: "นำทาง (Navigation)", name: "ไปที่ Local SLM Manager", desc: "หน้าดาวน์โหลดและรันประมวลผลโมเดล", action: () => { router.push("/models"); setOpen(false); } },
    { id: "go-workflow", category: "นำทาง (Navigation)", name: "ไปที่ Workflow Builder", desc: "หน้าออกแบบสายกระบวนงานแบบทัศนภาพ", action: () => { router.push("/workflow"); setOpen(false); } },
    { id: "go-monitor", category: "นำทาง (Navigation)", name: "ไปที่ System Monitor", desc: "หน้าตรวจสอบสถานะความปลอดภัยและการดริฟต์", action: () => { router.push("/monitor"); setOpen(false); } },
    { id: "go-settings", category: "นำทาง (Navigation)", name: "ไปที่ Settings", desc: "แผงตั้งค่าและชุดธีมสี", action: () => { router.push("/settings"); setOpen(false); } },
    
    { id: "theme-dark", category: "การออกแบบ (Theme)", name: "เปลี่ยนธีม: Space Deep (Default Dark)", desc: "สลับเป็นธีมมืดดั้งเดิมของ Delentia", action: () => { setTheme("dark-modern-default"); setOpen(false); } },
    { id: "theme-abyss", category: "การออกแบบ (Theme)", name: "เปลี่ยนธีม: Abyss (Deep Oceanic)", desc: "สลับเป็นโทนครามลึกก้นทะเล", action: () => { setTheme("abyss"); setOpen(false); } },
    { id: "theme-monokai", category: "การออกแบบ (Theme)", name: "เปลี่ยนธีม: Monokai Classic", desc: "สลับเป็นธีมสีเขียวมะนาว/เทาโมโนไก", action: () => { setTheme("monokai"); setOpen(false); } },
    { id: "theme-synthwave", category: "การออกแบบ (Theme)", name: "เปลี่ยนธีม: Synthwave '84 (Cyberpunk)", desc: "สลับเป็นสไตล์นีออนไซเบอร์พังก์สุดล้ำ", action: () => { setTheme("synthwave-84"); setOpen(false); } },
    { id: "theme-powershell", category: "การออกแบบ (Theme)", name: "เปลี่ยนธีม: PowerShell ISE (Light)", desc: "สลับเป็นโหมดสว่างน้ำเงิน ISE สดใส", action: () => { setTheme("powershell-ise"); setOpen(false); } },
  ];

  const filtered = commands.filter(
    (cmd) =>
      cmd.name.toLowerCase().includes(query.toLowerCase()) ||
      cmd.category.toLowerCase().includes(query.toLowerCase()) ||
      cmd.desc.toLowerCase().includes(query.toLowerCase())
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[selectedIndex]) {
        filtered[selectedIndex].action();
      }
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[999] flex items-start justify-center pt-24 px-4 animate-in fade-in duration-200">
      <div
        ref={containerRef}
        className="w-full max-w-lg bg-surface-card border border-surface-border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[400px]"
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-border">
          <Search className="w-4 h-4 text-gray-500 shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="ค้นหาคำสั่งด่วน... (พิมพ์ 'นำทาง' หรือ 'ธีม')"
            className="flex-1 bg-transparent text-xs text-gray-200 outline-none placeholder-gray-500"
            autoFocus
          />
          <span className="text-[9px] text-gray-600 bg-surface border border-surface-border px-1.5 py-0.5 rounded font-mono">
            ESC
          </span>
        </div>

        {/* Command list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-500 flex flex-col items-center gap-2">
              <HelpCircle className="w-6 h-6 text-gray-600" />
              <span>ไม่พบคำสั่งที่คุณกำลังมองหา</span>
            </div>
          ) : (
            filtered.map((cmd, i) => {
              const active = i === selectedIndex;
              return (
                <button
                  key={cmd.id}
                  onClick={() => cmd.action()}
                  onMouseEnter={() => setSelectedIndex(i)}
                  className={`w-full flex items-center justify-between p-2.5 rounded-lg text-left transition ${
                    active
                      ? "bg-delentia-600/10 border border-delentia-500/30 text-white"
                      : "border border-transparent text-gray-400 hover:text-gray-200 hover:bg-white/5"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Terminal className={`w-3.5 h-3.5 shrink-0 ${active ? "text-delentia-400" : "text-gray-500"}`} />
                    <div className="truncate">
                      <p className="text-xs font-semibold">{cmd.name}</p>
                      <p className="text-[9px] text-gray-500 truncate max-w-[320px]">{cmd.desc}</p>
                    </div>
                  </div>
                  <span className="text-[8px] font-mono px-2 py-0.5 rounded-full bg-surface border border-surface-border shrink-0">
                    {cmd.category}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="bg-surface/50 border-t border-surface-border/50 px-4 py-2.5 flex items-center justify-between text-[9px] text-gray-500">
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-delentia-500" />
            กดสลับหน้าต่างและคำสั่งแบบรวดเร็ว
          </span>
          <div className="flex items-center gap-2 font-mono">
            <span>↑↓ เพื่อเลือก</span>
            <span>·</span>
            <span>Enter เพื่อสั่งงาน</span>
          </div>
        </div>
      </div>
    </div>
  );
}
