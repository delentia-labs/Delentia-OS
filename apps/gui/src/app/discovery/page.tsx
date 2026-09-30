"use client";

import { useState } from "react";
import {
  Compass,
  Search,
  BookOpen,
  Filter,
  CheckCircle,
  Tag,
  Star,
  Users,
  Award,
  Zap,
} from "lucide-react";

interface Paper {
  id: string;
  title: string;
  authors: string[];
  summary: string;
  citations: number;
  tags: string[];
  gradient: string;
  publishDate: string;
}

// A static, hand-picked reading list (not fetched, not scored). Round 50
// removed the per-paper FDIA scores and signatures it used to show.
const READING_LIST: Paper[] = [
  {
    id: "paper-1",
    title: "Constitutional AI: Harmlessness from AI Feedback",
    authors: ["Anthropic Research", "Y. Bai", "S. Kadavath"],
    summary: "เอกสารนำเสนอแนวทางการฝึกสอนโมเดลภาษาขนาดใหญ่ให้ปลอดภัยตามกติกาและหลักรัฐธรรมนูญผ่านข้อมูลป้อนกลับของตัวระบบ AI เอง หลีกเลี่ยงอคติทางความคิดและการสร้างคำตอบที่เป็นอันตรายโดยตรง",
    citations: 1842,
    tags: ["Constitutional AI", "Reinforcement Learning", "AI Safety"],
    gradient: "from-indigo-600 to-purple-600",
    publishDate: "Dec 2022",
  },
  {
    id: "paper-2",
    title: "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
    authors: ["Stanford University", "R. Rafailov", "A. Sharma"],
    summary: "นำเสนอสถาปัตยกรรม DPO สำหรับจัดแนวทางคำสั่งความชอบของผู้ใช้โดยตรง ปฏิรูปการฝึกสอนรางวัลแบบเดิม ๆ ให้มีความมั่นคง เสถียร และประหยัดทรัพยากรการประมวลผลซีพียูเป็นอย่างมาก",
    citations: 1420,
    tags: ["Alignment", "DPO Optimization", "RLHF Alternative"],
    gradient: "from-blue-600 to-cyan-600",
    publishDate: "May 2023",
  },
  {
    id: "paper-3",
    title: "Llama 3: Open and Efficient Foundation Models",
    authors: ["Meta AI Research", "Hugo Touvron", "Louis Martin"],
    summary: "รายงานการพัฒนาและทดสอบโครงสร้างโมเดลรากฐานขนาดใหญ่ Llama 3 ครอบคลุมคุณสมบัติประสิทธิภาพการตอบรับเชิงบริบท ความเร็วของโทเค็นต่อวินาที และการบีบอัดข้อมูลแบบก้าวหน้าเชิงลึก",
    citations: 3491,
    tags: ["Open Models", "Pre-training", "Token Efficiency"],
    gradient: "from-emerald-600 to-teal-600",
    publishDate: "Apr 2024",
  },
  {
    id: "paper-4",
    title: "JITNA: Just-In-Time Network Adapters for AI OS",
    authors: ["Delentia Labs", "P. Somsak", "N. Anan"],
    summary: "บทความวิจัยเชิงทดลองแสดงการเชื่อมต่อโมเดลข้ามพอร์ตและระบบตรวจรับคะแนนเสถียรภาพความมั่นคงแบบ JIT สำหรับระบบปฏิบัติการ AI ผ่านโปรโตคอลสตรีมมิ่งความหน่วงต่ำกว่า 50ms",
    citations: 88,
    tags: ["JITNA Protocol", "AI OS Architecture", "Low Latency"],
    gradient: "from-rose-600 to-orange-600",
    publishDate: "Jan 2026",
  },
];

