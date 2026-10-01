"use client";

import { useRef, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, ErrorNote, PageBody, PageHeader, Panel, Row } from "@/components/desk/ui";
import { desk, type JitnaReport } from "@/lib/desk-api";

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-2 text-[12px] text-dl-text placeholder:text-dl-muted/50";
const LANGUAGE_NAMES: Record<string, string> = { I: "Intent", D: "Data", "Δ": "Delta", A: "Approach", R: "Reflection", M: "Memory" };

export default function JitnaPage() {
  const { lang } = useLang();
  const T = (en: string, th: string) => (lang === "th" ? th : en);
  const [text, setText] = useState("");
  const [trusted, setTrusted] = useState("");
  const [report, setReport] = useState<JitnaReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const load = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) { setError(T("A .jitna file is at most 4 MiB.", "ไฟล์ .jitna ใหญ่ได้ไม่เกิน 4 MiB")); return; }
    setText(await file.text());
    setReport(null);
    setError(null);
  };

  const verify = async () => {
    setBusy(true); setError(null); setReport(null);
    try {
      const file = JSON.parse(text);
      const keys = trusted.split(/[\s,]+/).filter(Boolean);
      setReport(await desk.verifyJitna(file, keys));
    } catch (err) {
      setError(err instanceof SyntaxError ? T("This is not JSON, so it is not a .jitna file.", "นี่ไม่ใช่ JSON จึงไม่ใช่ไฟล์ .jitna") : err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };

  const verdict = report ? (report.valid && report.trusted ? "trusted" : report.valid ? "untrusted" : "invalid") : null;
  return (
    <>
      <PageHeader title="JITNA"
        lead={lang === "th"
          ? "ตรวจไฟล์ .jitna: แพ็กเก็ต JITNA ที่ลงลายเซ็น Ed25519 พร้อม seal ครอบทั้งไฟล์ ไฟล์ที่ผ่านแปลว่า 'ไม่ถูกแก้หลังเซ็น' ส่วน 'เชื่อถือได้' ต้องเป็นกุญแจที่คุณระบุไว้เองเท่านั้น (ใครก็สร้างกุญแจแล้วเซ็นได้) ไฟล์ .jitna เซ็นแต่ไม่ได้เข้ารหัส"
          : "Check a .jitna file: JITNA packets signed with Ed25519 plus a seal over the whole file. 'Valid' means nothing changed after signing; 'trusted' only counts keys you name yourself (anyone can generate a key and sign). A .jitna file is signed, not encrypted."} />
      <PageBody>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title={T("The file", "ไฟล์")}>
            <div className="flex flex-wrap items-center gap-2">
              <input ref={picker} type="file" accept=".jitna,application/json" className="sr-only" aria-label="Choose a .jitna file"
                onChange={(e) => load(e.target.files?.[0])} />
              <Button tone="ghost" onClick={() => picker.current?.click()}>{T("Choose a .jitna file", "เลือกไฟล์ .jitna")}</Button>
              <span className="text-[12px] text-dl-muted">{T("or paste its contents", "หรือวางเนื้อหา")}</span>
            </div>
            <label className="mt-3 block">
              <span className="sr-only">File contents</span>
              <textarea value={text} onChange={(e) => { setText(e.target.value); setReport(null); }} rows={12} spellCheck={false} aria-label="File contents"
                placeholder='{"format": "jitna-file", "version": 1, …}' className={field} />
            </label>
            <label className="mt-3 block">
              <span className="text-[13px] text-dl-muted">{T("Public keys you trust (hex or fingerprint, one per line)", "กุญแจสาธารณะที่คุณเชื่อถือ (hex หรือ fingerprint บรรทัดละหนึ่งอัน)")}</span>
              <textarea value={trusted} onChange={(e) => { setTrusted(e.target.value); setReport(null); }} rows={3} spellCheck={false} aria-label="Trusted public keys" className={field} />
            </label>
            <div className="mt-4 flex items-center gap-3">
              <Button onClick={verify} disabled={busy || !text.trim()}>{busy ? "Checking…" : T("Verify", "ตรวจ")}</Button>
              <span className="text-[12px] text-dl-muted">{T("Nothing is stored or executed.", "ไม่มีอะไรถูกบันทึกหรือรัน")}</span>
            </div>
            {error ? <div className="mt-3"><ErrorNote error={error} /></div> : null}
          </Panel>

          <div className="space-y-6">
            {report ? (
              <Panel title={T("Result", "ผล")} aside={verdict === "trusted" ? <Badge tone="leaf">valid · trusted</Badge> : verdict === "untrusted" ? <Badge tone="amber">valid · not trusted</Badge> : <Badge tone="rust">invalid</Badge>}>
                <p role="status" className="text-[13px] leading-relaxed text-dl-text">
                  {verdict === "trusted" ? T("Nothing changed after signing, and every signer is a key you trust.", "ไม่มีการแก้ไขหลังเซ็น และผู้เซ็นทุกคนเป็นกุญแจที่คุณเชื่อถือ")
                    : verdict === "untrusted" ? T(`Nothing changed after signing, but you have not said you trust ${report.untrusted_keys.map((k) => k.slice(0, 16)).join(", ")}. Anyone could have made this file.`,
                      `ไม่มีการแก้ไขหลังเซ็น แต่คุณยังไม่ได้ระบุว่าเชื่อถือ ${report.untrusted_keys.map((k) => k.slice(0, 16)).join(", ")} ใครก็ทำไฟล์นี้ได้`)
                    : T("Do not use this file.", "อย่าใช้ไฟล์นี้")}
                </p>
                <Row label="Sealed by">{report.sender_fingerprint.slice(0, 24)}…</Row>
                <Row label="Created">{report.created ?? "-"}</Row>
                {report.problems.length ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-dl-rust">{report.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
                ) : null}
              </Panel>
            ) : (
              <Panel title={T("How to make one", "สร้างอย่างไร")}>
                <p className="text-[13px] leading-relaxed text-dl-muted">
                  {T("Signing needs a private key, which this page never touches. On the machine that holds the key:", "การเซ็นต้องใช้กุญแจส่วนตัว ซึ่งหน้านี้ไม่แตะต้อง บนเครื่องที่เก็บกุญแจ:")}
                </p>
                <pre className="desk-mono mt-2 overflow-x-auto rounded border border-dl-rule bg-dl-ink p-2 text-[12px] text-dl-muted">{`delentia jitna keygen --out ~/.delentia/keys/jitna.pem
delentia jitna pack --language intent.txt \\
  --source planner --target worker \\
  --key ~/.delentia/keys/jitna.pem -o task.jitna`}</pre>
                <p className="mt-2 text-[12px] text-dl-muted">{T("The language file:", "ไฟล์ภาษา:")} <Code>I: …</Code> <Code>D: …</Code> <Code>Δ: …</Code> <Code>A: …</Code> <Code>R: …</Code> <Code>M: …</Code> ({T("I is required", "ต้องมี I")})</p>
              </Panel>
            )}

            {report?.packets.map((p) => (
              <Panel key={p.packet_id} title={`${p.source} → ${p.target}`} aside={p.signature_valid ? <Badge tone="leaf">signature ok</Badge> : <Badge tone="rust">signature BAD</Badge>}>
                <Row label="Packet">{p.packet_id.slice(0, 8)} · {p.message_type}</Row>
                <Row label="Signer">{p.signer ? `${p.signer.slice(0, 16)}…` : "-"}</Row>
                {p.language ? (
                  <div className="mt-2 space-y-1">
                    {Object.entries(p.language).map(([k, v]) => (
                      <p key={k} className="text-[13px] leading-relaxed"><span className="desk-mono text-dl-leaf">{k}</span> <span className="text-dl-muted">{LANGUAGE_NAMES[k] ?? ""}</span> <span className="text-dl-text">{v}</span></p>
                    ))}
                    {verdict !== "trusted" ? <p className="text-[12px] text-dl-amber">{T("Shown for reading only: act on it only after it is valid and trusted.", "แสดงเพื่ออ่านเท่านั้น: ทำตามเมื่อไฟล์ถูกต้องและเชื่อถือได้เท่านั้น")}</p> : null}
                  </div>
                ) : <p className="mt-2 text-[12px] text-dl-muted">{T("This packet carries no JITNA language.", "แพ็กเก็ตนี้ไม่มีภาษา JITNA")}</p>}
                {p.problems.length ? <ul className="mt-2 list-disc pl-5 text-[13px] text-dl-rust">{p.problems.map((x, i) => <li key={i}>{x}</li>)}</ul> : null}
              </Panel>
            ))}
          </div>
        </div>
      </PageBody>
    </>
  );
}
