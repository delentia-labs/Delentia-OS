"use client";

import { useState } from "react";
import { Badge, Button, Code, Panel, Row } from "@/components/desk/ui";
import { desk, type FdiaEvaluation, type FdiaPolicy, type FdiaState } from "@/lib/desk-api";
import type { Scenario } from "./Learn";

type T = (en: string, th: string) => string;

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/50";

const PRESETS: { label: [string, string]; s: Scenario }[] = [
  { label: ["Read the README", "อ่าน README"], s: { id: "p1", tool: "delentia_read_repo_file", args: { relative_path: "README.md" }, D: 0.9, I: 1 } },
  { label: ["Write notes.md", "เขียน notes.md"], s: { id: "p2", tool: "delentia_write_repo_file", args: { relative_path: "notes.md", content_text: "hello" }, D: 1, I: 1 } },
  { label: ["Write .env (signed)", "เขียน .env (เซ็นแล้ว)"], s: { id: "p3", tool: "delentia_write_repo_file", args: { relative_path: ".env", content_text: "x" }, D: 1, I: 1, approved: true } },
  { label: ["Shell: echo", "shell: echo"], s: { id: "p4", tool: "delentia_run_sandboxed_command", args: { command: "echo hello" }, D: 1, I: 1 } },
  { label: ["Shell reading .env", "shell อ่าน .env"], s: { id: "p5", tool: "delentia_run_sandboxed_command", args: { command: "cat .env" }, D: 1, I: 1 } },
  { label: ["Crawl a URL", "crawl URL"], s: { id: "p6", tool: "delentia_crawl_url", args: { url: "https://example.org" }, D: 0.8, I: 1 } },
  { label: ["Thin data, strict intent", "ข้อมูลบาง เจตนาเข้ม"], s: { id: "p7", tool: "delentia_run_sandboxed_command", args: { command: "echo hello" }, D: 0.5, I: 1.5 } },
];