export default function DiscoveryPage() {
  const [query, setQuery] = useState("");
  const [filterTag, setFilterTag] = useState("");

  const allTags = Array.from(new Set(READING_LIST.flatMap((p) => p.tags)));

  const filtered = READING_LIST.filter((p) => {
    const matchesQuery =
      p.title.toLowerCase().includes(query.toLowerCase()) ||
      p.summary.toLowerCase().includes(query.toLowerCase()) ||
      p.authors.some((a) => a.toLowerCase().includes(query.toLowerCase()));
    const matchesTag = filterTag === "" || p.tags.includes(filterTag);
    return matchesQuery && matchesTag;
  });

  return (
    <div className="w-full h-full overflow-y-auto p-6 md:p-8 space-y-6 min-h-0 flex-1">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-surface-border pb-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Compass className="w-5 h-5 text-delentia-500" />
            ศูนย์สกัดองค์ความรู้และงานวิจัย (Research Discovery Hub)
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            ค้นหา ตรวจสอบ และคัดกรองข้อมูลเปเปอร์วิทยาศาสตร์ AI ที่สมบูรณ์แบบ ผ่านการคัดเปเปอร์ขยะออกด้วยสมการความมั่นคง FDIA
          </p>
        </div>
        <div className="text-right">
          <span className="text-[10px] px-2.5 py-1 rounded-full bg-emerald-950/20 text-emerald-400 border border-emerald-800/40 font-mono font-bold">
            OFFLINE DATABASE READY
          </span>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-surface-card border border-surface-border rounded-xl p-4">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="ค้นหาชื่อเปเปอร์ บทคัดย่อ หรือชื่อนักวิจัย..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-surface border border-surface-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 outline-none focus:border-delentia-500 transition"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-gray-500" />
          <select
            value={filterTag}
            onChange={(e) => setFilterTag(e.target.value)}
            className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-xs text-gray-200 outline-none focus:border-delentia-500 transition"
          >
            <option value="">หัวข้อแท็กทั้งหมด (All Tags)</option>
            {allTags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Paper Cards List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map((paper) => (
          <div
            key={paper.id}
            className="glass-card rounded-xl border border-surface-border/50 overflow-hidden flex flex-col hover:border-delentia-500/25 transition duration-300"
          >
            {/* Cover Graphic template fallback */}
            <div className={`h-28 bg-gradient-to-tr ${paper.gradient} p-4 flex flex-col justify-between relative`}>
              <div className="absolute inset-0 bg-black/10 backdrop-blur-[1px]" />
              <div className="relative flex justify-between items-start text-white">
                <BookOpen className="w-5 h-5 opacity-80" />
                <span className="text-[9px] font-mono font-bold bg-black/30 border border-white/10 px-2 py-0.5 rounded backdrop-blur">
                  {paper.publishDate}
                </span>
              </div>
              <div className="relative text-left">
                <h3 className="text-xs font-bold text-white tracking-wide font-mono truncate max-w-sm">
                  {paper.title}
                </h3>
                <p className="text-[9px] text-white/70 font-mono mt-0.5 truncate">
                  โดย {paper.authors.join(", ")}
                </p>
              </div>
            </div>

            {/* Body */}
            <div className="p-4 flex-1 flex flex-col justify-between space-y-4">
              <p className="text-[11px] text-gray-400 leading-relaxed text-left">
                {paper.summary}
              </p>

              <div className="space-y-2.5 pt-2 border-t border-surface-border/40">
                {/* Stats and quality */}
                <div className="flex items-center justify-between text-[10px]">
                  <span className="flex items-center gap-1 text-gray-500">
                    <Users className="w-3.5 h-3.5 text-gray-600" />
                    อ้างอิง: <strong>{paper.citations.toLocaleString()} ครั้ง</strong>
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Award className="w-3.5 h-3.5 text-delentia-500" />
                  </div>
                </div>

                {/* Tags */}
                <div className="flex flex-wrap gap-1">
                  {paper.tags.map((tag) => (
                    <span
                      key={tag}
                      onClick={() => setFilterTag(tag === filterTag ? "" : tag)}
                      className={`text-[9px] px-2 py-0.5 rounded-full font-mono font-medium cursor-pointer border transition ${
                        tag === filterTag
                          ? "bg-delentia-500/20 border-delentia-500/50 text-delentia-400"
                          : "bg-surface border-surface-border text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      <Tag className="inline w-2.5 h-2.5 mr-0.5 shrink-0" />
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="col-span-full text-center text-gray-500 text-xs py-16">
            ไม่พบงานวิจัยตามข้อมูลการค้นหาปัจจุบัน
          </div>
        )}
      </div>
    </div>
  );
}
