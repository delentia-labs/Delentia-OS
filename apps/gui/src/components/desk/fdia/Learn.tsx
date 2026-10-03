"use client";

import { useState } from "react";
import { Badge, Button, Code, Panel } from "@/components/desk/ui";
import { BUILT_IN_THRESHOLD, fdiaScore } from "@/lib/fdia-math";

type T = (en: string, th: string) => string;

export interface Scenario {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  D: number;
  I: number;
  approved?: boolean;
}

/** Four calls worked through by hand; each can be sent to the tester with one click. */
const SCENARIOS: { s: Scenario; title: [string, string]; story: [string, string] }[] = [
  {
    s: { id: "read", tool: "delentia_read_repo_file", args: { relative_path: "README.md" }, D: 0.9, I: 1.0 },
    title: ["Read a file", "อ่านไฟล์"],
    story: [
      "Reading is allowed, the data is good (D 0.9), the intent is plain (I 1): F = 0.9 ^ 1 × 1 = 0.9. It runs.",
      "อ่านได้ ข้อมูลดี (D 0.9) เจตนาชัด (I 1): F = 0.9 ^ 1 × 1 = 0.9 จึงรันได้",
    ],
  },
  {
    s: { id: "env", tool: "delentia_write_repo_file", args: { relative_path: ".env", content_text: "x" }, D: 1.0, I: 1.0, approved: true },
    title: ["Write .env, even signed", "เขียน .env ต่อให้เซ็นแล้ว"],
    story: [
      "The path is on the owner's forbidden list, so A = 0 and F = 1 ^ 1 × 0 = 0. A signature cannot lift what the owner forbade.",
      "path นี้อยู่ในรายการที่เจ้าของห้าม จึง A = 0 และ F = 1 ^ 1 × 0 = 0 ลายเซ็นไม่สามารถปลดสิ่งที่เจ้าของห้ามได้",
    ],
  },
  {
    s: { id: "weak", tool: "delentia_run_sandboxed_command", args: { command: "echo hello" }, D: 0.5, I: 1.5 },
    title: ["Demanding goal, thin data", "เป้าหมายเข้มข้น ข้อมูลบาง"],
    story: [
      "D 0.5 and I 1.5: F = 0.5 ^ 1.5 = 0.35, under the 0.5 threshold. The more demanding the intent, the better the data must be.",
      "D 0.5 และ I 1.5: F = 0.5 ^ 1.5 = 0.35 ต่ำกว่าเกณฑ์ 0.5 ยิ่งเจตนาเข้มข้น ข้อมูลยิ่งต้องดี",
    ],
  },
  {
    s: { id: "sign", tool: "delentia_run_sandboxed_command", args: { command: "echo hello" }, D: 1.0, I: 1.0 },
    title: ["A command that needs a human", "คำสั่งที่ต้องมีมนุษย์เซ็น"],
    story: [
      "With a rule that requires a signature, the call waits. A becomes 1 only when the required approvers sign this exact action.",
      "เมื่อมีกฎให้ต้องเซ็น การเรียกจะรอ A เป็น 1 ก็ต่อเมื่อผู้อนุมัติที่กำหนดเซ็น action นี้ครบ",
    ],
  },
];