export function Try({ state, draft, dirty, initial, T }: {
  state: FdiaState; draft: FdiaPolicy; dirty: boolean; initial: Scenario | null; T: T;
}) {
  const [tool, setTool] = useState(initial?.tool ?? "delentia_write_repo_file");
  const [args, setArgs] = useState(JSON.stringify(initial?.args ?? { relative_path: "notes.md", content_text: "hello" }, null, 2));
  const [principal, setPrincipal] = useState("");
  const [D, setD] = useState(initial?.D ?? 0.9);
  const [I, setI] = useState(initial?.I ?? 1);
  const [approved, setApproved] = useState(initial?.approved ?? false);
  const [useDraft, setUseDraft] = useState(true);
  const [result, setResult] = useState<FdiaEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (s: Scenario) => { setTool(s.tool); setArgs(JSON.stringify(s.args, null, 2)); setD(s.D); setI(s.I); setApproved(!!s.approved); setResult(null); setError(null); };

  const run = async () => {
    setBusy(true); setError(null);
    try {
      let parsed: Record<string, unknown>;
      try { parsed = JSON.parse(args || "{}"); } catch { throw new Error(T("The arguments are not valid JSON.", "arguments ไม่ใช่ JSON ที่ถูกต้อง")); }
      setResult(await desk.fdiaEvaluate({ tool_name: tool.trim(), tool_args: parsed, principal, approved, D, I, ...(useDraft ? { policy: draft } : {}) }));
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setResult(null); }
    finally { setBusy(false); }
  };

  const tone = !result ? "muted" : result.outcome.startsWith("allowed") ? "leaf" : result.outcome.startsWith("waits") ? "amber" : result.outcome.startsWith("no policy") ? "fern" : "rust";
  const outcomeText = (o: string) => ({
    allowed: T("Allowed: it runs.", "อนุญาต: รันได้"),
    blocked: T("Blocked: A = 0 and nobody can sign for it.", "ถูกบล็อก: A = 0 และไม่มีใครเซ็นแทนได้"),
    "waits for signature": T("Waits: it pauses until the required people sign this exact action.", "รอ: หยุดจนกว่าผู้ที่กำหนดจะเซ็น action นี้"),
    "blocked (F below threshold)": T("Blocked: F is under the threshold, so the data is too thin for this intent.", "ถูกบล็อก: F ต่ำกว่าเกณฑ์ ข้อมูลบางเกินไปสำหรับเจตนานี้"),
  } as Record<string, string>)[o] ?? o;

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Panel title={T("A tool call to test", "การเรียกเครื่องมือที่จะทดสอบ")}>
        <div className="mb-3 flex flex-wrap gap-2">
          {PRESETS.map((p) => <Button key={p.s.id} tone="ghost" onClick={() => load(p.s)}>{T(p.label[0], p.label[1])}</Button>)}
        </div>
        <label className="block"><span className="text-[12px] text-dl-muted">{T("Tool", "เครื่องมือ")}</span>
          <input list="fdia-tools" value={tool} onChange={(e) => setTool(e.target.value)} className={field} aria-label="Tool name" />
          <datalist id="fdia-tools">{state.tools.map((t) => <option key={t.name} value={t.name}>{t.built_in}</option>)}</datalist>
        </label>
        <label className="mt-3 block"><span className="text-[12px] text-dl-muted">{T("Arguments (JSON)", "arguments (JSON)")}</span>
          <textarea value={args} onChange={(e) => setArgs(e.target.value)} rows={5} className={field} aria-label="Arguments" /></label>
        <div className="mt-3 grid grid-cols-2 gap-4">
          <label className="block"><span className="flex justify-between text-[12px] text-dl-muted"><span>D</span><span className="desk-mono text-dl-text">{D.toFixed(2)}</span></span>
            <input type="range" min={0} max={1} step={0.01} value={D} onChange={(e) => setD(Number(e.target.value))} className="desk-focus w-full accent-[var(--dl-leaf)]" aria-label="D" /></label>
          <label className="block"><span className="flex justify-between text-[12px] text-dl-muted"><span>I</span><span className="desk-mono text-dl-text">{I.toFixed(2)}</span></span>
            <input type="range" min={0.5} max={3} step={0.05} value={I} onChange={(e) => setI(Number(e.target.value))} className="desk-focus w-full accent-[var(--dl-leaf)]" aria-label="I" /></label>
        </div>
        <label className="mt-3 block"><span className="text-[12px] text-dl-muted">{T("Who is asking (identity the server sees; empty = nobody listed)", "ผู้ขอ (ตัวตนที่ server เห็น; ว่าง = ไม่อยู่ในรายการ)")}</span>
          <input value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="alice" className={field} aria-label="Identity" /></label>
        <label className="mt-3 flex items-start gap-2 text-[13px] text-dl-text">
          <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} className="mt-1 accent-[var(--dl-leaf)]" />
          <span>{T("Pretend the required signatures are already given", "สมมติว่าลายเซ็นที่ต้องมีให้ครบแล้ว")}
            <span className="block text-[12px] text-dl-muted">{T("Shows that a signature still cannot lift a forbidden path or pattern.", "ดูว่าลายเซ็นก็ยังปลดสิ่งต้องห้ามไม่ได้")}</span></span>
        </label>
        <label className="mt-2 flex items-start gap-2 text-[13px] text-dl-text">
          <input type="checkbox" checked={useDraft} onChange={(e) => setUseDraft(e.target.checked)} className="mt-1 accent-[var(--dl-leaf)]" />
          <span>{T("Use the draft on the Policy tab", "ใช้ฉบับร่างในแท็บ Policy")} {dirty ? <Badge tone="amber">{T("unsaved", "ยังไม่บันทึก")}</Badge> : null}
            <span className="block text-[12px] text-dl-muted">{T("Unticked, the saved file on disk is used.", "ถ้าไม่ติ๊ก จะใช้ไฟล์ที่บันทึกไว้")}</span></span>
        </label>
        <div className="mt-4"><Button onClick={run} disabled={busy || !tool.trim()}>{busy ? "…" : T("Evaluate", "ประเมิน")}</Button></div>
      </Panel>

      <Panel title={T("What the gate would do", "ด่านจะทำอะไร")} aside={result ? <Badge tone={tone}>{result.outcome}</Badge> : undefined}>
        {error ? <p role="alert" className="text-[13px] text-dl-rust">{error}</p> : null}
        {!result && !error ? <p className="text-[13px] text-dl-muted">{T("Pick a preset or fill the form, then Evaluate. Nothing runs: this only asks the policy.", "เลือกตัวอย่างหรือกรอกฟอร์ม แล้วกด ประเมิน ไม่มีอะไรถูกรัน แค่ถามนโยบาย")}</p> : null}
        {result ? (
          <div role="status">
            <p className={`text-sm leading-relaxed ${tone === "leaf" ? "text-dl-leaf" : tone === "amber" ? "text-dl-amber" : tone === "rust" ? "text-dl-rust" : "text-dl-text"}`}>{outcomeText(result.outcome)}</p>
            <p className="desk-mono my-3 text-[15px] text-dl-text">F = {(result.D ?? D).toFixed(2)}<sup>{(result.I ?? I).toFixed(2)}</sup> × {result.needs_signature ? "A(signed)=1" : result.A} = {result.F.toFixed(4)} <span className="text-dl-muted">{T("vs threshold", "เทียบเกณฑ์")} {result.threshold}</span></p>
            <Row label="A">{result.A}</Row>
            <Row label={T("Rule", "กฎ")}>{result.rule_id ?? "-"}</Row>
            <Row label={T("Rule type", "ชนิดกฎ")}>{result.action_type ?? "-"}</Row>
            <Row label={T("Caller role", "role ของผู้ขอ")}>{result.role ?? "-"}</Row>
            {result.needs_signature ? <Row label={T("Signatures", "ลายเซ็น")}>{result.required_signatures}{result.approver_roles?.length ? ` · ${result.approver_roles.join(" / ")}` : ""}</Row> : null}
            {result.jury_tier ? <Row label={T("Jury first", "คณะลูกขุนก่อน")}>{result.jury_tier}</Row> : null}
            {result.matched_rules && result.matched_rules.length > 1 ? <Row label={T("Also matched", "ที่ตรงอีก")}>{result.matched_rules.join(", ")}</Row> : null}
            <p className="mt-3 text-[13px] leading-relaxed text-dl-muted">{result.reason}</p>
            <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
              {T("This is the policy's view. The built-in gate still applies on top: repository writes always wait for a signature, an unsafe path is refused, and the 0.5 threshold is a floor. ", "นี่คือมุมมองของนโยบาย ด่านในตัวยังทำงานซ้อนอยู่: การเขียน repo รอลายเซ็นเสมอ path ที่ไม่ปลอดภัยถูกปฏิเสธ และเกณฑ์ 0.5 เป็นขั้นต่ำ ")}
              {T("Same answer from the command line: ", "ผลเดียวกันจากบรรทัดคำสั่ง: ")}<Code>delentia fdia test {tool}</Code>
            </p>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