function Curves({ D, I, threshold }: { D: number; I: number; threshold: number }) {
  const W = 320;
  const H = 170;
  const pad = 26;
  const x = (d: number) => pad + d * (W - pad - 8);
  const y = (f: number) => H - pad - f * (H - pad - 10);
  const path = (i: number) =>
    Array.from({ length: 41 }, (_, k) => {
      const d = k / 40;
      return `${k === 0 ? "M" : "L"}${x(d).toFixed(1)},${y(fdiaScore(d, i, 1)).toFixed(1)}`;
    }).join(" ");
  const f = fdiaScore(D, I, 1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="F as D grows, for several values of I" className="w-full max-w-[420px]">
      <rect x={pad} y={y(1)} width={W - pad - 8} height={y(0) - y(1)} fill="none" stroke="rgb(var(--dl-rule-rgb))" />
      <line x1={pad} x2={W - 8} y1={y(threshold)} y2={y(threshold)} stroke="rgb(var(--dl-amber-rgb))" strokeDasharray="4 3" />
      <text x={W - 10} y={y(threshold) - 4} textAnchor="end" fontSize="9" fill="rgb(var(--dl-amber-rgb))">threshold {threshold}</text>
      {[0.5, 1, 2, 3].map((i, k) => (
        <path key={i} d={path(i)} fill="none" stroke="rgb(var(--dl-leaf-rgb))" strokeOpacity={0.35 + k * 0.2} strokeWidth="1.5" />
      ))}
      <circle cx={x(Math.min(1, D))} cy={y(f)} r="4.5" fill={f >= threshold ? "rgb(var(--dl-leaf-rgb))" : "rgb(var(--dl-rust-rgb))"} />
      <text x={pad} y={H - 8} fontSize="9" fill="rgb(var(--dl-muted-rgb))">D 0</text>
      <text x={W - 8} y={H - 8} textAnchor="end" fontSize="9" fill="rgb(var(--dl-muted-rgb))">D 1</text>
      <text x={4} y={y(1) + 3} fontSize="9" fill="rgb(var(--dl-muted-rgb))">F 1</text>
      <text x={4} y={y(0)} fontSize="9" fill="rgb(var(--dl-muted-rgb))">0</text>
    </svg>
  );
}

function Calculator({ T }: { T: T }) {
  const [D, setD] = useState(0.8);
  const [I, setI] = useState(1.0);
  const [A, setA] = useState(1);
  const F = fdiaScore(D, I, A);
  const ok = F >= BUILT_IN_THRESHOLD;
  const slider = "desk-focus w-full accent-[var(--dl-leaf)]";
  return (
    <Panel title={T("Try the equation", "ลองสมการ")}>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-4">
          <label className="block">
            <span className="flex justify-between text-[13px] text-dl-muted"><span>D · {T("Data", "ข้อมูล")}</span><span className="desk-mono text-dl-text">{D.toFixed(2)}</span></span>
            <input type="range" min={0} max={1} step={0.01} value={D} onChange={(e) => setD(Number(e.target.value))} className={slider} aria-label="D" />
          </label>
          <label className="block">
            <span className="flex justify-between text-[13px] text-dl-muted"><span>I · {T("Intent (how demanding)", "เจตนา (ความเข้มข้น)")}</span><span className="desk-mono text-dl-text">{I.toFixed(2)}</span></span>
            <input type="range" min={0.5} max={3} step={0.05} value={I} onChange={(e) => setI(Number(e.target.value))} className={slider} aria-label="I" />
          </label>
          <div>
            <span className="text-[13px] text-dl-muted">A · {T("Architect", "ผู้รับผิดชอบ")}</span>
            <div className="mt-1 flex gap-2">
              <Button tone={A === 1 ? "fern" : "ghost"} onClick={() => setA(1)}>A = 1 · {T("an accountable human stands behind it", "มีผู้รับผิดชอบ")}</Button>
              <Button tone={A === 0 ? "amber" : "ghost"} onClick={() => setA(0)}>A = 0 · {T("nobody does", "ไม่มีใครรับผิดชอบ")}</Button>
            </div>
          </div>
          <p className="desk-mono text-[15px] text-dl-text">
            F = {D.toFixed(2)}<sup>{I.toFixed(2)}</sup> × {A} = <span className={ok ? "text-dl-leaf" : "text-dl-rust"}>{F.toFixed(4)}</span>
          </p>
          <p role="status" className={`text-[13px] ${ok ? "text-dl-leaf" : "text-dl-rust"}`}>
            {ok
              ? T(`F is at or above ${BUILT_IN_THRESHOLD}: the gate lets a risky action through.`, `F ไม่ต่ำกว่า ${BUILT_IN_THRESHOLD}: ด่านปล่อยให้ action เสี่ยงผ่าน`)
              : A === 0
                ? T("A = 0, so F = 0 whatever the data: no responsibility, no outcome.", "A = 0 จึง F = 0 ไม่ว่าข้อมูลจะดีแค่ไหน: ไม่มีผู้รับผิดชอบ ก็ไม่มีผลลัพธ์")
                : T(`F is under ${BUILT_IN_THRESHOLD}: a risky action is blocked.`, `F ต่ำกว่า ${BUILT_IN_THRESHOLD}: action เสี่ยงถูกบล็อก`)}
          </p>
        </div>
        <div>
          <Curves D={D} I={I} threshold={BUILT_IN_THRESHOLD} />
          <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">
            {T("Curves are F for I = 0.5, 1, 2, 3 as D grows (A = 1). The dot is your D and I. A larger I bends the curve down: it asks more of the data.",
              "เส้นโค้งคือ F เมื่อ I = 0.5, 1, 2, 3 ขณะที่ D เพิ่ม (A = 1) จุดคือ D และ I ที่คุณเลือก I ที่มากขึ้นทำให้เส้นโค้งต่ำลง คือเรียกร้องข้อมูลที่ดีขึ้น")}
          </p>
        </div>
      </div>
    </Panel>
  );
}

export function Learn({ T, onTry }: { T: T; onTry: (s: Scenario) => void }) {
  const symbols: { sym: string; name: [string, string]; meaning: [string, string]; here: [string, string]; zero: [string, string] }[] = [
    {
      sym: "F", name: ["Future", "อนาคต"],
      meaning: ["The outcome that actually happens, not a prediction.", "ผลลัพธ์ที่เกิดขึ้นจริง ไม่ใช่การทำนาย"],
      here: ["A score from 0 to 1 for one action. A risky action runs only if F reaches the threshold (0.5 at least).", "คะแนน 0 ถึง 1 ของแต่ละ action action เสี่ยงจะรันได้เมื่อ F ถึงเกณฑ์ (อย่างน้อย 0.5)"],
      zero: ["F = 0 means: do not run.", "F = 0 คือ ไม่รัน"],
    },
    {
      sym: "D", name: ["Data", "ข้อมูล"],
      meaning: ["All of reality the person has: experience, memory, constraints, even trauma. Raw material.", "ความจริงทั้งหมดที่คนคนนั้นมี ทั้งประสบการณ์ ความจำ ข้อจำกัด แม้แต่บาดแผล เป็นวัตถุดิบ"],
      here: ["Measured from the user's own data, not from how the request is worded: do the files the goal names exist, is there relevant memory, verified skills, a track record, a clear request.", "วัดจากข้อมูลจริงของผู้ใช้ ไม่ใช่จากสำนวนคำขอ: ไฟล์ที่เป้าหมายกล่าวถึงมีอยู่จริงไหม มีความจำที่เกี่ยวข้อง สกิลที่ผ่านการตรวจ ประวัติความสำเร็จ และคำขอที่ชัด"],
      zero: ["D = 0 means no data, so no future.", "D = 0 คือ ไม่มีข้อมูล จึงไม่มีอนาคต"],
    },
    {
      sym: "I", name: ["Intent", "เจตนา"],
      meaning: ["The exponent. It gives the data a direction. Without intent, data goes nowhere.", "เลขชี้กำลัง ให้ข้อมูลมีทิศทาง ไม่มีเจตนา ข้อมูลก็ไปไหนไม่ได้"],
      here: ["Read from the goal by the intent compiler. Because D is between 0 and 1 here, a larger I makes F smaller: the more demanding the intent, the better the data must be.", "อ่านจากเป้าหมายด้วย intent compiler เพราะ D อยู่ระหว่าง 0 ถึง 1 I ที่มากขึ้นทำให้ F เล็กลง: ยิ่งเจตนาเข้มข้น ข้อมูลยิ่งต้องดี"],
      zero: ["I = 0 means no intent, so no outcome.", "I = 0 คือ ไม่มีเจตนา จึงไม่มีผลลัพธ์"],
    },
    {
      sym: "A", name: ["Architect", "ผู้รับผิดชอบ"],
      meaning: ["The human who designs, decides and signs off. Never removed from the loop.", "มนุษย์ที่ออกแบบ ตัดสินใจ และลงนาม ไม่ถูกตัดออกจากวงจร"],
      here: ["Three sources: the built-in checks (path safety, denied shell commands), the rules you write on the Policy tab, and Ed25519 signatures from approvers you trust.", "มีสามที่มา: การตรวจในตัว (ความปลอดภัยของ path, คำสั่ง shell ที่ถูกปฏิเสธ), กฎที่คุณเขียนในแท็บ Policy และลายเซ็น Ed25519 จากผู้อนุมัติที่คุณไว้ใจ"],
      zero: ["A = 0 means no one is accountable, so F = 0.", "A = 0 คือ ไม่มีผู้รับผิดชอบ จึง F = 0"],
    },
  ];

  const layers: [string, string, string, string][] = [
    ["1 · The life equation", "1 · สมการชีวิต", "A philosophy before it was software: a person's future is what their reality becomes when intent drives it, with someone taking responsibility.", "เป็นปรัชญาก่อนเป็นซอฟต์แวร์: อนาคตของคนคือสิ่งที่ความจริงของเขากลายเป็น เมื่อเจตนาขับเคลื่อน และมีผู้รับผิดชอบ"],
    ["2 · The safety gate", "2 · ด่านความปลอดภัย", "For an AI: A = 0 blocks at once, before any model or tool is used. D and I are enforced too: weak data under a demanding intent is blocked.", "สำหรับ AI: A = 0 บล็อกทันที ก่อนใช้โมเดลหรือเครื่องมือ และ D กับ I ก็ถูกบังคับด้วย: ข้อมูลบางภายใต้เจตนาเข้มข้นถูกบล็อก"],
    ["3 · A as the owner's policy", "3 · A เป็นนโยบายของเจ้าของ", "You write the rules: which actions are free, which need a signature (from whom, how many), which paths are off limits, who may ask. This is the Policy tab.", "คุณเขียนกฎเอง: action ไหนเสรี ไหนต้องเซ็น (ใคร กี่คน) path ไหนห้ามแตะ ใครขอได้ นี่คือแท็บ Policy"],
  ];

  const flow: [string, string][] = [
    ["Built-in A: path safety, denied shell commands, key-file names. Always on.", "A ในตัว: ความปลอดภัยของ path, คำสั่ง shell ที่ถูกปฏิเสธ, ชื่อไฟล์กุญแจ เปิดตลอด"],
    ["Your policy: the most restrictive matching rule wins; roles and forbidden paths are checked.", "นโยบายของคุณ: กฎที่เข้มที่สุดที่ตรงกันชนะ ตรวจ role และ path ต้องห้าม"],
    ["F = D^I × A against the threshold (yours can be higher than 0.5, never lower).", "F = D^I × A เทียบกับเกณฑ์ (ของคุณสูงกว่า 0.5 ได้ ต่ำกว่าไม่ได้)"],
    ["A jury, if the rule asks for one: independent models vote, a silent or single-model jury does not count.", "คณะลูกขุน ถ้ากฎขอ: โมเดลต่างกันโหวตอิสระ คณะที่เงียบหรือเป็นโมเดลเดียวไม่นับ"],
    ["Human signatures, if the rule asks: Ed25519, from approvers with the right role, from distinct keys.", "ลายเซ็นมนุษย์ ถ้ากฎขอ: Ed25519 จากผู้อนุมัติที่มี role ถูกต้อง และเป็นคนละกุญแจ"],
    ["The action runs once and the decision is written to the hash-chained audit trail.", "action รันหนึ่งครั้ง และการตัดสินใจถูกบันทึกลง audit chain"],
  ];

  return (
    <div className="space-y-6">
      <Panel>
        <p className="desk-mono text-2xl tracking-wide text-dl-text">F = D<sup>I</sup> × A</p>
        <p className="mt-3 max-w-[75ch] text-sm leading-relaxed text-dl-muted">
          {T("The Architect's own equation. It decides what an agent may do: a future exists only when real data is driven by a clear intent and an accountable person stands behind it. The code does not just compute it, it keeps its meaning: any one of D, I or A at zero makes F zero.",
            "สมการของ Architect เอง ใช้ตัดสินว่า agent ทำอะไรได้: อนาคตจะมีก็ต่อเมื่อข้อมูลจริงถูกขับด้วยเจตนาที่ชัด และมีผู้รับผิดชอบยืนอยู่เบื้องหลัง โค้ดไม่ได้แค่คำนวณ แต่รักษาความหมายไว้: D, I หรือ A ตัวใดเป็นศูนย์ F ก็เป็นศูนย์")}
        </p>
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        {symbols.map((x) => (
          <Panel key={x.sym} title={`${x.sym} · ${T(x.name[0], x.name[1])}`} aside={<Badge tone="muted">{T(x.zero[0], x.zero[1])}</Badge>}>
            <p className="text-sm leading-relaxed text-dl-text">{T(x.meaning[0], x.meaning[1])}</p>
            <p className="mt-2 text-[13px] leading-relaxed text-dl-muted"><span className="desk-mono text-dl-leaf">{T("In Delentia", "ใน Delentia")} </span>{T(x.here[0], x.here[1])}</p>
          </Panel>
        ))}
      </div>

      <Calculator T={T} />

      <Panel title={T("Four calls, worked through", "สี่การเรียก คิดให้ดู")}>
        <div className="grid gap-4 md:grid-cols-2">
          {SCENARIOS.map(({ s, title, story }) => (
            <div key={s.id} className="rounded border border-dl-rule bg-dl-ink/40 p-3">
              <p className="desk-mono text-[13px] text-dl-text">{T(title[0], title[1])}</p>
              <p className="desk-mono mt-1 text-[11px] text-dl-muted">{s.tool} · D {s.D} · I {s.I}</p>
              <p className="mt-2 text-[13px] leading-relaxed text-dl-muted">{T(story[0], story[1])}</p>
              <div className="mt-3"><Button tone="ghost" onClick={() => onTry(s)}>{T("Open in the tester", "เปิดในตัวทดสอบ")}</Button></div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={T("Three layers, in the order the Architect built them", "สามชั้น เรียงตามที่ Architect สร้าง")}>
          <ol className="space-y-3">
            {layers.map((l) => (
              <li key={l[0]}>
                <p className="desk-mono text-[13px] text-dl-text">{T(l[0], l[1])}</p>
                <p className="text-[13px] leading-relaxed text-dl-muted">{T(l[2], l[3])}</p>
              </li>
            ))}
          </ol>
        </Panel>
        <Panel title={T("What happens to one tool call", "เกิดอะไรกับการเรียกเครื่องมือหนึ่งครั้ง")}>
          <ol className="space-y-2.5">
            {flow.map((step, i) => (
              <li key={step[0]} className="flex gap-3 text-[13px] leading-relaxed text-dl-muted">
                <span className="desk-mono mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-dl-fern text-[11px] text-dl-leaf">{i + 1}</span>
                <span>{T(step[0], step[1])}</span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
            {T("Your policy can only tighten this. It cannot remove the signature repository writes always need, lower the 0.5 threshold, or allow a path the built-in checks refuse.",
              "นโยบายของคุณทำได้แค่ทำให้เข้มขึ้น ไม่สามารถยกเลิกลายเซ็นที่การเขียน repo ต้องมีเสมอ ลดเกณฑ์ 0.5 หรืออนุญาต path ที่การตรวจในตัวปฏิเสธ")}
          </p>
        </Panel>
      </div>

      <Panel title={T("Patterns, in one minute", "รูปแบบ pattern ใน 1 นาที")}>
        <ul className="space-y-1.5 text-[13px] leading-relaxed text-dl-muted">
          <li><Code>read_*</Code> {T("matches read_repo_file, read_exchange_file … A tool is matched by its full name (delentia_read_repo_file) and by the short name without delentia_.", "ตรงกับ read_repo_file, read_exchange_file … เครื่องมือถูกจับคู่ด้วยชื่อเต็ม (delentia_read_repo_file) และชื่อสั้นที่ไม่มี delentia_")}</li>
          <li><Code>*drop_*</Code> {T("matches anything with drop_ inside it, so an action named read_then_drop_table is not waved through by a read_* rule: the most restrictive match wins, whatever the order.", "ตรงกับชื่อที่มี drop_ อยู่ข้างใน ดังนั้น action ชื่อ read_then_drop_table จะไม่ถูกปล่อยผ่านด้วยกฎ read_*: กฎที่เข้มที่สุดชนะเสมอ ไม่ขึ้นกับลำดับ")}</li>
          <li><Code>.env</Code> · <Code>.git/*</Code> · <Code>*.pem</Code> {T("as forbidden paths: .env also covers config/.env and .env.local, but not environment.py.", "เป็น path ต้องห้าม: .env ครอบคลุม config/.env และ .env.local แต่ไม่ใช่ environment.py")}</li>
        </ul>
      </Panel>
    </div>
  );
}
